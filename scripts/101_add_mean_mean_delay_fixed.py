"""Adds `meanMeanDelay` (session-weighted historical average of mean_delay, from the actual
CVR-model training panel) to Austria's and Pakistan's `cvrCoef` rows in both the standalone JSON
bundle and the live HTML's embedded DATA blob -- the value `predictCVRRaw` uses for these two
countries instead of DT-predicting mean_delay (see MEAN_DELAY_HELD_FIXED_COUNTRIES, 2026-08-13d).

Does NOT touch bPdt/bPdt2/bMeanDelay/r2/nZones/etc. -- the underlying CVR~PDT+controls regression
is unchanged; only how mean_delay's VALUE is sourced at prediction time changes for at/pk.

Run: .venv/bin/python3 productions/v2/scripts/101_add_mean_mean_delay_fixed.py
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent.parent  # optimal_dt_gmv_roi_ip/
V2_ROOT = Path(__file__).resolve().parent.parent
PANEL_PATH = ROOT / "review" / "2026-07-17_dt_scenario_simulator" / "zone_day_panel_with_surge_multiplier.csv"
JSON_PATH = V2_ROOT / "data" / "simulator_data_reverted_2026-07-25_v6.json"
HTML_PATH = V2_ROOT / "dt_gmv_simulator.html"
CODES = ["at", "pk"]
ROUND = 6

panel = pd.read_csv(PANEL_PATH)
panel["surge_multiplier"] = panel["surge_multiplier"].replace([np.inf, -np.inf], np.nan)

mean_delay_fixed = {}
for code in CODES:
    g = panel[panel["lg_country_code"] == code].dropna(subset=["mean_delay", "sessions"])
    mean_delay_fixed[code] = round(float(np.average(g["mean_delay"], weights=g["sessions"])), ROUND)
print("Session-weighted historical mean_delay:", mean_delay_fixed)


def patch_cvr_coef(cvr_coef):
    n = 0
    for row in cvr_coef:
        if row.get("code") in mean_delay_fixed:
            row["meanMeanDelay"] = mean_delay_fixed[row["code"]]
            n += 1
    return n


with open(JSON_PATH) as f:
    bundle = json.load(f)
n = patch_cvr_coef(bundle["cvrCoef"])
print(f"[JSON] patched meanMeanDelay for {n} countries")
with open(JSON_PATH, "w") as f:
    json.dump(bundle, f, separators=(",", ":"))
print(f"Saved: {JSON_PATH}")

html = HTML_PATH.read_text(encoding="utf-8")
m = re.search(r"const DATA\s*=\s*(\{.*?\});", html, re.S)
assert m, "could not find `const DATA = {...};` in the live HTML"
html_bundle = json.loads(m.group(1))
n = patch_cvr_coef(html_bundle["cvrCoef"])
print(f"[HTML] patched meanMeanDelay for {n} countries")
new_data_literal = json.dumps(html_bundle, separators=(",", ":"))
new_html = html[: m.start()] + f"const DATA = {new_data_literal};" + html[m.end() :]
HTML_PATH.write_text(new_html, encoding="utf-8")
print(f"Saved: {HTML_PATH}")
