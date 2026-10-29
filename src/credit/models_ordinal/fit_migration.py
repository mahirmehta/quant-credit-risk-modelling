"""
M2: Augmented Ordinal Migration Scale with Watch / Outlook States.
Models multi-state migration over horizon h = 4 quarters:
  0: Upgrade (notch_diff_h < 0)
  1: Stable (notch_diff_h == 0, without negative watch/outlook)
  2: Negative Outlook / Watch only (notch_diff_h == 0, watch or outlook == 'NEG')
  3: Single-notch downgrade (notch_diff_h == 1)
  4: Multi-notch downgrade / default (notch_diff_h >= 2)

Evaluates:
  - Ordered Probit & Ordered Logit
  - Firm fundamentals + Macro variables + Current rating + Initial Watch/Outlook
  - Average Marginal Effects (AME) on all 5 migration states
  - Standard errors clustered by firm (gvkey)
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
from src.credit.models_ordinal.fit_ordinal import compute_mcfadden_pseudo_r2


def prepare_migration_data(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare feature matrix for M2 migration model."""
    data = df.copy()
    
    # Negative watch and outlook flags at time t
    data["watch_neg"] = (data["watch"] == "NEG").astype(float)
    data["outlook_neg"] = (data["outlook"] == "NEG").astype(float)
    
    # Interactions
    data["leverage_x_d4_fedfunds"] = data["leverage"] * data["d4_fedfunds"]
    data["icov_x_hy_oas"] = data["interest_coverage"] * data["hy_oas"]
    
    # Filter to valid forward migration outcome
    data = data.dropna(subset=["migr_cat_h", "gvkey"]).copy()
    data["migr_cat_h"] = data["migr_cat_h"].astype(int)
    
    return data


def compute_m2_ame(model_res, X: pd.DataFrame, target_cols: list, eps: float = 1e-4) -> dict:
    """
    Compute Average Marginal Effects (AME) for all 5 migration categories:
      0: Upgrade
      1: Stable
      2: Negative Watch/Outlook Only
      3: Single Downgrade
      4: Multi-notch Downgrade
    """
    ame_dict = {}
    n_cats = 5
    
    for col in target_cols:
        if col not in X.columns:
            continue
        X_plus = X.copy()
        X_minus = X.copy()
        
        X_plus[col] += eps
        X_minus[col] -= eps
        
        # Interactions propagation
        if col == "leverage" and "leverage_x_d4_fedfunds" in X.columns:
            X_plus["leverage_x_d4_fedfunds"] = X_plus["leverage"] * X_plus["d4_fedfunds"] if "d4_fedfunds" in X_plus.columns else X_plus["leverage_x_d4_fedfunds"]
            X_minus["leverage_x_d4_fedfunds"] = X_minus["leverage"] * X_minus["d4_fedfunds"] if "d4_fedfunds" in X_minus.columns else X_minus["leverage_x_d4_fedfunds"]
        if col == "hy_oas" and "icov_x_hy_oas" in X.columns:
            X_plus["icov_x_hy_oas"] = X_plus["interest_coverage"] * X_plus["hy_oas"] if "interest_coverage" in X_plus.columns else X_plus["icov_x_hy_oas"]
            X_minus["icov_x_hy_oas"] = X_minus["interest_coverage"] * X_minus["hy_oas"] if "interest_coverage" in X_minus.columns else X_minus["icov_x_hy_oas"]
            
        prob_plus = model_res.predict(X_plus)
        prob_minus = model_res.predict(X_minus)
        
        cat_names = ["Upgrade", "Stable", "NegWatchOutlook", "Downgrade_1N", "MultiDowngrade"]
        ame_dict[col] = {}
        for c_idx in range(min(n_cats, prob_plus.shape[1])):
            diff = (prob_plus.iloc[:, c_idx] - prob_minus.iloc[:, c_idx]) / (2.0 * eps)
            ame_dict[col][cat_names[c_idx]] = float(np.mean(diff))
            
    return ame_dict


