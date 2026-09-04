"""
Reproduce the Singapore-only control-dropping ladder (S0-S5) built as a claude.ai artifact
(https://claude.ai/code/artifact/cea01574-f5f8-4602-9360-a5bea568a6a1), then extend it with a
FORWARD-USABLE version for productions/v2/dt_gmv_simulator.html.

Why extend at all: S4 ("+ date FE") and S5 ("+ zone x DOW FE") explain SG's CVR variance far
better (R^2 0.402 -> 0.845 -> 0.864) than the ops controls (mean_delay/surge/avail) did, and once
those FEs are in, b_pdt is no longer statistically significant (p=0.235, p=0.745) -- delivery time
has no measurable effect on SG's conversion once real demand-day variation is netted out. Per the
user (2026-09-04), that finding gets published as-is (S5's b_pdt/b_pdt2/r2, honestly flattened).

But "date FE" (one dummy per historical calendar date) cannot be evaluated for a future scenario
date -- there is no such thing as "today's date FE" for a hypothetical DT scenario. Per the user's
explicit ask, reconciled the SAME way production already collapses zone FE into one number
(zoneAdjustedIntercept = sessions-weighted average zone effect, never exposed as a live "pick a
zone" control): date FE is folded into the intercept as a sessions-weighted average effect across
the training window, not exposed as a live control. zone x DOW FE, in contrast, generalizes to any
future date (day-of-week is always knowable in advance) -- but the ladder's own DATA blob does not
expose the underlying per-DOW fixed-effect coefficients, only the pooled S5 curve. So the
forward-usable "day type" filter here is a SEPARATE weekday/weekend refit (matching this project's
existing wknd/wkdy convention from review/2026-08-25_stratified_cvr, dayofweek>=4 = Fri/Sat/Sun),
each with date FE folded into its own intercept the same way -- not a literal reproduction of S5's
joint zone x DOW estimate, which cannot be deployed live.

Run from project root (optimal_dt_gmv_roi_ip/):
    .venv/bin/python3 productions/v2/scripts/103_sg_date_dow_fe_ladder.py
"""
import json

import numpy as np
import pandas as pd
import statsmodels.api as sm

SOURCE = "review/2026-07-17_dt_scenario_simulator/zone_day_panel_with_surge_multiplier.csv"
PDT = "avg_promised_delivery_time_min"


def load_sg():
    df = pd.read_csv(SOURCE, parse_dates=["report_date"])
    df = df[df["lg_country_code"] == "sg"].copy()
    df["dow"] = df["report_date"].dt.dayofweek
    df["is_weekend"] = (df["dow"] >= 4).astype(int)  # Fri/Sat/Sun, project convention
    return df


def fit_wls(df, formula_rhs_cols, weight_col="sessions", y_col="cvr"):
    X = sm.add_constant(df[formula_rhs_cols].to_numpy(dtype=float))
    y = df[y_col].to_numpy(dtype=float)
    w = df[weight_col].to_numpy(dtype=float)
    return sm.WLS(y, X, weights=w).fit()


