# Agentic generation of LAMMPS data files for cementitious systems, with a deterministic validator in the loop

*Draft, 2026-10-28; main claim reframed on 2026-11-05 after the development runs (owner decision; the plan's original claim was the value of validator feedback, see Section 5.3). This draft contains the sections that do not depend on model runs. Places that need results are marked **[RESULTS]**; they are filled from `docs/BASELINE_RESULTS.md`, `docs/RESULTS_DEV.md` and the test run (plan Days 41–43). Every number below comes from a generated document in this repository, which is named next to it. The prior-work statements were re-checked against the papers on 2026-10-28.*

---

## Abstract

**[RESULTS]**: written last. The intended shape is as follows. Large language models can drive molecular-dynamics tools, but the LAMMPS data file a simulation starts from can be wrong without LAMMPS noticing. We build a deterministic validator for LAMMPS data files: 44 properties in four tiers, calibrated tolerances, and LAMMPS used only as the last tier, never as proof. We show that the validator catches every one of 948 corrupted files, including 515 of the 521 that LAMMPS accepts silently or with only a warning. We then build an LLM agent that turns a plain-English request into a LAMMPS data file for PCE superplasticisers, INTERFACE FF cement minerals and PCE-on-mineral composites in CVFF- and PCFF-INTERFACE. The model chooses what to build, deterministic builders write the file, and the validator checks every file before it is accepted. On held-out tasks, the generated files are accepted by LAMMPS without error in **[X] %** of cases and match the requested system in **[Y] %**, at about **[cost]** per file. An ablation against a single-call baseline and retries without feedback shows where this reliability comes from: the builders prevent invalid files, and the validator certifies them rather than repairs them.

---

## 1. Problem

A LAMMPS simulation starts from two inputs: the **input script** (what to run) and the **data file** (what is simulated). The data file holds the atoms, their types and charges, the bonded topology (bonds, angles, dihedrals, impropers), the box and, in this project, the force-field coefficients. For cementitious systems these files are produced by a chain of converters and builders (Materials Studio and msi2lmp, EMC, ASE, in-house scripts), and every link can corrupt them.

**The difficulty is that many corruptions are silent.** LAMMPS reads the file, the simulation runs, and the result is plausible but wrong. A source-and-experiment audit of LAMMPS 22 Jul 2025 – Update 6 (`docs/FAILURE_MODES.md`, 2026-10-02) found the following.

**Corruptions LAMMPS accepts without any message:**
- permuted atom types (LAMMPS has no element concept in `read_data`);
- dropped bonds when the header count is adjusted to match;
- duplicated bonds;
- lines over 254 characters, which are cut;
- a missing box line, which silently defaults to −0.5…0.5.

**LAMMPS defects found on this build:**
- `run 0` can exit normally with an infinite potential energy;
- `replicate … bond/periodic` joins the wrong periodic images in tilted cells;
- the PPPM solver segfaults on many valid boxes.

**Common converters also corrupt files.** An ASE read→write round trip collapses force-field types to elements and drops every angle, dihedral and improper (`docs/R13_ASE_ROUNDTRIP.md`). msi2lmp leaves a triclinic tilt unreduced.

The corrupted-file experiment in Section 3.4 puts a number on this. On 948 corrupted files:
- LAMMPS by itself is **silent on 402** and **only warns on 119**;
- it errors or crashes on the remaining 427 (`docs/VALIDATOR_RESULTS.md`).

**"It runs" is therefore a weak test of a data file.** This matters for LLM agents in particular. An agent that checks its work by running LAMMPS will accept most of these files, and an agent that writes coordinates or topology itself can introduce exactly these defects.

**Question.** Can an LLM-based system turn a plain-English request into a LAMMPS data file for a realistic class of cementitious systems that (1) LAMMPS accepts without error and (2) is the system that was asked for, and can this be verified independently of LAMMPS?

**Main claim.** Given a plain-English request, the system generates LAMMPS data files that LAMMPS accepts without errors in **[X] %** of cases and that match the requested system in **[Y] %** of cases, on held-out test tasks. Every file is checked by a deterministic validator that caught all 948 deliberately corrupted files. "Accurate" therefore has two measured parts:
- **validity:** every Tier 0–3 check passes, including LAMMPS with the full force field;
- **correctness:** TC.2 matches a trusted reference of the requested system.

**What is not claimed:**
- that validator feedback improves the agent (Section 6.4 reports what the ablation shows);
- coverage beyond the system class of Section 2;
- scientific correctness of a simulation set up from the file.

## 2. Scope and design decisions

The scope was fixed in `docs/SPEC.md` (§7.3, §7.16, §7.17) and agreed with the supervisor on 2026-10-20 and 2026-10-26.

**Artifact.** The output is one LAMMPS data file per task, not an input script. Input scripts are already studied (R18, Section 7), and the silent corruption lives in the data file.

**System class.** Three domains:
- PCE (polycarboxylate ether/ester) superplasticisers of any architecture: the ester anchor (MPEG type), the vinyl-ether anchors (APEG, HPEG, TPEG, VPEG) and maleic backbones; any backbone length, side-chain length, sequence and number of chains. The PCE sits in a box slightly larger than its atoms.
- All cement-mineral models of the INTERFACE FF 1.5 database, with supercells.
- A PCE on a cement-mineral surface (composite).

**Force fields.** CVFF-INTERFACE (class I) and PCFF-INTERFACE (class II), INTERFACE FF 1.5. CVFF-INTERFACE covers only the C3S and C3A mineral models. Every other mineral is class II only.

**Model output.** The model never writes coordinates or topology (decision E).
- **Its only output is a builder spec**, a JSON object such as "builder pce; monomers …; composition …; sequence …; counter-ion …" or "builder minerals; model …; supercell …".
- **Deterministic builders turn the spec into the file:** INTERFACE FF typing and charges via msi2lmp, bonded topology, tilt reduction, PCE conformation and placement on the surface.

The decision follows from Section 1: what a model is worst at (consistent bookkeeping of thousands of atoms and their topology) is what a builder does reliably.

**Validator.** It is deterministic and never a tool of the agent. The orchestrator always runs it after every attempt. The agent cannot skip it, cannot choose when to call it, and cannot see its configuration as something to negotiate.

**Non-goals** (SPEC §7.5):
- no input-script generation;
- no MD workflow beyond the starting data file;
- no force-field invention;
- no reactive force fields;
- no cluster submission;
- no modification of trusted references;
- no silent fallback to another force field or units;
- **no claim that passing the validator implies scientific correctness.**

## 3. The validator

### 3.1 Correctness model

**Tiers.** A file is checked in four tiers of increasing cost. Each tier runs only if the previous one allows it (`docs/PROPERTIES.md`, v0.8).

| Tier | Question | Properties | Examples |
|---|---|---|---|
| 0 | Can the file be parsed exactly as LAMMPS would? | 12 | header keywords, section names, numeric syntax, Atoms columns per atom_style, the 254-character line limit, box lines |
| 1 | Is it internally consistent? | 17 | counts vs rows, unique IDs, every topology reference resolves, Masses and Coeff rows complete, image flags, topology-type signatures, bonded-term completeness, units hint |
| 2 | Is it physically plausible for this system? | 10 | net charge, cell consistency, overlaps, bond lengths, density, mass ↔ element, image consistency, tilt bound, bond coefficients vs geometry, box margin |
| 3 | Does LAMMPS accept it under the declared configuration? | 5 | `read_data … nocoeff`; the full force field + `run 0`; a warning allow-list; crash and timeout classification |
| TC | Is it the requested system? | 2 | comparison with a reference: by molecular graph, or by chemistry (position- and sequence-free) |

**Verdicts.** Each property returns PASS, FAIL, NOT_APPLICABLE, NOT_EVALUATED or NOT_CALIBRATED. A file **passes** only if every Tier 0–3 property is PASS or NOT_APPLICABLE.

**Three rules keep the validator honest:**
1. **No tolerance without a derivation.** Every Tier 2 tolerance comes from measured reference structures, or from a stated requirement (§8.5 of PROPERTIES). A property with no calibrated tolerance returns NOT_CALIBRATED, which never counts as a pass.
2. **"LAMMPS would catch it" never satisfies a property** (§8.8). LAMMPS is the last tier, not the safety net. The absence of an ERROR line is never a PASS.
3. **No LLM, ASE or pymatgen in a verdict.** The validator has its own parser, derived from the LAMMPS `read_data` source. Converters are only things under test.

**The declared configuration.** Every check runs against a declared configuration (`configs/*.yaml`): units, atom_style, boundary, styles, policies for image flags, tilt and charge, the warning allow-list, and the calibration file. The same file can be valid under one configuration and invalid under another. Being explicit about the configuration is what makes a verdict reproducible.

### 3.2 Failure modes

The validator is designed against a taxonomy of **35 data-file failure modes** (`docs/FAILURE_MODES.md`; 33 in scope). Each failure mode records:
- how it arises in practice;
- what LAMMPS does with it (Silent, Warn, Loud, Loud at run, Crash), established from the LAMMPS source and probe experiments on this build;
- the property that must catch it.

**Examples:**
- atom-type permutation;
- element mis-identification from masses;
- unit mismatch;
- dropped or duplicated bonds;
- charge loss;
- atom-style mismatch;
- image-flag and tilt corruption;
- ID renumbering;
- missing or duplicate atoms;
- missing box keywords;
- line truncation;
- overlaps;
- implausible bond lengths and densities.

### 3.3 Calibration

**Tier 2 tolerances are measured on references:**
- the research group's EMC PCE files;
- published INTERFACE FF mineral structures;
- the builders' validated output.

Each tolerance is recorded with its source in `calibration/*.json`.

**Examples:**
- **Overlap floor:** 75 % of the closest contact seen in the references for that element pair. Ion–oxygen floors come from published structures in which the ions are coordinated.
- **Bond lengths:** ±10 % beyond the reference range.
- **Bond coefficients vs geometry:** the observed ratio of bond length to r0 per type pair, ± 0.03. Measured deviations reach 12 % in C3A, so a fixed tolerance would be wrong.
- **Box margin for PCE:** 1–5 Å. This is a requirement from the supervisor ("slightly bigger than the atoms"), not a measurement.

**Statuses.** The supervisor accepted the Tier 2 margins on 2026-10-26. Values that are requirements rather than measurements are labelled as such.

### 3.4 How the validator was validated

The validator is itself tested with **positive controls** (files that must pass) and **negative controls** (files that must fail). The negative controls are produced by **49 corruption operators** (`scripts/mutate.py`) covering 34 failure modes, each applied to correct parent files. The matrix below is from 2026-10-26 (`docs/VALIDATOR_RESULTS.md`, `scripts/run_matrix.py`).

| Measure | Result |
|---|---|
| Positive controls passing all tiers | **36 / 36** (no false alarms) |
| Corrupted files | 948 (49 operator variants, 34 failure modes, 22 parents) |
| Caught by the validator's own checks (Tiers 0–2) | **942 / 948** |
| Caught only by the reference comparison (TC.2) | 6 |
| Caught only by LAMMPS diagnostics (Tier 3) | 0 |
| **Missed** (would be certified) | **0** |
| LAMMPS alone: silent / warning only | 402 / 119 |
| Of those 521, caught by Tiers 0–2 | **515** |

**What the table shows:**
- **Nothing was missed.** Every one of the 948 corrupted files failed at least one check.
- **The validator stands on its own checks.** It never needed LAMMPS to reject a file.
- **It covers what LAMMPS misses.** It caught 515 of the 521 files that LAMMPS accepts quietly. The other 6 (equal-length swaps and similar) are invisible to any check that sees only one file, and only the reference comparison catches them.

**Real converter output** was rejected for the right reasons: the ASE round trip, and msi2lmp's unreduced tilt.

**Limits of this evidence:**
- **The corruptions are ours.** They follow the failure-mode taxonomy, which was itself built from the LAMMPS source and the literature, so the test is only as complete as the taxonomy.
- **One LAMMPS build.** Every Tier 3 statement is specific to LAMMPS 22 Jul 2025 – Update 6 (Homebrew, serial).
- **Passing is necessary, not sufficient.** A file that passes is consistent and plausible, not proven to be the scientifically right model (non-goal 10).

## 4. Task set and metrics

### 4.1 Tasks

The evaluation set v3 (`docs/EVAL_SET.md`) has **22 tasks**:
- **by domain:** 7 mineral, 9 PCE, 6 composite;
- **by difficulty:** 6 easy, 9 representative, 7 hard;
- **by force field:** 14 in PCFF-INTERFACE, 8 in CVFF-INTERFACE.

The systems range from 40 to 8 492 atoms.

**What a task contains:**
- **Input.** A natural-language request, written the way a researcher would ask, is all the system under test receives.
- **Hidden spec** and the declared validation configuration, never shown to the system.
- **Reference.** A reference data file and a comparison mode.

The hard tasks include known traps:
- a supercell along a tilted axis, where LAMMPS `replicate` builds wrong bonds;
- replication that pushes a tilt beyond half the box;
- COOH typing in class II;
- gradient sequences;
- multi-chain systems;
- surfaces whose normal is not *z*.

**References.**
- **Source.** They are built from the hidden spec by the same deterministic builders the systems use. Each one passes the validator, matches itself under TC.2, and is rebuilt byte-identically.
- **Checked against independent sources.** The builders were compared with the group's EMC files and with published INTERFACE structures (`docs/PCE_BUILDER.md`, `docs/MINERALS.md`, `docs/COMPOSITE.md`). For example, p01 has the same chemistry as the group's EMC file REF-04.
- **What TC.2 therefore measures.** Whether the system asked the builders for the requested system. The builders' own correctness is a separate claim, with its own evidence.

**Split** (frozen 2026-10-26, sha256 in `docs/METRICS.md`): **13 development tasks and 9 held-out test tasks**. The split was drawn per domain and difficulty. The harness refuses to open the test split before the evaluation date, so the test tasks have not been seen while building the systems.

### 4.2 Metrics

The metrics were frozen in METRICS v1.1 (2026-10-26), before any scored run. They were revised once, to v1.2 (2026-11-05, before any test-split run; see below). A run of a task **succeeds** iff both of the following hold:
1. **Valid:** every Tier 0–3 property passes under the task's declared configuration.
2. **Correct:** TC.2 against the reference passes.

**TC.2 modes:**
- **`graph`:** identical molecules by a Weisfeiler–Lehman hash of the typed, charged bond graph; for minerals, also the same cell.
- **`chemistry`:** for random or gradient sequences, where any draw of the requested architecture is correct. Per molecule it requires the same atom types, net charge and number of bonds on each atom type. Every bond kind and every (atom type, charge) must also occur in the reference, or in a catalogue of the values any draw can contain. The catalogue is built from two-unit chains of the requested monomers.

**The one revision (v1.2).** In v1.1 the chemistry mode also compared the count of each bond kind and the exact list of charges. Both depend on the random order: the bonds that join neighbouring units, and the charges of the units at the chain ends. A correct file could therefore fail by chance. On dev task c04, the reference recipe itself passed with only 5 of 10 seeds. v1.2 removes that dependence. Every buildable draw now passes (55 of 55 on the four dev tasks), and wrong compositions, side-chain lengths and chain ends still fail. All development results were re-scored, and the validator matrix was re-run.

**Neither condition alone is enough.** A valid file can be the wrong system, and the right system can be written invalidly.

**Reporting:**
- **Headline:** the mean of per-task success rates over 3 repeats per task, with its spread across repeats.
- **Breakdowns:** domain, difficulty and force field.
- **Diagnostics:** pass@k, which is never the headline; validity rate; first failing property; failure-mode incidence; recovery rate; attempts; tokens; cost at the list price on the run date; latency.

### 4.3 Checking the harness

Before any model was scored, the harness was checked with reference systems on the development split (`docs/HARNESS.md`, 13 tasks × 3 repeats):

| Reference system | Expected | Observed |
|---|---|---|
| Oracle (builds the hidden spec) | success = 1 | 1.00 |
| File corrupter (oracle file + one corruption) | success ≈ 0, validity ≈ 0 | 0.00, 0.00 |
| Spec corrupter (one more cell, EO unit or monomer) | success ≈ 0, validity ≈ 1 | 0.00, 1.00 |

The spec corrupter matters most. It shows that a file that is perfectly valid but describes a slightly different system is scored as a failure: TC.2 does its job.

## 5. Systems

**Shared setup.** All systems use the same model (`config.yaml` → `model:`), the same domain knowledge in their system prompt and the same builders. The model is Claude Sonnet 5.5 (`claude-sonnet-5-5`, effort medium), chosen on 3 Nov 2026; the frozen record is `docs/FROZEN_CONFIG.md`. The domain knowledge (shared word for word between the systems) is:
- force-field coverage;
- the builder fields;
- the monomer chemistry, including how APEG/HPEG/TPEG/VPEG/MPEG map to the fields;
- one line per mineral model in the database.

The systems differ only in tools, feedback and retries.

### 5.1 Baseline (A): one call

One model call per task, with no tools, no feedback and no retry (`docs/BASELINE.md`). The model returns a builder spec as structured output, and the builders produce the file. This measures what the model does with the knowledge alone.

### 5.2 Agent (C): tools and validator feedback

The agent is a plain tool-use loop with no agent framework, so its control flow is visible (`docs/AGENT.md`, `docs/TOOLS.md`).

**Tools.** Three tools, all deterministic, all with strict JSON schemas, and none able to run arbitrary commands:
- `build_data_file(spec)` builds a file and returns plain facts about it: counts, elements, net charge, box, PCE sequences and counter-ions, surface placement. It reports the net charge but does not say whether that charge is acceptable; judging is the validator's job.
- `get_model_info(model, force_field)` returns a mineral model's cell, composition, atom types and charges.
- `get_reference_example(kind)` returns one of six worked request → spec examples.

**Loop:**
1. The model works with the tools until it stops.
2. The orchestrator validates the attempt's last build with Tiers 0–3. The configuration follows from what was built. The task's reference is never used inside the loop.
3. **On a pass**, the build is accepted.
4. **On a failure**, the failing checks go back to the model as a short message: property, tier, message with its key numbers, up to five LAMMPS ERROR lines. The message never contains the whole log. For example, "P2.1 (tier 2, FAIL): total charge = −4.000000 e, target +0.0000 e".
5. Steps 1–4 repeat for up to K = 3 attempts.

**Bounds:**
- model calls per attempt;
- tokens and wall time per task;
- a timeout per tool call.

**Non-convergence.** The same set of failing checks a second time adds an instruction to reconsider the approach. A third time escalates.

**On escalation.** A run that ends without an accepted build writes a report: what was tried, what failed, and that the last file must not be used without review. It never produces a plausible-looking wrong file.

**Traces.** Every run keeps a full trace (every model response, tool call, validation and feedback), and `replay()` reproduces a run exactly from its trace.

### 5.3 Ablation systems

| Label | System | What the comparison isolates |
|---|---|---|
| A | single call | the model with knowledge alone |
| B | the loop with retries, but only "the last build did not pass validation, try again" | tools and retries without information |
| C | the loop with validator feedback (the agent) | B vs C: whether the validator's feedback adds to retries |
| D (optional) | feedback from Tier 0–1 checks only | the value of the physically informed Tier 2–3 feedback |
| E (dropped after dev) | C + a build summary + a request check | catching valid-but-wrong builds (5.4) |

### 5.4 A known limitation of the loop, and variant E

**What the validator cannot see.** Inside the loop, the validator can only catch **invalid** files. The builders produce valid files for almost every consistent spec, so a **valid file of the wrong system** passes inside the loop. Examples are the wrong mineral model, the wrong supercell, a wrong side-chain length, or HPEG where TPEG was asked for. It fails only TC.2 afterwards.

**Why it matters for the comparison.** If most baseline failures are of this kind, B and C may differ little. That would be a finding about where validator feedback helps, not a defect of the experiment. On the development split this is what happened: the validator rejected no build, so its feedback never fired (Section 6.2). This is why the main claim (Section 1) is about validity and correctness, not about feedback.

**Variant E** (`docs/AGENT.md`) addresses this without ever seeing the reference. It adds two things:
- **A build summary.** One plain sentence saying what was built.
- **A request check.** A separate model call, given only the request, lists what the request states explicitly: counts, EO lengths, anchor, counter-ion, supercell, height and similar. Plain code compares that list with each build, and a mismatch is fed back like a failing check. If the agent rebuilds the same thing, its reading wins, so an extraction error costs at most one attempt.

**E was dropped after the development runs** (owner, 5 Nov). The request check misread one dev request: "30 methacrylate units and 10 MPEG methacrylate side chains" was read as a backbone of 30, when it is 40. In all three runs the agent followed the check and broke a correct build. E scored 0.92 against C's 1.00, so the test split runs A, B and C only.

**What replaces it.** Every run returns the build summary, and the command-line tool prints it. The person who wrote the request checks it against what they meant. Shown to the agent instead (C + summary), the sentence had no effect on dev: the model never rebuilt.

**Checks with scripted models.** E and the other systems were tested with scripted models whose behaviour is fixed in advance. These check the loop's control flow, not a model:
- a "perfect" model is accepted in one attempt;
- a model whose first build lacks counter-ions is corrected through the charge feedback;
- a model that repeats its error escalates;
- a model whose first build is valid but slightly wrong is accepted by C and caught by E.

## 6. Results

**[RESULTS]** Filled from `python -m eval.experiment` (`docs/EVALUATION.md`). Planned content:

- **6.1 Baseline on the development split.** Success, validity, failure categories and the failure analysis (`eval/analyse.py`). Gap types are suggested from a field-by-field comparison of the model's spec with the hidden spec: formatting, knowledge, reasoning, pipeline, validator. A human confirms them. The key question is what share of failures are TC-only (valid but wrong).
- **6.2 Agent on the development split.** Side by side with the baseline. Recovery from first-attempt failures. Remaining failure categories. The changes made on dev and their measured effect. Notes for writing this up (from `docs/RESULTS_DEV.md`, `docs/BASELINE_RESULTS*.md` and `docs/LOG.md`, 3 Nov):
  - **Baseline v1: 0.59.** 12 of its failures came from requests that leave the backbone end groups unstated. The prompt now states the default, and baseline v2 scores 0.92.
  - **Validity 1.00.** The in-loop validator rejected no build, so C's feedback never fired.
  - **The seed hint.** The refusal for a PCE too wide for a fixed slab cell now also suggests another seed. With it, the agents keep the requested cell: c06 went from 0/3 to 3/3.
  - **Final dev scores (METRICS v1.2, re-scored from the saved files):** A 0.92, B 1.00, C 1.00, E 0.92, so E was dropped. C + summary scored 1.00 and never rebuilt.
- **6.3 Held-out test split: the main result.** The agent's (C's) validity and TC.2 success on 9 tasks × 3 repeats: the [X] % and [Y] % of the main claim. They are given with their spread across repeats, and by domain, difficulty and force field. A and B (and D, if run) are reported alongside.
- **6.4 Ablation: where the reliability comes from.** Paired per-task comparisons, reported as tasks better / same / worse with a sign test. They are read as an explanation of the main result, not as the claim:
  - B vs A: tools and retries;
  - C vs B: feedback;
  - C vs D: Tier 2–3 feedback;

  With 9 test tasks, a sign test reaches p < 0.05 only if at least 6 tasks improve and none worsen. Claims are limited to what the per-task counts show.
