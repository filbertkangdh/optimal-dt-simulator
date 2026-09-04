"""
Zone-level rerun of 105_sg_weather_vs_date_fe.py, using the user-supplied
`SG Zone Region Mapping.csv` (project root) to join each of the CVR panel's 12 named zones to a
region, instead of 105's single SG-wide rain number repeated for every zone. This lets zone-day
rain vary by zone-day (not just by day), which is the right grain to compete against the date-FE
ladder's own zone-day fit.

Two name-resolution issues in the mapping file, both handled explicitly below (not silently):

1. **Region taxonomy mismatch**: the mapping CSV uses URA's 5 Planning Regions (Central, East,
   North, North-East, West -- no "South"); the weather file uses NEA's 5 nowcast regions (central,
   east, north, south, west -- no "North-East"). These are two different systems. Crosswalk used
   here: North-East -> north (nearest cardinal bucket under a simple 4-point-compass collapse --
   this is an ASSUMPTION, not a verified NEA boundary, and affects Amk/Sengkang/Serangoon).
2. **2 of the panel's 12 zone names don't appear verbatim in the mapping file** (`Far_east`,
   `Sg_south` are delivery-zone names, not URA planning-area names). Resolved by literal reading
   of the name against the weather file's OWN region set directly (Far_east -> east, Sg_south ->
   south) rather than routing through the URA mapping (which has no "South" entry to route
   Sg_south through anyway).

Run from project root (optimal_dt_gmv_roi_ip/):
    .venv/bin/python3 productions/v2/scripts/106_sg_weather_vs_date_fe_zone_level.py
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

PANEL = "review/2026-07-17_dt_scenario_simulator/zone_day_panel_with_surge_multiplier.csv"
WEATHER = "SG Weather Store.csv"
ZONE_REGION_MAP = "SG Zone Region Mapping.csv"
PDT = "avg_promised_delivery_time_min"

RAIN_CODES = {"HG", "LR", "PS", "RA", "SH", "TL"}

# panel zone_name -> mapping-file Zone (exact name match after normalizing case/diacritics)
PANEL_TO_MAPPING_ZONE = {
    "Amk": "Ang Mo Kio",
    "Bukit timah": "Bukit Timah",
    "Bukitpanjang": "Bukit Panjang",
    "Geylang": "Geylang",
    "Jurong east": "Jurong East • Jurong Timur",
    "Jurongwest": "Jurong West • Jurong Barat",
    "Sengkang": "Sengkang",
    "Serangoon": "Serangoon",
    "Woodlands": "Woodlands",
    "Yishun": "Yishun",
}
# not in the mapping file at all -- resolved by literal name reading against the WEATHER file's
# own region set (see docstring point 2)
PANEL_ZONE_DIRECT_WEATHER_REGION = {
    "Far_east": "east",
    "Sg_south": "south",
}
# URA region -> NEA weather region (see docstring point 1; North-East->north is an assumption)
URA_TO_WEATHER_REGION = {
    "Central": "central",
    "East": "east",
    "West": "west",
    "North": "north",
    "North-East": "north",
}


def build_zone_to_weather_region():
    zmap = pd.read_csv(ZONE_REGION_MAP).set_index("Zone")["Region"].to_dict()
    zone_region = {}
    for panel_zone, mapping_name in PANEL_TO_MAPPING_ZONE.items():
        ura_region = zmap[mapping_name]
        zone_region[panel_zone] = URA_TO_WEATHER_REGION[ura_region]
    zone_region.update(PANEL_ZONE_DIRECT_WEATHER_REGION)
    return zone_region


def load_weather_by_region():
    w = pd.read_csv(WEATHER, parse_dates=["issued_ts", "updated_ts", "period_start", "period_end"])
    w["dur_h"] = (w["period_end"] - w["period_start"]).dt.total_seconds() / 3600
    w = w[np.isclose(w["dur_h"], 6.0)].copy()
    w = w.sort_values("updated_ts").drop_duplicates(
        subset=["period_start", "period_end", "region"], keep="last"
    )
    w["is_rain"] = w["forecast_code"].isin(RAIN_CODES).astype(int)

    day_mon = w["period_text"].str.extract(r"(\d{2} \w{3})$")[0]
    candidate = pd.to_datetime(day_mon + " " + w["issued_ts"].dt.year.astype(str), format="%d %b %Y")
    delta_days = (candidate - w["issued_ts"].dt.tz_localize(None)).dt.days
    candidate = candidate.where(delta_days > -300, candidate + pd.DateOffset(years=1))
    candidate = candidate.where(delta_days < 300, candidate - pd.DateOffset(years=1))
    w["report_date"] = candidate.dt.tz_localize(None)

    daily = w.groupby(["report_date", "region"])["is_rain"].agg(rain_frac="mean", n_periods="count").reset_index()
    daily["is_rain_day"] = (daily["rain_frac"] > 0.5).astype(int)
    return daily


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
    print("zone -> weather region:")
    for z, r in zone_region.items():
        flag = " (URA North-East->north assumption)" if z in ("Amk", "Sengkang", "Serangoon") else \
               " (name-based, not in mapping file)" if z in PANEL_ZONE_DIRECT_WEATHER_REGION else ""
        print(f"  {z:14s} -> {r}{flag}")
    print()

    weather = load_weather_by_region()
    print(f"weather: {weather['report_date'].nunique()} days x {weather['region'].nunique()} regions, "
          f"{weather['report_date'].min().date()} .. {weather['report_date'].max().date()}\n")

    sg = load_sg_panel()
    sg["pdt2"] = sg[PDT] ** 2
    sg["region"] = sg["zone_name"].map(zone_region)
    assert sg["region"].isna().sum() == 0, "unmapped zone found"

    merged = sg.merge(weather, on=["report_date", "region"], how="inner")
    n_days = merged["report_date"].nunique()
    print(f"overlap subsample: {len(merged)} zone-day rows, {n_days} unique days "
          f"({n_days / sg['report_date'].nunique():.1%} of the SG panel's date range)\n")

    print("Zone-level rainy-day rate (majority rule, on overlap window):")
    print(merged.groupby("zone_name")["is_rain_day"].mean().sort_values(ascending=False).to_string())
    print()

    fit_base = fit_r2(merged, None)
    fit_rain_bin = fit_r2(merged, merged[["is_rain_day"]])
    fit_rain_frac = fit_r2(merged, merged[["rain_frac"]])

    date_dum = pd.get_dummies(merged["report_date"], drop_first=True, dtype=float)
    fit_datefe = fit_r2(merged, date_dum)

    print("Same-subsample R^2 comparison (pdt+pdt^2+zone FE as the common base), "
          "NOW using zone-specific (not country-wide) rain:")
    print(f"  base:                                 r2={fit_base.rsquared:.4f}")
    print(f"  + is_rain_day (zone-specific, binary): r2={fit_rain_bin.rsquared:.4f}  "
          f"(delta={fit_rain_bin.rsquared - fit_base.rsquared:+.4f}, "
          f"p_rain={fit_rain_bin.pvalues[-1]:.4f})")
    print(f"  + rain_frac (zone-specific, continuous): r2={fit_rain_frac.rsquared:.4f}  "
          f"(delta={fit_rain_frac.rsquared - fit_base.rsquared:+.4f}, "
          f"p_rain={fit_rain_frac.pvalues[-1]:.4f})")
    print(f"  + full date FE:                        r2={fit_datefe.rsquared:.4f}  "
          f"(delta={fit_datefe.rsquared - fit_base.rsquared:+.4f})")
    denom = fit_datefe.rsquared - fit_base.rsquared
    print(f"  -> zone-specific rain (binary) recovers "
          f"{(fit_rain_bin.rsquared - fit_base.rsquared) / denom:.1%} of the date-FE R^2 jump")
    print(f"  -> zone-specific rain (continuous) recovers "
          f"{(fit_rain_frac.rsquared - fit_base.rsquared) / denom:.1%} of the date-FE R^2 jump")


if __name__ == "__main__":
    main()