def ladder(df):
    """Reproduce S0-S5 exactly as in the artifact, to sanity-check this script is using the same
    data/methodology before trusting anything derived from it.

    Fit directly on RAW pdt/pdt^2 (not centered) so statsmodels' own p-value for the pdt column IS
    p_pdt directly -- centering-then-recombining b_pdt = b_u - 2*mean*b_u2 (first attempt) matches
    the artifact's b_pdt/b_pdt2/r2 exactly but NOT its p_pdt, because that recombination is a linear
    combination of two correlated coefficients (b_u, b_u2) and needs the joint covariance (delta
    method), not just b_u's own marginal p-value. Fitting on raw pdt sidesteps that entirely."""
    df = df.copy()
    df["pdt2"] = df[PDT] ** 2

    zone_dum = pd.get_dummies(df["zone_name"], drop_first=True, dtype=float)
    date_dum = pd.get_dummies(df["report_date"], drop_first=True, dtype=float)
    zone_dow_dum = pd.get_dummies(df["zone_name"].astype(str) + "|" + df["dow"].astype(str), drop_first=True, dtype=float)

    specs = {
        "S0": [PDT, "pdt2", "healthy_vendor_availability_pct", "mean_delay", "surge_multiplier"],
        "S1": [PDT, "pdt2", "healthy_vendor_availability_pct", "surge_multiplier"],
        "S2": [PDT, "pdt2", "healthy_vendor_availability_pct"],
        "S3": [PDT, "pdt2"],
    }
    results = {}
    for spec, cols in specs.items():
        Xc = sm.add_constant(pd.concat([df[cols], zone_dum], axis=1).to_numpy(dtype=float))
        fit = sm.WLS(df["cvr"].to_numpy(dtype=float), Xc, weights=df["sessions"].to_numpy(dtype=float)).fit()
        results[spec] = {"r2": fit.rsquared, "b_pdt": fit.params[1], "b_pdt2": fit.params[2], "p_pdt": fit.pvalues[1]}

    # S4: S3 + date FE
    X4 = pd.concat([df[[PDT, "pdt2"]], zone_dum, date_dum], axis=1)
    X4c = sm.add_constant(X4.to_numpy(dtype=float))
    fit4 = sm.WLS(df["cvr"].to_numpy(dtype=float), X4c, weights=df["sessions"].to_numpy(dtype=float)).fit()
    results["S4"] = {"r2": fit4.rsquared, "b_pdt": fit4.params[1], "b_pdt2": fit4.params[2], "p_pdt": fit4.pvalues[1]}

    # S5: S4 + zone x DOW FE
    X5 = pd.concat([df[[PDT, "pdt2"]], zone_dum, date_dum, zone_dow_dum], axis=1)
    X5c = sm.add_constant(X5.to_numpy(dtype=float))
    fit5 = sm.WLS(df["cvr"].to_numpy(dtype=float), X5c, weights=df["sessions"].to_numpy(dtype=float)).fit()
    results["S5"] = {"r2": fit5.rsquared, "b_pdt": fit5.params[1], "b_pdt2": fit5.params[2], "p_pdt": fit5.pvalues[1]}

    mean_pdt = df[PDT].mean()
    return results, mean_pdt


def fit_forward_usable(sub, label):
    """S5-methodology (pdt+pdt^2+zone FE+date FE), but folds zone FE AND date FE into ONE
    intercept -- the same treatment production already gives zone FE via zoneAdjustedIntercept
    (a single sessions-weighted number, never a live "pick a zone" control). date FE can't be
    evaluated for a future scenario date either, so it gets the identical treatment: baked into
    the constant as its sessions-weighted average effect over the training window, not exposed.

    zone x DOW FE is dropped here on purpose -- `sub` is already pre-split to one day type
    (weekday-only or weekend-only), so within-subset zone FE + date FE is the whole story; no
    separate DOW term is needed once the sample itself is restricted to one day type."""
    zone_dum = pd.get_dummies(sub["zone_name"], drop_first=True, dtype=float)
    date_dum = pd.get_dummies(sub["report_date"], drop_first=True, dtype=float)
    X = pd.concat([sub[[PDT, "pdt2"]], zone_dum, date_dum], axis=1)
    Xc = sm.add_constant(X.to_numpy(dtype=float))
    y = sub["cvr"].to_numpy(dtype=float)
    w = sub["sessions"].to_numpy(dtype=float)
    fit = sm.WLS(y, Xc, weights=w).fit()
    b_pdt, b_pdt2 = fit.params[1], fit.params[2]
    p_pdt, p_pdt2 = fit.pvalues[1], fit.pvalues[2]

    pdt = sub[PDT].to_numpy(dtype=float)
    residual_intercept = fit.fittedvalues - b_pdt * pdt - b_pdt2 * pdt**2
    intercept = float(np.average(residual_intercept, weights=w))

    vertex = -b_pdt / (2 * b_pdt2) if b_pdt2 != 0 else None
    print(f"{label}: n={len(sub)}  r2={fit.rsquared:.6f}  intercept={intercept:.6f}  "
          f"b_pdt={b_pdt:.6f} (p={p_pdt:.4f})  b_pdt2={b_pdt2:.8f} (p={p_pdt2:.4f})  vertex={vertex}")
    return {
        "n": len(sub), "r2": fit.rsquared, "intercept": intercept,
        "b_pdt": b_pdt, "p_pdt": p_pdt, "b_pdt2": b_pdt2, "p_pdt2": p_pdt2,
        "pdt_min": float(pdt.min()), "pdt_max": float(pdt.max()),
    }