- **6.5 Cost.** Attempts, tokens, cost (list price on the run date, cited) and latency per task.

## 7. Related work

Every statement below was re-checked against the papers on 2026-10-28 (abstract and HTML full text).

**Holbrook, Verduzco and Strachan (R18, arXiv 2603.20630).** "Evaluating LLM-generated code for domain-specific languages: molecular dynamics with LAMMPS."
- **What it checks.** LLM-generated LAMMPS **input scripts** from eight models on three prompts of increasing complexity.
- **The pipeline:** normalisation, a grammar-based parser producing an abstract syntax tree, reduced-step execution (with `pair_style zero` substituted on failure), and an expert checklist of physical criteria.
- **Results:**
  - "Across all 80 scripts evaluated on the most complex prompt, only one was fully correct as generated."
  - Parser pass rates rose from 74 % to 91 % over a year.
  - Packaged as a Claude Code skill, the validator helped two models produce five fully correct scripts out of six.
- **Relation to this project.** R18 is the closest work in spirit: deterministic, staged validation of LLM output, made available to an agent. It validates the input script; the structure is created by the script inside LAMMPS. It does not address data files, topology, charges or atom types. Our validator covers the other half of a LAMMPS input. The two are complementary.
- **One design difference.** In R18 the validator is a tool the agent can call. Here it is always run by the orchestrator, so an agent cannot skip it.