def run_migration_model():
    """Estimate M2 Augmented Ordinal Migration Scale."""
    panel_path = ROOT_DIR / "data" / "processed" / "panel_firmq.parquet"
    if not panel_path.exists():
        raise FileNotFoundError(f"Missing {panel_path}")
        
    print(f"[M2 Migration] Loading panel from {panel_path}...")
    df = pd.read_parquet(panel_path)
    df_migr = prepare_migration_data(df)
    
    # Train sample
    train_mask = (df_migr["split"] == "train")
    train_data = df_migr[train_mask].copy()
    n_train = len(train_data)
    n_firms = train_data["gvkey"].nunique()
    
    print(f"[M2 Migration] Estimation sample: N = {n_train} firm-quarters across {n_firms} firms.")
    print(f"[M2 Migration] Class distribution (4Q horizon):")
    counts = train_data["migr_cat_h"].value_counts().sort_index()
    names = ["0: Upgrade", "1: Stable", "2: Neg Watch/Outlook", "3: 1-Notch Downgrade", "4: Multi-Notch Downgrade"]
    for idx, count in counts.items():
        print(f"  {names[idx]:25s}: {count:6d} ({count/n_train*100:5.2f}%)")
        
    features = [
        "rating_num", "watch_neg", "outlook_neg",
        "leverage", "interest_coverage", "roa", "current_ratio", "cash_to_assets", "log_assets", "tangibility",
        "fedfunds", "term_spread", "hy_oas", "cpi_yoy", "gdp_yoy",
        "leverage_x_d4_fedfunds", "icov_x_hy_oas"
    ]
    
    # 1. Ordered Probit
    print("\n[M2 Migration] Fitting Ordered Probit with cluster-robust standard errors...")
    mod_probit = OrderedModel(train_data["migr_cat_h"], train_data[features], distr="probit")
    res_probit = mod_probit.fit(method="bfgs", maxiter=250, disp=False, cov_type="cluster", cov_kwds={"groups": train_data["gvkey"]})
    
    pseudo_r2_probit = compute_mcfadden_pseudo_r2(float(res_probit.llf), train_data["migr_cat_h"])
    print(f"Ordered Probit Log-Likelihood: {res_probit.llf:.2f} | Pseudo-R2: {pseudo_r2_probit:.4f}")
    
    save_result_metric(
        key="m2_pseudo_r2_probit",
        value=pseudo_r2_probit,
        n=n_train,
        spec="m2_augmented_probit",
        notes="McFadden pseudo-R2 for M2 Augmented Ordinal Migration Probit"
    )
    save_result_metric(
        key="m2_llf_probit",
        value=float(res_probit.llf),
        n=n_train,
        spec="m2_augmented_probit",
        notes="Log-Likelihood for M2 Augmented Ordinal Migration Probit"
    )

    # 2. Ordered Logit
    print("\n[M2 Migration] Fitting Ordered Logit benchmark...")
    mod_logit = OrderedModel(train_data["migr_cat_h"], train_data[features], distr="logit")
    res_logit = mod_logit.fit(method="bfgs", maxiter=250, disp=False, cov_type="cluster", cov_kwds={"groups": train_data["gvkey"]})
    pseudo_r2_logit = compute_mcfadden_pseudo_r2(float(res_logit.llf), train_data["migr_cat_h"])
    print(f"Ordered Logit Log-Likelihood:  {res_logit.llf:.2f} | Pseudo-R2: {pseudo_r2_logit:.4f}")
    
    save_result_metric(
        key="m2_pseudo_r2_logit",
        value=pseudo_r2_logit,
        n=n_train,
        spec="m2_augmented_logit",
        notes="McFadden pseudo-R2 for M2 Augmented Ordinal Migration Logit"
    )

    # 3. Average Marginal Effects (AME)
    print("\n[M2 Migration] Calculating Average Marginal Effects on Migration Categories...")
    key_vars = ["hy_oas", "fedfunds", "term_spread", "gdp_yoy", "watch_neg", "leverage", "roa"]
    ame_m2 = compute_m2_ame(res_probit, train_data[features], key_vars)
    
    for var, states in ame_m2.items():
        print(f"\nAME for {var}:")
        for st_name, ame_val in states.items():
            print(f"  {st_name:18s}: {ame_val:+8.4f}")
            save_result_metric(
                key=f"m2_ame_{var}_{st_name}",
                value=ame_val,
                n=n_train,
                spec="m2_ordered_probit",
                notes=f"AME of {var} on state {st_name}"
            )

    # Plot M2 Marginal Effects
    fig_dir = ROOT_DIR / "results" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    plot_migration_ame(ame_m2, fig_dir / "migration_marginal_effects.png")
    
    print("\n[M2 Migration] Completed successfully.")
    return res_probit, ame_m2


def plot_migration_ame(ame_m2: dict, out_path: Path):
    """Plot AME for key macro and firm factors on downgrade & negative watch states."""
    selected_vars = ["hy_oas", "fedfunds", "term_spread", "gdp_yoy", "leverage", "roa"]
    var_labels = {
        "hy_oas": "HY Spread (hy_oas)",
        "fedfunds": "Fed Funds Rate",
        "term_spread": "Term Spread",
        "gdp_yoy": "GDP Growth",
        "leverage": "Leverage",
        "roa": "ROA"
    }
    
    records = []
    for var in selected_vars:
        if var in ame_m2:
            lbl = var_labels.get(var, var)
            records.append({"Variable": lbl, "State": "Neg Watch / Outlook", "AME": ame_m2[var].get("NegWatchOutlook", 0.0)})
            records.append({"Variable": lbl, "State": "1-Notch Downgrade", "AME": ame_m2[var].get("Downgrade_1N", 0.0)})
            records.append({"Variable": lbl, "State": "Multi-Notch Downgrade", "AME": ame_m2[var].get("MultiDowngrade", 0.0)})
            
    df_plot = pd.DataFrame(records)
    
    sns.set_theme(style="whitegrid", font="sans-serif")
    fig, ax = plt.subplots(figsize=(10, 6))
    
    sns.barplot(data=df_plot, y="Variable", x="AME", hue="State", palette="magma", ax=ax, edgecolor="black", alpha=0.85)
    ax.axvline(0, color="black", linestyle="--", linewidth=1.0)
    ax.set_title("M2: Average Marginal Effects on Downgrade & Watch States (4Q Horizon)", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Average Marginal Effect (pp)", fontsize=11)
    ax.set_ylabel("Covariate", fontsize=11)
    ax.legend(title="Migration State", loc="lower right", frameon=True)
    
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[Figure] Saved migration marginal effects plot to {out_path}")


if __name__ == "__main__":
    run_migration_model()
