"""
M1: Kaplan-Urwitz Ordered Probit and Ordered Logit Model.
Estimates credit rating levels / buckets across a specification ladder:
  (a) Firm fundamentals only
  (b) Macro only
  (c) Firm + Macro combined
  (d) Firm + Macro + Key interactions
  (e) Spec (d) + Sector fixed effects (FF12)

Computes McFadden pseudo-R2, Likelihood Ratio test for incremental value
of macro block (H2), and Average Marginal Effects (AME) on P(IG), P(BBB-), P(BB+).
All standard errors clustered by firm (gvkey).
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns
from statsmodels.miscmodels.ordinal_model import OrderedModel

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.credit.utils.helpers import save_result_metric


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare feature matrix with interaction terms and sector dummies."""
    data = df.copy()
    
    # Interactions: leverage * d4_fedfunds, interest_coverage * hy_oas
    data["leverage_x_d4_fedfunds"] = data["leverage"] * data["d4_fedfunds"]
    data["icov_x_hy_oas"] = data["interest_coverage"] * data["hy_oas"]
    
    # One-hot encode sector_ff12 (drop 'Other' or first as reference)
    if "sector_ff12" in data.columns:
        sector_dummies = pd.get_dummies(data["sector_ff12"], prefix="sec", drop_first=True, dtype=float)
        data = pd.concat([data, sector_dummies], axis=1)
        
    return data


def compute_mcfadden_pseudo_r2(llf_model: float, y: pd.Series) -> float:
    """
    McFadden pseudo-R2 = 1 - (llf_model / llf_null).
    Null model has only cutoffs / category proportions: llf_null = sum(n_j * ln(n_j / N)).
    """
    counts = y.value_counts().values
    n = len(y)
    p_null = counts / n
    llf_null = np.sum(counts * np.log(p_null))
    return float(1.0 - (llf_model / llf_null))


def compute_ame(model_res, model_cls, X: pd.DataFrame, target_cols: list, eps: float = 1e-4) -> dict:
    """
    Compute Average Marginal Effects (AME) using two-sided finite difference.
    Evaluates impact of each predictor on:
      - P(IG): Bucket <= 4
      - P(BBB-): Bucket == 4
      - P(BB+): Bucket == 5
    """
    ame_dict = {}
    
    base_probs = model_res.predict(X)
    p_ig_base = base_probs.iloc[:, :5].sum(axis=1) if base_probs.shape[1] >= 5 else base_probs.iloc[:, 0]
    p_bbb_minus_base = base_probs.iloc[:, 4] if base_probs.shape[1] > 4 else 0.0
    p_bb_plus_base = base_probs.iloc[:, 5] if base_probs.shape[1] > 5 else 0.0
    
    for col in target_cols:
        if col not in X.columns:
            continue
        X_plus = X.copy()
        X_minus = X.copy()
        
        X_plus[col] += eps
        X_minus[col] -= eps
        
        # Propagate changes to interactions if present
        if col == "leverage" and "leverage_x_d4_fedfunds" in X.columns:
            X_plus["leverage_x_d4_fedfunds"] = X_plus["leverage"] * X_plus["d4_fedfunds"] if "d4_fedfunds" in X_plus.columns else X_plus["leverage_x_d4_fedfunds"]
            X_minus["leverage_x_d4_fedfunds"] = X_minus["leverage"] * X_minus["d4_fedfunds"] if "d4_fedfunds" in X_minus.columns else X_minus["leverage_x_d4_fedfunds"]
        if col == "d4_fedfunds" and "leverage_x_d4_fedfunds" in X.columns:
            X_plus["leverage_x_d4_fedfunds"] = X_plus["leverage"] * X_plus["d4_fedfunds"] if "leverage" in X_plus.columns else X_plus["leverage_x_d4_fedfunds"]
            X_minus["leverage_x_d4_fedfunds"] = X_minus["leverage"] * X_minus["d4_fedfunds"] if "leverage" in X_minus.columns else X_minus["leverage_x_d4_fedfunds"]
        if col == "interest_coverage" and "icov_x_hy_oas" in X.columns:
            X_plus["icov_x_hy_oas"] = X_plus["interest_coverage"] * X_plus["hy_oas"] if "hy_oas" in X_plus.columns else X_plus["icov_x_hy_oas"]
            X_minus["icov_x_hy_oas"] = X_minus["interest_coverage"] * X_minus["hy_oas"] if "hy_oas" in X_minus.columns else X_minus["icov_x_hy_oas"]
        if col == "hy_oas" and "icov_x_hy_oas" in X.columns:
            X_plus["icov_x_hy_oas"] = X_plus["interest_coverage"] * X_plus["hy_oas"] if "interest_coverage" in X_plus.columns else X_plus["icov_x_hy_oas"]
            X_minus["icov_x_hy_oas"] = X_minus["interest_coverage"] * X_minus["hy_oas"] if "interest_coverage" in X_minus.columns else X_minus["icov_x_hy_oas"]
            
        prob_plus = model_res.predict(X_plus)
        prob_minus = model_res.predict(X_minus)
        
        p_ig_plus = prob_plus.iloc[:, :5].sum(axis=1) if prob_plus.shape[1] >= 5 else prob_plus.iloc[:, 0]
        p_ig_minus = prob_minus.iloc[:, :5].sum(axis=1) if prob_minus.shape[1] >= 5 else prob_minus.iloc[:, 0]
        ame_ig = float(np.mean((p_ig_plus - p_ig_minus) / (2.0 * eps)))
        
        p_bbb_plus = prob_plus.iloc[:, 4] if prob_plus.shape[1] > 4 else 0.0
        p_bbb_minus = prob_minus.iloc[:, 4] if prob_minus.shape[1] > 4 else 0.0
        ame_bbb_m = float(np.mean((p_bbb_plus - p_bbb_minus) / (2.0 * eps)))
        
        p_bb_plus_hi = prob_plus.iloc[:, 5] if prob_plus.shape[1] > 5 else 0.0
        p_bb_plus_lo = prob_minus.iloc[:, 5] if prob_minus.shape[1] > 5 else 0.0
        ame_bb_p = float(np.mean((p_bb_plus_hi - p_bb_plus_lo) / (2.0 * eps)))
        
        ame_dict[col] = {
            "ame_P_IG": ame_ig,
            "ame_P_BBB_minus": ame_bbb_m,
            "ame_P_BB_plus": ame_bb_p
        }
        
    return ame_dict