**MDGym (R19, arXiv 2605.08941; Kumar, Rajput, Mausam, Krishnan).**
- **What it benchmarks.** Coding agents on 169 end-to-end LAMMPS and GROMACS simulations. Final numerical outputs are scored against reference values within a 5 % relative tolerance.
- **Results.** The strongest agents solve 21 % of easy tasks and under 10 % at higher difficulty. Agents also fabricate numerical outputs or stop early.
- **Silent errors.** R19 states the silent-error problem directly: "a physically incoherent choice at any stage produces not a runtime error but a silently wrong simulation".
- **Its survey of MD agents:**
  - MDCrow and DynaMate (protein simulations);
  - PolyJarvis (an LLM coupled with RadonPy for polymer properties);
  - MDAgent and MDAgent2 (LAMMPS code generation with self-correction);
  - MD-EvalBench (LAMMPS code generation and question answering).
- **Relation to this project.** MDGym scores the end result of a whole workflow. Here we score the starting artifact, and a wrong data file is one way to reach a silently wrong simulation.

**Paimon (R20, arXiv 2606.09422; Park, Chung, You, Kim, Ju, Han).** "An Extensible Agentic Framework for Expert-Level Automation of Atomistic Simulations."
- **What it is.** An orchestrator with executors (LAMMPS, ASE, PACKMOL) that write simulation scripts by retrieval over the documentation.
- **How it checks work:**
  - an LLM "critic committee";
  - LLM rubric grading of scripts against binary criteria;
  - LAMMPS's own syntax check.
