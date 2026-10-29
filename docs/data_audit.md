# Data Audit & Access Report

**Project:** Macro-Sensitivity of Corporate Credit Ratings & Fallen-Angel Early Warning  
**Audit Date:** 2026-10-29  
**Status:** Gate G0 / G1 Baseline Established  

---

## 1. Executive Summary & Access Audit

| Source | Target Concept | Target Tables | Primary Status | Fallback / Alternative |
|--------|---------------|---------------|----------------|------------------------|
| **FRED / ALFRED** | US Macro-financial series (FFR, 10Y, OAS, GDP, CPI, VIX) | Direct FRED API / CSV endpoints | **VERIFIED & EXTRACTED** (104 quarters, 2000Q1–2025Q4) | Primary live FRED extraction fully operational. |
| **WRDS Compustat** | US Corporate Quarterly Fundamentals (`fundq`) | `comp.fundq` (`gvkey`, `datadate`, `rdq`, `dlcq`, `dlttq`, `oibdpq`, `oiadpq`, `xintq`, `atq`, `cheq`, `actq`, `lctq`) | Requires user `.pgpass` authentication | Production WRDS extractor script provided (`extract_fundamentals_wrds.py`); empirical calibrated panel generator provided for local execution. |
| **WRDS Ratings** | S&P Issuer Credit Ratings & CreditWatch/Outlook | `comp.adsprate` (historical), `fisd.fisd_issuer`, `ciq.wrds_ratings` | Legacy Compustat ratings end ~2017; Mergent FISD / CIQ require active subscription | Fallback ladder implemented per §4.1: S&P Empirical Calibration preserving transition dynamics, BBB cliff, and Watch/Outlook states. |
| **LSEG Datastream / TRACE** | Corporate bond prices, yields, duration, spreads | TRACE (`wrds_trace`), Datastream bond files | University library terminal / terminal export | Secondary Tier 2 priority. Synthetic bond pricing & spread model provided. |

---

## 2. WRDS Environment & Credentials Status

- **Python Connector:** `wrds` version 3.5.0 verified installed on Python 3.11.4.
- **Credential Storage:** `~/.pgpass` file is not currently present on this host.
- **Lineage Policy:** In accordance with university cybersecurity policies, credentials are never written to code or version control. A one-time setup command:
  ```python
  import wrds
  db = wrds.Connection(wrds_username='your_smu_username')
  db.create_pgpass_file()
  ```
  will store encrypted connection tokens locally in `~/.pgpass` for automatic unattended runs.
- **SQL Scripts:** Ready-to-run queries with exact filtering (`fic = 'USA'`, non-financials `sic NOT BETWEEN 6000 AND 6999`, non-utilities `sic NOT BETWEEN 4900 AND 4999`) are implemented in `src/credit/data_fund/extract_fundamentals.py` and `src/credit/data_ratings/extract_ratings.py`.

---

## 3. Macro Series Lineage (FRED Live Extraction)

All series were retrieved directly from Federal Reserve Bank of St. Louis public data service on 2026-10-29.
- `FEDFUNDS`: Federal Funds Effective Rate (Monthly -> Quarter End, 104 quarters)
- `DGS10`: Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity
- `T10Y2Y`: 10-Year Treasury Constant Maturity Minus 2-Year Treasury Constant Maturity
- `CPIAUCSL`: Consumer Price Index for All Urban Consumers: All Items in U.S. City Average (YoY Inflation)
- `GDPC1`: Real Gross Domestic Product (YoY growth and QoQ annualized)
- `BAMLH0A0HYM2`: ICE BofA US High Yield Index Option-Adjusted Spread
- `BAA10Y`: Moody's Seasoned Baa Corporate Bond Yield Relative to 10-Year Treasury
- `UNRATE`: Civilian Unemployment Rate
- `VIXCLS`: CBOE Volatility Index
- `USREC`: NBER based Recession Indicators for the United States

Contract compliance: Stored at `data/processed/macro_q.csv` (104 rows × 22 columns).
