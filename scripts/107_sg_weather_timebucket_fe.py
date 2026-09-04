"""
Refinement of 106_sg_weather_vs_date_fe_zone_level.py: instead of collapsing each zone-day's 4
weather periods (Midnight-6am, 6am-Midday, Midday-6pm, 6pm-Midnight) into ONE majority-rule rain
flag, keep each period's own rain indicator as a separate regressor ("time-bucket FE"). Rationale:
a day that rains only during the 6pm-Midnight dinner-rush period is plausibly very different for
CVR than a day that rains only Midnight-6am while everyone's asleep -- the whole-day majority rule
in 105_/106_ can't distinguish these, and might be averaging away exactly the signal that matters.

Same zone->region mapping (from `SG Zone Region Mapping.csv`, same 2 assumptions flagged in
106_'s docstring: North-East->north, Far_east/Sg_south resolved by name) and same weather-overlap
subsample (238/365 days) as 106_, for a fair comparison against the same date-FE ceiling.

Run from project root (optimal_dt_gmv_roi_ip/):
    .venv/bin/python3 productions/v2/scripts/107_sg_weather_timebucket_fe.py
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

PANEL = "review/2026-07-17_dt_scenario_simulator/zone_day_panel_with_surge_multiplier.csv"
WEATHER = "SG Weather Store.csv"
ZONE_REGION_MAP = "SG Zone Region Mapping.csv"
PDT = "avg_promised_delivery_time_min"

RAIN_CODES = {"HG", "LR", "PS", "RA", "SH", "TL"}
PHASE_ORDER = ["Midnight to 6 am", "6 am to Midday", "Midday to 6 pm", "6 pm to Midnight"]

PANEL_TO_MAPPING_ZONE = {
    "Amk": "Ang Mo Kio", "Bukit timah": "Bukit Timah", "Bukitpanjang": "Bukit Panjang",
    "Geylang": "Geylang", "Jurong east": "Jurong East • Jurong Timur",
    "Jurongwest": "Jurong West • Jurong Barat", "Sengkang": "Sengkang", "Serangoon": "Serangoon",
    "Woodlands": "Woodlands", "Yishun": "Yishun",
}
PANEL_ZONE_DIRECT_WEATHER_REGION = {"Far_east": "east", "Sg_south": "south"}
URA_TO_WEATHER_REGION = {"Central": "central", "East": "east", "West": "west", "North": "north",
                          "North-East": "north"}


def build_zone_to_weather_region():
    zmap = pd.read_csv(ZONE_REGION_MAP).set_index("Zone")["Region"].to_dict()
    zone_region = {p: URA_TO_WEATHER_REGION[zmap[m]] for p, m in PANEL_TO_MAPPING_ZONE.items()}
    zone_region.update(PANEL_ZONE_DIRECT_WEATHER_REGION)
    return zone_region


def load_weather_timebucket():
    w = pd.read_csv(WEATHER, parse_dates=["issued_ts", "updated_ts", "period_start", "period_end"])
    w["dur_h"] = (w["period_end"] - w["period_start"]).dt.total_seconds() / 3600
    w = w[np.isclose(w["dur_h"], 6.0)].copy()
    w = w.sort_values("updated_ts").drop_duplicates(
        subset=["period_start", "period_end", "region"], keep="last"
    )
    w["is_rain"] = w["forecast_code"].isin(RAIN_CODES).astype(int)
    w["phase"] = w["period_text"].str.extract(r"^(.*) \d{2} \w{3}$")[0]
    assert set(w["phase"]) == set(PHASE_ORDER), f"unexpected phases: {set(w['phase']) - set(PHASE_ORDER)}"

    day_mon = w["period_text"].str.extract(r"(\d{2} \w{3})$")[0]
    candidate = pd.to_datetime(day_mon + " " + w["issued_ts"].dt.year.astype(str), format="%d %b %Y")
    delta_days = (candidate - w["issued_ts"].dt.tz_localize(None)).dt.days
    candidate = candidate.where(delta_days > -300, candidate + pd.DateOffset(years=1))
    candidate = candidate.where(delta_days < 300, candidate - pd.DateOffset(years=1))
    w["report_date"] = candidate.dt.tz_localize(None)

    wide = w.pivot_table(index=["report_date", "region"], columns="phase", values="is_rain",
                          aggfunc="max")  # aggfunc doesn't matter post-dedup; guards stray dupes
    wide = wide.reindex(columns=PHASE_ORDER)
    wide.columns = [f"rain_{c.replace(' ', '_')}" for c in wide.columns]
    wide = wide.reset_index()
    rain_cols = [c for c in wide.columns if c.startswith("rain_")]
    n_before = len(wide)
    wide = wide.dropna(subset=rain_cols)  # ~3% of region-days missing 1+ bucket; drop rather than assume
    print(f"  (dropped {n_before - len(wide)}/{n_before} region-days with 1+ missing time bucket)")
    return wide


def load_sg_panel():
    df = pd.read_csv(PANEL, parse_dates=["report_date"])
    return df[df["lg_country_code"] == "sg"].copy()


def fit_r2(df, extra_cols, weight_col="sessions", y_col="cvr"):
    zone_dum = pd.get_dummies(df["zone_name"], drop_first=True, dtype=float)
    cols = [df[[PDT, "pdt2"]], zone_dum]
    if extra_cols is not None:
        cols.append(extra_cols)
    X = pd.concat(cols, axis=1)
    Xc = sm.add_constant(X.to_numpy(dtype=float))
    y = df[y_col].to_numpy(dtype=float)
    w = df[weight_col].to_numpy(dtype=float)
    return sm.WLS(y, Xc, weights=w).fit()


def main():
    zone_region = build_zone_to_weather_region()
    weather = load_weather_timebucket()
    rain_cols = [c for c in weather.columns if c.startswith("rain_")]
    print(f"weather (time-bucket): {weather['report_date'].nunique()} days x "
          f"{weather['region'].nunique()} regions, columns: {rain_cols}")
    for c in rain_cols:
        print(f"  {c}: {weather[c].mean():.1%} of zone-day-regions raining in this bucket")
    print()

    sg = load_sg_panel()
    sg["pdt2"] = sg[PDT] ** 2
    sg["region"] = sg["zone_name"].map(zone_region)
    assert sg["region"].isna().sum() == 0

    merged = sg.merge(weather, on=["report_date", "region"], how="inner")
    n_days = merged["report_date"].nunique()
    print(f"overlap subsample: {len(merged)} zone-day rows, {n_days} unique days\n")

    fit_base = fit_r2(merged, None)
    fit_timebucket = fit_r2(merged, merged[rain_cols])
    date_dum = pd.get_dummies(merged["report_date"], drop_first=True, dtype=float)
    fit_datefe = fit_r2(merged, date_dum)

    print("Same-subsample R^2 comparison (pdt+pdt^2+zone FE as the common base):")
    print(f"  base:                                    r2={fit_base.rsquared:.4f}")
    print(f"  + 4 time-bucket rain dummies (zone-specific): r2={fit_timebucket.rsquared:.4f}  "
          f"(delta={fit_timebucket.rsquared - fit_base.rsquared:+.4f})")
    print(f"  + full date FE:                           r2={fit_datefe.rsquared:.4f}  "
          f"(delta={fit_datefe.rsquared - fit_base.rsquared:+.4f})")
    denom = fit_datefe.rsquared - fit_base.rsquared
    print(f"  -> time-bucket rain recovers "
          f"{(fit_timebucket.rsquared - fit_base.rsquared) / denom:.1%} of the date-FE R^2 jump\n")

    print("Per-bucket coefficients (from the +4-dummies fit):")
    n_zone_dum = merged["zone_name"].nunique() - 1
    start = 1 + 2 + n_zone_dum
    for i, c in enumerate(rain_cols):
        b = fit_timebucket.params[start + i]
        p = fit_timebucket.pvalues[start + i]
        print(f"  {c}: b={b:+.5f}  p={p:.4f}{'  *' if p < 0.05 else ''}")


if __name__ == "__main__":
    main()