def run_specifications():
    """Execute complete M1 specification ladder and hypothesis testing."""
    panel_path = ROOT_DIR / "data" / "processed" / "panel_firmq.csv"
    if not panel_path.exists():
        raise FileNotFoundError(f"Missing {panel_path}")
        
    print(f"[M1 Ordinal] Loading panel from {panel_path}...")
    df = pd.read_csv(panel_path, parse_dates=["qdate"])
    df_feat = prepare_features(df)
    
    # Restrict to train split (2002-2014) for core econometric estimation
    train_mask = (df_feat["split"] == "train") & df_feat["rating_bucket"].notna()
    train_data = df_feat[train_mask].copy()
    n_train = len(train_data)
    n_clusters = train_data["gvkey"].nunique()
    print(f"[M1 Ordinal] Training sample: N = {n_train} firm-quarters across {n_clusters} unique firms.")
    
    # Variable blocks
    firm_vars = [
        "leverage", "interest_coverage", "roa",
        "current_ratio", "cash_to_assets", "log_assets", "tangibility"
    ]
    macro_vars = [
        "fedfunds", "term_spread", "hy_oas", "cpi_yoy", "gdp_yoy"
    ]
    interaction_vars = [
        "leverage_x_d4_fedfunds", "icov_x_hy_oas"
    ]
    sector_vars = [c for c in df_feat.columns if c.startswith("sec_")]
    
    specifications = {
        "spec_a_firm_only": firm_vars,
        "spec_b_macro_only": macro_vars,
        "spec_c_combined": firm_vars + macro_vars,
        "spec_d_interactions": firm_vars + macro_vars + interaction_vars,
        "spec_e_sector_fe": firm_vars + macro_vars + interaction_vars + sector_vars,
    }
    
    results_summary = {}
    fitted_models = {}
    
    print("\n[M1 Ordinal] Fitting Probit Specification Ladder with Cluster-Robust Covariance...")
    for spec_name, cols in specifications.items():
        print(f"\n--- Estimating {spec_name} (k = {len(cols)}) ---")
        X_train = train_data[cols]
        y_train = train_data["rating_bucket"]
        
        mod = OrderedModel(y_train, X_train, distr="probit")
        # Fit with BFGS and cluster standard errors by gvkey
        res = mod.fit(method="bfgs", maxiter=250, disp=False, cov_type="cluster", cov_kwds={"groups": train_data["gvkey"]})
        
        llf = float(res.llf)
        aic = float(res.aic)
        bic = float(res.bic)
        pseudo_r2 = compute_mcfadden_pseudo_r2(llf, y_train)
        
        print(f"Log-Likelihood: {llf:.2f} | Pseudo-R2: {pseudo_r2:.4f} | AIC: {aic:.1f} | BIC: {bic:.1f}")
        
        fitted_models[spec_name] = (mod, res, cols)
        results_summary[spec_name] = {
            "llf": llf,
            "pseudo_r2": pseudo_r2,
            "aic": aic,
            "bic": bic,
            "nobs": n_train,
            "k_vars": len(cols),
            "params": res.params.to_dict(),
            "bse": res.bse.to_dict(),
            "pvalues": res.pvalues.to_dict()
        }
        
        # Save metric to JSON registry
        save_result_metric(
            key=f"m1_pseudo_r2_{spec_name}",
            value=pseudo_r2,
            n=n_train,
            spec=spec_name,
            notes=f"McFadden pseudo-R2 for M1 Ordered Probit {spec_name}"
        )
        save_result_metric(
            key=f"m1_llf_{spec_name}",
            value=llf,
            n=n_train,
            spec=spec_name,
            notes=f"Log-Likelihood for M1 Ordered Probit {spec_name}"
        )

    # Hypothesis H2: Likelihood Ratio Test for incremental value of macro block
    # Comparing Spec C (Combined) vs Spec A (Firm only)
    llf_firm = results_summary["spec_a_firm_only"]["llf"]
    llf_comb = results_summary["spec_c_combined"]["llf"]
    df_macro = len(macro_vars)
    lr_stat_h2 = 2.0 * (llf_comb - llf_firm)
    p_val_h2 = float(1.0 - stats.chi2.cdf(lr_stat_h2, df_macro))
    
    print("\n=======================================================")
    print("HYPOTHESIS H2 TEST: INCREMENTAL VALUE OF MACRO BLOCK")
    print(f"Spec A (Firm Only) Log-Likelihood:     {llf_firm:.2f}")
    print(f"Spec C (Firm + Macro) Log-Likelihood: {llf_comb:.2f}")
    print(f"Likelihood Ratio Statistic (LR):      {lr_stat_h2:.2f}")
    print(f"Degrees of Freedom:                   {df_macro}")
    print(f"p-value:                              {p_val_h2:.4e}")
    if p_val_h2 < 0.001:
        print("RESULT: Reject H0 with p < 0.001. Macro block provides highly significant incremental explanatory power (H2 confirmed).")
    print("=======================================================\n")
    
    save_result_metric(
        key="m1_h2_lr_stat",
        value=lr_stat_h2,
        n=n_train,
        spec="spec_c_vs_spec_a",
        notes=f"LR test stat for incremental macro block; df={df_macro}, p={p_val_h2:.4e}"
    )
    save_result_metric(
        key="m1_h2_pvalue",
        value=p_val_h2,
        n=n_train,
        spec="spec_c_vs_spec_a",
        notes="p-value for H2 LR test"
    )

    # Ordered Logit comparison on Spec C
    print("[M1 Ordinal] Fitting Ordered Logit benchmark on Spec C (Combined)...")
    mod_logit = OrderedModel(train_data["rating_bucket"], train_data[specifications["spec_c_combined"]], distr="logit")
    res_logit = mod_logit.fit(method="bfgs", maxiter=250, disp=False, cov_type="cluster", cov_kwds={"groups": train_data["gvkey"]})
    pseudo_r2_logit = compute_mcfadden_pseudo_r2(float(res_logit.llf), train_data["rating_bucket"])
    print(f"Ordered Logit Spec C Log-Likelihood: {res_logit.llf:.2f} | Pseudo-R2: {pseudo_r2_logit:.4f}")
    
    save_result_metric(
        key="m1_pseudo_r2_spec_c_logit",
        value=pseudo_r2_logit,
        n=n_train,
        spec="spec_c_combined_logit",
        notes="McFadden pseudo-R2 for M1 Ordered Logit benchmark"
    )

    # Average Marginal Effects (AME) on Spec D (Interactions)
    print("\n[M1 Ordinal] Computing Average Marginal Effects (AME) for Key Predictors on Spec D...")
    mod_d, res_d, cols_d = fitted_models["spec_d_interactions"]
    ame_vars = ["hy_oas", "fedfunds", "term_spread", "gdp_yoy", "cpi_yoy", "leverage", "roa", "interest_coverage", "log_assets"]
    ame_results = compute_ame(res_d, mod_d, train_data[cols_d], ame_vars)
    
    for var, vals in ame_results.items():
        print(f"  {var:20s} | AME P(IG): {vals['ame_P_IG']:+8.4f} | AME P(BBB-): {vals['ame_P_BBB_minus']:+8.4f} | AME P(BB+): {vals['ame_P_BB_plus']:+8.4f}")
        save_result_metric(
            key=f"m1_ame_{var}_P_IG",
            value=vals["ame_P_IG"],
            n=n_train,
            spec="spec_d_interactions",
            notes=f"Average marginal effect of {var} on probability of Investment Grade P(IG)"
        )
        save_result_metric(
            key=f"m1_ame_{var}_P_BBB_minus",
            value=vals["ame_P_BBB_minus"],
            n=n_train,
            spec="spec_d_interactions",
            notes=f"Average marginal effect of {var} on probability of BBB-"
        )
        save_result_metric(
            key=f"m1_ame_{var}_P_BB_plus",
            value=vals["ame_P_BB_plus"],
            n=n_train,
            spec="spec_d_interactions",
            notes=f"Average marginal effect of {var} on probability of BB+"
        )

    # Plot Figure: macro_marginal_effects.png
    fig_dir = ROOT_DIR / "results" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    plot_macro_marginal_effects(ame_results, fig_dir / "macro_marginal_effects.png")
    
    print("\n[M1 Ordinal] Completed successfully.")
    return results_summary, fitted_models


