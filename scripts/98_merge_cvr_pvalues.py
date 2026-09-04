"""Merges R^2/p-value goodness-of-fit stats into cvrCoef, in both places that carry the
simulator's data (per MEMORY.md Thread 2: the live dt_gmv_simulator.html embeds its own inline
copy of DATA, separate from data/simulator_data_reverted_2026-07-25_v6.json -- both must be
patched). Deliberately a narrow field-merge, NOT a full re-run of
review/2026-07-17_dt_scenario_simulator/40_export_simulator_data_v3.py -- that script also
rebuilds mediatorCoef/dtBaseline/etc., which per productions/v2/README.md's known caveat have
already drifted from what the live HTML actually carries. Re-running the full export risked
reverting or diverging that drifted state; a targeted merge by `code` avoids touching anything
else.

Source: review/2026-07-17_dt_scenario_simulator/39_zone_day_cvr_winter_ramadan_coefficients.csv
(re-run 2026-08-13 to add p_pdt/p_pdt_joint/p_model columns -- see that script's diff).

New cvrCoef fields (per country):
  pPdt, pPdt2       -- individual t-test p-values for the linear/quadratic PDT terms.
  pPdtJoint         -- joint F-test p-value that b_pdt = b_pdt2 = 0 (the statistically correct
                       single significance number for "is DT related to CVR at all", since the
                       two terms are highly collinear by construction and an individual t-test on
                       either one alone can understate the joint relationship).
  pModel            -- overall model F-test p-value (all regressors incl. controls + zone FE vs.
                       intercept-only).
  nObs              -- zone-day observation count the country's model was fit on (n_zones * n_obs
                       already existed as nZones; n_obs did not).

Run: .venv/bin/python3 productions/v2/scripts/98_merge_cvr_pvalues.py
"""

import json
import re

import pandas as pd

REPO_ROOT = "."
CVR_CSV = f"{REPO_ROOT}/review/2026-07-17_dt_scenario_simulator/39_zone_day_cvr_winter_ramadan_coefficients.csv"
JSON_PATH = f"{REPO_ROOT}/productions/v2/data/simulator_data_reverted_2026-07-25_v6.json"
HTML_PATH = f"{REPO_ROOT}/productions/v2/dt_gmv_simulator.html"
ROUND = 6


def r(x):
    if pd.isna(x):
        return None
    return round(float(x), ROUND)


cvr = pd.read_csv(CVR_CSV)
new_fields_by_code = {}
for _, row in cvr.iterrows():
    new_fields_by_code[row["lg_country_code"]] = {
        "pPdt": r(row["p_pdt"]),
        "pPdt2": r(row["p_pdt2"]),
        "pPdtJoint": r(row["p_pdt_joint"]),
        "pModel": r(row["p_model"]),
        "nObs": int(row["n_obs"]),
    }


def merge_cvr_coef(data):
    missing = []
    for entry in data["cvrCoef"]:
        code = entry["code"]
        if code not in new_fields_by_code:
            missing.append(code)
            continue
        entry.update(new_fields_by_code[code])
    if missing:
        raise SystemExit(f"cvrCoef codes with no match in {CVR_CSV}: {missing}")
    return data


# ---- 1. standalone data JSON ----
with open(JSON_PATH) as f:
    json_data = json.load(f)
merge_cvr_coef(json_data)
with open(JSON_PATH, "w") as f:
    json.dump(json_data, f)
print(f"Patched {JSON_PATH}")

# ---- 2. inline DATA blob in the live HTML (const DATA = {...};, single line) ----
with open(HTML_PATH) as f:
    html = f.read()

match = re.search(r"^const DATA = (\{.*\});$", html, flags=re.MULTILINE)
if not match:
    raise SystemExit("Could not find `const DATA = {...};` line in dt_gmv_simulator.html")

html_data = json.loads(match.group(1))
merge_cvr_coef(html_data)
new_data_line = "const DATA = " + json.dumps(html_data) + ";"
html = html[: match.start()] + new_data_line + html[match.end() :]
with open(HTML_PATH, "w") as f:
    f.write(html)
print(f"Patched inline DATA blob in {HTML_PATH}")
