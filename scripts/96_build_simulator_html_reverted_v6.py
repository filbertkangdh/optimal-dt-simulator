"""Builds dt_gmv_simulator.html with the corrected lateness source (order_delay_in_minutes from
pandora__order_logistics, 2026-07-29) baked into both the lateness-band curves and the on-time
DT-bin survival curves, using the v6 data bundle.

Run from anywhere: .venv/bin/python3 productions/v2/scripts/96_build_simulator_html_reverted_v6.py
"""

from pathlib import Path

V2_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = V2_ROOT / "dt_gmv_simulator_template.html"
DATA_PATH = V2_ROOT / "data" / "simulator_data_reverted_2026-07-25_v6.json"
OUT_PATH = V2_ROOT / "dt_gmv_simulator.html"
PLACEHOLDER = "/*__SIM_DATA__*/"

template = TEMPLATE_PATH.read_text()
data_json = DATA_PATH.read_text()

assert template.count(PLACEHOLDER) == 1, f"Expected exactly 1 placeholder, found {template.count(PLACEHOLDER)}"
out = template.replace(PLACEHOLDER, data_json)

OUT_PATH.write_text(out)
print(f"Saved: {OUT_PATH} ({len(out)} bytes)")
