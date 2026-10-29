"""
Fallen-Angel Binary Forecasting Pipeline (Specification Ladder S1 - S4).
Estimates 12-month forward Fallen-Angel transition probabilities for Investment Grade
issuers using Firth penalized and L2-regularized logistic regression.
Strictly adheres to Section 5 (Validation Protocol) and Section 6.4 (Results Registry).
"""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_curve,
    precision_recall_curve
)
from sklearn.calibration import calibration_curve

# Root path and imports
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.credit.utils.helpers import save_result_metric

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Firth Penalized Logistic Regression Implementation
# ----------------------------------------------------------------------
class FirthLogisticRegression:
    """
    Firth's Penalized Likelihood Logistic Regression.
    Removes first-order bias and resolves quasi-complete separation in rare-event models
    by adding Jeffreys invariant prior penalty: 0.5 * log |X^T W X|.
    """
    def __init__(self, max_iter: int = 50, tol: float = 1e-6, penalty_ridge: float = 1e-5):
        self.max_iter = max_iter
        self.tol = tol
        self.penalty_ridge = penalty_ridge
        self.beta = None
        self.intercept_ = None
        self.coef_ = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        """Fit model with intercept automatically appended."""
        n, p = X.shape
        X_design = np.column_stack([np.ones(n), X])
        k = p + 1
        beta = np.zeros(k)

        for it in range(self.max_iter):
            eta = np.clip(X_design @ beta, -30.0, 30.0)
            pi = 1.0 / (1.0 + np.exp(-eta))
            w = np.clip(pi * (1.0 - pi), 1e-10, None)
            
            # Fisher Information matrix
            XtW = X_design.T * w
            XtWX = XtW @ X_design + self.penalty_ridge * np.eye(k)
            
            try:
                inv_XtWX = np.linalg.pinv(XtWX)
            except np.linalg.LinAlgError:
                inv_XtWX = np.linalg.inv(XtWX + 1e-3 * np.eye(k))

            # Hat matrix diagonal leverages: h_i = w_i * x_i^T (X^T W X)^-1 x_i
            h = w * np.sum((X_design @ inv_XtWX) * X_design, axis=1)
            
            # Firth modified score function: U*(beta) = X^T (y - pi + h*(0.5 - pi))
            score = X_design.T @ (y - pi + h * (0.5 - pi))
            step = inv_XtWX @ score
            
            # Step dampening for numerical robustness
            step_norm = np.max(np.abs(step))
            scale = 1.0
            if step_norm > 2.0:
                scale = 2.0 / step_norm
            beta += scale * step

            if step_norm < self.tol:
                logger.debug(f"Firth logit converged in {it+1} iterations.")
                break

        self.beta = beta
        self.intercept_ = beta[0]
        self.coef_ = beta[1:]
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict probabilities (returns shape [n, 2])."""
        n = X.shape[0]
        X_design = np.column_stack([np.ones(n), X])
        eta = np.clip(X_design @ self.beta, -30.0, 30.0)
        p1 = 1.0 / (1.0 + np.exp(-eta))
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])


# ----------------------------------------------------------------------
# Fast Exact DeLong Test for Correlated ROC AUCs
# ----------------------------------------------------------------------
def delong_roc_test(y_true: np.ndarray, pred_a: np.ndarray, pred_b: np.ndarray) -> Tuple[float, float, float, float, float]:
    """
    Computes exact DeLong test for paired ROC curves on identical out-of-sample data.
    Returns:
        auc_a, auc_b, diff (auc_a - auc_b), z_statistic, p_value
    """
    y_true = np.asarray(y_true).astype(int)
    pos_mask = (y_true == 1)
    neg_mask = (y_true == 0)
    m = np.sum(pos_mask)
    n = np.sum(neg_mask)

    pa_pos = pred_a[pos_mask]
    pa_neg = pred_a[neg_mask]
    pb_pos = pred_b[pos_mask]
    pb_neg = pred_b[neg_mask]

    # Mann-Whitney structural components
    v10_a = np.mean(pa_pos[:, None] > pa_neg[None, :], axis=1) + 0.5 * np.mean(pa_pos[:, None] == pa_neg[None, :], axis=1)
    v01_a = np.mean(pa_pos[:, None] > pa_neg[None, :], axis=0) + 0.5 * np.mean(pa_pos[:, None] == pa_neg[None, :], axis=0)

    v10_b = np.mean(pb_pos[:, None] > pb_neg[None, :], axis=1) + 0.5 * np.mean(pb_pos[:, None] == pb_neg[None, :], axis=1)
    v01_b = np.mean(pb_pos[:, None] > pb_neg[None, :], axis=0) + 0.5 * np.mean(pb_pos[:, None] == pb_neg[None, :], axis=0)

    auc_a = float(np.mean(v10_a))
    auc_b = float(np.mean(v10_b))

    cov10 = np.cov(np.vstack([v10_a, v10_b]))
    cov01 = np.cov(np.vstack([v01_a, v01_b]))
    s = cov10 / m + cov01 / n
    var_diff = s[0, 0] + s[1, 1] - 2.0 * s[0, 1]

    diff = auc_a - auc_b
    z_stat = float(diff / np.sqrt(max(var_diff, 1e-12)))
    p_value = float(2.0 * (1.0 - stats.norm.cdf(np.abs(z_stat))))

    return auc_a, auc_b, diff, z_stat, p_value


# ----------------------------------------------------------------------
# Core Modelling & Evaluation Function
# ----------------------------------------------------------------------
def prepare_binary_dataset(df: pd.DataFrame, sample_type: str = "ig") -> pd.DataFrame:
    """Prepare feature dataset with clean dummy variables and interaction terms."""
    if sample_type == "ig":
        sub = df[(df["is_ig"] == 1) & (df["fa_h"].notna())].copy()
    elif sample_type == "bbb":
        sub = df[(df["rating_num"].isin([8, 9, 10])) & (df["fa_h"].notna())].copy()
    else:
        raise ValueError(f"Unknown sample_type: {sample_type}")

    # Watch and Outlook indicator dummies
    sub["watch_neg"] = (sub["watch"] == "NEG").astype(float)
    sub["watch_pos"] = (sub["watch"] == "POS").astype(float)
    sub["outlook_neg"] = (sub["outlook"] == "NEG").astype(float)
    sub["outlook_pos"] = (sub["outlook"] == "POS").astype(float)

    # Standardize interaction components or raw interactions
    sub["leverage_x_d4_fedfunds"] = sub["leverage"] * sub["d4_fedfunds"]
    sub["intcov_x_d4_hy_oas"] = sub["interest_coverage"] * sub["d4_hy_oas"]

    return sub


def get_specification_features() -> Dict[str, List[str]]:
    """Define features for Section 5 M3 Specification Ladder."""
    s1 = ["rating_num", "watch_neg", "watch_pos", "outlook_neg", "outlook_pos"]
    s2 = s1 + ["leverage", "interest_coverage", "roa", "current_ratio", "cash_to_assets", "log_assets", "tangibility"]
    s3 = s2 + ["fedfunds", "d4_fedfunds", "term_spread", "hy_oas", "d4_hy_oas", "cpi_yoy", "gdp_yoy"]
    s4 = s3 + ["leverage_x_d4_fedfunds", "intcov_x_d4_hy_oas"]
    return {"S1": s1, "S2": s2, "S3": s3, "S4": s4}


def fit_and_evaluate_specifications(panel_path: Path = None) -> Dict[str, Any]:
    """Execute the full binary fallen-angel forecasting estimation pipeline."""
    if panel_path is None:
        panel_path = ROOT_DIR / "data" / "processed" / "panel_firmq.parquet"

    logger.info(f"Loading firm panel from {panel_path}...")
    df = pd.read_parquet(panel_path)
    
    spec_features = get_specification_features()
    all_results = {}

    for sample_name in ["ig", "bbb"]:
        pop_label = "Investment Grade (Full)" if sample_name == "ig" else "BBB-Band Subsample"
        logger.info(f"\n==========================================")
        logger.info(f"Estimating Specification Ladder for {pop_label}")
        logger.info(f"==========================================")
        
        data = prepare_binary_dataset(df, sample_type=sample_name)
        train_df = data[data["split"] == "train"].copy()
        val_df = data[data["split"] == "validation"].copy()
        test_df = data[data["split"] == "test"].copy()

        y_train = train_df["fa_h"].values.astype(int)
        y_val = val_df["fa_h"].values.astype(int)
        y_test = test_df["fa_h"].values.astype(int)

        logger.info(f"Sample breakdown: Train={len(train_df)} (pos={y_train.sum()}), "
                    f"Val={len(val_df)} (pos={y_val.sum()}), "
                    f"Test={len(test_df)} (pos={y_test.sum()})")

        sample_res = {
            "predictions_test": {},
            "predictions_val": {},
            "metrics": {},
            "y_test": y_test,
            "y_val": y_val,
            "test_df": test_df
        }

        # Fit each specification (L2 and Firth)
        for spec_name, cols in spec_features.items():
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(train_df[cols])
            X_val_scaled = scaler.transform(val_df[cols])
            X_test_scaled = scaler.transform(test_df[cols])

            # 1. L2 Regularized Logistic Regression
            clf_l2 = LogisticRegression(penalty="l2", C=1.0, max_iter=1000, random_state=42)
            clf_l2.fit(X_train_scaled, y_train)
            p_test_l2 = clf_l2.predict_proba(X_test_scaled)[:, 1]
            p_val_l2 = clf_l2.predict_proba(X_val_scaled)[:, 1]

            # 2. Firth Penalized Logistic Regression
            clf_firth = FirthLogisticRegression(max_iter=30)
            clf_firth.fit(X_train_scaled, y_train)
            p_test_firth = clf_firth.predict_proba(X_test_scaled)[:, 1]

            # Compute out-of-sample metrics for L2
            auc = roc_auc_score(y_test, p_test_l2)
            pr_auc = average_precision_score(y_test, p_test_l2)
            brier = brier_score_loss(y_test, p_test_l2)
            ll = log_loss(y_test, p_test_l2)

            # Top decile capture rate and lift
            top10_threshold = np.percentile(p_test_l2, 90)
            top10_pos = y_test[p_test_l2 >= top10_threshold].sum()
            top10_capture = float(top10_pos / max(y_test.sum(), 1))
            top10_lift = float(top10_capture / 0.10)

            # Brier calibration score (decomposition: reliability / calibration error)
            prob_true, prob_pred = calibration_curve(y_test, p_test_l2, n_bins=10, strategy="quantile")
            brier_cal = float(np.mean((prob_true - prob_pred) ** 2))

            # Firth metrics
            auc_firth = roc_auc_score(y_test, p_test_firth)
            pr_auc_firth = average_precision_score(y_test, p_test_firth)
            brier_firth = brier_score_loss(y_test, p_test_firth)

            sample_res["predictions_test"][spec_name] = p_test_l2
            sample_res["predictions_val"][spec_name] = p_val_l2
            sample_res["predictions_test"][f"{spec_name}_firth"] = p_test_firth

            metric_dict = {
                "roc_auc": float(auc),
                "pr_auc": float(pr_auc),
                "brier_score": float(brier),
                "log_loss": float(ll),
                "top10_capture": float(top10_capture),
                "top10_lift": float(top10_lift),
                "brier_calibration": float(brier_cal),
                "roc_auc_firth": float(auc_firth),
                "pr_auc_firth": float(pr_auc_firth),
                "brier_firth": float(brier_firth),
                "n_obs": len(y_test),
                "n_pos": int(y_test.sum())
            }
            sample_res["metrics"][spec_name] = metric_dict

            logger.info(f"[{sample_name.upper()} {spec_name}] AUC={auc:.4f} | PR-AUC={pr_auc:.4f} | "
                        f"Brier={brier:.4f} | Top10Capture={top10_capture*100:.1f}% (Lift={top10_lift:.2f}x) | "
                        f"Firth AUC={auc_firth:.4f}")

            # Save to JSON registry
            prefix = f"fa_{sample_name}_{spec_name.lower()}"
            save_result_metric(f"{prefix}_auc_test", auc, n=len(y_test), spec=spec_name, notes=f"ROC-AUC on test {pop_label}")
            save_result_metric(f"{prefix}_prauc_test", pr_auc, n=len(y_test), spec=spec_name, notes=f"PR-AUC on test {pop_label}")
            save_result_metric(f"{prefix}_brier_test", brier, n=len(y_test), spec=spec_name, notes=f"Brier score on test {pop_label}")
            save_result_metric(f"{prefix}_logloss_test", ll, n=len(y_test), spec=spec_name, notes=f"Log-loss on test {pop_label}")
            save_result_metric(f"{prefix}_top10_capture_test", top10_capture, n=len(y_test), spec=spec_name, notes=f"Top decile capture {pop_label}")
            save_result_metric(f"{prefix}_top10_lift_test", top10_lift, n=len(y_test), spec=spec_name, notes=f"Top decile lift {pop_label}")

        # Compute DeLong Tests for pairs
        logger.info(f"\n--- DeLong Hypothesis Tests for {pop_label} ---")
        p_test_dict = sample_res["predictions_test"]
        
        # S2 vs S1 (Value of Fundamentals)
        auc_s2, auc_s1, diff_21, z_21, p_21 = delong_roc_test(y_test, p_test_dict["S2"], p_test_dict["S1"])
        logger.info(f"S2 vs S1: AUC_S2={auc_s2:.4f}, AUC_S1={auc_s1:.4f}, Diff={diff_21:+.4f}, Z={z_21:.3f}, p-val={p_21:.4f}")
        save_result_metric(f"fa_{sample_name}_delong_s2_vs_s1_diff", diff_21, spec="S2 vs S1", notes="AUC diff S2 - S1")
        save_result_metric(f"fa_{sample_name}_delong_s2_vs_s1_z", z_21, spec="S2 vs S1", notes="Z-stat S2 vs S1")
        save_result_metric(f"fa_{sample_name}_delong_s2_vs_s1_pval", p_21, spec="S2 vs S1", notes="p-val S2 vs S1")

        # S3 vs S2 (Hypothesis H2: Value of Macro Block)
        auc_s3, auc_s2_comp, diff_32, z_32, p_32 = delong_roc_test(y_test, p_test_dict["S3"], p_test_dict["S2"])
        logger.info(f"S3 vs S2 (Hypothesis H2): AUC_S3={auc_s3:.4f}, AUC_S2={auc_s2_comp:.4f}, Diff={diff_32:+.4f}, Z={z_32:.3f}, p-val={p_32:.4f}")
        save_result_metric(f"fa_{sample_name}_delong_s3_vs_s2_diff", diff_32, spec="S3 vs S2", notes="AUC diff S3 - S2 (Hypothesis H2)")
        save_result_metric(f"fa_{sample_name}_delong_s3_vs_s2_z", z_32, spec="S3 vs S2", notes="Z-stat S3 vs S2")
        save_result_metric(f"fa_{sample_name}_delong_s3_vs_s2_pval", p_32, spec="S3 vs S2", notes="p-val S3 vs S2 (Hypothesis H2)")

        # S4 vs S3 (Value of Non-linear Macro*Firm Interactions)
        auc_s4, auc_s3_comp, diff_43, z_43, p_43 = delong_roc_test(y_test, p_test_dict["S4"], p_test_dict["S3"])
        logger.info(f"S4 vs S3: AUC_S4={auc_s4:.4f}, AUC_S3={auc_s3_comp:.4f}, Diff={diff_43:+.4f}, Z={z_43:.3f}, p-val={p_43:.4f}")
        save_result_metric(f"fa_{sample_name}_delong_s4_vs_s3_diff", diff_43, spec="S4 vs S3", notes="AUC diff S4 - S3")
        save_result_metric(f"fa_{sample_name}_delong_s4_vs_s3_z", z_43, spec="S4 vs S3", notes="Z-stat S4 vs S3")
        save_result_metric(f"fa_{sample_name}_delong_s4_vs_s3_pval", p_43, spec="S4 vs S3", notes="p-val S4 vs S3")

        all_results[sample_name] = sample_res

    # Generate Figures
    generate_publication_figures(all_results)
    return all_results


# ----------------------------------------------------------------------
# Publication Figure Generation
# ----------------------------------------------------------------------
def generate_publication_figures(results: Dict[str, Any]):
    """Generate publication-ready figures in results/figures/."""
    fig_dir = ROOT_DIR / "results" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    colors = {"S1": "#4A7BB0", "S2": "#388E3C", "S3": "#D32F2F", "S4": "#7B1FA2"}
    spec_labels = {
        "S1": "S1: Baseline (Rating + Watch/Outlook)",
        "S2": "S2: + Firm Fundamentals",
        "S3": "S3: + Macro Block (Full Point-in-Time)",
        "S4": "S4: + Macro * Firm Interactions"
    }

    # 1. ROC and PR Curves Out-of-Sample (IG and BBB band side-by-side)
    fig, axes = plt.subplots(2, 2, figsize=(14, 12), dpi=300)
    
    for row_idx, sample_name in enumerate(["ig", "bbb"]):
        sample_title = "Full Investment Grade (AAA-BBB)" if sample_name == "ig" else "BBB-Band Subsample (Cliff Edge)"
        y_test = results[sample_name]["y_test"]
        preds = results[sample_name]["predictions_test"]
        metrics = results[sample_name]["metrics"]

        # ROC Curve (Left column)
        ax_roc = axes[row_idx, 0]
        ax_roc.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Chance (AUC = 0.50)")
        for spec in ["S1", "S2", "S3", "S4"]:
            fpr, tpr, _ = roc_curve(y_test, preds[spec])
            auc_val = metrics[spec]["roc_auc"]
            ax_roc.plot(fpr, tpr, color=colors[spec], lw=2.2, label=f"{spec_labels[spec]} (AUC = {auc_val:.3f})")
        ax_roc.set_xlim([-0.02, 1.02])
        ax_roc.set_ylim([-0.02, 1.02])
        ax_roc.set_xlabel("False Positive Rate (1 - Specificity)", fontsize=11, fontweight="bold")
        ax_roc.set_ylabel("True Positive Rate (Sensitivity)", fontsize=11, fontweight="bold")
        ax_roc.set_title(f"Out-of-Sample ROC Curves (2020-2025)\n{sample_title}", fontsize=12, fontweight="bold")
        ax_roc.legend(loc="lower right", frameon=True, fontsize=9)

        # PR Curve (Right column)
        ax_pr = axes[row_idx, 1]
        base_rate = y_test.mean()
        ax_pr.axhline(base_rate, color="k", linestyle="--", alpha=0.5, label=f"Base Rate ({base_rate*100:.1f}%)")
        for spec in ["S1", "S2", "S3", "S4"]:
            prec, rec, _ = precision_recall_curve(y_test, preds[spec])
            pr_val = metrics[spec]["pr_auc"]
            ax_pr.plot(rec, prec, color=colors[spec], lw=2.2, label=f"{spec_labels[spec]} (PR-AUC = {pr_val:.3f})")
        ax_pr.set_xlim([-0.02, 1.02])
        ax_pr.set_ylim([-0.02, 1.02])
        ax_pr.set_xlabel("Recall (True Positive Rate)", fontsize=11, fontweight="bold")
        ax_pr.set_ylabel("Precision (PPV)", fontsize=11, fontweight="bold")
        ax_pr.set_title(f"Out-of-Sample Precision-Recall Curves (2020-2025)\n{sample_title}", fontsize=12, fontweight="bold")
        ax_pr.legend(loc="upper right", frameon=True, fontsize=9)

    plt.tight_layout()
    roc_pr_path = fig_dir / "roc_pr_curves_oos.png"
    plt.savefig(roc_pr_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved ROC/PR curves to {roc_pr_path}")

    # 2. Calibration Curves (Reliability Diagrams)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), dpi=300)
    for idx, sample_name in enumerate(["ig", "bbb"]):
        sample_title = "Full Investment Grade (AAA-BBB)" if sample_name == "ig" else "BBB-Band Subsample (Cliff Edge)"
        ax = axes[idx]
        y_test = results[sample_name]["y_test"]
        preds = results[sample_name]["predictions_test"]
        metrics = results[sample_name]["metrics"]

        ax.plot([0, 1], [0, 1], "k--", alpha=0.6, label="Perfect Calibration")
        for spec in ["S1", "S2", "S3", "S4"]:
            prob_true, prob_pred = calibration_curve(y_test, preds[spec], n_bins=10, strategy="quantile")
            brier_val = metrics[spec]["brier_score"]
            ax.plot(prob_pred, prob_true, marker="o", lw=2, color=colors[spec],
                    label=f"{spec_labels[spec]} (Brier = {brier_val:.4f})")

        ax.set_xlim([-0.02, 0.70])
        ax.set_ylim([-0.02, 0.70])
        ax.set_xlabel("Mean Predicted Fallen-Angel Probability", fontsize=11, fontweight="bold")
        ax.set_ylabel("Empirical Fraction of Fallen Angels", fontsize=11, fontweight="bold")
        ax.set_title(f"Reliability Diagrams (10-Quantile Calibration)\n{sample_title}", fontsize=12, fontweight="bold")
        ax.legend(loc="upper left", frameon=True, fontsize=9)

    plt.tight_layout()
    cal_path = fig_dir / "calibration_curves.png"
    plt.savefig(cal_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved calibration curves to {cal_path}")

    # 3. Top-Decile Lift and Cumulative Gains Chart
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), dpi=300)
    for idx, sample_name in enumerate(["ig", "bbb"]):
        sample_title = "Full Investment Grade" if sample_name == "ig" else "BBB-Band Subsample"
        ax = axes[idx]
        y_test = results[sample_name]["y_test"]
        preds = results[sample_name]["predictions_test"]
        n_total = len(y_test)
        total_pos = y_test.sum()

        deciles = np.linspace(0.1, 1.0, 10)
        ax.plot([0, 100], [0, 100], "k--", alpha=0.5, label="Random Selection (Lift = 1.0x)")

        for spec in ["S1", "S2", "S3", "S4"]:
            captures = []
            for d in deciles:
                cutoff = np.percentile(preds[spec], (1.0 - d) * 100)
                cap = y_test[preds[spec] >= cutoff].sum() / max(total_pos, 1) * 100.0
                captures.append(cap)
            lift_top10 = captures[0] / 10.0
            ax.plot(deciles * 100, captures, marker="s", lw=2.2, color=colors[spec],
                    label=f"{spec} (Top 10% Capture: {captures[0]:.1f}%, Lift: {lift_top10:.2f}x)")

        ax.set_xlim([0, 105])
        ax.set_ylim([0, 105])
        ax.set_xlabel("Top Decile Population Examined (%)", fontsize=11, fontweight="bold")
        ax.set_ylabel("Cumulative % of Realized Fallen Angels Captured", fontsize=11, fontweight="bold")
        ax.set_title(f"Cumulative Gains & Decile Capture Rate (2020-2025)\n{sample_title}", fontsize=12, fontweight="bold")
        ax.legend(loc="lower right", frameon=True, fontsize=9)

    plt.tight_layout()
    lift_path = fig_dir / "top_decile_lift.png"
    plt.savefig(lift_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved top decile lift figure to {lift_path}")


if __name__ == "__main__":
    fit_and_evaluate_specifications()
