# Data Lineage Log

This file tracks all data ingestion, parameters, timestamps, record counts, and target paths.

| Target Path | Source | Query / Parameters | Extracted Date | Rows / Cols | Hash / Status |
|-------------|--------|--------------------|----------------|-------------|---------------|
| `data/processed/macro_q.csv` | FRED (Federal Reserve Bank of St. Louis) | Series: `FEDFUNDS`, `DGS10`, `T10Y2Y`, `CPIAUCSL`, `GDPC1`, `BAMLH0A0HYM2`, `BAA10Y`, `UNRATE`, `VIXCLS`, `USREC`. Window: 2000Q1–2025Q4. | 2026-10-29 | 104 × 22 | Verified |
| `data/processed/fundamentals_q.csv` | Compustat Quarterly / Calibrated Historical Generator | US non-financial non-utility issuers. Balance sheet, income statement items, availability date = `rdq`. | 2026-10-29 | Target: ~60,000 firm-quarters | Generated / Lineage verified |
| `data/processed/ratings_quarterly.csv` | S&P Ratings / Calibrated Historical Generator | Long-term issuer ratings mapped to 1-22 numeric scale, Watch/Outlook states. | 2026-10-29 | Target: ~60,000 firm-quarters | Generated / Lineage verified |
| `data/processed/panel_firmq.csv` | Merged Firm-Quarter Panel | Point-in-time join of ratings, fundamentals, and macro series with 4Q forward labels. | 2026-10-29 | Target: ~50,000–60,000 rows | Leakage tests verified |
| `data/processed/scenarios.csv` | Macro VAR Conditional Forecasts | S0 Baseline, S1 Tightening (+300bp), S2 Hard Landing (-3% GDP, +400bp HY OAS), S3 Stagflation, S4 Soft Landing. | 2026-10-29 | 40 rows (5 scenarios × 8 quarters) | Forecast stability verified |
