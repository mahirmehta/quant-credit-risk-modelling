"""
Vector Autoregression (VAR) & Waggoner-Zha (1999) Macro Scenario Engine.
Estimates quarterly VAR on [fedfunds, term_spread, cpi_yoy, gdp_yoy, hy_oas],
evaluates lag selection, companion matrix stability, and impulse response functions (IRFs).
Generates coherent conditional stress paths for mandated scenarios:
  - S0: Baseline (Unconditional continuation)
  - S1: Monetary Tightening (+300bp FFR shock over 4 quarters)
  - S2: Hard Landing (Real GDP -3.0pp, HY OAS +400bp)
  - S3: Stagflation (CPI +3.0pp, Real GDP -1.5pp, FFR +150bp)
  - S4: Soft Landing / Easing (FFR -200bp, GDP +2.5pp, OAS -100bp)
Outputs saved to data/processed/scenarios.parquet and results/.
"""

import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from statsmodels.tsa.api import VAR

# Root path setup
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.credit.utils.helpers import save_result_metric, load_yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROCESSED_DIR = ROOT_DIR / "data" / "processed"
FIGURES_DIR = ROOT_DIR / "results" / "figures"
VAR_VARIABLES = ["fedfunds", "term_spread", "cpi_yoy", "gdp_yoy", "hy_oas"]
VARIABLE_LABELS = {
    "fedfunds": "Fed Funds Rate (%)",
    "term_spread": "10Y - 2Y Term Spread (%)",
    "cpi_yoy": "CPI Inflation YoY (%)",
    "gdp_yoy": "Real GDP Growth YoY (%)",
    "hy_oas": "High Yield OAS (%)"
}


def fit_var_model(
    macro_path: Path = None,
    maxlags: int = 6,
    selected_lag: int = None
) -> Tuple[Any, pd.DataFrame, int, Dict[str, Any]]:
    """
    Load quarterly macro data, select lag order by BIC / AIC,
    verify companion matrix eigenvalues for strict stability,
    and return fitted VARResults.
    """
    if macro_path is None:
        macro_path = PROCESSED_DIR / "macro_q.parquet"

    logger.info(f"Loading macro dataset from {macro_path}...")
    df = pd.read_parquet(macro_path)
    df["qdate"] = pd.to_datetime(df["qdate"])
    
    # Sort and set index
    vdf = df.set_index("qdate")[VAR_VARIABLES].dropna().sort_index()
    n_obs = len(vdf)
    logger.info(f"Clean quarterly observations: {n_obs} ({vdf.index.min().date()} to {vdf.index.max().date()})")

    # Order selection
    var_init = VAR(vdf)
    order_sel = var_init.select_order(maxlags=maxlags)
    bic_lag = int(order_sel.bic)
    aic_lag = int(order_sel.aic)
    hqic_lag = int(order_sel.hqic)
    logger.info(f"VAR Lag Selection: BIC={bic_lag}, AIC={aic_lag}, HQIC={hqic_lag}")

    # Determine estimation lag (defaulting to config or BIC, standard lag 2 for quarterly macro dynamics)
    if selected_lag is None:
        cfg = load_yaml("config/config.yaml")
        cfg_lags = cfg.get("models", {}).get("var", {}).get("lags", 2)
        # Use config lag (2) or BIC
        selected_lag = cfg_lags if cfg_lags is not None else bic_lag

    logger.info(f"Fitting VAR({selected_lag}) on {VAR_VARIABLES}...")
    var_model = var_init.fit(selected_lag)

    # Stability diagnostic: Companion matrix eigenvalues
    # In statsmodels, var_model.roots are the roots of det(I - A1 z - ... - Ap z^p) = 0.
    # Roots must be strictly outside the unit circle (|z| > 1),
    # which corresponds to companion matrix eigenvalues lambda = 1/z strictly inside (|lambda| < 1).
    roots = var_model.roots
    min_root_modulus = float(np.min(np.abs(roots)))
    max_eigenvalue_modulus = float(1.0 / min_root_modulus)
    is_stable = bool(var_model.is_stable())
    logger.info(f"VAR Stability Check: is_stable={is_stable}, max companion eigenvalue modulus={max_eigenvalue_modulus:.4f}")

    if not is_stable:
        logger.warning("WARNING: VAR companion matrix has eigenvalues outside unit circle!")
    else:
        logger.info("Stability confirmed: All companion eigenvalues lie strictly inside the unit circle.")

    # Save metrics to registry
    save_result_metric("var_bic_lag", bic_lag, spec="VAR order selection", notes="Minimum BIC lag order")
    save_result_metric("var_aic_lag", aic_lag, spec="VAR order selection", notes="Minimum AIC lag order")
    save_result_metric("var_selected_lag", selected_lag, spec="VAR order selection", notes="Selected lag order for scenario engine")
    save_result_metric("var_max_companion_eigenvalue", max_eigenvalue_modulus, spec=f"VAR({selected_lag})", notes="Max companion eigenvalue modulus (must be < 1.0)")
    save_result_metric("var_is_stable", 1 if is_stable else 0, spec=f"VAR({selected_lag})", notes="Binary stability indicator (1=stable)")

    diagnostics = {
        "bic_lag": bic_lag,
        "aic_lag": aic_lag,
        "hqic_lag": hqic_lag,
        "selected_lag": selected_lag,
        "is_stable": is_stable,
        "max_eigenvalue": max_eigenvalue_modulus,
        "n_obs": n_obs
    }
    return var_model, vdf, selected_lag, diagnostics


