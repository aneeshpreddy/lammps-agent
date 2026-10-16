"""Interchangeable LAMMPS execution backends (plan Day 13).

One interface: run(input_text, files, timeout_s) -> RunResult. `files` maps the names used inside
the input script to local paths; every backend copies them next to the input before running, so
the same input text works locally, in Docker, or on a cluster. Only tiny runs (read_data, run 0)
are ever sent through a backend — never production jobs.
"""
from __future__ import annotations

import os
import shlex
import shutil
import signal as _signal
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class RunResult:
    returncode: Optional[int]
    stdout: str
    stderr: str
    log: str
    timed_out: bool = False
    signal: Optional[int] = None
    elapsed_s: float = 0.0
    backend: str = "local"
    command: str = ""
    launch_error: Optional[str] = None
    extra: Dict[str, str] = field(default_factory=dict)


def _decode(b) -> str:
    if b is None:
        return ""
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else b


def _signal_of(rc: Optional[int]) -> Optional[int]:
    if rc is None:
        return None
    if rc < 0:
        return -rc
    if rc >= 128 + 1 and rc - 128 in {s.value for s in _signal.Signals}:
        return rc - 128      # shells report a signal death as 128+N
    return None


class Backend:
    name = "base"

    def run(self, input_text: str, files: Dict[str, str], timeout_s: float) -> RunResult:
        raise NotImplementedError


class LocalBackend(Backend):
    name = "local"

    def __init__(self, executable: str, workdir_root: Optional[str] = None):
        self.executable = executable
        self.workdir_root = workdir_root

    def run(self, input_text, files, timeout_s):
        exe = shutil.which(self.executable) or (self.executable if os.path.exists(self.executable) else None)
        if exe is None:
            return RunResult(None, "", "", "", launch_error=f"LAMMPS executable '{self.executable}' not found",
                             backend=self.name)
        with tempfile.TemporaryDirectory(prefix="lmpval_", dir=self.workdir_root) as wd:
            for name, src in files.items():
                shutil.copyfile(src, os.path.join(wd, name))
            with open(os.path.join(wd, "in.lammps"), "w") as fh:
                fh.write(input_text)
            cmd = [exe, "-in", "in.lammps", "-log", "log.lammps", "-nocite"]
            t0 = time.time()
            timed_out = False
            try:
                p = subprocess.run(cmd, cwd=wd, capture_output=True, timeout=timeout_s)
                rc, out, err = p.returncode, _decode(p.stdout), _decode(p.stderr)
            except subprocess.TimeoutExpired as e:
                rc, out, err, timed_out = None, _decode(e.stdout), _decode(e.stderr), True
            elapsed = time.time() - t0
            log = ""
            lp = os.path.join(wd, "log.lammps")
            if os.path.exists(lp):
                with open(lp, errors="replace") as fh:
                    log = fh.read()
        return RunResult(rc, out, err, log, timed_out, _signal_of(rc), elapsed, self.name, " ".join(cmd))


