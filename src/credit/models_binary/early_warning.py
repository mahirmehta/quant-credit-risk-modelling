"""
Early-Warning Lead Time Analysis (N6).
Compares the point-in-time warning lead time of the macro-augmented Fallen-Angel model (S3)
against S&P Negative CreditWatch and Negative Outlook actions for all realized fallen angels
in the out-of-sample test period (2020-2025: COVID shock + 2022-2023 rate hiking cycle).
"""

import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_curve

# Root path and imports
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.credit.utils.helpers import save_result_metric

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def compute_early_warning_lead_times(panel_path: Path = None) -> Dict[str, Any]:
    """
    Executes N6 early-warning evaluation:
    1. Calibrates alert threshold tau on validation set (2015-2019) to achieve 85% sensitivity.
    2. Identifies all realized fallen angel downgrade events in the test set (2020-2025).
    3. Calculates point-in-time lead times (in quarters) for:
       (a) Macro-augmented model (S3) crossing threshold tau.
       (b) Rating agency placing issuer on Negative CreditWatch / Negative Outlook.
    4. Quantifies lead time advantage, saves metrics to JSON, and generates publication figure.
    """
    if panel_path is None:
        panel_path = ROOT_DIR / "data" / "processed" / "panel_firmq.csv"

    logger.info(f"[Early-Warning] Loading panel from {panel_path}...")
    df = pd.read_csv(panel_path)
    
    # Filter to investment grade records
    df["qdate"] = pd.to_datetime(df["qdate"])
    df = df.sort_values(["gvkey", "qdate"]).reset_index(drop=True)

    # Indicator features
    df["watch_neg"] = (df["watch"] == "NEG").astype(float)
    df["watch_pos"] = (df["watch"] == "POS").astype(float)
    df["outlook_neg"] = (df["outlook"] == "NEG").astype(float)
    df["outlook_pos"] = (df["outlook"] == "POS").astype(float)

    s3_cols = [
        "rating_num", "watch_neg", "watch_pos", "outlook_neg", "outlook_pos",
        "leverage", "interest_coverage", "roa", "current_ratio", "cash_to_assets", "log_assets", "tangibility",
        "fedfunds", "d4_fedfunds", "term_spread", "hy_oas", "d4_hy_oas", "cpi_yoy", "gdp_yoy"
    ]

    ig_df = df[(df["is_ig"] == 1) & (df["fa_h"].notna())].copy()
    train_df = ig_df[ig_df["split"] == "train"].copy()
    val_df = ig_df[ig_df["split"] == "validation"].copy()
    test_df = ig_df[ig_df["split"] == "test"].copy()

    # 1. Fit S3 Macro Model on Train (<=2014)
    scaler = StandardScaler()
    X_train = scaler.fit_transform(train_df[s3_cols])
    y_train = train_df["fa_h"].values.astype(int)

    clf_s3 = LogisticRegression(penalty="l2", C=1.0, max_iter=1000, random_state=42)
    clf_s3.fit(X_train, y_train)

    # 2. Calibrate Alert Threshold tau on Validation Set (2015-2019)
    X_val = scaler.transform(val_df[s3_cols])
    y_val = val_df["fa_h"].values.astype(int)
    p_val = clf_s3.predict_proba(X_val)[:, 1]

    fpr_v, tpr_v, thresholds_v = roc_curve(y_val, p_val)
    # Find index achieving at least 85% sensitivity (TPR >= 0.85)
    target_sens = 0.85
    idx_sens = np.where(tpr_v >= target_sens)[0][0]
    tau_alert = float(thresholds_v[idx_sens])
    val_tpr = float(tpr_v[idx_sens])
    val_fpr = float(fpr_v[idx_sens])

    logger.info(f"[Threshold Calibration] Selected Alert Threshold tau = {tau_alert:.4f} "
                f"(Validation TPR = {val_tpr*100:.2f}%, FPR = {val_fpr*100:.2f}%)")

    save_result_metric("early_warning_alert_threshold", tau_alert, spec="S3", notes="Alert threshold calibrated on validation set")
    save_result_metric("early_warning_val_sensitivity", val_tpr, spec="S3", notes="Validation sensitivity at alert threshold")
    save_result_metric("early_warning_val_fpr", val_fpr, spec="S3", notes="Validation FPR at alert threshold")

    # 3. Score the full panel with the point-in-time model
    X_full = scaler.transform(df[s3_cols])
    df["pred_p_s3"] = clf_s3.predict_proba(X_full)[:, 1]
    df["model_alert"] = (df["pred_p_s3"] >= tau_alert).astype(int)
    df["agency_alert"] = ((df["watch"] == "NEG") | (df["outlook"] == "NEG")).astype(int)

    # 4. Identify Realized Fallen Angel Events in Out-of-Sample Test Period (2020-2025)
    # An event occurs when an issuer was IG (rating_num <= 10) in previous quarter
    # and crosses into speculative grade (rating_num >= 11) during the test window.
    df["prev_rating"] = df.groupby("gvkey")["rating_num"].shift(1)
    df["prev_qdate"] = df.groupby("gvkey")["qdate"].shift(1)

    test_fa_events = df[
        (df["split"] == "test") &
        (df["prev_rating"] <= 10) &
        (df["rating_num"] >= 11)
    ].copy()

    # Drop duplicate events for same gvkey if re-transitioning within 1 year; keep first transition
    test_fa_events = test_fa_events.drop_duplicates(subset=["gvkey"], keep="first")
    n_fa = len(test_fa_events)
    logger.info(f"[Test Window] Found {n_fa} distinct realized Fallen Angel transitions in 2020-2025.")

    # 5. Calculate Lead Times for each Fallen Angel issuer
    lead_time_records = []
    max_lookback_q = 8  # Look back up to 8 quarters (2 years)

    for _, row in test_fa_events.iterrows():
        gvkey = row["gvkey"]
        t_event = row["qdate"]

        # Extract issuer trajectory prior to event date
        prior_hist = df[
            (df["gvkey"] == gvkey) &
            (df["qdate"] < t_event)
        ].sort_values("qdate", ascending=False).head(max_lookback_q)

        # Map elapsed quarters: (t_event - qdate) in quarter steps
        # Using exact quarter counting
        event_period = pd.Period(t_event, freq="Q")
        prior_hist["lead_q"] = prior_hist["qdate"].apply(lambda q: (event_period - pd.Period(q, freq="Q")).n)

        # Model alert lead time (earliest alert in the lookback window)
        model_alerts = prior_hist[prior_hist["model_alert"] == 1]
        if len(model_alerts) > 0:
            lead_model = int(model_alerts["lead_q"].max())
        else:
            lead_model = 0

        # Agency alert lead time (earliest negative watch/outlook in lookback window)
        agency_alerts = prior_hist[prior_hist["agency_alert"] == 1]
        if len(agency_alerts) > 0:
            lead_agency = int(agency_alerts["lead_q"].max())
        else:
            lead_agency = 0

        advantage = lead_model - lead_agency

        lead_time_records.append({
            "gvkey": gvkey,
            "event_date": str(t_event.date()),
            "rating_before": int(row["prev_rating"]),
            "rating_after": int(row["rating_num"]),
            "lead_time_model": lead_model,
            "lead_time_agency": lead_agency,
            "lead_time_advantage": advantage
        })

    lead_df = pd.DataFrame(lead_time_records)

    # 6. Summary Statistics
    mean_model = float(lead_df["lead_time_model"].mean())
    median_model = float(lead_df["lead_time_model"].median())
    mean_agency = float(lead_df["lead_time_agency"].mean())
    median_agency = float(lead_df["lead_time_agency"].median())
    mean_adv = float(lead_df["lead_time_advantage"].mean())
    median_adv = float(lead_df["lead_time_advantage"].median())

    pct_earlier = float((lead_df["lead_time_advantage"] > 0).mean() * 100.0)
    pct_same = float((lead_df["lead_time_advantage"] == 0).mean() * 100.0)
    pct_later = float((lead_df["lead_time_advantage"] < 0).mean() * 100.0)

    logger.info("\n==========================================")
    logger.info("EARLY WARNING LEAD TIME SUMMARY (2020-2025)")
    logger.info("==========================================")
    logger.info(f"Number of Realized Fallen Angels: {n_fa}")
    logger.info(f"Model Alert Lead Time (Quarters):  Mean = {mean_model:.2f} | Median = {median_model:.1f}")
    logger.info(f"Agency Action Lead Time (Quarters): Mean = {mean_agency:.2f} | Median = {median_agency:.1f}")
    logger.info(f"Lead Time Advantage (Quarters):    Mean = {mean_adv:+.2f} | Median = {median_adv:+.1f}")
    logger.info(f"Distribution: Earlier than Agency = {pct_earlier:.1f}% | Synchronous = {pct_same:.1f}% | Later = {pct_later:.1f}%")

    # Save to JSON registry
    save_result_metric("early_warning_fa_count_test", n_fa, notes="Distinct fallen angels in 2020-2025")
    save_result_metric("early_warning_lead_time_model_mean", mean_model, notes="Mean model lead time in quarters")
    save_result_metric("early_warning_lead_time_model_median", median_model, notes="Median model lead time in quarters")
    save_result_metric("early_warning_lead_time_agency_mean", mean_agency, notes="Mean agency lead time in quarters")
    save_result_metric("early_warning_lead_time_agency_median", median_agency, notes="Median agency lead time in quarters")
    save_result_metric("early_warning_lead_time_advantage_mean", mean_adv, notes="Mean model lead time advantage in quarters")
    save_result_metric("early_warning_lead_time_advantage_median", median_adv, notes="Median model lead time advantage in quarters")
    save_result_metric("early_warning_pct_earlier", pct_earlier, notes="% FAs where model alerted earlier than agency")
    save_result_metric("early_warning_pct_same", pct_same, notes="% FAs where model alerted at same quarter as agency")
    save_result_metric("early_warning_pct_later", pct_later, notes="% FAs where agency alerted earlier than model")

    # 7. Generate Publication Figure
    generate_lead_time_figure(lead_df, mean_model, mean_agency, mean_adv, median_adv, pct_earlier)

    return {
        "lead_df": lead_df,
        "mean_model": mean_model,
        "mean_agency": mean_agency,
        "mean_advantage": mean_adv,
        "median_advantage": median_adv,
        "pct_earlier": pct_earlier
    }


