"""
Test whether SG's observed weather (NEA 4x-daily regional forecast text, user-supplied
`SG Weather Store.csv`) explains any of the date-FE R^2 jump found in the S0-S5 ladder
(script 103_sg_date_dow_fe_ladder.py: S3 (pdt+pdt^2+zone FE) r2=0.402 -> S4 (+date FE)
r2=0.845, the single biggest step in the whole ladder).

Known, accepted limitations (per user, 2026-09-04): this is a FORECAST feed, not observed
rainfall, issued 4x/day for 5 broad NEA regions (west/east/central/north/south) -- not by
the 12 named delivery zones in the CVR panel (no verified zone->region mapping exists, and
this project has been burned before by unverified name-based geo joins -- see MEMORY.md's
"City-name joins" caveat). So: aggregate to ONE country-day rain measure (equal-weight
across the 5 regions), don't try to assign zone-specific weather. Also: weather coverage
is 2025-11-01 to 2026-09-04, while the CVR panel is 2025-07-01 to 2026-06-30 -- restrict
every comparison to the OVERLAP window so weather's own R^2 contribution isn't confounded
with just having fewer training days.

Rain definition: user's own rule ("majority of the time in a day is raining -> call that day
raining"). NEA forecast_code taxonomy found in the data: rain-coded = HG/LR/PS/RA/SH/TL
(Heavy Thundery Showers w/ Gusty Winds, Light Rain, Passing Showers, Moderate Rain, Showers,
Thundery Showers); non-rain = CL/FA/FN/FW/PC/PN/WD (Cloudy/Fair/Partly Cloudy/Windy variants).
Each NEA period is nominally 6h (4/day); the raw feed has forecast REVISIONS (same period
re-issued as issued_ts advances) and some 12h "tonight" periods -- keep only 6h periods,
dedup revisions by taking the latest `updated_ts` per (period_start, period_end, region).

Data-quality note (found, not assumed): `period_start`'s DATE component has a real year-rollover
bug -- a period issued 2025-12-31 for "01 Jan" is stored with period_start='2025-01-01' (year not
incremented) instead of '2026-01-01'. Every `period_text` reliably ends in a literal "DD Mon" for
the actual calendar day (verified: 100% of rows match), so this script derives the day-bucket from
that text + issued_ts's year (with a rollover correction) instead of trusting period_start's date.

Two ways of testing "does rain explain the date FE", run on the SAME weather-overlap
subsample for a fair comparison:
  (1) Direct R^2 comparison: pdt+pdt^2+zone FE [+ rain] vs [+ date FE], same n.
  (2) Extract the actual per-date fixed-effect coefficients from the date-FE fit, then
      regress THOSE on the rain flag -- this isolates how much of the date-to-date
      heterogeneity (not the whole model's R^2) rain accounts for.

Run from project root (optimal_dt_gmv_roi_ip/):
    .venv/bin/python3 productions/v2/scripts/105_sg_weather_vs_date_fe.py
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm

PANEL = "review/2026-07-17_dt_scenario_simulator/zone_day_panel_with_surge_multiplier.csv"
WEATHER = "SG Weather Store.csv"
PDT = "avg_promised_delivery_time_min"

RAIN_CODES = {"HG", "LR", "PS", "RA", "SH", "TL"}


def load_weather_daily():
    w = pd.read_csv(WEATHER, parse_dates=["issued_ts", "updated_ts", "period_start", "period_end"])
    w["dur_h"] = (w["period_end"] - w["period_start"]).dt.total_seconds() / 3600
    w = w[np.isclose(w["dur_h"], 6.0)].copy()  # drop the overlapping 12h "tonight" periods

    # dedup forecast revisions: keep the latest updated_ts per (period_start, period_end, region)
    w = w.sort_values("updated_ts").drop_duplicates(
        subset=["period_start", "period_end", "region"], keep="last"
    )

    w["is_rain"] = w["forecast_code"].isin(RAIN_CODES).astype(int)

    # true calendar date, NOT period_start's own (buggy) date component -- see module docstring.
    # period_text always ends "DD Mon"; anchor the year to issued_ts, correcting for rollover.
    day_mon = w["period_text"].str.extract(r"(\d{2} \w{3})$")[0]
    candidate = pd.to_datetime(day_mon + " " + w["issued_ts"].dt.year.astype(str), format="%d %b %Y")
    delta_days = (candidate - w["issued_ts"].dt.tz_localize(None)).dt.days
    candidate = candidate.where(delta_days > -300, candidate + pd.DateOffset(years=1))
    candidate = candidate.where(delta_days < 300, candidate - pd.DateOffset(years=1))
    w["report_date"] = candidate

    # country-day: equal-weight across the 5 regions' periods (no verified zone<->region
    # mapping exists for this project's 12 named delivery zones -- see module docstring)
    daily = w.groupby("report_date")["is_rain"].agg(rain_frac="mean", n_periods="count").reset_index()
    daily["is_rain_day"] = (daily["rain_frac"] > 0.5).astype(int)  # user's own majority rule
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
    weather = load_weather_daily()
    print(f"weather: {len(weather)} days, {weather['report_date'].min().date()} .. "
          f"{weather['report_date'].max().date()}, rainy days (majority rule) = "
          f"{weather['is_rain_day'].sum()}/{len(weather)} "
          f"({weather['is_rain_day'].mean():.1%})")

    sg = load_sg_panel()
    sg["pdt2"] = sg[PDT] ** 2
    print(f"sg panel: {sg['report_date'].nunique()} days, "
          f"{sg['report_date'].min().date()} .. {sg['report_date'].max().date()}")

    weather["report_date"] = weather["report_date"].dt.tz_localize(None)
    merged = sg.merge(weather, on="report_date", how="inner")
    n_days = merged["report_date"].nunique()
    print(f"overlap subsample: {len(merged)} zone-day rows, {n_days} unique days "
          f"({n_days / sg['report_date'].nunique():.1%} of the SG panel's date range)\n")

    # --- (1) direct R^2 comparison, all on the SAME overlap subsample ---
    fit_base = fit_r2(merged, None)
    fit_rain_bin = fit_r2(merged, merged[["is_rain_day"]])
    fit_rain_frac = fit_r2(merged, merged[["rain_frac"]])

    date_dum = pd.get_dummies(merged["report_date"], drop_first=True, dtype=float)
    fit_datefe = fit_r2(merged, date_dum)

    print("Same-subsample R^2 comparison (pdt+pdt^2+zone FE as the common base):")
    print(f"  base (no weather, no date FE):      r2={fit_base.rsquared:.4f}")
    print(f"  + is_rain_day (binary, majority rule): r2={fit_rain_bin.rsquared:.4f}  "
          f"(delta={fit_rain_bin.rsquared - fit_base.rsquared:+.4f}, "
          f"p_rain={fit_rain_bin.pvalues[-1]:.4f})")
    print(f"  + rain_frac (continuous, share of day's periods raining): r2={fit_rain_frac.rsquared:.4f}  "
          f"(delta={fit_rain_frac.rsquared - fit_base.rsquared:+.4f}, "
          f"p_rain={fit_rain_frac.pvalues[-1]:.4f})")
    print(f"  + full date FE (one dummy per calendar day): r2={fit_datefe.rsquared:.4f}  "
          f"(delta={fit_datefe.rsquared - fit_base.rsquared:+.4f})")
    print(f"  -> rain (binary) recovers {(fit_rain_bin.rsquared - fit_base.rsquared) / (fit_datefe.rsquared - fit_base.rsquared):.1%} "
          f"of the date-FE R^2 jump on this subsample")
    print(f"  -> rain (continuous) recovers {(fit_rain_frac.rsquared - fit_base.rsquared) / (fit_datefe.rsquared - fit_base.rsquared):.1%} "
          f"of the date-FE R^2 jump on this subsample\n")

    # --- (2) regress the date-FE's own per-date effects on rain ---
    # extract each date's fixed-effect coefficient (relative to the dropped reference date),
    # then see how much of THAT date-to-date variance rain explains directly.
    date_col_names = date_dum.columns  # Timestamps, in the same order as the dummy columns
    n_zone_dum = merged["zone_name"].nunique() - 1
    date_coefs = fit_datefe.params[1 + 2 + n_zone_dum:]  # skip const, pdt, pdt2, zone dummies
    assert len(date_coefs) == len(date_col_names)
    date_effects = pd.DataFrame({"report_date": date_col_names, "date_effect": date_coefs})

    ref_date = sorted(set(merged["report_date"]) - set(date_col_names))[0]
    date_effects = pd.concat([
        date_effects,
        pd.DataFrame({"report_date": [ref_date], "date_effect": [0.0]}),
    ], ignore_index=True)

    de = date_effects.merge(weather, on="report_date", how="inner")
    Xc = sm.add_constant(de[["is_rain_day"]].to_numpy(dtype=float))
    fit_de = sm.OLS(de["date_effect"].to_numpy(dtype=float), Xc).fit()
    print("Regressing the date-FE's own per-date coefficients on the rain flag "
          "(unweighted OLS, one obs per calendar day):")
    print(f"  n_days={len(de)}  r2={fit_de.rsquared:.4f}  "
          f"b_rain={fit_de.params[1]:.5f} (p={fit_de.pvalues[1]:.4f})")
    print("  -> this is the cleanest read: how much of the DAY-TO-DAY heterogeneity that "
          "date FE captures is attributable to rain, isolated from the pdt/zone effects")


if __name__ == "__main__":
    main()
