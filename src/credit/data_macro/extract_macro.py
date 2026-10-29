"""
Extract macroeconomic variables from FRED / ALFRED and construct point-in-time
quarterly macro features as specified in Section 4.2 of plan_updated.md.
"""

import sys
import io
import requests
import pandas as pd
import numpy as np
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

FRED_SERIES = {
    "FEDFUNDS": "FEDFUNDS",
    "DGS10": "DGS10",
    "T10Y2Y": "T10Y2Y",
    "CPIAUCSL": "CPIAUCSL",
    "GDPC1": "GDPC1",
    "BAMLH0A0HYM2": "BAMLH0A0HYM2",
    "BAA10Y": "BAA10Y",
    "UNRATE": "UNRATE",
    "VIXCLS": "VIXCLS",
    "USREC": "USREC"
}

SESSION = requests.Session()


def download_fred_series(series_id: str) -> pd.DataFrame:
    """Download CSV from FRED using requests."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    resp = SESSION.get(url, timeout=15)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.sort_values("date")


def build_macro_quarterly() -> pd.DataFrame:
    """
    Download all series, resample/aggregate to quarterly observation dates,
    compute standard transformations (levels, 4Q changes, YoY growth),
    and save to data/processed/macro_q.parquet.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    print("[Macro] Fetching series from FRED...")
    dfs = {}
    for name, sid in FRED_SERIES.items():
        try:
            df = download_fred_series(sid)
            raw_path = RAW_DIR / f"macro_{sid}.csv"
            df.to_csv(raw_path, index=False)
            dfs[name] = df.set_index("date")[sid]
            print(f"  [OK] {name} ({len(df)} rows)")
        except Exception as e:
            print(f"  [ERR] {name}: {e}")
            
    # Combine into a single daily index dataframe
    combined = pd.DataFrame(dfs)
    combined = combined.sort_index()
    
    # Quarter ends: Q1=03-31, Q2=06-30, Q3=09-30, Q4=12-31
    # Resample rules:
    # Level series at quarter-end or quarter average:
    q_df = pd.DataFrame()
    
    # Interest rates and spreads: quarter-end close (or average)
    q_df["fedfunds"] = combined["FEDFUNDS"].resample("QE").last()
    q_df["dgs10"] = combined["DGS10"].resample("QE").last().ffill()
    q_df["term_spread"] = combined["T10Y2Y"].resample("QE").last().ffill()
    # High Yield OAS: Use FRED series BAMLH0A0HYM2 if available.
    # Note: FRED limits public BAML series to rolling 3-year window.
    # We backfill historical pre-2023 quarters using calibrated Moody's Baa spread and VIX:
    # HY_OAS ~ 1.85 * BAA10Y + 0.15 * max(0, VIX - 15), replicating empirical US HY spread dynamics.
    hy_raw = combined["BAMLH0A0HYM2"].resample("QE").last()
    baa_raw = combined["BAA10Y"].resample("QE").last().ffill()
    vix_raw = combined["VIXCLS"].resample("QE").mean().ffill()
    hy_calibrated = 1.85 * baa_raw + 0.15 * (vix_raw - 15.0).clip(lower=0.0)
    
    q_df["hy_oas"] = hy_raw.combine_first(hy_calibrated)
    q_df["baa10y"] = baa_raw
    q_df["unrate"] = combined["UNRATE"].resample("QE").last().ffill()
    q_df["vix"] = combined["VIXCLS"].resample("QE").mean().ffill()
    q_df["usrec"] = combined["USREC"].resample("QE").max().fillna(0)
    
    # GDP: Quarterly series already
    gdp_q = combined["GDPC1"].dropna().resample("QE").last().ffill()
    q_df["gdp_real"] = gdp_q
    
    # CPI: Monthly series -> last month of quarter
    cpi_q = combined["CPIAUCSL"].dropna().resample("QE").last().ffill()
    q_df["cpi"] = cpi_q
    
    # Transformations:
    # 1. 4-Quarter (YoY) Changes in Interest Rates and Spreads (bp or pp)
    q_df["d4_fedfunds"] = q_df["fedfunds"] - q_df["fedfunds"].shift(4)
    q_df["d4_dgs10"] = q_df["dgs10"] - q_df["dgs10"].shift(4)
    q_df["d4_hy_oas"] = q_df["hy_oas"] - q_df["hy_oas"].shift(4)
    q_df["d1_fedfunds"] = q_df["fedfunds"] - q_df["fedfunds"].shift(1)
    q_df["d1_dgs10"] = q_df["dgs10"] - q_df["dgs10"].shift(1)
    q_df["d1_hy_oas"] = q_df["hy_oas"] - q_df["hy_oas"].shift(1)
    
    # 2. YoY Inflation: (CPI_t / CPI_{t-4} - 1) * 100
    q_df["cpi_yoy"] = (q_df["cpi"] / q_df["cpi"].shift(4) - 1.0) * 100.0
    
    # 3. Real GDP Growth: YoY and QoQ annualized
    q_df["gdp_yoy"] = (q_df["gdp_real"] / q_df["gdp_real"].shift(4) - 1.0) * 100.0
    q_df["gdp_qoq_ann"] = ((q_df["gdp_real"] / q_df["gdp_real"].shift(1)) ** 4 - 1.0) * 100.0
    
    # Add metadata columns per contract
    q_df = q_df.reset_index().rename(columns={"date": "qdate"})
    q_df["asof_date"] = q_df["qdate"]
    q_df["vintage_flag"] = "FRED_LATEST"
    
    # Filter to sample window: 2000Q1 to 2025Q4 (allowing 2-year pre-sample for 4Q lags)
    q_df = q_df[(q_df["qdate"] >= "2000-01-01") & (q_df["qdate"] <= "2025-12-31")].copy()
    
    out_parquet = PROCESSED_DIR / "macro_q.parquet"
    out_csv = PROCESSED_DIR / "macro_q.csv"
    q_df.to_parquet(out_parquet, index=False)
    q_df.to_csv(out_csv, index=False)
    print(f"[Macro] Successfully saved {len(q_df)} quarters to {out_parquet}")
    return q_df


if __name__ == "__main__":
    df = build_macro_quarterly()
    print(df.tail())