def plot_impulse_response_functions(var_model: Any, periods: int = 12, save_path: Path = None):
    """
    Compute and generate publication-quality Impulse Response Functions (IRFs)
    with 95% asymptotic error bands demonstrating economic coherence.
    """
    if save_path is None:
        save_path = FIGURES_DIR / "var_irf_plots.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Computing orthogonalized IRFs for {periods} quarters...")
    irf = var_model.irf(periods=periods)

    # Key economic transmission pairs to highlight:
    # 1. Fed Funds shock -> Term Spread (Yield curve inversion)
    # 2. Fed Funds shock -> Real GDP YoY (Monetary tightening slows growth)
    # 3. Fed Funds shock -> HY OAS (Credit spread widening)
    # 4. GDP shock -> CPI YoY (Demand pull inflation)
    # 5. HY OAS shock -> Real GDP YoY (Financial accelerator / credit drag)
    # 6. HY OAS shock -> Fed Funds (Policy easing response to financial stress)

    fig, axes = plt.subplots(2, 3, figsize=(15, 9), dpi=300)
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    shock_pairs = [
        ("fedfunds", "term_spread", "Monetary Tightening -> Term Spread\n(Yield Curve Inversion)", "#1976D2"),
        ("fedfunds", "gdp_yoy", "Monetary Tightening -> Real GDP Growth\n(Demand Compression)", "#388E3C"),
        ("fedfunds", "hy_oas", "Monetary Tightening -> HY OAS\n(Credit Spread Widening)", "#D32F2F"),
        ("gdp_yoy", "cpi_yoy", "Positive GDP Shock -> CPI Inflation\n(Phillips Curve Coherence)", "#E64A19"),
        ("hy_oas", "gdp_yoy", "Credit Spread Shock -> Real GDP Growth\n(Financial Friction Contraction)", "#7B1FA2"),
        ("hy_oas", "fedfunds", "Credit Spread Shock -> Fed Funds Rate\n(Endogenous Monetary Reaction)", "#00796B"),
    ]

    h_range = np.arange(periods + 1)
    for idx, (impulse_var, response_var, title, col) in enumerate(shock_pairs):
        ax = axes[idx // 3, idx % 3]
        imp_idx = VAR_VARIABLES.index(impulse_var)
        resp_idx = VAR_VARIABLES.index(response_var)

        # Orthogonalized IRF and standard errors
        orth_irfs = irf.orth_irfs[:, resp_idx, imp_idx]
        stderr = irf.stderr(orth=True)[:, resp_idx, imp_idx]

        ci_lower = orth_irfs - 1.96 * stderr
        ci_upper = orth_irfs + 1.96 * stderr

        ax.axhline(0.0, color="black", linestyle="--", alpha=0.6, lw=1.0)
        ax.plot(h_range, orth_irfs, color=col, lw=2.4, label="Orthogonalized IRF")
        ax.fill_between(h_range, ci_lower, ci_upper, color=col, alpha=0.18, label="95% CI")

        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("Quarters Post Shock", fontsize=10)
        ax.set_ylabel(f"Response of {response_var} (pp)", fontsize=10)
        ax.set_xlim([0, periods])
        ax.grid(True, linestyle=":", alpha=0.6)
        if idx == 0:
            ax.legend(loc="upper right", fontsize=8, frameon=True)

    plt.suptitle("Vector Autoregression Impulse Response Functions (Economic Transmission & Coherence)",
                 fontsize=14, fontweight="bold", y=0.99)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved publication-quality IRF plot to {save_path}")


def waggoner_zha_conditional_forecast(
    var_model: Any,
    history_df: pd.DataFrame,
    horizon: int = 8,
    conditions: Dict[Tuple[int, str], float] = None
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Implements Waggoner & Zha (1999) "Conditional Forecasts in Dynamic Multivariate Models".
    Finds the minimum Mahalanobis norm structural shock vector epsilon* satisfying linear
    path constraints on the VAR over horizon H.

    Parameters:
        var_model: Fitted statsmodels VARResults
        history_df: Historical dataset containing the VAR variables
        horizon: Forecast horizon quarters (default 8)
        conditions: Dictionary mapping (quarter_index, var_name) -> target_value.
                    quarter_index is 0-indexed (0 to horizon-1).

    Returns:
        y_cond: (horizon, m) conditional forecast path
        eps_star: (horizon * m) minimum-norm shock vector
        mahalanobis_norm: Euclidean norm of structural shocks (exact Mahalanobis distance)
    """
    p = var_model.k_ar
    m = len(VAR_VARIABLES)
    
    # 1. Unconditional baseline forecast
    last_p_obs = history_df[VAR_VARIABLES].values[-p:]
    y_baseline = var_model.forecast(y=last_p_obs, steps=horizon) # shape (H, m)
    y_base_flat = y_baseline.flatten()

    if conditions is None or len(conditions) == 0:
        return y_baseline, np.zeros(horizon * m), 0.0

    # 2. Moving Average (MA) matrices Phi_0, ..., Phi_{H-1}
    ma = var_model.ma_rep(maxn=horizon) # shape (H+1, m, m)
    
    # Structural decomposition: Sigma_u = C @ C^T (Cholesky)
    sigma_u = var_model.sigma_u
    C = np.linalg.cholesky(sigma_u)

    # 3. Stacked dynamic multiplier matrix G (m*H, m*H)
    # y_{T+h} - y_hat_{T+h} = sum_{k=0}^{h-1} Phi_{h-1-k} C eps_{T+k+1}
    G = np.zeros((m * horizon, m * horizon))
    for h in range(horizon):
        for k in range(h + 1):
            G[h * m : (h + 1) * m, k * m : (k + 1) * m] = ma[h - k] @ C

    # 4. Construct condition matrix R (k x m*H) and target vector r (k)
    k = len(conditions)
    R = np.zeros((k, m * horizon))
    r = np.zeros(k)

    for i, ((h_idx, var_name), val) in enumerate(conditions.items()):
        if var_name not in VAR_VARIABLES:
            raise ValueError(f"Variable {var_name} not in VAR variables {VAR_VARIABLES}")
        v_idx = VAR_VARIABLES.index(var_name)
        col_idx = h_idx * m + v_idx
        R[i, col_idx] = 1.0
        r[i] = val

    # 5. Waggoner-Zha solution:
    # Condition: R (y - y_hat) = r - R y_hat
    # <=> R G eps = q
    # Min-norm: eps* = (R G)^T [(R G) (R G)^T]^-1 q
    M = R @ G
    q = r - R @ y_base_flat

    # Use pseudo-inverse for numerical stability
    M_MT = M @ M.T
    eps_star = M.T @ np.linalg.pinv(M_MT) @ q
    
    # Conditional path
    y_cond_flat = y_base_flat + G @ eps_star
    y_cond = y_cond_flat.reshape((horizon, m))
    
    mahalanobis_norm = float(np.linalg.norm(eps_star))
    return y_cond, eps_star, mahalanobis_norm


def generate_all_scenarios(
    var_model: Any,
    history_df: pd.DataFrame,
    horizon: int = 8
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Generate the 5 mandated Section 5 scenarios over 8 quarters:
      - S0: Baseline (Unconditional VAR continuation)
      - S1: Monetary Tightening (FFR +300bp over 4 quarters, 2022-like)
      - S2: Hard Landing (Real GDP -3.0pp, HY OAS +400bp, GFC-lite)
      - S3: Stagflation (CPI +3.0pp, Real GDP -1.5pp, FFR +150bp)
      - S4: Soft Landing / Easing (FFR -200bp, GDP +2.5pp, OAS -100bp)
    Saves to data/processed/scenarios.parquet.
    """
    logger.info(f"Generating 5 conditional scenarios over {horizon} quarters...")
    p = var_model.k_ar
    m = len(VAR_VARIABLES)
    last_p = history_df[VAR_VARIABLES].values[-p:]
    base_fc = var_model.forecast(y=last_p, steps=horizon)

    last_date = history_df.index.max()
    future_dates = pd.date_range(start=last_date + pd.DateOffset(days=1), periods=horizon, freq="QE")

    scenario_specs = {}

    # S0: Baseline
    s0_cond = {}
    scenario_specs["S0"] = ("Baseline (Unconditional Continuation)", s0_cond)

    # S1: Monetary Tightening (FFR +300bp shock over 4 quarters)
    s1_cond = {}
    ffr_idx = VAR_VARIABLES.index("fedfunds")
    for h in range(4):
        # Gradual hike of +75bp, +150bp, +225bp, +300bp
        s1_cond[(h, "fedfunds")] = float(base_fc[h, ffr_idx] + 0.75 * (h + 1))
    for h in range(4, horizon):
        s1_cond[(h, "fedfunds")] = float(base_fc[h, ffr_idx] + 3.00)
    scenario_specs["S1"] = ("Monetary Tightening (+300bp FFR shock)", s1_cond)

    # S2: Hard Landing (Real GDP -3.0pp, HY OAS +400bp)
    s2_cond = {}
    gdp_idx = VAR_VARIABLES.index("gdp_yoy")
    oas_idx = VAR_VARIABLES.index("hy_oas")
    for h in range(1, 5):
        s2_cond[(h, "gdp_yoy")] = float(base_fc[h, gdp_idx] - 3.0)
        s2_cond[(h, "hy_oas")] = float(base_fc[h, oas_idx] + 4.0)
    scenario_specs["S2"] = ("Hard Landing (GDP -3.0pp, OAS +400bp)", s2_cond)

    # S3: Stagflation (CPI +3.0pp, Real GDP -1.5pp, FFR +150bp)
    s3_cond = {}
    cpi_idx = VAR_VARIABLES.index("cpi_yoy")
    for h in range(4):
        s3_cond[(h, "cpi_yoy")] = float(base_fc[h, cpi_idx] + 3.0)
        s3_cond[(h, "gdp_yoy")] = float(base_fc[h, gdp_idx] - 1.5)
        s3_cond[(h, "fedfunds")] = float(base_fc[h, ffr_idx] + 1.5)
    scenario_specs["S3"] = ("Stagflation (CPI +3.0pp, GDP -1.5pp, FFR +150bp)", s3_cond)

    # S4: Soft Landing / Easing (FFR -200bp, GDP +2.5pp, OAS -100bp)
    s4_cond = {}
    for h in range(1, 5):
        s4_cond[(h, "fedfunds")] = float(max(0.25, base_fc[h, ffr_idx] - 2.0))
        s4_cond[(h, "gdp_yoy")] = float(base_fc[h, gdp_idx] + 2.5)
        s4_cond[(h, "hy_oas")] = float(max(2.0, base_fc[h, oas_idx] - 1.0))
    scenario_specs["S4"] = ("Soft Landing / Easing (FFR -200bp, GDP +2.5pp, OAS -100bp)", s4_cond)

    all_dfs = []
    meta = {}

    for s_id, (s_name, conds) in scenario_specs.items():
        y_path, eps_star, norm = waggoner_zha_conditional_forecast(
            var_model, history_df, horizon=horizon, conditions=conds
        )
        sdf = pd.DataFrame(y_path, columns=VAR_VARIABLES)
        sdf["scenario_id"] = s_id
        sdf["scenario_name"] = s_name
        sdf["horizon_q"] = np.arange(1, horizon + 1)
        sdf["qdate"] = future_dates
        
        # Add delta transformations needed for firm modeling
        # Changes relative to baseline and 4Q differences
        # For d4_fedfunds and d4_hy_oas along path:
        # At h=1..4, comparison is against history; at h>4, against earlier quarters
        hist_ffr = history_df["fedfunds"].values
        hist_oas = history_df["hy_oas"].values
        
        full_ffr = np.concatenate([hist_ffr[-4:], sdf["fedfunds"].values])
        full_oas = np.concatenate([hist_oas[-4:], sdf["hy_oas"].values])
        
        sdf["d4_fedfunds"] = full_ffr[4:] - full_ffr[:horizon]
        sdf["d4_hy_oas"] = full_oas[4:] - full_oas[:horizon]
        sdf["d1_fedfunds"] = np.diff(np.concatenate([[hist_ffr[-1]], sdf["fedfunds"].values]))
        sdf["d1_hy_oas"] = np.diff(np.concatenate([[hist_oas[-1]], sdf["hy_oas"].values]))
        
        sdf["mahalanobis_norm"] = norm
        all_dfs.append(sdf)
        
        meta[s_id] = {
            "name": s_name,
            "norm": norm,
            "peak_ffr": float(sdf["fedfunds"].max()),
            "trough_gdp": float(sdf["gdp_yoy"].min()),
            "peak_oas": float(sdf["hy_oas"].max()),
            "peak_cpi": float(sdf["cpi_yoy"].max())
        }
        logger.info(f"[{s_id}: {s_name}] Mahalanobis Norm={norm:.3f} | Peak FFR={meta[s_id]['peak_ffr']:.2f}% | "
                    f"Trough GDP={meta[s_id]['trough_gdp']:.2f}% | Peak OAS={meta[s_id]['peak_oas']:.2f}%")
        
        # Save scenario summary metrics
        save_result_metric(f"scenario_{s_id.lower()}_norm", norm, spec=s_id, notes="Mahalanobis shock norm")
        save_result_metric(f"scenario_{s_id.lower()}_peak_oas", meta[s_id]["peak_oas"], spec=s_id, notes="Peak HY OAS")
        save_result_metric(f"scenario_{s_id.lower()}_trough_gdp", meta[s_id]["trough_gdp"], spec=s_id, notes="Trough Real GDP YoY")

    scenarios_df = pd.concat(all_dfs, ignore_index=True)
    out_parquet = PROCESSED_DIR / "scenarios.parquet"
    scenarios_df.to_parquet(out_parquet, index=False)
    logger.info(f"Saved {len(scenarios_df)} scenario rows to {out_parquet}")

    return scenarios_df, meta


def plot_scenario_paths(history_df: pd.DataFrame, scenarios_df: pd.DataFrame, save_path: Path = None):
    """
    Plot publication-quality macro scenario paths across all 5 variables,
    displaying 4 years of history (2022-2025) and the 8-quarter forecast horizon (2026-2027).
    """
    if save_path is None:
        save_path = FIGURES_DIR / "macro_scenario_paths.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    colors = {
        "S0": "#546E7A", # Gray/slate baseline
        "S1": "#1E88E5", # Blue tightening
        "S2": "#D81B60", # Red/magenta hard landing
        "S3": "#FB8C00", # Orange stagflation
        "S4": "#43A047"  # Green soft landing
    }
    linestyles = {"S0": "--", "S1": "-", "S2": "-", "S3": "-", "S4": "-"}

    # Use recent history (2021Q1 to 2025Q4)
    hist_sub = history_df[history_df.index >= "2021-01-01"].copy()
    hist_dates = hist_sub.index
    
    fig, axes = plt.subplots(3, 2, figsize=(16, 13), dpi=300)
    axes_flat = axes.flatten()

    for idx, var in enumerate(VAR_VARIABLES):
        ax = axes_flat[idx]
        
        # Plot historical series
        ax.plot(hist_dates, hist_sub[var], color="#212121", lw=2.4, label="Historical Actual (2021-2025)")
        
        # Plot each scenario path
        for s_id in ["S0", "S1", "S2", "S3", "S4"]:
            s_data = scenarios_df[scenarios_df["scenario_id"] == s_id]
            # Connect last history point to first forecast point
            plot_dates = [hist_dates[-1]] + list(s_data["qdate"])
            plot_vals = [hist_sub[var].iloc[-1]] + list(s_data[var])
            s_label = s_data["scenario_name"].iloc[0]
            ax.plot(plot_dates, plot_vals, color=colors[s_id], lw=2.2,
                    linestyle=linestyles[s_id], label=f"{s_id}: {s_label}")

        # Vertical line demarcating forecast origin
        ax.axvline(hist_dates[-1], color="black", linestyle=":", lw=1.5, alpha=0.8)
        ax.axvspan(hist_dates[-1], scenarios_df["qdate"].max(), color="#EEEEEE", alpha=0.5, label="8Q Forecast Window")

        ax.set_title(VARIABLE_LABELS[var], fontsize=12, fontweight="bold")
        ax.set_ylabel("Percent (%)", fontsize=10)
        ax.grid(True, linestyle=":", alpha=0.6)
        if idx == 0:
            ax.legend(loc="upper left", fontsize=8, frameon=True)

    # 6th panel: Mahalanobis Shock Norm Comparison
    ax_norm = axes_flat[5]
    norms = scenarios_df.groupby("scenario_id")["mahalanobis_norm"].first()
    scenario_names = [scenarios_df[scenarios_df["scenario_id"] == s]["scenario_name"].iloc[0].split("(")[0].strip()
                      for s in norms.index]
    bar_colors = [colors[s] for s in norms.index]
    bars = ax_norm.bar(norms.index, norms.values, color=bar_colors, width=0.55, edgecolor="black", alpha=0.85)
    
    for bar, val in zip(bars, norms.values):
        ax_norm.text(bar.get_x() + bar.get_width() / 2.0, val + 0.15,
                     f"{val:.2f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax_norm.set_title("Waggoner-Zha (1999) Mahalanobis Shock Norm ||ε*||_2", fontsize=12, fontweight="bold")
    ax_norm.set_ylabel("Mahalanobis Distance (Shock Norm)", fontsize=10)
    ax_norm.set_ylim([0, max(norms.values) * 1.25])
    ax_norm.set_xticks(range(len(norms)))
    ax_norm.set_xticklabels([f"{s}\n{name}" for s, name in zip(norms.index, scenario_names)], fontsize=9)
    ax_norm.grid(axis="y", linestyle=":", alpha=0.6)

    plt.suptitle("Mandated Macroeconomic Stress Testing Scenarios (8-Quarter Horizons 2026-2027)",
                 fontsize=14, fontweight="bold", y=0.99)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved publication-quality macro scenario paths plot to {save_path}")


def run_var_scenarios_pipeline():
    """Main execution entrypoint for VAR scenario modeling."""
    logger.info("Starting VAR Scenario Modeling Pipeline...")
    var_model, history_df, selected_lag, diag = fit_var_model()
    plot_impulse_response_functions(var_model, periods=12)
    scenarios_df, meta = generate_all_scenarios(var_model, history_df, horizon=8)
    plot_scenario_paths(history_df, scenarios_df)
    logger.info("VAR Scenarios Pipeline completed successfully.")
    return var_model, scenarios_df, meta


if __name__ == "__main__":
    run_var_scenarios_pipeline()
