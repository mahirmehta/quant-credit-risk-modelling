"""
Data contract, schema compliance, rating scale, and sector mapper unit tests.
Mandated by Section 3, Section 5, and Section 6.3 of plan_updated.md.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.credit.panel.build_panel import map_ordinal_bucket
from src.credit.utils.helpers import assign_ff12_sector, load_yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"


class TestDataContracts:
    """Verify data schema and primary key contracts for all processed CSVs."""

    def test_ratings_quarterly_contract(self):
        """Verify ratings_quarterly.csv schema, keys, and valid ranges."""
        file_path = PROCESSED_DIR / "ratings_quarterly.csv"
        assert file_path.exists(), f"File missing: {file_path}"
        df = pd.read_csv(file_path)

        required_cols = [
            "gvkey", "qdate", "rating_num", "rating_str",
            "is_ig", "outlook", "watch", "exit_flag", "exit_reason"
        ]
        for col in required_cols:
            assert col in df.columns, f"ratings_quarterly missing required column: {col}"

        # Primary key uniqueness
        dup_count = df.duplicated(subset=["gvkey", "qdate"]).sum()
        assert dup_count == 0, f"Duplicate (gvkey, qdate) keys found in ratings_quarterly: {dup_count}"

        # Value bounds
        assert df["rating_num"].between(1, 22).all(), "rating_num outside valid range [1, 22]"
        assert df["is_ig"].isin([0, 1]).all(), "is_ig must be binary {0, 1}"
        assert (df[df["rating_num"] <= 10]["is_ig"] == 1).all(), "Ratings <= 10 must have is_ig == 1"
        assert (df[df["rating_num"] >= 11]["is_ig"] == 0).all(), "Ratings >= 11 must have is_ig == 0"

    def test_macro_quarterly_contract(self):
        """Verify macro_q.csv schema, keys, and temporal monotonicity."""
        file_path = PROCESSED_DIR / "macro_q.csv"
        assert file_path.exists(), f"File missing: {file_path}"
        df = pd.read_csv(file_path, parse_dates=["qdate"])

        required_cols = [
            "qdate", "fedfunds", "dgs10", "term_spread", "hy_oas", "baa10y",
            "unrate", "vix", "usrec", "gdp_real", "cpi",
            "d4_fedfunds", "d4_dgs10", "d4_hy_oas",
            "d1_fedfunds", "d1_dgs10", "d1_hy_oas",
            "cpi_yoy", "gdp_yoy", "gdp_qoq_ann", "asof_date", "vintage_flag"
        ]
        for col in required_cols:
            assert col in df.columns, f"macro_q missing required column: {col}"

        # Primary key uniqueness & sorting
        assert df["qdate"].is_unique, "qdate in macro_q must be unique"
        assert df["qdate"].is_monotonic_increasing, "qdate in macro_q must be monotonically increasing"
        assert len(df) >= 80, f"Expected at least 80 quarterly macro observations, found {len(df)}"

    def test_fundamentals_quarterly_contract(self):
        """Verify fundamentals_q.csv schema and key uniqueness."""
        file_path = PROCESSED_DIR / "fundamentals_q.csv"
        assert file_path.exists(), f"File missing: {file_path}"
        df = pd.read_csv(file_path)

        required_cols = [
            "gvkey", "datadate", "avail_date", "sic", "log_assets", "leverage",
            "debt_to_assets", "current_ratio", "cash_to_assets", "interest_coverage",
            "roa", "tangibility", "ebitda_margin_vol", "ebitda_nonpos"
        ]
        for col in required_cols:
            assert col in df.columns, f"fundamentals_q missing required column: {col}"

        dup_count = df.duplicated(subset=["gvkey", "datadate"]).sum()
        assert dup_count == 0, f"Duplicate (gvkey, datadate) keys found in fundamentals_q: {dup_count}"

    def test_panel_firmq_contract(self):
        """Verify panel_firmq.csv schema, keys, splits, and forward label columns."""
        file_path = PROCESSED_DIR / "panel_firmq.csv"
        assert file_path.exists(), f"File missing: {file_path}"
        df = pd.read_csv(file_path)

        required_cols = [
            "gvkey", "qdate", "rating_num", "rating_str", "is_ig",
            "avail_date", "asof_date", "sector_ff12", "rating_bucket",
            "future_rating_num_h", "future_qdate_h", "fa_h", "downgrade_h",
            "notch_diff_h", "migr_cat_h", "split",
            "leverage", "roa", "log_assets", "interest_coverage",
            "term_spread", "d4_fedfunds", "d4_hy_oas"
        ]
        for col in required_cols:
            assert col in df.columns, f"panel_firmq missing required column: {col}"

        # Primary key uniqueness
        dup_count = df.duplicated(subset=["gvkey", "qdate"]).sum()
        assert dup_count == 0, f"Duplicate (gvkey, qdate) keys found in panel_firmq: {dup_count}"

        # Valid splits
        allowed_splits = {"train", "validation", "test", "embargo", "none"}
        actual_splits = set(df["split"].unique())
        assert actual_splits.issubset(allowed_splits), f"Invalid split names found: {actual_splits - allowed_splits}"


class TestRatingScaleMapping:
    """Verify S&P 22-notch alphanumeric-to-numeric rating scale and ordinal buckets."""

    def test_numeric_mapping_from_config(self):
        """Verify rating numeric mapping defined in definitions.yaml."""
        defs = load_yaml("config/definitions.yaml")
        num_map = defs["rating_scale"]["numeric_map"]

        # Exact Kaplan-Urwitz 22-point scale
        assert num_map["AAA"] == 1
        assert num_map["AA+"] == 2
        assert num_map["AA"] == 3
        assert num_map["AA-"] == 4
        assert num_map["A+"] == 5
        assert num_map["A"] == 6
        assert num_map["A-"] == 7
        assert num_map["BBB+"] == 8
        assert num_map["BBB"] == 9
        assert num_map["BBB-"] == 10
        assert num_map["BB+"] == 11
        assert num_map["BB"] == 12
        assert num_map["BB-"] == 13
        assert num_map["B+"] == 14
        assert num_map["B"] == 15
        assert num_map["B-"] == 16
        assert num_map["CCC+"] == 17
        assert num_map["CCC"] == 18
        assert num_map["CCC-"] == 19
        assert num_map["CC"] == 20
        assert num_map["C"] == 21
        assert num_map["D"] == 22
        assert num_map["SD"] == 22

        # IG cutoff
        assert defs["rating_scale"]["ig_cutoff"] == 10
        assert defs["rating_scale"]["fallen_angel_threshold_from"] == 10
        assert defs["rating_scale"]["fallen_angel_threshold_to"] == 11

    def test_ordinal_bucket_mapping(self):
        """Verify map_ordinal_bucket compresses 22 notches to 11 ordinal categories."""
        # Category 0: AAA (1) to AA- (4)
        for r in [1, 2, 3, 4]:
            assert map_ordinal_bucket(r) == 0, f"Rating {r} should map to bucket 0"

        # Category 1: A+ (5) to A- (7)
        for r in [5, 6, 7]:
            assert map_ordinal_bucket(r) == 1, f"Rating {r} should map to bucket 1"

        # Individual boundary notches
        assert map_ordinal_bucket(8) == 2   # BBB+
        assert map_ordinal_bucket(9) == 3   # BBB
        assert map_ordinal_bucket(10) == 4  # BBB- (IG cliff edge)
        assert map_ordinal_bucket(11) == 5  # BB+  (Fallen Angel entry)
        assert map_ordinal_bucket(12) == 6  # BB
        assert map_ordinal_bucket(13) == 7  # BB-
        assert map_ordinal_bucket(14) == 8  # B+
        assert map_ordinal_bucket(15) == 9  # B

        # Category 10: B- (16) and below through D (22)
        for r in range(16, 23):
            assert map_ordinal_bucket(r) == 10, f"Rating {r} should map to bucket 10"


class TestFamaFrench12SectorMapper:
    """Verify Fama-French 12 sector mapper coverage and exclusion classifications."""

    def test_all_12_sectors_covered(self):
        """Verify that representative SIC codes map to all 12 Fama-French categories."""
        test_cases = [
            (2086, "NoDur"),  # Consumer Non-Durables: Beverages
            (3714, "Durbl"),  # Consumer Durables: Motor Vehicles Parts
            (3531, "Manuf"),  # Manufacturing: Construction Machinery
            (1311, "Enrgy"),  # Oil and Gas Extraction
            (2810, "Chems"),  # Chemical & Allied Products
            (7372, "BusEq"),  # Business Equipment: Software
            (4813, "Telcm"),  # Telecommunications
            (4911, "Utils"),  # Regulated Utilities
            (5311, "Shops"),  # Wholesale and Retail: Dept Stores
            (2834, "Hlth"),   # Healthcare & Pharmaceuticals
            (6021, "Money"),  # Financials: Commercial Banks
            (7011, "Other"),  # Other: Hotels
        ]

        assigned_sectors = set()
        for sic, expected_sector in test_cases:
            sector = assign_ff12_sector(sic)
            assert sector == expected_sector, (
                f"SIC {sic} mapped to '{sector}', expected '{expected_sector}'"
            )
            assigned_sectors.add(sector)

        expected_all_12 = {
            "NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq",
            "Telcm", "Utils", "Shops", "Hlth", "Money", "Other"
        }
        assert assigned_sectors == expected_all_12, (
            f"Missing sectors in test mapping: {expected_all_12 - assigned_sectors}"
        )

    def test_exclusion_filters(self):
        """Verify Financials (6000-6999) and Utilities (4900-4949) are properly categorized."""
        # Financials -> Money
        for sic in [6000, 6022, 6141, 6211, 6311, 6712, 6999]:
            assert assign_ff12_sector(sic) == "Money", f"Financial SIC {sic} should map to Money"

        # Utilities -> Utils
        for sic in [4900, 4911, 4923, 4931, 4941]:
            assert assign_ff12_sector(sic) == "Utils", f"Utility SIC {sic} should map to Utils"

    def test_missing_and_invalid_sic(self):
        """Verify NaN, None, and unclassified SIC codes map cleanly to 'Other'."""
        assert assign_ff12_sector(np.nan) == "Other"
        assert assign_ff12_sector(None) == "Other"
        assert assign_ff12_sector(9999) == "Other"
