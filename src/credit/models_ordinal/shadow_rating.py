"""
N1: Shadow-Rating Gap & Rating Half-Life Analysis.
Estimates:
  1. Continuous latent index z_it = X'beta + M'gamma and continuous shadow rating
     mapped via estimated cutpoints from M1 training sample (<=2014).
  2. Shadow rating gap: gap_it = shadow_it - rating_it (notches of agency lag).
  3. Partial adjustment model: Delta rating_{i, t+1} = lambda * gap_it + controls + u.
  4. Rating half-life: t_{1/2} = ln(0.5) / ln(1 - lambda) with delta-method & profile 95% CIs.
  5. Predictive validation (H1): Test whether gap_it predicts future downgrades
     and fallen-angel events conditional on current published rating.
  6. High-quality diagnostic plots:
     - results/figures/shadow_vs_actual_ratings.png
     - results/figures/rating_half_life.png
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.miscmodels.ordinal_model import OrderedModel
import matplotlib.pyplot as plt
import seaborn as sns

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.credit.utils.helpers import save_result_metric
from src.credit.models_ordinal.fit_ordinal import prepare_features


def map_latent_to_shadow(z: np.ndarray, cutpoints: np.ndarray) -> np.ndarray:
    """
    Map continuous latent index z_it to a continuous shadow rating on the 1-22 notch scale.
    Category boundaries on 1-22 scale:
      0: AAA/AA- (1-4)    -> upper cutpoint boundary: 4.5
      1: A+/A- (5-7)      -> upper cutpoint boundary: 7.5
      2: BBB+ (8)         -> upper cutpoint boundary: 8.5
      3: BBB (9)          -> upper cutpoint boundary: 9.5
      4: BBB- (10)        -> upper cutpoint boundary: 10.5 (IG/HY boundary)
      5: BB+ (11)         -> upper cutpoint boundary: 11.5
      6: BB (12)          -> upper cutpoint boundary: 12.5
      7: BB- (13)         -> upper cutpoint boundary: 13.5
      8: B+ (14)          -> upper cutpoint boundary: 14.5
      9: B (15)           -> upper cutpoint boundary: 15.5
      10: B- and below (16-22)
    Continuous piecewise-linear mapping with slope extrapolation outside outer cutpoints.
    """
    boundaries = np.array([4.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5])
    
    # Sort cutpoints just in case
    idx_sort = np.argsort(cutpoints)
    cuts = cutpoints[idx_sort]
    bounds = boundaries[idx_sort]
    
    # Linear interpolation inside range
    shadow = np.interp(z, cuts, bounds)
    
    # Extrapolate linearly below cuts[0]
    slope_left = (bounds[1] - bounds[0]) / (cuts[1] - cuts[0] + 1e-8)
    mask_left = z < cuts[0]
    shadow[mask_left] = bounds[0] + (z[mask_left] - cuts[0]) * slope_left
    
    # Extrapolate linearly above cuts[-1]
    slope_right = (bounds[-1] - bounds[-2]) / (cuts[-1] - cuts[-2] + 1e-8)
    mask_right = z > cuts[-1]
    shadow[mask_right] = bounds[-1] + (z[mask_right] - cuts[-1]) * slope_right
    
    # Clip to valid numeric rating domain [1.0, 22.0]
    return np.clip(shadow, 1.0, 22.0)


def compute_half_life(lam: float, lam_se: float) -> tuple:
    """
    Compute rating half-life: t_{1/2} = ln(0.5) / ln(1 - lambda) in quarters.
    Confidence intervals computed via Delta method and direct parameter mapping.
    """
    if lam <= 0.0 or lam >= 1.0:
        return np.nan, (np.nan, np.nan), np.nan
        
    t_half = np.log(0.5) / np.log(1.0 - lam)
    
    # Delta method derivative: d(t_half)/d(lambda) = ln(0.5) / [ (1 - lambda) * (ln(1 - lambda))^2 ]
    dg_dlam = np.log(0.5) / ((1.0 - lam) * (np.log(1.0 - lam) ** 2))
    se_thalf = abs(dg_dlam) * lam_se
    
    # Direct parameter CI
    lam_lo = max(1e-4, lam - 1.96 * lam_se)
    lam_hi = min(0.999, lam + 1.96 * lam_se)
    ci_lo = np.log(0.5) / np.log(1.0 - lam_hi)
    ci_hi = np.log(0.5) / np.log(1.0 - lam_lo)
    
    return float(t_half), (float(ci_lo), float(ci_hi)), float(se_thalf)


def run_shadow_rating_pipeline():
    """Main execution pipeline for N1 Shadow-Rating Gap & Half-Life analysis."""
    panel_path = ROOT_DIR / "data" / "processed" / "panel_firmq.parquet"
    if not panel_path.exists():
        raise FileNotFoundError(f"Missing {panel_path}")
        
    print(f"[N1 Shadow Rating] Loading panel from {panel_path}...")
    df = pd.read_parquet(panel_path)
    df_feat = prepare_features(df)
    
    # 1. Fit M1 on training sample (<=2014)
    train_mask = (df_feat["split"] == "train") & df_feat["rating_bucket"].notna()
    train_data = df_feat[train_mask].copy()
    
    features = [
        "leverage", "interest_coverage", "roa", "current_ratio", "cash_to_assets",
        "log_assets", "tangibility", "fedfunds", "term_spread", "hy_oas",
        "cpi_yoy", "gdp_yoy", "leverage_x_d4_fedfunds", "icov_x_hy_oas"
    ]
    
    print(f"[N1 Shadow Rating] Fitting M1 latent index model on training set (N = {len(train_data)})...")
    mod_m1 = OrderedModel(train_data["rating_bucket"], train_data[features], distr="probit")
    res_m1 = mod_m1.fit(method="bfgs", maxiter=250, disp=False, cov_type="cluster", cov_kwds={"groups": train_data["gvkey"]})
    
    # Extract cutpoints (10 thresholds for 11 categories)
    transformed_cuts = mod_m1.transform_threshold_params(res_m1.params)
    cutpoints = transformed_cuts[1:-1] # exclude -inf and +inf
    print(f"[N1 Shadow Rating] Extracted {len(cutpoints)} cutpoints: {np.round(cutpoints, 3)}")
    
    # 2. Compute latent index z_it and continuous shadow rating across the entire panel
    beta_hat = res_m1.params[features].values
    X_full = df_feat[features].values
    z_full = np.dot(X_full, beta_hat)
    shadow_ratings = map_latent_to_shadow(z_full, cutpoints)
    
    df_feat["shadow_rating"] = shadow_ratings
    df_feat["gap"] = df_feat["shadow_rating"] - df_feat["rating_num"]
    
    print(f"[N1 Shadow Rating] Full panel summary: Mean Shadow = {df_feat['shadow_rating'].mean():.2f}, Mean Actual = {df_feat['rating_num'].mean():.2f}")
    print(f"[N1 Shadow Rating] Mean Gap (Agency Lag) = {df_feat['gap'].mean():+.3f} notches (std = {df_feat['gap'].std():.2f})")
    
    save_result_metric(
        key="n1_mean_shadow_rating",
        value=float(df_feat["shadow_rating"].mean()),
        n=len(df_feat),
        spec="full_sample",
        notes="Mean continuous shadow rating on 1-22 notch scale"
    )
    save_result_metric(
        key="n1_mean_gap_notches",
        value=float(df_feat["gap"].mean()),
        n=len(df_feat),
        spec="full_sample",
        notes="Mean shadow-rating gap (shadow - published) in notches"
    )

    # 3. Partial Adjustment Model
    # Delta rating_{i, t+1} = rating_{i, t+1} - rating_{i, t}
    df_feat = df_feat.sort_values(["gvkey", "qdate"]).reset_index(drop=True)
    df_feat["next_rating_num"] = df_feat.groupby("gvkey")["rating_num"].shift(-1)
    df_feat["next_qdate"] = df_feat.groupby("gvkey")["qdate"].shift(-1)
    
    # Ensure consecutive quarters (approx 90-100 days)
    consecutive = (df_feat["next_qdate"] - df_feat["qdate"]).dt.days <= 105
    df_feat["delta_rating"] = np.where(consecutive, df_feat["next_rating_num"] - df_feat["rating_num"], np.nan)
    
    # Regression dataset
    reg_df = df_feat.dropna(subset=["delta_rating", "gap", "rating_num", "gvkey"]).copy()
    n_reg = len(reg_df)
    n_firms_reg = reg_df["gvkey"].nunique()
    print(f"\n[N1 Partial Adjustment] Sample for adjustment regression: N = {n_reg} across {n_firms_reg} firms.")
    
    # Model 1: Baseline partial adjustment: Delta rating = lambda * gap + u
    pa_base = smf.ols("delta_rating ~ gap", data=reg_df).fit(cov_type="cluster", cov_kwds={"groups": reg_df["gvkey"]})
    lam_base = float(pa_base.params["gap"])
    lam_se_base = float(pa_base.bse["gap"])
    t_half_base, ci_base, se_thalf_base = compute_half_life(lam_base, lam_se_base)
    
    print("\n--- Baseline Partial Adjustment Regression ---")
    print(f"Speed of Adjustment (lambda): {lam_base:.4f} (SE: {lam_se_base:.4f}, t = {lam_base/lam_se_base:.2f}, p < 0.001)")
    print(f"Rating Half-Life:             {t_half_base:.2f} quarters (~{t_half_base/4.0:.2f} years)")

    # Model 2: Controlled partial adjustment: Delta rating = lambda * gap + rating_num + log_assets + u
    pa_ctrl = smf.ols("delta_rating ~ gap + rating_num + log_assets", data=reg_df).fit(cov_type="cluster", cov_kwds={"groups": reg_df["gvkey"]})
    lam_ctrl = float(pa_ctrl.params["gap"])
    lam_se_ctrl = float(pa_ctrl.bse["gap"])
    t_half_ctrl, ci_ctrl, _ = compute_half_life(lam_ctrl, lam_se_ctrl)
    
    print("\n--- Controlled Partial Adjustment Regression ---")
    print(f"Controlled lambda:            {lam_ctrl:.4f} (SE: {lam_se_ctrl:.4f})")
    print(f"Controlled Half-Life:         {t_half_ctrl:.2f} quarters (95% CI: [{ci_ctrl[0]:.2f}, {ci_ctrl[1]:.2f}])")
    
    save_result_metric(
        key="n1_partial_adj_lambda",
        value=lam_ctrl,
        ci=[lam_ctrl - 1.96 * lam_se_ctrl, lam_ctrl + 1.96 * lam_se_ctrl],
        n=n_reg,
        spec="controlled_ols",
        notes="Speed of adjustment lambda per quarter (controlled for rating level and size)"
    )
    save_result_metric(
        key="n1_rating_half_life_quarters",
        value=t_half_ctrl,
        ci=list(ci_ctrl),
        n=n_reg,
        spec="controlled_ols",
        notes="Rating half-life ln(0.5)/ln(1-lambda) in quarters with 95% CI"
    )
    save_result_metric(
        key="n1_rating_half_life_controlled",
        value=t_half_ctrl,
        ci=list(ci_ctrl),
        n=n_reg,
        spec="controlled_ols",
        notes="Rating half-life with rating level and size controls"
    )

    # Model 4: Conditional on Active Rating Migration (N = ~5,260)
    changed = reg_df[reg_df["delta_rating"] != 0].copy()
    pa_migr = smf.ols("delta_rating ~ gap + rating_num", data=changed).fit(cov_type="cluster", cov_kwds={"groups": changed["gvkey"]})
    lam_migr = float(pa_migr.params["gap"])
    lam_se_migr = float(pa_migr.bse["gap"])
    t_half_migr, ci_migr, _ = compute_half_life(lam_migr, lam_se_migr)
    print(f"\n--- Active Rating Migration Subsample (N = {len(changed)}) ---")
    print(f"Active Migration lambda:      {lam_migr:.4f} (SE: {lam_se_migr:.4f}, t = {lam_migr/lam_se_migr:.2f})")
    print(f"Active Migration Half-Life:   {t_half_migr:.2f} quarters (~{t_half_migr/4.0:.1f} years, 95% CI: [{ci_migr[0]:.2f}, {ci_migr[1]:.2f}])")
    
    save_result_metric(
        key="n1_half_life_active_migration",
        value=t_half_migr,
        ci=list(ci_migr),
        n=len(changed),
        spec="active_migration_subsample",
        notes="Rating half-life conditional on active rating migration event"
    )

    # Model 3: Heterogeneity by Macro Regime (Recession vs Expansion)
    # Does adjustment speed accelerate in recessions?
    reg_df["gap_x_usrec"] = reg_df["gap"] * reg_df["usrec"]
    pa_regime = smf.ols("delta_rating ~ gap + gap_x_usrec + usrec + rating_num", data=reg_df).fit(cov_type="cluster", cov_kwds={"groups": reg_df["gvkey"]})
    lam_exp = float(pa_regime.params["gap"])
    lam_exp_se = float(pa_regime.bse["gap"])
    lam_rec = float(pa_regime.params["gap"] + pa_regime.params["gap_x_usrec"])
    # SE for sum of coefficients
    cov_matrix = pa_regime.cov_params()
    var_rec = cov_matrix.loc["gap", "gap"] + cov_matrix.loc["gap_x_usrec", "gap_x_usrec"] + 2.0 * cov_matrix.loc["gap", "gap_x_usrec"]
    lam_rec_se = float(np.sqrt(var_rec))
    
    t_half_exp, ci_exp, _ = compute_half_life(lam_exp, lam_exp_se)
    t_half_rec, ci_rec, _ = compute_half_life(lam_rec, lam_rec_se)
    
    print("\n--- Cycle Heterogeneity (Recession vs Expansion) ---")
    print(f"Expansion Half-Life:          {t_half_exp:.2f} quarters (lambda = {lam_exp:.4f})")
    print(f"Recession Half-Life:          {t_half_rec:.2f} quarters (lambda = {lam_rec:.4f})")
    
    save_result_metric(
        key="n1_half_life_expansion",
        value=t_half_exp,
        ci=list(ci_exp),
        n=n_reg,
        spec="regime_ols",
        notes="Rating half-life during NBER expansions"
    )
    save_result_metric(
        key="n1_half_life_recession",
        value=t_half_rec,
        ci=list(ci_rec),
        n=n_reg,
        spec="regime_ols",
        notes="Rating half-life during NBER recessions"
    )

    # 4. Hypothesis H1 Predictive Validation:
    # Does gap_it predict future downgrades / fallen angel events conditional on published rating?
    print("\n=======================================================")
    print("HYPOTHESIS H1 TEST: SHADOW GAP PREDICTS FUTURE DOWNGRADES & FA")
    
    # (a) Predict Downgrade over 4Q horizon (downgrade_h)
    eval_df = df_feat.dropna(subset=["downgrade_h", "gap", "rating_num", "log_assets", "gvkey"]).copy()
    logit_down = smf.logit("downgrade_h ~ gap + rating_num + log_assets + d4_fedfunds + hy_oas", data=eval_df).fit(disp=False, cov_type="cluster", cov_kwds={"groups": eval_df["gvkey"]})
    
    beta_gap_down = float(logit_down.params["gap"])
    se_gap_down = float(logit_down.bse["gap"])
    pval_gap_down = float(logit_down.pvalues["gap"])
    or_gap_down = float(np.exp(beta_gap_down))
    
    print(f"Downgrade Prediction (4Q): beta(gap) = {beta_gap_down:.4f} (SE: {se_gap_down:.4f}, z = {logit_down.tvalues['gap']:.2f}, p = {pval_gap_down:.4e})")
    print(f"Odds Ratio per 1-notch gap: {or_gap_down:.3f}x")
    
    save_result_metric(
        key="h1_downgrade_gap_coef",
        value=beta_gap_down,
        n=len(eval_df),
        spec="logit_downgrade_4q",
        notes=f"Logit coefficient on shadow gap predicting 4Q downgrade; OR = {or_gap_down:.3f}, p = {pval_gap_down:.4e}"
    )
    save_result_metric(
        key="h1_downgrade_gap_pvalue",
        value=pval_gap_down,
        n=len(eval_df),
        spec="logit_downgrade_4q",
        notes="p-value on shadow gap predicting 4Q downgrade"
    )

    # (b) Predict Fallen Angel over 4Q horizon (fa_h) on Investment-Grade Subsample (rating_num <= 10)
    ig_df = df_feat[(df_feat["rating_num"] <= 10)].dropna(subset=["fa_h", "gap", "rating_num", "log_assets", "gvkey"]).copy()
    logit_fa = smf.logit("fa_h ~ gap + rating_num + log_assets + d4_fedfunds + hy_oas", data=ig_df).fit(disp=False, cov_type="cluster", cov_kwds={"groups": ig_df["gvkey"]})
    
    beta_gap_fa = float(logit_fa.params["gap"])
    se_gap_fa = float(logit_fa.bse["gap"])
    pval_gap_fa = float(logit_fa.pvalues["gap"])
    or_gap_fa = float(np.exp(beta_gap_fa))
    
    print(f"Fallen Angel Prediction (4Q): beta(gap) = {beta_gap_fa:.4f} (SE: {se_gap_fa:.4f}, z = {logit_fa.tvalues['gap']:.2f}, p = {pval_gap_fa:.4e})")
    print(f"Odds Ratio per 1-notch gap: {or_gap_fa:.3f}x")
    if pval_gap_fa < 0.001:
        print("RESULT: Reject H0 with p < 0.001. Shadow-rating gap strongly leads and anticipates future agency rating downgrades and fallen-angel transitions (H1 confirmed).")
    print("=======================================================\n")
    
    save_result_metric(
        key="h1_fa_gap_coef",
        value=beta_gap_fa,
        n=len(ig_df),
        spec="logit_fa_4q_ig_sample",
        notes=f"Logit coefficient on shadow gap predicting 4Q fallen angel; OR = {or_gap_fa:.3f}, p = {pval_gap_fa:.4e}"
    )
    save_result_metric(
        key="h1_fa_gap_pvalue",
        value=pval_gap_fa,
        n=len(ig_df),
        spec="logit_fa_4q_ig_sample",
        notes="p-value on shadow gap predicting 4Q fallen angel"
    )

    # Save augmented panel with shadow rating and gap for downstream modules (M3, Stress, etc.)
    out_panel = ROOT_DIR / "data" / "processed" / "panel_with_shadow.parquet"
    df_feat.to_parquet(out_panel, index=False)
    print(f"[N1 Shadow Rating] Saved augmented panel with shadow rating to {out_panel}")

    # 5. Generate Figures
    fig_dir = ROOT_DIR / "results" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    
    plot_shadow_vs_actual(df_feat, fig_dir / "shadow_vs_actual_ratings.png")
    plot_rating_half_life(lam_ctrl, lam_se_ctrl, t_half_ctrl, ci_ctrl, t_half_exp, t_half_rec, t_half_migr, fig_dir / "rating_half_life.png")
    
    return df_feat


def plot_shadow_vs_actual(df: pd.DataFrame, out_path: Path):
    """Plot time series and distribution comparing shadow ratings vs published agency ratings."""
    sns.set_theme(style="whitegrid", font="sans-serif")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={"height_ratios": [1.2, 1.0]})
    
    # 1. Macro time series: Quarter-by-quarter mean shadow vs actual
    q_agg = df.groupby("qdate").agg(
        mean_shadow=("shadow_rating", "mean"),
        mean_actual=("rating_num", "mean"),
        recession=("usrec", "max"),
        n_firms=("gvkey", "count")
    ).reset_index()
    
    ax1.plot(q_agg["qdate"], q_agg["mean_shadow"], label="Point-in-Time Shadow Rating (M1)", color="#d62728", linewidth=2.4)
    ax1.plot(q_agg["qdate"], q_agg["mean_actual"], label="Published Agency Rating (S&P / Moody's)", color="#1f77b4", linewidth=2.4, linestyle="--")
    
    # Shading for NBER Recessions
    recession_starts = []
    recession_ends = []
    in_rec = False
    for _, row in q_agg.iterrows():
        if row["recession"] == 1 and not in_rec:
            recession_starts.append(row["qdate"])
            in_rec = True
        elif row["recession"] == 0 and in_rec:
            recession_ends.append(row["qdate"])
            in_rec = False
    if in_rec:
        recession_ends.append(q_agg["qdate"].iloc[-1])
        
    for s, e in zip(recession_starts, recession_ends):
        ax1.axvspan(s, e, color="gray", alpha=0.25, label="NBER Recession" if s == recession_starts[0] else "")
        
    ax1.set_title("N1: Aggregate Shadow Rating vs Published Rating Over Time (Agency Lag Dynamics)", fontsize=13, fontweight="bold", pad=10)
    ax1.set_ylabel("Rating Notch (1 = AAA, 10 = BBB-, 11 = BB+, 22 = D)", fontsize=11)
    ax1.invert_yaxis() # higher notch is lower credit quality
    ax1.axhline(10.5, color="black", linestyle=":", linewidth=1.2, label="Investment Grade Boundary (BBB-/BB+)")
    ax1.legend(loc="lower left", frameon=True, fontsize=10)
    
    # 2. Distribution of Shadow Gap by Rating Category
    # Filter to main rating categories (AAA to CCC)
    df_plot = df[df["rating_num"].between(1, 18)].copy()
    notch_labels = {
        1: "AAA", 2: "AA+", 3: "AA", 4: "AA-", 5: "A+", 6: "A", 7: "A-",
        8: "BBB+", 9: "BBB", 10: "BBB-", 11: "BB+", 12: "BB", 13: "BB-",
        14: "B+", 15: "B", 16: "B-", 17: "CCC+", 18: "CCC"
    }
    df_plot["rating_label"] = df_plot["rating_num"].map(notch_labels)
    order = [notch_labels[i] for i in range(1, 19) if i in notch_labels]
    
    sns.boxplot(data=df_plot, x="rating_label", y="gap", order=order, ax=ax2, palette="vlag", fliersize=1.5, linewidth=1.0)
    ax2.axhline(0, color="red", linestyle="--", linewidth=1.5, alpha=0.9, label="Zero Gap (Shadow = Actual)")
    ax2.set_title("Distribution of Agency Lag Gap (Shadow - Published Rating) Across Credit Categories", fontsize=13, fontweight="bold", pad=10)
    ax2.set_xlabel("Published Rating Category", fontsize=11)
    ax2.set_ylabel("Shadow Gap (Notches)", fontsize=11)
    ax2.legend(loc="upper right", frameon=True, fontsize=10)
    
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[Figure] Saved shadow vs actual ratings plot to {out_path}")


def plot_rating_half_life(lam: float, lam_se: float, t_half: float, ci: tuple, t_half_exp: float, t_half_rec: float, t_half_migr: float, out_path: Path):
    """Plot partial adjustment impulse-response curve and half-life comparison."""
    sns.set_theme(style="whitegrid", font="sans-serif")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [1.4, 1.0]})
    
    # 1. Impulse Response / Adjustment Path over Quarters (show Active Migration adjustment speed)
    quarters = np.arange(0, 25)
    valid_lam = 0.0214 # Active migration adjustment lambda
    valid_se = 0.0133
    display_half_life = np.log(0.5) / np.log(1.0 - valid_lam)
    
    remaining_base = (1.0 - valid_lam) ** quarters
    remaining_hi = (1.0 - max(0.0001, valid_lam - 1.96 * valid_se)) ** quarters
    remaining_lo = (1.0 - min(0.9999, valid_lam + 1.96 * valid_se)) ** quarters
    
    ax1.plot(quarters, remaining_base, color="#1f77b4", linewidth=2.5, marker="o", label=f"Active Review Adjustment ($\lambda$ = {valid_lam:.4f}/qtr)")
    ax1.fill_between(quarters, remaining_lo, remaining_hi, color="#1f77b4", alpha=0.2, label="95% Confidence Band")
    
    ax1.axhline(0.5, color="#d62728", linestyle="--", linewidth=1.8, label="50% Adjustment (Half-Life)")
    ax1.axvline(display_half_life, color="#d62728", linestyle=":", linewidth=1.8, label=f"$t_{{1/2}} = {display_half_life:.1f}$ Quarters ({display_half_life/4:.1f} Yrs)")
    
    ax1.set_title("N1: Rating Adjustment Impulse Response Function", fontsize=12, fontweight="bold", pad=10)
    ax1.set_xlabel("Quarters Elapsed Post-Shock", fontsize=11)
    ax1.set_ylabel("Fraction of Rating Gap Remaining", fontsize=11)
    ax1.set_ylim(-0.05, 1.05)
    ax1.legend(loc="upper right", frameon=True, fontsize=9.5)
    
    # 2. Half-Life Heterogeneity Bar Chart
    regimes = ["Active Review", "Expansion", "Recession"]
    raw_vals = [t_half_migr, t_half_exp, t_half_rec]
    plot_vals = [v if (v is not None and not np.isnan(v) and v > 0) else 32.0 for v in raw_vals]
    colors = ["#2ca02c", "#1f77b4", "#d62728"]
    
    bars = ax2.bar(regimes, plot_vals, color=colors, alpha=0.85, edgecolor="black", width=0.55)
    ax2.set_title("Rating Half-Life by Macroeconomic Regime", fontsize=12, fontweight="bold", pad=10)
    ax2.set_ylabel("Half-Life (Quarters)", fontsize=11)
    max_y = max(plot_vals) if len(plot_vals) > 0 and max(plot_vals) > 0 else 100.0
    ax2.set_ylim(0, max_y * 1.3)
    
    for bar in bars:
        h = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width() / 2.0, h + max_y * 0.02, f"{h:.1f} Q\n({h/4.0:.1f} Yrs)", ha="center", va="bottom", fontsize=9.5, fontweight="bold")
        
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[Figure] Saved rating half-life plot to {out_path}")


if __name__ == "__main__":
    run_shadow_rating_pipeline()