- **Its error taxonomy:**
  - **benign:** a minor deviation;
  - **loud:** an explicit failure;
  - **silent:** "the simulation completes without runtime errors and produces seemingly plausible data, but the underlying physical meaning is corrupted".

  We use the same distinction (SPEC §7.7).
- **Results.** Paimon raises pass rates substantially on expert-level electrolyte tasks, for example Li-ion MSD from 1 % to 66 %.
- **Relation to this project.** Paimon's checking is largely LLM-based. Here the checking is deterministic and calibrated: the same file always gets the same verdict, with a stated tolerance and its source.

**URSA LAMMPS agent (R21, arXiv 2607.22596; Somasundaram et al., LANL).** "An Agentic Orchestration of Atomistic Simulations."
- **What it does.** Selects interatomic potentials and writes LAMMPS input scripts for metals (aluminium benchmarks; copper for potential selection).
- **How it recovers from errors.** "If the simulation results in an error, the agent iteratively attempts to fix it … until the simulation is successful or until a user-specified limit on the number of iterations is achieved." Validation beyond that is a comparison of computed properties with the LAVA toolkit and an LLM literature check.
- **Human override.** A human can interrupt the workflow and override the agent's potential choice.
- **Relation to this project.** Success there means the run completes. Section 1 shows why that is not enough for a data file: here 521 of 948 corrupted files pass LAMMPS silently or with a warning. Like URSA, the loop here keeps the human in charge, through the escalation report and by never overwriting results or reference files.

