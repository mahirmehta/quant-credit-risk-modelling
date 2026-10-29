"""
Assemble the firm-quarter panel merging ratings, fundamentals, and macro series.
Strictly enforces point-in-time discipline, training-window winsorisation,
no look-ahead leakage, and generates 4-quarter forward labels.
Complies with Section 3, 5, 6.3, 6.5 of plan_updated.md.
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

from src.credit.utils.helpers import assign_ff12_sector, load_yaml, save_result_metric


def map_ordinal_bucket(rating_num: int) -> int:
    """
    Map 1-22 numeric rating to 11 collapsed ordinal categories (Section 3.3):
      0: AAA to AA- (1-4)
      1: A+ to A- (5-7)
      2: BBB+ (8)
      3: BBB (9)
      4: BBB- (10)  <- IG boundary
      5: BB+ (11)   <- HY boundary
      6: BB (12)
      7: BB- (13)
      8: B+ (14)
      9: B (15)
      10: B- and below (16-22)
    """
    if rating_num <= 4:
        return 0
    elif rating_num <= 7:
        return 1
    elif rating_num == 8:
        return 2
    elif rating_num == 9:
        return 3
    elif rating_num == 10:
        return 4
    elif rating_num == 11:
        return 5
    elif rating_num == 12:
        return 6
    elif rating_num == 13:
        return 7
    elif rating_num == 14:
        return 8
    elif rating_num == 15:
        return 9
    else:
        return 10


def build_panel(h: int = 4) -> pd.DataFrame:
    """Build firm-quarter panel with h-quarter forward labels."""
    print(f"[Panel] Building firm-quarter panel (horizon h={h} quarters)...")
    
    # 1. Load data
    ratings_p = PROCESSED_DIR / "ratings_quarterly.csv"
    fund_p = PROCESSED_DIR / "fundamentals_q.csv"
    macro_p = PROCESSED_DIR / "macro_q.csv"
    
    if not ratings_p.exists():
        from src.credit.data_ratings.extract_ratings import extract_or_build_ratings
        extract_or_build_ratings()
    if not fund_p.exists():
        from src.credit.data_fund.extract_fundamentals import extract_or_build_fundamentals
        extract_or_build_fundamentals()
    if not macro_p.exists():
        from src.credit.data_macro.extract_macro import build_macro_quarterly
        build_macro_quarterly()
        
    ratings_df = pd.read_csv(ratings_p)
    fund_df = pd.read_csv(fund_p)
    macro_df = pd.read_csv(macro_p)
    
    # 2. Point-in-time merge of ratings and fundamentals:
    # At each (gvkey, qdate), match the latest available filing where avail_date <= qdate (Section 6.4, 6.5)
    ratings_df["qdate"] = pd.to_datetime(ratings_df["qdate"])
    fund_df["avail_date"] = pd.to_datetime(fund_df["avail_date"])
    fund_df["datadate"] = pd.to_datetime(fund_df["datadate"])
    macro_df["qdate"] = pd.to_datetime(macro_df["qdate"])
    
    ratings_sorted = ratings_df.sort_values(["qdate", "gvkey"]).reset_index(drop=True)
    fund_sorted = fund_df.sort_values(["avail_date", "gvkey"]).reset_index(drop=True)
    
    merged = pd.merge_asof(
        ratings_sorted,
        fund_sorted,
        left_on="qdate",
        right_on="avail_date",
        by="gvkey",
        direction="backward"
    )
    # Drop rows prior to firm's first filing date
    merged = merged.dropna(subset=["avail_date", "datadate"]).reset_index(drop=True)
    print(f"  [Merge 1] Ratings + Fundamentals (Point-in-Time avail_date <= qdate): {len(merged)} rows")
    
    # 3. Merge macro series on qdate (asof_date <= qdate)
    merged = pd.merge(merged, macro_df, on="qdate", how="left")
    print(f"  [Merge 2] + Macro series: {len(merged)} rows")
    
    # 4. Map sectors
    merged["sector_ff12"] = merged["sic"].apply(assign_ff12_sector)
    
    # 5. Map ordinal buckets
    merged["rating_bucket"] = merged["rating_num"].apply(map_ordinal_bucket)
    
    # 6. Sort and construct forward labels (horizon h)
    merged = merged.sort_values(["gvkey", "qdate"]).reset_index(drop=True)
    
    # Shift within gvkey for forward ratings
    grouped = merged.groupby("gvkey")
    merged["future_rating_num_h"] = grouped["rating_num"].shift(-h)
    merged["future_qdate_h"] = grouped["qdate"].shift(-h)
    
    # Check that future_qdate_h is actually h quarters ahead (within ~130 days tolerance)
    expected_days = h * 91.25
    day_diff = (merged["future_qdate_h"] - merged["qdate"]).dt.days
    valid_forward = (day_diff >= (expected_days - 30)) & (day_diff <= (expected_days + 30))
    
    # Fallen Angel indicator: IG now (<=10) and HY in h quarters (>=11)
    merged["fa_h"] = np.where(
        valid_forward & (merged["rating_num"] <= 10) & (merged["future_rating_num_h"] >= 11),
        1, 0
    )
    # If not valid_forward (end of series or missing future rating), mark NaN label
    merged.loc[~valid_forward, "fa_h"] = np.nan
    
    # General Downgrade indicator
    merged["downgrade_h"] = np.where(
        valid_forward & (merged["future_rating_num_h"] > merged["rating_num"]),
        1, 0
    )
    merged.loc[~valid_forward, "downgrade_h"] = np.nan
    
    merged["notch_diff_h"] = merged["future_rating_num_h"] - merged["rating_num"]
    
    # Multi-state migration scale (M2):
    # 0: Upgrade, 1: Stable, 2: Neg Watch/Outlook, 3: Downgrade 1 notch, 4: Multi-notch Downgrade/FA/Default
    conditions = [
        merged["notch_diff_h"] < 0,
        (merged["notch_diff_h"] == 0) & (merged["watch"] != "NEG") & (merged["outlook"] != "NEG"),
        (merged["notch_diff_h"] == 0) & ((merged["watch"] == "NEG") | (merged["outlook"] == "NEG")),
        merged["notch_diff_h"] == 1,
        merged["notch_diff_h"] >= 2
    ]
    choices = [0, 1, 2, 3, 4]
    merged["migr_cat_h"] = np.select(conditions, choices, default=1)
    merged.loc[~valid_forward, "migr_cat_h"] = np.nan
    
    # 7. Assign train, validation, test splits with 4-quarter embargo (Section 6.4 Rule 4, splits.yaml)
    # Forward labels at horizon h=4 quarters require a 4-quarter embargo buffer
    # between train and validation, and between validation and test.
    # Train: 2002-01-01 to 2013-12-31 (labels extend through 2014-12-31)
    # Embargo 1: 2014-01-01 to 2014-12-31 (4 quarters embargo before val)
    # Validation: 2015-01-01 to 2018-12-31 (labels extend through 2019-12-31)
    # Embargo 2: 2019-01-01 to 2019-12-31 (4 quarters embargo before test)
    # Test: 2020-01-01 to 2025-12-31
    merged["split"] = "none"
    
    train_mask = (merged["qdate"] >= "2002-01-01") & (merged["qdate"] <= "2013-12-31")
    val_mask = (merged["qdate"] >= "2015-01-01") & (merged["qdate"] <= "2018-12-31")
    test_mask = (merged["qdate"] >= "2020-01-01") & (merged["qdate"] <= "2025-12-31")
    embargo_mask = (
        ((merged["qdate"] >= "2014-01-01") & (merged["qdate"] <= "2014-12-31")) |
        ((merged["qdate"] >= "2019-01-01") & (merged["qdate"] <= "2019-12-31"))
    )
    
    merged.loc[train_mask, "split"] = "train"
    merged.loc[val_mask, "split"] = "validation"
    merged.loc[test_mask, "split"] = "test"
    merged.loc[embargo_mask, "split"] = "embargo"
    
    # 8. Winsorization on training window only (Section 3.4, Section 6.4 Rule 4)
    continuous_fund_cols = [
        "leverage", "debt_to_assets", "current_ratio", "cash_to_assets",
        "interest_coverage", "roa", "log_assets", "tangibility", "ebitda_margin_vol"
    ]
    train_df = merged[merged["split"] == "train"]
    winsor_cutoffs = {}
    for col in continuous_fund_cols:
        q_low = float(train_df[col].quantile(0.01))
        q_high = float(train_df[col].quantile(0.99))
        winsor_cutoffs[col] = {"lower": q_low, "upper": q_high}
        merged[col] = merged[col].clip(lower=q_low, upper=q_high)
        
    # Save winsorization cutoffs to results registry
    import json
    cutoffs_dir = ROOT_DIR / "results" / "json"
    cutoffs_dir.mkdir(parents=True, exist_ok=True)
    with open(cutoffs_dir / "winsor_cutoffs.json", "w", encoding="utf-8") as f:
        json.dump(winsor_cutoffs, f, indent=2)
        
    out_csv = PROCESSED_DIR / "panel_firmq.csv"
    merged.to_csv(out_csv, index=False)
    
    print(f"[Panel] Saved {len(merged)} firm-quarters to {out_csv}")
    print("  Splits distribution:\n", merged["split"].value_counts())
    print("  FA count by split:\n", merged.groupby("split")["fa_h"].sum())
    
    # Save panel metadata to results registry
    save_result_metric("panel_total_rows", len(merged), n=len(merged), spec="panel_firmq")
    save_result_metric("panel_firms_count", merged["gvkey"].nunique(), spec="panel_firmq")
    save_result_metric("panel_fa_total", int(merged["fa_h"].sum()), spec="panel_firmq")
    
    return merged


if __name__ == "__main__":
    df = build_panel(h=4)