class SSHBackend(Backend):
    """Copy files to a scratch directory on a cluster login/compute node, run there, copy the log back.

    Uses the system `ssh`/`scp` with key-based authentication (never passwords in code).
    UNTESTED in this repository: no cluster account was available when it was written (plan Day 13
    says to build it only if the local build lacks the needed styles; the local Homebrew build has
    CLASS2, KSPACE and MOLECULE, so it is not needed yet).
    """
    name = "ssh"

    def __init__(self, host: str, remote_scratch: str, executable: str = "lmp"):
        if not host or not remote_scratch:
            raise ValueError("ssh backend needs lammps.ssh.host and lammps.ssh.remote_scratch in config.yaml")
        self.host, self.remote_scratch, self.executable = host, remote_scratch, executable

    def _ssh(self, cmd: str, timeout: float):
        return subprocess.run(["ssh", "-o", "BatchMode=yes", self.host, cmd], capture_output=True, timeout=timeout)

    def run(self, input_text, files, timeout_s):
        rdir = f"{self.remote_scratch.rstrip('/')}/lmpval_{uuid.uuid4().hex[:12]}"
        t0 = time.time()
        with tempfile.TemporaryDirectory(prefix="lmpval_ssh_") as wd:
            for name, src in files.items():
                shutil.copyfile(src, os.path.join(wd, name))
            with open(os.path.join(wd, "in.lammps"), "w") as fh:
                fh.write(input_text)
            try:
                self._ssh(f"mkdir -p {shlex.quote(rdir)}", 60)
                subprocess.run(["scp", "-q", "-o", "BatchMode=yes"] + [os.path.join(wd, f) for f in os.listdir(wd)]
                               + [f"{self.host}:{rdir}/"], check=True, capture_output=True, timeout=300)
                remote = (f"cd {shlex.quote(rdir)} && timeout {int(timeout_s)} {shlex.quote(self.executable)} "
                          f"-in in.lammps -log log.lammps -nocite")
                p = self._ssh(remote, timeout_s + 60)
                rc, out, err = p.returncode, _decode(p.stdout), _decode(p.stderr)
                timed_out = rc == 124
                subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"{self.host}:{rdir}/log.lammps", wd],
                               capture_output=True, timeout=120)
                log = open(os.path.join(wd, "log.lammps"), errors="replace").read() \
                    if os.path.exists(os.path.join(wd, "log.lammps")) else ""
            except (subprocess.SubprocessError, OSError) as e:
                return RunResult(None, "", "", "", launch_error=f"ssh backend failure: {e}", backend=self.name)
            finally:
                try:
                    self._ssh(f"rm -rf {shlex.quote(rdir)}", 60)
                except subprocess.SubprocessError:
                    pass
        return RunResult(None if timed_out else rc, out, err, log, timed_out, _signal_of(rc),
                         time.time() - t0, self.name, remote)


class DockerBackend(Backend):
    """Optional (plan Day 13: skip unless Docker is already in use). UNTESTED: Docker is not installed here."""
    name = "docker"

    def __init__(self, image: str, executable: str = "lmp"):
        if not image:
            raise ValueError("docker backend needs lammps.docker.image in config.yaml")
        self.image, self.executable = image, executable

    def run(self, input_text, files, timeout_s):
        with tempfile.TemporaryDirectory(prefix="lmpval_docker_") as wd:
            for name, src in files.items():
                shutil.copyfile(src, os.path.join(wd, name))
            with open(os.path.join(wd, "in.lammps"), "w") as fh:
                fh.write(input_text)
            cmd = ["docker", "run", "--rm", "--network", "none", "-v", f"{wd}:/work", "-w", "/work", self.image,
                   self.executable, "-in", "in.lammps", "-log", "log.lammps", "-nocite"]
            t0 = time.time()
            try:
                p = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
                rc, out, err, to = p.returncode, _decode(p.stdout), _decode(p.stderr), False
            except subprocess.TimeoutExpired as e:
                rc, out, err, to = None, _decode(e.stdout), _decode(e.stderr), True
            except OSError as e:
                return RunResult(None, "", "", "", launch_error=f"docker not available: {e}", backend=self.name)
            lp = os.path.join(wd, "log.lammps")
            log = open(lp, errors="replace").read() if os.path.exists(lp) else ""
        return RunResult(rc, out, err, log, to, _signal_of(rc), time.time() - t0, self.name, " ".join(cmd))


def make_backend(cfg) -> Backend:
    lc = cfg.get("lammps", {})
    kind = lc.get("backend", "local")
    if kind == "local":
        return LocalBackend(lc.get("executable", "lmp_serial"), lc.get("workdir_root"))
    if kind == "ssh":
        s = lc.get("ssh", {})
        return SSHBackend(s.get("host"), s.get("remote_scratch"), s.get("executable", "lmp"))
    if kind == "docker":
        d = lc.get("docker", {})
        return DockerBackend(d.get("image"), d.get("executable", "lmp"))
    raise ValueError(f"unknown lammps.backend {kind!r}")