**Data-file builders** (moltemplate, EMC, ClayCode) write files; they are not independent validators. **Deterministic checks of LLM output** are established in other domains, for example structural checks of LLM-generated crystal structures.

**Position.** In the works reviewed, no deterministic validator for the LAMMPS data file itself (types, charges, topology, box and force-field consistency) is provided. Deterministic checking of LLM output is not new (R18). This project contributes:
1. such a validator, tested against a failure-mode taxonomy;
2. a data-file-generating agent whose every output this validator certifies, evaluated on held-out tasks for both validity and correctness against trusted references, with an ablation showing where its reliability comes from.

We state this as a gap in the reviewed literature, not as proven novelty. A wider search of data-file checking tools was not completed.

## 8. Limitations

**About the evidence:**
- **Small task set.** 13 development and 9 test tasks, with 3 repeats. Differences of a few tasks are within noise, so results are reported per task and claims are limited to what the counts support.
- **References come from the same builders.** TC.2 measures whether the right system was requested, not whether the builders are right. The builders' correctness rests on separate comparisons with the group's EMC files and published structures.
- **TC.2 ignores PCE placement.** For composites it does not compare the adsorption height or orientation. A PCE placed elsewhere in the box with the right chemistry counts as correct (METRICS §2).
- **Tolerances are only as good as the references.** They are derived from a limited set of reference structures. The PCE density window (±2 %) is a requirement, not a measurement, because the two reference densities are identical.
- **One LAMMPS build, one platform.** Tier 3 findings (including the PPPM and `replicate` defects) are build-specific.
- **One model.** Results are for the model recorded in `docs/FROZEN_CONFIG.md`. A different model may fail differently.