def plot_macro_marginal_effects(ame_results: dict, out_path: Path):
    """Generate high-quality visualization of Average Marginal Effects across rating states."""
    selected = ["hy_oas", "fedfunds", "term_spread", "gdp_yoy", "cpi_yoy", "leverage", "roa", "log_assets"]
    labels = {
        "hy_oas": "HY Credit Spread (hy_oas, %)",
        "fedfunds": "Fed Funds Rate (%)",
        "term_spread": "Term Spread (10Y-2Y, %)",
        "gdp_yoy": "Real GDP YoY Growth (%)",
        "cpi_yoy": "CPI YoY Inflation (%)",
        "leverage": "Leverage (Total Debt / EBITDA)",
        "roa": "Return on Assets (ROA)",
        "log_assets": "Firm Size (log Total Assets)"
    }
    
    plot_data = []
    for var in selected:
        if var in ame_results:
            vals = ame_results[var]
            name = labels.get(var, var)
            plot_data.append({"Variable": name, "Target State": "P(IG) [AAA to BBB-]", "AME": vals["ame_P_IG"]})
            plot_data.append({"Variable": name, "Target State": "P(BBB-) [Boundary IG]", "AME": vals["ame_P_BBB_minus"]})
            plot_data.append({"Variable": name, "Target State": "P(BB+) [Boundary HY]", "AME": vals["ame_P_BB_plus"]})
            
    df_plot = pd.DataFrame(plot_data)
    
    sns.set_theme(style="whitegrid", font="sans-serif")
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), sharey=True)
    
    palette = ["#1f77b4", "#ff7f0e", "#d62728"]
    states = ["P(IG) [AAA to BBB-]", "P(BBB-) [Boundary IG]", "P(BB+) [Boundary HY]"]
    
    for i, state in enumerate(states):
        sub = df_plot[df_plot["Target State"] == state]
        ax = axes[i]
        bars = ax.barh(sub["Variable"], sub["AME"], color=palette[i], alpha=0.85, edgecolor="black", height=0.6)
        ax.axvline(0, color="black", linestyle="--", linewidth=1.0, alpha=0.7)
        ax.set_title(f"Marginal Effect on {state}", fontsize=12, fontweight="bold", pad=10)
        ax.set_xlabel("Average Marginal Effect (pp)", fontsize=10)
        
        # Add data labels
        for bar in bars:
            val = bar.get_width()
            offset = 0.002 if val >= 0 else -0.002
            ha = "left" if val >= 0 else "right"
            ax.text(val + offset, bar.get_y() + bar.get_height() / 2, f"{val:+.3f}", va="center", ha=ha, fontsize=8, fontweight="bold")
            
    fig.suptitle("M1 Kaplan-Urwitz Ordered Probit: Macro & Fundamental Marginal Effects", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[Figure] Saved macro marginal effects plot to {out_path}")


if __name__ == "__main__":
    run_specifications()
