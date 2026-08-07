---
id: v2
title: V2
tags: []
methods: []
datasets: []
summary: Live working copy of the simulator, promoted out of the much larger iterative
last_updated: '2026-08-04'
---
# DT → GMV ROI Simulator — Production v2

Live working copy of the simulator, promoted out of the much larger iterative
working directory (`review/2026-07-17_dt_scenario_simulator/`, ~400 files
incl. multi-GB raw BigQuery pulls) so day-to-day editing doesn't drag that
directory's size along. This is a **pragmatic promotion**: it captures the
current build chain (template → data → HTML), not a full re-derivation of
every coefficient-fitting script behind the data bundle. For that lineage
(CVR/GMV model specs, reorder-rate survival curves, etc.), see `MEMORY.md` /
`CONTEXT.md` in the parent directory and the numbered scripts still in
`review/2026-07-17_dt_scenario_simulator/`.

## Folder structure

```
v2/
├── dt_gmv_simulator.html             <- published artifact (edit via template, not directly)
├── dt_gmv_simulator_template.html    <- edit this; has a /*__SIM_DATA__*/ placeholder
├── scripts/
│   └── 96_build_simulator_html_reverted_v6.py   <- splices data into the template
├── data/
│   └── simulator_data_reverted_2026-07-25_v6.json   <- the DATA blob spliced into the template
└── assets/                            <- Pandora brand images (source PNGs + base64 .txt forms)
    ├── pandora_bar_b64.txt
    ├── pandora_logo_b64.txt
    ├── pandora_logo_black_b64.txt
    └── pandora_logo_white.png
```

## How to rebuild

```bash
.venv/bin/python3 productions/v2/scripts/96_build_simulator_html_reverted_v6.py
```

Reads `dt_gmv_simulator_template.html` + `data/simulator_data_reverted_2026-07-25_v6.json`,
replaces the `/*__SIM_DATA__*/` placeholder, writes `dt_gmv_simulator.html`.
The brand images are already inlined as literal base64 in the template
(not spliced by this script) — the `assets/*_b64.txt` files are kept only
as the source encodings, for reference if the branding ever needs to change.

## Known caveat (as of 2026-08-04 promotion)

Re-running the build script does **not** reproduce the `dt_gmv_simulator.html`
byte-for-byte as it stood right before this promotion — the template and/or
data bundle had drifted from whatever last produced the live file (possibly
via a direct hand-edit to the built HTML, bypassing the template). The
promoted `dt_gmv_simulator.html` in this folder is the actual last-live
version, kept as-is; it has **not** been overwritten by a fresh rebuild.
Before trusting the rebuild script for a real edit, diff its output against
the current `dt_gmv_simulator.html` to see what actually differs.