**About the systems:**
- **The loop was built against scripted models** before any real model was available. Its limits (attempts, steps, tokens) were checked on the development split, where no run needed more than one attempt.
- **Feedback was barely exercised.** The builders refuse inconsistent specs, so the validator found nothing to reject in the agent's builds on the development split. The value of its feedback on systems where builders are less protective is therefore not measured here.
- **Validity is not scientific correctness.** The validator certifies that a file is consistent and plausible. It does not certify that a model is suitable for a given scientific question.
- **Scope.** Only CVFF/PCFF-INTERFACE, cement minerals, PCE and their composites. No C-S-H models beyond the database minerals, no CLAYFF, no reactive force fields, no input scripts.

## 9. Future work

- **The whole LAMMPS input.** Combine with input-script validation (R18) so that both halves of a LAMMPS input are checked.
- **More systems.** C-S-H models of varying Ca/Si, CLAYFF, and hydrated interfaces with explicit water and ions.
- **The validator for other agents.** Offer it as a service other MD agents call before running (R19–R21 all run LAMMPS on files they did not check).
- **Better checking for composites.** Extend TC.2 to adsorption geometry; add short-equilibration checks (energy drift, density relaxation) as an optional Tier 4.
- **A larger, independently written task set,** to give the ablation statistical power.

