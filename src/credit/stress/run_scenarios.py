"""
Macro Stress Testing & Sector Analysis Execution Engine (A3 & A7).
Evaluates 8-quarter Fallen-Angel migration probabilities across Investment Grade issuers
under mandated scenarios S0-S4, computes parameter uncertainty intervals via asymptotic
covariance sampling, ranks FF12 sector vulnerability, and executes the N5 Reverse Stress Test.
Adheres strictly to Section 5, 6.3, and 6.4 of plan_updated.md.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import statsmodels.api as sm
from statsmodels.tsa.api import VAR
import scipy.optimize as opt
from scipy import stats

# Project Root Setup
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.credit.utils.helpers import save_result_metric
from src.credit.models_binary.fit_fallen_angel import prepare_binary_dataset, get_specification_features

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROCESSED_DIR = ROOT_DIR / "data" / "processed"
FIGURES_DIR = ROOT_DIR / "results" / "figures"
VAR_VARIABLES = ["fedfunds", "term_spread", "cpi_yoy", "gdp_yoy", "hy_oas"]
SCENARIO_IDS = ["S0", "S1", "S2", "S3", "S4"]
SCENARIO_NAMES = {
    "S0": "S0: Baseline (Unconditional)",
    "S1": "S1: Monetary Tightening (+300bp FFR)",
    "S2": "S2: Hard Landing (GDP -3%, OAS +400bp)",
    "S3": "S3: Stagflation (CPI +3pp, GDP -1.5pp, FFR +150bp)",
    "S4": "S4: Soft Landing (FFR -200bp, GDP +2.5pp, OAS -100bp)"
}


def fit_fallen_angel_forecasting_model(
    panel_df: pd.DataFrame
) -> Tuple[Any, np.ndarray, np.ndarray, List[str]]:
    """
    Fit Specification S4 (Firm + Macro + Interactions) on training split
    using cluster-robust standard errors by firm (gvkey).
    Returns fitted Logit model, parameter estimates, and covariance matrix.
    """
    logger.info("Fitting M3 Specification S4 on training split for stress testing...")
    train_data = prepare_binary_dataset(panel_df, sample_type="ig")
    train_split = train_data[train_data["split"] == "train"].copy()

    spec_features = get_specification_features()["S4"]
    X_train = sm.add_constant(train_split[spec_features])
    y_train = train_split["fa_h"].values.astype(int)

    # Fit Logit with cluster-robust standard errors
    logit_res = sm.Logit(y_train, X_train).fit(
        disp=False,
        cov_type="cluster",
        cov_kwds={"groups": train_split["gvkey"]}
    )

    params = logit_res.params.values
    cov_params = logit_res.cov_params().values
    logger.info(f"M3 S4 Model successfully fitted. Pseudo-R2: {logit_res.prsquared:.4f}, Obs: {len(train_split)}")
    return logit_res, params, cov_params, spec_features


def prepare_firm_design_matrix(
    snapshot_df: pd.DataFrame,
    macro_row: pd.Series,
    spec_features: List[str]
) -> np.ndarray:
    """Prepare design matrix for firm snapshot under specific macro conditions."""
    d = snapshot_df.copy()
    
    # Watch and outlook indicators
    d["watch_neg"] = (d["watch"] == "NEG").astype(float)
    d["watch_pos"] = (d["watch"] == "POS").astype(float)
    d["outlook_neg"] = (d["outlook"] == "NEG").astype(float)
    d["outlook_pos"] = (d["outlook"] == "POS").astype(float)

    # Inject macro scenario variables
    for c in ["fedfunds", "d4_fedfunds", "term_spread", "hy_oas", "d4_hy_oas", "cpi_yoy", "gdp_yoy"]:
        d[c] = float(macro_row[c])

    # Dynamic interactions
    d["leverage_x_d4_fedfunds"] = d["leverage"] * d["d4_fedfunds"]
    d["intcov_x_d4_hy_oas"] = d["interest_coverage"] * d["d4_hy_oas"]

    X = sm.add_constant(d[spec_features], has_constant="add")
    return X.values


def evaluate_scenarios_over_horizon(
    panel_df: pd.DataFrame,
    scenarios_df: pd.DataFrame,
    params: np.ndarray,
    cov_params: np.ndarray,
    spec_features: List[str],
    n_bootstrap: int = 500,
    seed: int = 42
) -> Dict[str, Any]:
    """
    Evaluate projected fallen-angel probabilities across firms, sectors, and horizons
    with parameter uncertainty intervals from asymptotic covariance sampling.
    """
    logger.info("Extracting latest usable IG firm snapshot (2025Q4)...")
    snapshot = panel_df[(panel_df["qdate"] == "2025-12-31") & (panel_df["is_ig"] == 1)].copy().reset_index(drop=True)
    n_firms = len(snapshot)
    logger.info(f"Snapshot contains {n_firms} active Investment Grade firms.")

    np.random.seed(seed)
    # Draw beta vectors from asymptotic normal distribution
    # Handle possible small negative eigenvalues in empirical covariance matrix
    cov_sym = 0.5 * (cov_params + cov_params.T)
    min_eig = np.min(np.real(np.linalg.eigvals(cov_sym)))
    if min_eig < 1e-8:
        cov_sym += (abs(min_eig) + 1e-6) * np.eye(len(params))
        
    beta_draws = np.random.multivariate_normal(params, cov_sym, size=n_bootstrap)

    horizons = sorted(scenarios_df["horizon_q"].unique())
    sectors = sorted(snapshot["sector_ff12"].unique())

    # Results containers
    # scenario -> horizon -> array of firm probabilities (n_firms,)
    firm_probs_point = {s: {} for s in SCENARIO_IDS}
    # scenario -> horizon -> (n_bootstrap, n_firms)
    firm_probs_boot = {s: {} for s in SCENARIO_IDS}

    for s_id in SCENARIO_IDS:
        for h in horizons:
            s_row = scenarios_df[(scenarios_df["scenario_id"] == s_id) & (scenarios_df["horizon_q"] == h)].iloc[0]
            X_design = prepare_firm_design_matrix(snapshot, s_row, spec_features)
            
            # Point estimate probabilities
            eta_point = np.clip(X_design @ params, -30.0, 30.0)
            p_point = 1.0 / (1.0 + np.exp(-eta_point))
            firm_probs_point[s_id][h] = p_point

            # Bootstrap draws: (n_bootstrap, n_firms)
            eta_boot = np.clip(beta_draws @ X_design.T, -30.0, 30.0)
            p_boot = 1.0 / (1.0 + np.exp(-eta_boot))
            firm_probs_boot[s_id][h] = p_boot

    # Aggregate by sector and total at primary horizon h=4 (12-month forward)
    primary_h = 4
    sector_summary = []
    
    for sec in sectors:
        sec_mask = (snapshot["sector_ff12"] == sec).values
        n_sec = int(sec_mask.sum())
        sec_row = {"sector_ff12": sec, "n_firms": n_sec}

        for s_id in SCENARIO_IDS:
            p_sec_point = float(np.mean(firm_probs_point[s_id][primary_h][sec_mask]))
            boot_sec = np.mean(firm_probs_boot[s_id][primary_h][:, sec_mask], axis=1)
            ci_lower = float(np.percentile(boot_sec, 2.5))
            ci_upper = float(np.percentile(boot_sec, 97.5))

            sec_row[f"p_{s_id}"] = p_sec_point
            sec_row[f"ci_lower_{s_id}"] = ci_lower
            sec_row[f"ci_upper_{s_id}"] = ci_upper
            sec_row[f"expected_fa_{s_id}"] = p_sec_point * n_sec

        # Deltas relative to Baseline S0
        for s_id in ["S1", "S2", "S3", "S4"]:
            delta_p = sec_row[f"p_{s_id}"] - sec_row["p_S0"]
            boot_delta = (
                np.mean(firm_probs_boot[s_id][primary_h][:, sec_mask], axis=1) -
                np.mean(firm_probs_boot["S0"][primary_h][:, sec_mask], axis=1)
            )
            sec_row[f"delta_p_{s_id}"] = delta_p
            sec_row[f"delta_ci_lower_{s_id}"] = float(np.percentile(boot_delta, 2.5))
            sec_row[f"delta_ci_upper_{s_id}"] = float(np.percentile(boot_delta, 97.5))
            sec_row[f"ratio_{s_id}"] = float(sec_row[f"p_{s_id}"] / max(sec_row["p_S0"], 1e-6))

        sector_summary.append(sec_row)

    sector_df = pd.DataFrame(sector_summary)

    # Total aggregate metrics
    agg_summary = {}
    for s_id in SCENARIO_IDS:
        p_agg_point = float(np.mean(firm_probs_point[s_id][primary_h]))
        boot_agg = np.mean(firm_probs_boot[s_id][primary_h], axis=1)
        ci_lower = float(np.percentile(boot_agg, 2.5))
        ci_upper = float(np.percentile(boot_agg, 97.5))
        delta_p = float(p_agg_point - np.mean(firm_probs_point["S0"][primary_h])) if s_id != "S0" else 0.0

        agg_summary[s_id] = {
            "p_fa": p_agg_point,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "expected_fa_count": p_agg_point * n_firms,
            "delta_p": delta_p
        }
        logger.info(f"Aggregate {s_id}: Mean P(FA)={p_agg_point*100:.2f}% [{ci_lower*100:.2f}%, {ci_upper*100:.2f}%] | "
                    f"Expected FA Count={agg_summary[s_id]['expected_fa_count']:.1f} / {n_firms} | Delta={delta_p*100:+.2f}pp")

        # Save to JSON registry
        save_result_metric(f"stress_fa_rate_{s_id.lower()}", p_agg_point, ci=(ci_lower, ci_upper),
                           n=n_firms, spec=s_id, notes=f"Projected 12m FA rate under {s_id}")
        if s_id != "S0":
            save_result_metric(f"stress_delta_p_{s_id.lower()}", delta_p, spec=s_id,
                               notes=f"Delta P(FA) relative to baseline under {s_id}")

    return {
        "snapshot": snapshot,
        "sector_df": sector_df,
        "agg_summary": agg_summary,
        "firm_probs_point": firm_probs_point,
        "firm_probs_boot": firm_probs_boot,
        "horizons": horizons,
        "sectors": sectors
    }


def execute_reverse_stress_test(
    panel_df: pd.DataFrame,
    macro_df: pd.DataFrame,
    params: np.ndarray,
    spec_features: List[str],
    target_rate: float = 0.10,
    horizon: int = 4
) -> Dict[str, Any]:
    """
    N5 Reverse Stress Test:
    Finds the minimum Mahalanobis norm macro shock path (under VAR covariance structure)
    that pushes the aggregate fallen-angel rate to the target rate (10.0%, GFC-level dislocation).
    """
    logger.info(f"Running N5 Reverse Stress Test (Target Aggregate FA Rate = {target_rate*100:.1f}%)...")
    snapshot = panel_df[(panel_df["qdate"] == "2025-12-31") & (panel_df["is_ig"] == 1)].copy().reset_index(drop=True)
    n_firms = len(snapshot)

    # Fit VAR model for the structural shock multiplier matrix G
    vdf = macro_df.set_index("qdate")[VAR_VARIABLES].dropna().sort_index()
    var_res = VAR(vdf).fit(2)
    m = len(VAR_VARIABLES)
    ma = var_res.ma_rep(maxn=horizon)
    sigma_u = var_res.sigma_u
    C = np.linalg.cholesky(sigma_u)

    G = np.zeros((m * horizon, m * horizon))
    for h in range(horizon):
        for k in range(h + 1):
            G[h * m : (h + 1) * m, k * m : (k + 1) * m] = ma[h - k] @ C

    p_lags = var_res.k_ar
    y_base = var_res.forecast(y=vdf.values[-p_lags:], steps=horizon).flatten()
    hist_ffr = vdf["fedfunds"].values
    hist_oas = vdf["hy_oas"].values

    # Pre-build firm base dataframe
    firm_base = snapshot.copy()
    firm_base["watch_neg"] = (firm_base["watch"] == "NEG").astype(float)
    firm_base["watch_pos"] = (firm_base["watch"] == "POS").astype(float)
    firm_base["outlook_neg"] = (firm_base["outlook"] == "NEG").astype(float)
    firm_base["outlook_pos"] = (firm_base["outlook"] == "POS").astype(float)

    def evaluate_shock_path(eps: np.ndarray) -> Tuple[float, np.ndarray, np.ndarray]:
        y_path = (y_base + G @ eps).reshape((horizon, m))
        q_target_vals = y_path[horizon - 1]
        ffr, term_spread, cpi_yoy, gdp_yoy, hy_oas = q_target_vals

        d4_ffr = ffr - hist_ffr[-1]
        d4_oas = hy_oas - hist_oas[-1]

        d = firm_base.copy()
        d["fedfunds"] = ffr
        d["d4_fedfunds"] = d4_ffr
        d["term_spread"] = term_spread
        d["hy_oas"] = hy_oas
        d["d4_hy_oas"] = d4_oas
        d["cpi_yoy"] = cpi_yoy
        d["gdp_yoy"] = gdp_yoy
        d["leverage_x_d4_fedfunds"] = d["leverage"] * d4_ffr
        d["intcov_x_d4_hy_oas"] = d["interest_coverage"] * d4_oas

        X_mat = sm.add_constant(d[spec_features], has_constant="add").values
        eta = np.clip(X_mat @ params, -25.0, 25.0)
        probs = 1.0 / (1.0 + np.exp(-eta))
        return float(np.mean(probs)), probs, y_path

    # Optimization objective: minimize Mahalanobis norm ||eps||_2^2
    def objective(eps: np.ndarray) -> float:
        return 0.5 * float(np.sum(eps ** 2))

    def obj_grad(eps: np.ndarray) -> np.ndarray:
        return eps

    def constraint_rate(eps: np.ndarray) -> float:
        rate, _, _ = evaluate_shock_path(eps)
        return rate - target_rate

    # Initial guess
    eps0 = np.zeros(m * horizon)
    # Warm start: tightening and widening at horizon
    eps0[(horizon - 1) * m + 0] = 1.5
    eps0[(horizon - 1) * m + 4] = 2.0

    logger.info("Solving minimum-norm reverse stress optimization...")
    res = opt.minimize(
        objective,
        eps0,
        jac=obj_grad,
        method="SLSQP",
        constraints={"type": "eq", "fun": constraint_rate},
        options={"maxiter": 300, "ftol": 1e-6}
    )

    opt_eps = res.x
    opt_norm = float(np.linalg.norm(opt_eps))
    final_rate, final_probs, opt_macro_path = evaluate_shock_path(opt_eps)
    logger.info(f"Reverse Stress Test Solved (Success={res.success}):")
    logger.info(f"  Minimum Mahalanobis Norm ||eps*||_2 = {opt_norm:.4f}")
    logger.info(f"  Realized Aggregate FA Rate = {final_rate*100:.2f}% (Target: {target_rate*100:.1f}%)")
    
    terminal_macro = opt_macro_path[horizon - 1]
    logger.info(f"  Terminal Macro State at 12M: FFR={terminal_macro[0]:.2f}%, "
                f"TermSpread={terminal_macro[1]:.2f}%, CPI={terminal_macro[2]:.2f}%, "
                f"Real GDP Growth={terminal_macro[3]:.2f}%, HY OAS={terminal_macro[4]:.2f}%")

    # Save metrics to registry
    save_result_metric("reverse_stress_norm", opt_norm, spec="N5 Reverse Stress", notes="Minimum Mahalanobis norm for 10% FA rate")
    save_result_metric("reverse_stress_rate", final_rate, spec="N5 Reverse Stress", notes="Achieved FA rate under reverse stress")
    save_result_metric("reverse_stress_terminal_ffr", float(terminal_macro[0]), spec="N5 Reverse Stress", notes="Terminal FFR under reverse stress")
    save_result_metric("reverse_stress_terminal_gdp", float(terminal_macro[3]), spec="N5 Reverse Stress", notes="Terminal Real GDP growth under reverse stress")
    save_result_metric("reverse_stress_terminal_oas", float(terminal_macro[4]), spec="N5 Reverse Stress", notes="Terminal HY OAS under reverse stress")

    return {
        "success": res.success,
        "optimal_norm": opt_norm,
        "optimal_shocks": opt_eps,
        "final_rate": final_rate,
        "firm_probabilities": final_probs,
        "macro_path": opt_macro_path,
        "horizon": horizon,
        "var_variables": VAR_VARIABLES
    }


def plot_sector_vulnerability_heatmap(sector_df: pd.DataFrame, save_path: Path = None):
    """
    Generate publication-quality FF12 sector vulnerability heatmap across scenarios.
    """
    if save_path is None:
        save_path = FIGURES_DIR / "sector_vulnerability_heatmap.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    plt.style.use("seaborn-v0_8-white" if "seaborn-v0_8-white" in plt.style.available else "default")
    
    # Sort sectors by vulnerability under S1 Monetary Tightening
    sorted_df = sector_df.sort_values("delta_p_S1", ascending=False).copy()
    sector_labels = [f"{s} (n={n})" for s, n in zip(sorted_df["sector_ff12"], sorted_df["n_firms"])]

    # Heatmap 1: Projected Fallen-Angel Probability P(FA) (%)
    p_matrix = sorted_df[[f"p_{s}" for s in SCENARIO_IDS]].values * 100.0
    # Heatmap 2: Delta P(FA) relative to Baseline (percentage points)
    delta_matrix = np.column_stack([
        np.zeros(len(sorted_df)), # S0 has 0 delta
        sorted_df["delta_p_S1"].values * 100.0,
        sorted_df["delta_p_S2"].values * 100.0,
        sorted_df["delta_p_S3"].values * 100.0,
        sorted_df["delta_p_S4"].values * 100.0
    ])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 8), dpi=300, gridspec_kw={"width_ratios": [1.1, 1.1]})

    # Left: Level P(FA)
    sns.heatmap(
        p_matrix,
        annot=True,
        fmt=".2f",
        cmap="YlOrRd",
        xticklabels=[SCENARIO_NAMES[s].split("(")[0].strip() for s in SCENARIO_IDS],
        yticklabels=sector_labels,
        cbar_kws={"label": "Projected Fallen-Angel Probability (%)"},
        ax=ax1,
        linewidths=0.5,
        annot_kws={"fontsize": 10, "fontweight": "bold"}
    )
    ax1.set_title("Projected 12-Month P(FA) by FF12 Sector (%)\n(Level Migration Probability)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Fama-French 12 Sector (Issuer Count)", fontsize=11, fontweight="bold")
    ax1.tick_params(axis="x", rotation=30)

    # Right: Delta P(FA) vs Baseline
    sns.heatmap(
        delta_matrix,
        annot=True,
        fmt="+.2f",
        cmap="coolwarm",
        center=0.0,
        xticklabels=[SCENARIO_NAMES[s].split("(")[0].strip() for s in SCENARIO_IDS],
        yticklabels=sector_labels,
        cbar_kws={"label": "Delta P(FA) vs Baseline (percentage points)"},
        ax=ax2,
        linewidths=0.5,
        annot_kws={"fontsize": 10, "fontweight": "bold"}
    )
    ax2.set_title("Sector Vulnerability: ΔP(FA) vs Baseline\n(Sensitivity to Macro Shocks)", fontsize=12, fontweight="bold")
    ax2.tick_params(axis="x", rotation=30)

    plt.suptitle("Fama-French 12 Sector Stress Testing Heatmap & Vulnerability Ranking",
                 fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved sector vulnerability heatmap to {save_path}")


def plot_stress_test_fa_distribution(
    eval_results: Dict[str, Any],
    save_path: Path = None
):
    """
    Plot firm-level fallen-angel probability distributions across scenarios S0 to S4,
    illustrating the shift in tail migration risk.
    """
    if save_path is None:
        save_path = FIGURES_DIR / "stress_test_fa_distribution.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    colors = {"S0": "#546E7A", "S1": "#1E88E5", "S2": "#D81B60", "S3": "#FB8C00", "S4": "#43A047"}

    firm_probs = eval_results["firm_probs_point"]
    snapshot = eval_results["snapshot"]
    primary_h = 4

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), dpi=300)

    # 1. Boxplot of probabilities by scenario
    data_box = []
    labels_box = []
    for s_id in SCENARIO_IDS:
        probs = firm_probs[s_id][primary_h] * 100.0
        data_box.append(probs)
        labels_box.append(s_id)

    bplot = ax1.boxplot(
        data_box,
        labels=[SCENARIO_NAMES[s].split("(")[0].strip() for s in SCENARIO_IDS],
        patch_artist=True,
        showmeans=True,
        meanprops={"marker": "D", "markeredgecolor": "black", "markerfacecolor": "yellow"}
    )
    for patch, s_id in zip(bplot["boxes"], SCENARIO_IDS):
        patch.set_facecolor(colors[s_id])
        patch.set_alpha(0.7)

    ax1.set_title("Distribution of Projected Firm Fallen-Angel Probabilities (12M)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Projected P(FA) (%)", fontsize=11, fontweight="bold")
    ax1.tick_params(axis="x", rotation=25)
    ax1.grid(True, linestyle=":", alpha=0.6)

    # 2. Cliff-edge sensitivity: P(FA) by Current Rating Category
    rating_analysis = []
    for s_id in SCENARIO_IDS:
        probs = firm_probs[s_id][primary_h] * 100.0
        temp = snapshot[["rating_num"]].copy()
        temp["prob"] = probs
        temp["scenario"] = s_id
        rating_analysis.append(temp)

    df_ratings = pd.concat(rating_analysis, ignore_index=True)
    rating_means = df_ratings.groupby(["rating_num", "scenario"])["prob"].mean().unstack()

    rating_labels = {
        1: "AAA", 2: "AA+", 3: "AA", 4: "AA-",
        5: "A+", 6: "A", 7: "A-",
        8: "BBB+", 9: "BBB", 10: "BBB-"
    }
    x_pos = np.arange(len(rating_means))
    width = 0.16

    for idx, s_id in enumerate(SCENARIO_IDS):
        ax2.bar(
            x_pos + (idx - 2) * width,
            rating_means[s_id],
            width=width,
            label=f"{s_id}",
            color=colors[s_id],
            alpha=0.85
        )

    ax2.set_xticks(x_pos)
    ax2.set_xticklabels([rating_labels.get(r, str(r)) for r in rating_means.index], fontsize=10, fontweight="bold")
    ax2.set_title("Fallen-Angel Risk by Current Rating Notch (Cliff-Edge Focus)", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Current Investment Grade Rating Notch", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Mean Projected P(FA) (%)", fontsize=11, fontweight="bold")
    ax2.legend(loc="upper left", frameon=True, fontsize=9)
    ax2.grid(True, linestyle=":", alpha=0.6)

    plt.suptitle("Investment Grade Fallen-Angel Tail Risk & Notch Migration Profiling",
                 fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved fallen-angel distribution figure to {save_path}")


def plot_reverse_stress_shock_profile(
    rev_results: Dict[str, Any],
    macro_df: pd.DataFrame,
    save_path: Path = None
):
    """
    Plot Reverse Stress Test macro path and structural shock decomposition.
    """
    if save_path is None:
        save_path = FIGURES_DIR / "reverse_stress_shock_profile.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    
    macro_path = rev_results["macro_path"] # (H, m)
    horizon = rev_results["horizon"]
    opt_norm = rev_results["optimal_norm"]
    shocks = rev_results["optimal_shocks"].reshape((horizon, len(VAR_VARIABLES)))

    fig, axes = plt.subplots(2, 3, figsize=(16, 9), dpi=300)
    axes_flat = axes.flatten()

    q_labels = [f"Q{h}" for h in range(1, horizon + 1)]

    var_titles = [
        "Fed Funds Rate (%)\n(Aggressive Tightening)",
        "10Y-2Y Term Spread (%)\n(Inversion Dynamic)",
        "CPI Inflation YoY (%)\n(Severe Deflationary Shock)",
        "Real GDP Growth YoY (%)\n(Depression-Scale Contraction)",
        "High Yield OAS (%)\n(Credit Spread Dynamic)"
    ]

    for idx, (var, title) in enumerate(zip(VAR_VARIABLES, var_titles)):
        ax = axes_flat[idx]
        ax.plot(q_labels, macro_path[:, idx], marker="o", lw=2.5, color="#D32F2F", label="Reverse Stress Path")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_ylabel("Percent (%)", fontsize=10)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="best", fontsize=9, frameon=True)

    # 6th panel: Structural shock decomposition ||eps_t||
    ax6 = axes_flat[5]
    shock_norms = [np.linalg.norm(shocks[h]) for h in range(horizon)]
    bars = ax6.bar(q_labels, shock_norms, color="#7B1FA2", width=0.5, edgecolor="black", alpha=0.8)
    
    for bar, val in zip(bars, shock_norms):
        ax6.text(bar.get_x() + bar.get_width() / 2.0, val + 0.1,
                 f"{val:.2f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax6.set_title(f"Reverse Stress Structural Shock Intensity\n(Total Mahalanobis Norm ||ε*|| = {opt_norm:.2f})",
                  fontsize=11, fontweight="bold")
    ax6.set_ylabel("Quarterly Shock Norm ||ε_t||", fontsize=10)
    ax6.set_ylim([0, max(shock_norms) * 1.3])
    ax6.grid(axis="y", linestyle=":", alpha=0.6)

    plt.suptitle("N5 Reverse Stress Test: Minimum-Norm Macro Path Inducing 10.0% Aggregate Fallen-Angel Rate",
                 fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved reverse stress shock profile figure to {save_path}")


def run_full_stress_pipeline():
    """Execute complete stress testing and sector analysis workflow."""
    logger.info("==================================================================")
    logger.info("EXECUTING MACRO STRESS TESTING & SECTOR ANALYSIS ENGINE (A3 & A7)")
    logger.info("==================================================================")

    # 1. Load data
    panel_path = PROCESSED_DIR / "panel_firmq.parquet"
    scenarios_path = PROCESSED_DIR / "scenarios.parquet"
    macro_path = PROCESSED_DIR / "macro_q.parquet"

    if not scenarios_path.exists():
        logger.info("Scenarios file missing; executing var_scenarios pipeline first...")
        from src.credit.stress.var_scenarios import run_var_scenarios_pipeline
        run_var_scenarios_pipeline()

    panel_df = pd.read_parquet(panel_path)
    scenarios_df = pd.read_parquet(scenarios_path)
    macro_df = pd.read_parquet(macro_path)

    # 2. Fit fallen angel model
    logit_res, params, cov_params, spec_features = fit_fallen_angel_forecasting_model(panel_df)

    # 3. Evaluate scenarios and sector vulnerability
    eval_results = evaluate_scenarios_over_horizon(
        panel_df, scenarios_df, params, cov_params, spec_features, n_bootstrap=500, seed=42
    )
    sector_df = eval_results["sector_df"]

    # 4. Identify most vulnerable sectors
    # Tightening (S1)
    s1_vulnerable = sector_df.sort_values("delta_p_S1", ascending=False).iloc[0]
    s1_top_sec = s1_vulnerable["sector_ff12"]
    s1_top_delta = float(s1_vulnerable["delta_p_S1"])
    logger.info(f"Most vulnerable sector under S1 Monetary Tightening: {s1_top_sec} (ΔP={s1_top_delta*100:+.2f}pp)")
    save_result_metric("vulnerable_sector_s1_name", s1_top_sec, spec="S1 Tightening", notes="Most vulnerable sector under monetary tightening")
    save_result_metric("vulnerable_sector_s1_delta", s1_top_delta, spec="S1 Tightening", notes="Delta P(FA) of most vulnerable sector under tightening")

    # Stagflation (S3)
    s3_vulnerable = sector_df.sort_values("delta_p_S3", ascending=False).iloc[0]
    s3_top_sec = s3_vulnerable["sector_ff12"]
    s3_top_delta = float(s3_vulnerable["delta_p_S3"])
    logger.info(f"Most vulnerable sector under S3 Stagflation: {s3_top_sec} (ΔP={s3_top_delta*100:+.2f}pp)")
    save_result_metric("vulnerable_sector_s3_name", s3_top_sec, spec="S3 Stagflation", notes="Most vulnerable sector under stagflation")
    save_result_metric("vulnerable_sector_s3_delta", s3_top_delta, spec="S3 Stagflation", notes="Delta P(FA) of most vulnerable sector under stagflation")

    # Save complete sector table to CSV
    sector_table_path = ROOT_DIR / "results" / "tables" / "sector_stress_vulnerability.csv"
    sector_table_path.parent.mkdir(parents=True, exist_ok=True)
    sector_df.to_csv(sector_table_path, index=False)
    logger.info(f"Saved sector vulnerability metrics to {sector_table_path}")

    # 5. Generate Figures
    plot_sector_vulnerability_heatmap(sector_df)
    plot_stress_test_fa_distribution(eval_results)

    # 6. N5 Reverse Stress Test
    rev_results = execute_reverse_stress_test(
        panel_df, macro_df, params, spec_features, target_rate=0.10, horizon=4
    )
    plot_reverse_stress_shock_profile(rev_results, macro_df)

    logger.info("==================================================================")
    logger.info("ALL STRESS TESTING & SECTOR ANALYSIS TASKS COMPLETED SUCCESSFULLY")
    logger.info("==================================================================")
    return eval_results, rev_results


if __name__ == "__main__":
    run_full_stress_pipeline()
