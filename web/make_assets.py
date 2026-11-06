"""Build the landing-page structures and the example illustrations from real AtomForge runs (run once; outputs committed).

  python web/make_assets.py          # needs the run folders below (runs/ is not in git) and Playwright + Chrome

For each example request, the validated data file that the agent built for it becomes a 3D scene
(web/structures/<name>.json: PDB text, bonds, cell edges and where it came from) and a still image
(web/assets/examples/<name>.png, rendered by 3Dmol in headless Chrome). Nothing is drawn by hand: every
picture is the actual structure a request produced.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import viewer  # noqa: E402

SOURCES = {     # name: run folder in runs/requests (each accepted, every Tier 0-3 check passed)
    "mpeg_pce": "web_20261106-045151",
    "c3s_supercell": "web_20261106-035548",
    "pce_on_c3s": "web_20261106-040057",
    "three_hpeg": "web_20261106-040336",
    "apeg_maleic": "web_20261106-042239",
}
ZOOM = {"mpeg_pce": 1.2, "three_hpeg": 1.3}     # extra zoom for loose polymers (checked for clipping by eye)
IMAGE_BG = "#0d1320"        # the example cards' image background (app.py PALETTES navy surface2)
CLOSE_UPS = {"intro_pce": ("mpeg_pce", "#0a0e16", 1.35)}     # landing-page close-up (no box): source, page background, zoom


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(os.path.join(HERE, "structures"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "assets", "examples"), exist_ok=True)
    pages = {}
    for name, run in SOURCES.items():
        d = os.path.join(ROOT, "runs", "requests", run)
        ev = [json.loads(line) for line in open(os.path.join(d, "trace.jsonl"))]
        stop = ev[-1]
        assert stop["event"] == "stop" and str(stop["stop"]).startswith("accepted"), run
        S = viewer.scene(os.path.join(d, stop["data_file"]))
        S["source"] = {"run": run, "request": ev[0]["input"], "model": next(e["model"] for e in ev if e.get("model"))}
        json.dump(S, open(os.path.join(HERE, "structures", f"{name}.json"), "w"))
        pages[name] = "<html><body style='margin:0'>" + viewer.showcase(S, 500, bg=IMAGE_BG, spin_speed=0, ao=True,
                                                                        zoom=ZOOM.get(name, 0.95)) + "</body></html>"
    for name, (src, bg, zoom) in CLOSE_UPS.items():
        S = json.load(open(os.path.join(HERE, "structures", f"{src}.json")))
        pages[name] = ("<html><body style='margin:0'>" + viewer.showcase(S, 500, bg=bg, spin_speed=0, ao=True, zoom=zoom,
                                                                        show_box=False) + "</body></html>")
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True,
                              args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"])
        for name, page in pages.items():
            tmp = os.path.join(HERE, "structures", f".{name}.html")
            open(tmp, "w").write(page)
            pg = b.new_page(viewport={"width": 800, "height": 500}, device_scale_factor=1)
            pg.goto("file://" + tmp)
            pg.wait_for_function("window.ready === true", timeout=60000)
            pg.wait_for_timeout(1500)
            pg.screenshot(path=os.path.join(HERE, "assets", "examples", f"{name}.png"))
            pg.close()
            os.remove(tmp)
        b.close()
    for name in SOURCES:
        print(name, os.path.getsize(os.path.join(HERE, "structures", f"{name}.json")) // 1024, "kB")


if __name__ == "__main__":
    main()
