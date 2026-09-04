"""Builds dt_gmv_simulator.html with the corrected lateness source (order_delay_in_minutes from
pandora__order_logistics, 2026-07-29) baked into both the lateness-band curves and the on-time
DT-bin survival curves, using the v6 data bundle.

Run: .venv/bin/python3 review/2026-07-17_dt_scenario_simulator/96_build_simulator_html_reverted_v6.py
"""

OUT_DIR = "review/2026-07-17_dt_scenario_simulator"
TEMPLATE_PATH = f"{OUT_DIR}/dt_gmv_simulator_template.html"
DATA_PATH = f"{OUT_DIR}/simulator_data_reverted_2026-07-25_v6.json"
OUT_PATH = f"{OUT_DIR}/dt_gmv_simulator.html"
PLACEHOLDER = "/*__SIM_DATA__*/"

with open(TEMPLATE_PATH) as f:
    template = f.read()
with open(DATA_PATH) as f:
    data_json = f.read()

assert template.count(PLACEHOLDER) == 1, f"Expected exactly 1 placeholder, found {template.count(PLACEHOLDER)}"
out = template.replace(PLACEHOLDER, data_json)

with open(OUT_PATH, "w") as f:
    f.write(out)

print(f"Saved: {OUT_PATH} ({len(out)} bytes)")
