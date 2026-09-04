"""Merges regime-specific (normal/winter/ramadan) dt_min/dt_max/n_obs into `dtBaseline`, in both
places that carry the simulator's data (same pattern as
productions/v2/scripts/98_merge_cvr_pvalues.py -- see that script's own docstring for why this is
a narrow field-merge rather than a full re-run of
review/2026-07-17_dt_scenario_simulator/40_export_simulator_data_v3.py: that script also rebuilds
mediatorCoef/cvrCoef/etc., which per productions/v2/README.md's known caveat have already drifted
from what the live HTML actually carries).

Ask (2026-08-13): the "Find best ROI DT" optimizer's search range and the GMV/UTR/rider-cost
charts' observed-vs-extrapolated shading (both driven by `observedRangeWhole(code)` ->
`countryBaselineByCode[code].dtMin/dtMax`) always used the all-days-pooled training range,
regardless of the simulator's existing Normal/Winter/Ramadan day-type toggle (`state.regime`,
2026-07-24) -- i.e. picking "Winter" changed the PREDICTED curve (via bWinter/winterInteraction)
but not which DT values were considered "observed" for that regime. This merges in the
regime-specific ranges computed by 02_build_dt_baseline.py (2026-08-13 update) so the JS side can
make `observedRangeWhole` (and the 4 chart in-sample masks that used to read `.dtMin`/`.dtMax`
directly) regime-aware.

Source: review/2026-07-17_dt_scenario_simulator/dt_baseline_stats.csv (re-run 2026-08-13 to add
dt_min_normal/dt_max_normal/n_obs_normal + _winter/_ramadan variants -- see that script's diff).

New dtBaseline fields (per row, population + every country):
  dtMinNormal, dtMaxNormal, nObsNormal   -- always populated (empty exclusion mask if this
                                            country/level has neither a winter nor ramadan term).
  dtMinWinter, dtMaxWinter, nObsWinter   -- null except at/cz/hu/no/se (WINTER_COUNTRIES).
  dtMinRamadan, dtMaxRamadan, nObsRamadan -- null except bd/my/pk/sg/t3 (RAMADAN_COUNTRIES).

Run: .venv/bin/python3 productions/v2/scripts/99_merge_regime_dt_ranges.py
"""

import json
import re

import pandas as pd

REPO_ROOT = "."
BASELINE_CSV = f"{REPO_ROOT}/review/2026-07-17_dt_scenario_simulator/dt_baseline_stats.csv"
JSON_PATH = f"{REPO_ROOT}/productions/v2/data/simulator_data_reverted_2026-07-25_v6.json"
HTML_PATH = f"{REPO_ROOT}/productions/v2/dt_gmv_simulator.html"
ROUND = 6

REGIME_FIELD_MAP = {
    "dt_min_normal": "dtMinNormal", "dt_max_normal": "dtMaxNormal", "n_obs_normal": "nObsNormal",
    "dt_min_winter": "dtMinWinter", "dt_max_winter": "dtMaxWinter", "n_obs_winter": "nObsWinter",
    "dt_min_ramadan": "dtMinRamadan", "dt_max_ramadan": "dtMaxRamadan", "n_obs_ramadan": "nObsRamadan",
}


def r(x):
    if pd.isna(x):
        return None
    return round(float(x), ROUND)


baseline = pd.read_csv(BASELINE_CSV)
new_fields_by_key = {}  # key: (level, code) -- code is "" for population, matching lg_country_code
for _, row in baseline.iterrows():
    key = (row["level"], row["lg_country_code"] if pd.notna(row["lg_country_code"]) else "")
    fields = {}
    for src, dst in REGIME_FIELD_MAP.items():
        val = row[src]
        fields[dst] = int(val) if dst.startswith("nObs") and pd.notna(val) else r(val)
    new_fields_by_key[key] = fields


def merge_dt_baseline(data):
    missing = []
    for entry in data["dtBaseline"]:
        key = (entry["level"], entry["code"] or "")
        if key not in new_fields_by_key:
            missing.append(key)
            continue
        entry.update(new_fields_by_key[key])
    if missing:
        raise SystemExit(f"dtBaseline (level, code) keys with no match in {BASELINE_CSV}: {missing}")
    return data


# ---- 1. standalone data JSON ----
with open(JSON_PATH) as f:
    json_data = json.load(f)
merge_dt_baseline(json_data)
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
merge_dt_baseline(html_data)
new_data_line = "const DATA = " + json.dumps(html_data) + ";"
html = html[: match.start()] + new_data_line + html[match.end() :]
with open(HTML_PATH, "w") as f:
    f.write(html)
print(f"Patched inline DATA blob in {HTML_PATH}")
