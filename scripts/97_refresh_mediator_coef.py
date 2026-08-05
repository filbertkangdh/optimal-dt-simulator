"""Refreshes ONLY the `mediatorCoef` array in the v6 simulator data bundle from peer's amended
part0_4_coefficients.csv (2026-08-04), leaving every other key in the bundle (cvrCoef, reorder
curves, EPH/CPO inputs, etc.) untouched since they come from unrelated source files.

Prerequisite: review/2026-07-17_dt_scenario_simulator/12_merge_coefficients_with_ci.py must already
have been re-run against the updated top-level part0_4_coefficients.csv (regenerates
review/2026-07-17_dt_scenario_simulator/part0_4_coefficients_merged.csv, this script's input).

Mirrors the exact mediatorCoef transform from review/2026-07-17_dt_scenario_simulator/
40_export_simulator_data_v3.py (lines 28-64) so the refreshed rows are structurally identical to
the ones already in the bundle.

Run from anywhere: .venv/bin/python3 productions/v2/scripts/97_refresh_mediator_coef.py
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent.parent  # optimal_dt_gmv_roi_ip/
V2_ROOT = Path(__file__).resolve().parent.parent
MERGED_COEF_PATH = ROOT / "review" / "2026-07-17_dt_scenario_simulator" / "part0_4_coefficients_merged.csv"
BUNDLE_PATH = V2_ROOT / "data" / "simulator_data_reverted_2026-07-25_v6.json"
ROUND = 6


def r(x):
    if pd.isna(x):
        return None
    return round(float(x), ROUND)


coef = pd.read_csv(MERGED_COEF_PATH)
coef_out = []
for _, row in coef.iterrows():
    coef_out.append({
        "metric": row["metric_pair"],
        "curveType": row["curve_type"],
        "level": row["level"],
        "groupId": row["group_id"] if pd.notna(row["group_id"]) else None,
        "r2": r(row["r_squared"]),
        "intercept": r(row["intercept"]),
        "interceptLow": r(row["intercept_low"]),
        "interceptHigh": r(row["intercept_high"]),
        "slope": r(row["slope"]),
        "slopeLow": r(row["slope_low"]),
        "slopeHigh": r(row["slope_high"]),
        "winterInteraction": r(row["winter_interaction"]),
        "winterInteractionLow": r(row["winter_interaction_low"]),
        "winterInteractionHigh": r(row["winter_interaction_high"]),
        "ramadanInteraction": r(row["ramadan_interaction"]),
        "ramadanInteractionLow": r(row["ramadan_interaction_low"]),
        "ramadanInteractionHigh": r(row["ramadan_interaction_high"]),
        "capL": r(row["cap_L"]),
        "capLLow": r(row["cap_L_low"]),
        "capLHigh": r(row["cap_L_high"]),
        "steepnessK": r(row["steepness_k"]),
        "steepnessKLow": r(row["steepness_k_low"]),
        "steepnessKHigh": r(row["steepness_k_high"]),
        "thresholdX0Z": r(row["threshold_x0_zscore"]),
        "thresholdX0ZLow": r(row["threshold_x0_zscore_low"]),
        "thresholdX0ZHigh": r(row["threshold_x0_zscore_high"]),
        "asymptoteA": r(row["asymptote_a"]),
        "asymptoteALow": r(row["asymptote_a_low"]),
        "asymptoteAHigh": r(row["asymptote_a_high"]),
        "halfSaturationB": r(row["half_saturation_b_min"]),
        "halfSaturationBLow": r(row["half_saturation_b_min_low"]),
        "halfSaturationBHigh": r(row["half_saturation_b_min_high"]),
    })

with open(BUNDLE_PATH) as f:
    bundle = json.load(f)

old_coef = bundle["mediatorCoef"]
old_keys = {(c["metric"], c["level"], c["groupId"]) for c in old_coef}
new_keys = {(c["metric"], c["level"], c["groupId"]) for c in coef_out}

print(f"Old mediatorCoef: {len(old_coef)} rows, {len(old_keys)} unique (metric, level, groupId)")
print(f"New mediatorCoef: {len(coef_out)} rows, {len(new_keys)} unique (metric, level, groupId)")
only_old = old_keys - new_keys
only_new = new_keys - old_keys
if only_old:
    print(f"WARNING: {len(only_old)} (metric,level,groupId) rows dropped: {sorted(only_old)}")
if only_new:
    print(f"NOTE: {len(only_new)} new (metric,level,groupId) rows added: {sorted(only_new)}")

old_by_key = {(c["metric"], c["level"], c["groupId"]): c for c in old_coef}
n_changed = 0
for c in coef_out:
    key = (c["metric"], c["level"], c["groupId"])
    old = old_by_key.get(key)
    if old is not None and old != c:
        n_changed += 1
print(f"{n_changed}/{len(coef_out)} rows have at least one changed field vs. the current bundle")

bundle["mediatorCoef"] = coef_out
with open(BUNDLE_PATH, "w") as f:
    json.dump(bundle, f, separators=(",", ":"))

print(f"Saved: {BUNDLE_PATH}")
