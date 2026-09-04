"""Refreshes `gmvInputs` and each `cvrCoef[].meanHealthyAvailability` in the v6 simulator data
bundle (both the standalone JSON and the live HTML's embedded DATA blob) using an UNFILTERED
(all-zone) country-day totals pull, replacing the zone-shortlisted (>=500 avg daily orders,
>=350/365 days coverage) totals both fields were previously built from.

Root cause being fixed: `data/country_day_panel_with_delay.csv` (the source `06_gmv_estimation_
inputs.py` and `14_healthy_availability_q2_2026.py` originally read) is built by aggregating
`data/zone_day_panel_with_delay.csv`, which only keeps a SHORTLIST of zones per country
(`zone_shortlist_final.csv`) -- e.g. Sweden keeps only 22 of 102 real zones. Every SUM column
(sessions, transactions, gmv_eur) inherited that undercount, and the availability rate inherited
the same big-zone composition bias. The user re-pulled the same 4+2 columns with NO zone filter,
full Jul 2025-Jun 2026 window, all 16 countries -> `data/country_day_totals_unfiltered.csv`
(this folder). This script rebuilds ONLY `gmvInputs` and `meanHealthyAvailability` from that file;
every other key in the bundle (mediatorCoef, dtBaseline, cvrCoef's own regression coefficients/
nZones/r2/p-values, surgeMultCoef, cpoInputs, dtCeiling, revenueBreakdown, reorder curves, etc.)
is left untouched -- the CVR regression itself still trains on the shortlisted panel, unchanged,
per the user's explicit 2026-08-13 scope decision (fix the Q2'2026 baseline inputs, not the model).

Mirrors `06_gmv_estimation_inputs.py` (sessions/AOV/CV% logic) and `14_healthy_availability_q2_
2026.py` (session-weighted, special-days-excluded Q2 availability mean) exactly, just pointed at
the new unfiltered source instead of `data/country_day_panel_with_delay.csv`.
`q2_2026_mean_orders_per_conversion` is NOT recomputed -- it already comes from an independent,
unfiltered source (`pandora__core_sessions`, `orders_per_conversion_q2_2026.csv`), untouched.

Run: .venv/bin/python3 productions/v2/scripts/100_refresh_gmv_inputs_unfiltered.py
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent.parent  # optimal_dt_gmv_roi_ip/
V2_ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = ROOT / "review" / "2026-07-17_dt_scenario_simulator"

UNFILTERED_PATH = V2_ROOT / "data" / "country_day_totals_unfiltered.csv"
SPECIAL_DAY_PATH = ROOT / "data" / "daily_country_panel_v2.csv"
OPC_PATH = REVIEW_DIR / "orders_per_conversion_q2_2026.csv"
JSON_PATH = V2_ROOT / "data" / "simulator_data_reverted_2026-07-25_v6.json"
HTML_PATH = V2_ROOT / "dt_gmv_simulator.html"
ROUND = 6


def r(x):
    return None if pd.isna(x) else round(float(x), ROUND)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
df = pd.read_csv(UNFILTERED_PATH, parse_dates=["report_date"])
df = df.rename(columns={"healthy_ns": "healthy_vendor_availability_sessions"})
required = [
    "lg_country_code", "report_date", "sessions", "transactions",
    "successful_orders", "gmv_eur", "healthy_vendor_availability_sessions",
    "total_availability_sessions",
]
missing = [c for c in required if c not in df.columns]
assert not missing, f"unfiltered pull missing columns: {missing}"
assert df["lg_country_code"].nunique() == 16, f"expected 16 countries, got {df['lg_country_code'].nunique()}"

sd = pd.read_csv(SPECIAL_DAY_PATH, parse_dates=["report_date"])[["lg_country_code", "report_date", "is_special_day"]]
df = df.merge(sd, on=["lg_country_code", "report_date"], how="left")
assert df["is_special_day"].isna().sum() == 0, "unexpected join miss merging is_special_day flag"

opc_by_code = pd.read_csv(OPC_PATH).set_index("lg_country_code")["mean_orders_per_converting_session"]

df["healthy_vendor_availability_pct"] = (
    df["healthy_vendor_availability_sessions"] / df["total_availability_sessions"]
)

q2 = df[(df["report_date"] >= "2026-04-01") & (df["report_date"] <= "2026-06-30")].copy()
n_months = q2["report_date"].dt.to_period("M").nunique()
assert n_months == 3, f"expected 3 months in Q2 2026, got {n_months}"

full_year_sessions_cv = df.groupby("lg_country_code")["sessions"].agg(lambda s: s.std() / s.mean() * 100)

# ---------------------------------------------------------------------------
# gmvInputs (06_gmv_estimation_inputs.py logic, unfiltered source)
# ---------------------------------------------------------------------------
gmv_rows = []
for lg_country_code, g in q2.groupby("lg_country_code"):
    total_sessions = g["sessions"].sum()
    total_transactions = g["transactions"].sum()
    total_gmv = g["gmv_eur"].sum()
    aov_per_conversion = total_gmv / total_transactions
    mean_orders_per_conversion = opc_by_code.loc[lg_country_code]
    gmv_rows.append({
        "lg_country_code": lg_country_code,
        "avgMonthlySessions": r(total_sessions / n_months),
        "sessionsCvPct": r(g["sessions"].std() / g["sessions"].mean() * 100),
        "fullYearSessionsCvPct": r(full_year_sessions_cv.loc[lg_country_code]),
        "meanOrdersPerConversion": r(mean_orders_per_conversion),
        "aovEur": r(aov_per_conversion / mean_orders_per_conversion),
    })
gmv_by_code = {row["lg_country_code"]: row for row in gmv_rows}

# ---------------------------------------------------------------------------
# meanHealthyAvailability (14_healthy_availability_q2_2026.py logic, unfiltered source)
# ---------------------------------------------------------------------------
q2_clean = q2[~q2["is_special_day"]]
avail_rows = []
for lg_country_code, g in q2_clean.groupby("lg_country_code"):
    avail_rows.append({
        "lg_country_code": lg_country_code,
        "meanHealthyAvailability": np.average(g["healthy_vendor_availability_pct"], weights=g["sessions"]),
    })
avail_by_code = {row["lg_country_code"]: row["meanHealthyAvailability"] for row in avail_rows}


def build_gmv_out(old_gmv_inputs):
    out = []
    for old_row in old_gmv_inputs:
        code = old_row["code"]
        new = gmv_by_code[code]
        out.append({
            "countryName": old_row["countryName"],
            "code": code,
            "avgMonthlySessions": new["avgMonthlySessions"],
            "sessionsCvPct": new["sessionsCvPct"],
            "fullYearSessionsCvPct": new["fullYearSessionsCvPct"],
            "meanOrdersPerConversion": new["meanOrdersPerConversion"],
            "aovEur": new["aovEur"],
        })
    return out


def patch_cvr_coef(cvr_coef):
    n_patched = 0
    for row in cvr_coef:
        code = row.get("code")
        if code in avail_by_code:
            row["meanHealthyAvailability"] = r(avail_by_code[code])
            n_patched += 1
    return n_patched


# ---------------------------------------------------------------------------
# Patch the standalone JSON bundle
# ---------------------------------------------------------------------------
with open(JSON_PATH) as f:
    bundle = json.load(f)

old_gmv = {row["code"]: row for row in bundle["gmvInputs"]}
new_gmv_out = build_gmv_out(bundle["gmvInputs"])
for row in new_gmv_out:
    old = old_gmv[row["code"]]
    print(
        f"[JSON] {row['code']}: avgMonthlySessions {old['avgMonthlySessions']:,.0f} -> "
        f"{row['avgMonthlySessions']:,.0f} ({row['avgMonthlySessions'] / old['avgMonthlySessions'] - 1:+.1%})"
    )
bundle["gmvInputs"] = new_gmv_out
n_patched_json = patch_cvr_coef(bundle["cvrCoef"])
print(f"[JSON] patched meanHealthyAvailability for {n_patched_json} countries")

with open(JSON_PATH, "w") as f:
    json.dump(bundle, f, separators=(",", ":"))
print(f"Saved: {JSON_PATH}")

# ---------------------------------------------------------------------------
# Patch the live HTML's embedded DATA blob (separate copy, must match)
# ---------------------------------------------------------------------------
html = HTML_PATH.read_text(encoding="utf-8")
m = re.search(r"const DATA\s*=\s*(\{.*?\});", html, re.S)
assert m, "could not find `const DATA = {...};` in the live HTML"
html_bundle = json.loads(m.group(1))

old_gmv_html = {row["code"]: row for row in html_bundle["gmvInputs"]}
new_gmv_out_html = build_gmv_out(html_bundle["gmvInputs"])
for row in new_gmv_out_html:
    old = old_gmv_html[row["code"]]
    print(
        f"[HTML] {row['code']}: avgMonthlySessions {old['avgMonthlySessions']:,.0f} -> "
        f"{row['avgMonthlySessions']:,.0f} ({row['avgMonthlySessions'] / old['avgMonthlySessions'] - 1:+.1%})"
    )
html_bundle["gmvInputs"] = new_gmv_out_html
n_patched_html = patch_cvr_coef(html_bundle["cvrCoef"])
print(f"[HTML] patched meanHealthyAvailability for {n_patched_html} countries")

new_data_literal = json.dumps(html_bundle, separators=(",", ":"))
new_html = html[: m.start()] + f"const DATA = {new_data_literal};" + html[m.end() :]
HTML_PATH.write_text(new_html, encoding="utf-8")
print(f"Saved: {HTML_PATH}")