if __name__ == "__main__":
    df = load_sg()
    print(f"n={len(df)}, zones={df['zone_name'].nunique()}")
    results, mean_pdt = ladder(df)
    print(f"mean_pdt={mean_pdt:.4f}")
    for spec, r in results.items():
        print(f"{spec}: r2={r['r2']:.6f}  b_pdt={r['b_pdt']:.6f}  b_pdt2={r['b_pdt2']:.6f}  p_pdt={r['p_pdt']:.6f}")

    print("\n--- forward-usable (zone FE + date FE folded into ONE intercept each) ---")
    s5 = results["S5"]
    df["pdt2"] = df[PDT] ** 2
    pdt_all = df[PDT].to_numpy(dtype=float)
    # Same fold-in treatment applied to the pooled S5 spec, to get its own deployable intercept
    # (zone FE + date FE + zone x DOW FE all folded, since bPdt/bPdt2 are already the pooled S5
    # estimate straight from the ladder reproduction above).
    zone_dum = pd.get_dummies(df["zone_name"], drop_first=True, dtype=float)
    date_dum = pd.get_dummies(df["report_date"], drop_first=True, dtype=float)
    zone_dow_dum = pd.get_dummies(df["zone_name"].astype(str) + "|" + df["dow"].astype(str), drop_first=True, dtype=float)
    X5 = pd.concat([df[[PDT, "pdt2"]], zone_dum, date_dum, zone_dow_dum], axis=1)
    X5c = sm.add_constant(X5.to_numpy(dtype=float))
    fit5 = sm.WLS(df["cvr"].to_numpy(dtype=float), X5c, weights=df["sessions"].to_numpy(dtype=float)).fit()
    resid_intercept = fit5.fittedvalues - s5["b_pdt"] * pdt_all - s5["b_pdt2"] * pdt_all**2
    pooled_intercept = float(np.average(resid_intercept, weights=df["sessions"].to_numpy(dtype=float)))
    print(f"POOLED (S5, all day types): r2={s5['r2']:.6f}  intercept={pooled_intercept:.6f}  "
          f"b_pdt={s5['b_pdt']:.6f} (p={s5['p_pdt']:.4f})  b_pdt2={s5['b_pdt2']:.8f}  "
          f"pdt_range=[{pdt_all.min():.2f}, {pdt_all.max():.2f}]")

    wkdy = fit_forward_usable(df[df["is_weekend"] == 0], "WEEKDAY")
    wknd = fit_forward_usable(df[df["is_weekend"] == 1], "WEEKEND")

    out = {
        "pooled": {"r2": s5["r2"], "intercept": pooled_intercept, "b_pdt": s5["b_pdt"], "p_pdt": s5["p_pdt"],
                   "b_pdt2": s5["b_pdt2"], "pdt_min": float(pdt_all.min()), "pdt_max": float(pdt_all.max())},
        "weekday": wkdy,
        "weekend": wknd,
    }
    out_path = "productions/v2/data/sg_date_dow_fe_cvrCoef.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {out_path}")