def generate_lead_time_figure(
    lead_df: pd.DataFrame,
    mean_model: float,
    mean_agency: float,
    mean_adv: float,
    median_adv: float,
    pct_earlier: float
):
    """Generate publication-ready figure: results/figures/lead_time_distribution.png."""
    fig_dir = ROOT_DIR / "results" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5), dpi=300)

    # Subplot 1: Distribution of Lead Times (Model vs Agency)
    ax1 = axes[0]
    bins = np.arange(-0.5, 9.5, 1)
    ax1.hist(lead_df["lead_time_model"], bins=bins, alpha=0.65, color="#D32F2F", label=f"Model S3 (Mean: {mean_model:.2f} Q)", rwidth=0.45, align="mid")
    ax1.hist(lead_df["lead_time_agency"] + 0.45, bins=bins, alpha=0.65, color="#1976D2", label=f"Agency Watch/Outlook (Mean: {mean_agency:.2f} Q)", rwidth=0.45, align="mid")
    ax1.set_xlabel("Quarters of Warning Prior to Downgrade", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Number of Fallen Angel Issuers", fontsize=11, fontweight="bold")
    ax1.set_title("Warning Lead Time Prior to Realized Downgrade\n(2020-2025 Out-of-Sample Test Set)", fontsize=11, fontweight="bold")
    ax1.set_xticks(range(9))
    ax1.legend(loc="upper left", frameon=True, fontsize=10)

    # Subplot 2: Lead Time Advantage (Model - Agency)
    ax2 = axes[1]
    adv_bins = np.arange(-8.5, 9.5, 1)
    counts, edges, patches = ax2.hist(lead_df["lead_time_advantage"], bins=adv_bins, color="#455A64", edgecolor="white", alpha=0.85, rwidth=0.8)
    for patch, edge in zip(patches, edges[:-1]):
        if edge > 0:
            patch.set_facecolor("#2E7D32")  # Model ahead
        elif edge < 0:
            patch.set_facecolor("#C62828")  # Agency ahead
        else:
            patch.set_facecolor("#78909C")  # Equal

    ax2.axvline(mean_adv, color="#D32F2F", linestyle="--", lw=2, label=f"Mean Advantage: {mean_adv:+.2f} Q")
    ax2.axvline(median_adv, color="#0D47A1", linestyle="-.", lw=2, label=f"Median Advantage: {median_adv:+.1f} Q")
    ax2.set_xlabel("Lead Time Advantage (Quarters Earlier than Agency)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Number of Issuers", fontsize=11, fontweight="bold")
    ax2.set_title(f"Early-Warning Lead Advantage Distribution\n({pct_earlier:.1f}% Flagged Ahead of Agency Action)", fontsize=11, fontweight="bold")
    ax2.set_xticks(range(-8, 9, 2))
    ax2.legend(loc="upper left", frameon=True, fontsize=10)

    # Subplot 3: Cumulative Warning Rate as a Function of Quarters Prior to Event
    ax3 = axes[2]
    quarters_ahead = np.arange(0, 9)
    cum_model = [float((lead_df["lead_time_model"] >= q).mean() * 100.0) for q in quarters_ahead]
    cum_agency = [float((lead_df["lead_time_agency"] >= q).mean() * 100.0) for q in quarters_ahead]

    ax3.plot(quarters_ahead, cum_model, marker="o", lw=2.5, color="#D32F2F", label="Macro-Augmented Model S3")
    ax3.plot(quarters_ahead, cum_agency, marker="s", lw=2.5, color="#1976D2", label="Rating Agency Negative Watch/Outlook")
    ax3.fill_between(quarters_ahead, cum_model, cum_agency, where=(np.array(cum_model) >= np.array(cum_agency)),
                     color="#C8E6C9", alpha=0.4, label="Model Early Warning Premium")
    ax3.set_xlabel("Quarters Prior to Fallen Angel Event", fontsize=11, fontweight="bold")
    ax3.set_ylabel("% of Fallen Angels Alerted by Quarter", fontsize=11, fontweight="bold")
    ax3.set_title("Cumulative Early-Warning Detection Rate", fontsize=11, fontweight="bold")
    ax3.set_xticks(quarters_ahead)
    ax3.set_ylim([-2, 102])
    ax3.legend(loc="lower left", frameon=True, fontsize=10)

    plt.tight_layout()
    out_fig = fig_dir / "lead_time_distribution.png"
    plt.savefig(out_fig, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"[Early-Warning] Publication figure saved to {out_fig}")


if __name__ == "__main__":
    compute_early_warning_lead_times()
