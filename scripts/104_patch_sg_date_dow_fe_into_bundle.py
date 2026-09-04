"""
Patches SG's cvrCoef row in the standalone JSON bundle (data/simulator_data_reverted_2026-07-25_v6.json)
to match the date-FE/zone-x-DOW-FE swap already applied directly to dt_gmv_simulator.html's inline
DATA blob (see productions/v2/scripts/103_sg_date_dow_fe_ladder.py for the model fit itself).

Per this project's own convention (every merge script since 98_/99_ patches BOTH the standalone
bundle AND the live HTML's separate inline DATA copy -- they are NOT the same object at runtime,
see MEMORY.md's "Do NOT" list): this script only does the bundle half, since the HTML was already
hand-edited directly (its DATA blob is one single line, not amenable to loading via json.load the
way this bundle is). The weekday/weekend split (SG_DAY_TYPE_CVR_COEF) lives ONLY in the HTML as a
JS constant -- this bundle has no equivalent live UI/toggle to serve, so it isn't replicated here.

Run from project root (optimal_dt_gmv_roi_ip/):
    .venv/bin/python3 productions/v2/scripts/104_patch_sg_date_dow_fe_into_bundle.py
"""
import json

BUNDLE_PATH = "productions/v2/data/simulator_data_reverted_2026-07-25_v6.json"

NEW_SG_ROW = {
    "countryName": "Singapore", "code": "sg", "nZones": 12,
    "zoneAdjustedIntercept": 0.313954, "bPdt": 0.000162, "bPdt2": -0.0000232,
    "bHealthyAvailability": 0, "bMeanDelay": 0, "bSurgeMultiplier": 0, "bWinter": 0,
    "bRamadan": None, "hasRamadanTerm": False, "r2": 0.864285,
    "pdtMinWinsorized": 26.780271, "pdtMaxWinsorized": 54.861881,
    "meanHealthyAvailability": 0.990038,
    "pPdt": 0.744513, "pPdt2": 0.000267, "pPdtJoint": None, "pModel": None, "nObs": 4380,
}


def main():
    with open(BUNDLE_PATH) as f:
        data = json.load(f)
    replaced = False
    for i, row in enumerate(data["cvrCoef"]):
        if row.get("code") == "sg":
            data["cvrCoef"][i] = NEW_SG_ROW
            replaced = True
            break
    if not replaced:
        raise RuntimeError("No SG row found in cvrCoef -- bundle schema may have changed")
    with open(BUNDLE_PATH, "w") as f:
        json.dump(data, f)
    print(f"Patched: {BUNDLE_PATH}")


if __name__ == "__main__":
    main()
