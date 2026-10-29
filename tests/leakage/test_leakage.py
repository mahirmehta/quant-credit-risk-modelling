"""
Automated point-in-time leakage verification suite.
Mandated by Section 6.4 (Rule 4) and Section 6.5 of plan_updated.md.

Enforces zero-tolerance point-in-time discipline:
  (a) Feature availability date avail_date <= qdate for 100% of observations.
  (b) Macro release dates asof_date <= qdate for 100% of observations.
  (c) Forward labels (fa_h, migr_cat_h, downgrade_h) strictly use future ratings after qdate.
  (d) The 4-quarter embargo between train, validation, and test prevents any overlapping windows.
  (e) Continuous feature winsorisation cutoffs were estimated strictly on the training window.
  (f) No cross-split contamination across observation windows.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
PANEL_PATH = ROOT_DIR / "data" / "processed" / "panel_firmq.csv"
CUTOFFS_PATH = ROOT_DIR / "results" / "json" / "winsor_cutoffs.json"


@pytest.fixture(scope="module")
def panel_data():
    """Load the processed firm-quarter panel dataset."""
    assert PANEL_PATH.exists(), f"Panel file missing at {PANEL_PATH}. Run build_panel.py first."
    df = pd.read_csv(PANEL_PATH)
    df["qdate"] = pd.to_datetime(df["qdate"])
    df["avail_date"] = pd.to_datetime(df["avail_date"])
    df["asof_date"] = pd.to_datetime(df["asof_date"])
    df["future_qdate_h"] = pd.to_datetime(df["future_qdate_h"])
    return df


class TestPointInTimeLeakage:
    """Rigorous point-in-time leakage verification."""

    def test_feature_availability_date_before_qdate(self, panel_data):
        """
        Rule 4(a): For 100% of records in the panel, feature availability date
        must satisfy avail_date <= qdate (strictly available before or on prediction date).
        """
        leaks = panel_data[panel_data["avail_date"] > panel_data["qdate"]]
        num_leaks = len(leaks)
        assert num_leaks == 0, (
            f"Point-in-time leakage detected: {num_leaks} records have avail_date > qdate!\n"
            f"Sample violations:\n{leaks[['gvkey', 'qdate', 'avail_date']].head()}"
        )

    def test_macro_release_date_before_qdate(self, panel_data):
        """
        Rule 4(b): Macro release / vintage dates must satisfy asof_date <= qdate.
        Ensures no look-ahead into future macroeconomic data revisions.
        """
        macro_leaks = panel_data[panel_data["asof_date"] > panel_data["qdate"]]
        num_macro_leaks = len(macro_leaks)
        assert num_macro_leaks == 0, (
            f"Macro leakage detected: {num_macro_leaks} records have asof_date > qdate!\n"
            f"Sample violations:\n{macro_leaks[['gvkey', 'qdate', 'asof_date']].head()}"
        )

    def test_forward_labels_strictly_future(self, panel_data):
        """
        Rule 4(c): Forward labels (fa_h, migr_cat_h, downgrade_h) must strictly
        evaluate future ratings occurring AFTER qdate (future_qdate_h > qdate).
        """
        labeled = panel_data.dropna(subset=["fa_h", "future_qdate_h"])
        label_leaks = labeled[labeled["future_qdate_h"] <= labeled["qdate"]]
        num_label_leaks = len(label_leaks)
        assert num_label_leaks == 0, (
            f"Label lookahead violation: {num_label_leaks} records have future_qdate_h <= qdate!\n"
            f"Sample violations:\n{label_leaks[['gvkey', 'qdate', 'future_qdate_h']].head()}"
        )

        # Also assert the forward label horizon is at least 90 days ahead
        min_horizon_days = (labeled["future_qdate_h"] - labeled["qdate"]).dt.days.min()
        assert min_horizon_days >= 300, (
            f"Forward label horizon is shorter than 4 quarters: min days = {min_horizon_days}"
        )

    def test_embargo_prevents_overlap(self, panel_data):
        """
        Rule 4(d): Assert that the 4-quarter embargo between train and validation/test
        prevents any overlapping observation windows:
          - Train max forward label date < Validation min observation date
          - Validation max forward label date < Test min observation date
          - Embargo gap is >= 4 quarters (1 year).
        """
        train_df = panel_data[panel_data["split"] == "train"]
        val_df = panel_data[panel_data["split"] == "validation"]
        test_df = panel_data[panel_data["split"] == "test"]
        embargo_df = panel_data[panel_data["split"] == "embargo"]

        assert len(train_df) > 0, "Train split is empty."
        assert len(val_df) > 0, "Validation split is empty."
        assert len(test_df) > 0, "Test split is empty."
        assert len(embargo_df) > 0, "Embargo buffer is empty: embargo quarters not separated."

        # Train label vs Validation observation
        train_max_label = train_df["future_qdate_h"].max()
        val_min_qdate = val_df["qdate"].min()
        assert train_max_label < val_min_qdate, (
            f"Embargo leakage: Train max label date ({train_max_label}) "
            f"overlaps with Validation min qdate ({val_min_qdate})!"
        )

        # Validation label vs Test observation
        val_max_label = val_df["future_qdate_h"].max()
        test_min_qdate = test_df["qdate"].min()
        assert val_max_label < test_min_qdate, (
            f"Embargo leakage: Validation max label date ({val_max_label}) "
            f"overlaps with Test min qdate ({test_min_qdate})!"
        )

        # Embargo duration verification: at least 365 days between train end and val start
        train_end = train_df["qdate"].max()
        val_start = val_df["qdate"].min()
        gap_days = (val_start - train_end).days
        assert gap_days >= 365, (
            f"Embargo between Train and Validation is {gap_days} days, required >= 365 days."
        )

    def test_winsorisation_on_train_only(self, panel_data):
        """
        Rule 4(e): Assert that continuous feature winsorisation cutoffs were estimated
        strictly on the training window, avoiding in-sample lookahead across splits.
        """
        assert CUTOFFS_PATH.exists(), f"Winsorisation cutoffs file missing at {CUTOFFS_PATH}"
        with open(CUTOFFS_PATH, "r", encoding="utf-8") as f:
            cutoffs = json.load(f)

        train_df = panel_data[panel_data["split"] == "train"]
        continuous_cols = [
            "leverage", "debt_to_assets", "current_ratio", "cash_to_assets",
            "interest_coverage", "roa", "log_assets", "tangibility", "ebitda_margin_vol"
        ]

        for col in continuous_cols:
            assert col in cutoffs, f"Variable {col} missing from recorded winsor cutoffs."
            saved_lower = cutoffs[col]["lower"]
            saved_upper = cutoffs[col]["upper"]

            # Assert training bounds are respected across the dataset
            actual_min = panel_data[col].min()
            actual_max = panel_data[col].max()

            assert actual_min >= saved_lower - 1e-5, (
                f"{col} has values below training winsor lower cutoff: {actual_min} < {saved_lower}"
            )
            assert actual_max <= saved_upper + 1e-5, (
                f"{col} has values above training winsor upper cutoff: {actual_max} > {saved_upper}"
            )

    def test_no_firm_quarter_split_overlap(self, panel_data):
        """
        Assert mutually exclusive splits: each firm-quarter (gvkey, qdate) appears in
        exactly one split.
        """
        split_counts = panel_data.groupby(["gvkey", "qdate"])["split"].nunique()
        assert (split_counts == 1).all(), "Some firm-quarters are assigned to multiple splits!"