---

## Appendix: reproducing the results

**[RESULTS]**: commands and the frozen configuration. From a clean checkout:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt   # + LAMMPS (README)
pytest -q                                                    # unit tests
python scripts/run_matrix.py                                 # validator table (docs/VALIDATOR_RESULTS.md)
python scripts/harness_checks.py                             # harness checks (docs/HARNESS.md)
python scripts/freeze_config.py --check                      # configuration unchanged since the freeze
python -m eval.experiment run --split test --systems baseline agent-nofeedback agent --write-doc docs/RESULTS_TEST.md
```

## References

- **R18** E. Holbrook, J. C. Verduzco, A. Strachan. Evaluating LLM-generated code for domain-specific languages: molecular dynamics with LAMMPS. arXiv:2603.20630 (v2, May 2026).
- **R19** V. Kumar, S. Rajput, Mausam, N. M. A. Krishnan. MDGym: Benchmarking AI Agents on Molecular Simulations. arXiv:2605.08941 (2026).
- **R20** Y. Park, Y. Chung, J. You, J. Kim, S. Ju, S. Han. An Extensible Agentic Framework for Expert-Level Automation of Atomistic Simulations. arXiv:2606.09422 (v3, Oct 2026).
- **R21** R. Somasundaram et al. An Agentic Orchestration of Atomistic Simulations. arXiv:2607.22596 (2026), LA-UR-26-24722.
- **INTERFACE FF 1.5**, CVFF-INTERFACE and PCFF-INTERFACE parameters and the cement-mineral model database (`UGRP/INTERFACE_FF_1_5`, `UGRP/CEMENT_MINERALS`). **[CITE]**: the Heinz group's INTERFACE FF papers, as used by the research group.
- **LAMMPS** 22 Jul 2025 – Update 6, `read_data` documentation and source (tag `stable_22Jul2025_update6`).
- **Claude API documentation** (models, pricing, tool use, structured outputs), read on the dates recorded in `eval/pricing.json` and `docs/FROZEN_CONFIG.md`.
