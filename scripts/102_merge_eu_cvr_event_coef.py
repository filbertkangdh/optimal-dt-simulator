"""Merges the EU CVR Impact Coefficient sheet (country x event-type CVR penalty) into `DATA` as a
new `euCvrEventCoef` array, in both places that carry the simulator's data (same pattern as
productions/v2/scripts/99_merge_regime_dt_ranges.py).

Ask (2026-08-21): the hump-flattening override (predictCVR, "N-shape (hump) GMV flattening") used
to freeze CVR flat below a country's own interior GMV peak, assuming zero CVR improvement for any
DT below it (see that function's own comment for the demand-simultaneity rationale). For the 4 EU
countries this sheet covers (Czech Republic/Hungary/Norway/Sweden), that flat freeze is replaced
by a curve driven by the predicted MIX of 3 operational events (surge/shrink/vendor-close) at each
DT: as DT falls below the peak, each event's own DT-mediator curve (pct_surge_by_time/pct_shrink/
pct_close, already in DATA.mediatorCoef, previously informational-only) predicts how much less
often that event occurs; multiplying that reduction by the event's own CVR penalty (this sheet)
and summing gives a real, event-mix-explained CVR recovery instead of an assumed-zero one. Every
other country keeps the pre-existing flat freeze unchanged (per user's explicit scope choice --
this sheet only covers these 4 countries, no pooled/extrapolated proxy for others).

Source: "EU CVR Impact Coefficient.csv" (repo root of this project, one level above productions/).
Columns: country_name, event_type ("2_surge"/"3_shrink"/"4_close"), "CVR Diff" (e.g. "24.59%") --
confirmed with user: this is the CVR PENALTY during that event vs. a normal order (positive number
= CVR that many percentage points LOWER during the event), not an already-signed uplift.

New DATA field `euCvrEventCoef` (array, one row per country x event):
  code       -- 2-letter country code (cz/hu/no/se)
  event      -- "surge" | "shrink" | "close"
  cvrDiff    -- fraction (0.2459 for "24.59%"), the CVR penalty during that event

Run: .venv/bin/python3 productions/v2/scripts/102_merge_eu_cvr_event_coef.py
"""

import json
import re

import pandas as pd

REPO_ROOT = "."
CSV_PATH = f"{REPO_ROOT}/EU CVR Impact Coefficient.csv"
JSON_PATH = f"{REPO_ROOT}/productions/v2/data/simulator_data_reverted_2026-07-25_v6.json"
HTML_PATH = f"{REPO_ROOT}/productions/v2/dt_gmv_simulator.html"
ROUND = 6

COUNTRY_NAME_TO_CODE = {
    "Czech Republic": "cz",
    "Hungary": "hu",
    "Norway": "no",
    "Sweden": "se",
}
EVENT_TYPE_TO_KEY = {
    "2_surge": "surge",
    "3_shrink": "shrink",
    "4_close": "close",
}


def parse_pct(s):
    return round(float(str(s).strip().rstrip("%")) / 100, ROUND)


df = pd.read_csv(CSV_PATH)
missing_countries = set(df["country_name"]) - set(COUNTRY_NAME_TO_CODE)
if missing_countries:
    raise SystemExit(f"Unmapped country_name value(s) in {CSV_PATH}: {missing_countries}")
missing_events = set(df["event_type"]) - set(EVENT_TYPE_TO_KEY)
if missing_events:
    raise SystemExit(f"Unmapped event_type value(s) in {CSV_PATH}: {missing_events}")

eu_cvr_event_coef = [
    {
        "code": COUNTRY_NAME_TO_CODE[row["country_name"]],
        "event": EVENT_TYPE_TO_KEY[row["event_type"]],
        "cvrDiff": parse_pct(row["CVR Diff"]),
    }
    for _, row in df.iterrows()
]


def merge_eu_cvr_event_coef(data):
    data["euCvrEventCoef"] = eu_cvr_event_coef
    return data


# ---- 1. standalone data JSON ----
with open(JSON_PATH) as f:
    json_data = json.load(f)
merge_eu_cvr_event_coef(json_data)
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
merge_eu_cvr_event_coef(html_data)
new_data_line = "const DATA = " + json.dumps(html_data) + ";"
html = html[: match.start()] + new_data_line + html[match.end() :]
with open(HTML_PATH, "w") as f:
    f.write(html)
print(f"Patched inline DATA blob in {HTML_PATH}")
