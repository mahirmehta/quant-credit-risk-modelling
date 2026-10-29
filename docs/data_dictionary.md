# Data Dictionary

**Project:** Macro-Sensitivity of Corporate Credit Ratings & Fallen-Angel Early Warning  
**Binding Data Contracts (Section 6.3)**  

---

## 1. `data/processed/macro_q.csv`
- `qdate` (datetime64): Calendar quarter-end date (YYYY-03-31, YYYY-06-30, etc.)
- `fedfunds` (float64): Effective Federal Funds Rate level (%)
- `dgs10` (float64): 10-Year Treasury Constant Maturity Yield (%)
- `term_spread` (float64): 10Y minus 2Y Treasury Yield Spread (%)
- `hy_oas` (float64): ICE BofA US High Yield Index OAS (%)
- `baa10y` (float64): Baa Corporate Yield minus 10Y Treasury (%)
- `unrate` (float64): Civilian Unemployment Rate (%)
- `vix` (float64): Average CBOE Volatility Index
- `usrec` (int64): NBER recession indicator (1 during recession, 0 otherwise)
- `d4_fedfunds` (float64): 4-quarter change in Fed Funds rate (pp)
- `d4_dgs10` (float64): 4-quarter change in 10Y Treasury yield (pp)
- `d4_hy_oas` (float64): 4-quarter change in HY OAS (pp)
- `cpi_yoy` (float64): 12-month percentage change in CPI (%)
- `gdp_yoy` (float64): 4-quarter percentage change in Real GDP (%)
- `gdp_qoq_ann` (float64): Quarter-on-quarter annualized GDP growth (%)
- `asof_date` (datetime64): Release/point-in-time publication date
- `vintage_flag` (string): Release vintage identifier

---

## 2. `data/processed/fundamentals_q.csv`
- `gvkey` (string/int): Compustat global company key
- `datadate` (datetime64): Fiscal quarter-end date
- `avail_date` (datetime64): SEC earnings filing date `rdq` (or `datadate + 90 days`)
- `leverage` (float64): Total Debt / TTM EBITDA (`(dlcq + dlttq) / oibdpq_ttm`)
- `debt_to_assets` (float64): Total Debt / Total Assets (`(dlcq + dlttq) / atq`)
- `current_ratio` (float64): Current Assets / Current Liabilities (`actq / lctq`)
- `cash_to_assets` (float64): Cash and Short-term Investments / Total Assets (`cheq / atq`)
- `interest_coverage` (float64): TTM EBIT / TTM Interest (`oiadpq_ttm / xintq_ttm`)
- `roa` (float64): TTM Net Income / Total Assets (`niq_ttm / atq`)
- `log_assets` (float64): Natural log of Total Assets (`ln(atq)`)
- `tangibility` (float64): Net PP&E / Total Assets (`ppentq / atq`)
- `ebitda_margin_vol` (float64): Rolling 8-quarter std dev of EBITDA margin
- `ebitda_nonpos` (int64): Binary flag (1 if TTM EBITDA <= 0, 0 otherwise)

---

## 3. `data/processed/ratings_quarterly.csv`
- `gvkey` (string/int): Compustat global company key
- `qdate` (datetime64): Observation quarter-end
- `rating_str` (string): S&P rating symbol (e.g., 'BBB-', 'BB+', 'A')
- `rating_num` (int64): 1-22 numeric mapping (1=AAA, 10=BBB-, 11=BB+, 22=D)
- `is_ig` (int64): Investment grade flag (1 if `rating_num <= 10`, 0 otherwise)
- `outlook` (string): 'POS', 'NEG', 'STA', 'DEV'
- `watch` (string): 'POS', 'NEG', 'DEV', 'NONE'
- `exit_flag` (int64): 1 if firm defaulted/withdrawn/acquired, 0 otherwise
- `exit_reason` (string): 'DEFAULT', 'WITHDRAWN', 'MERGER', 'NONE'

---

## 4. `data/processed/panel_firmq.csv`
Combined firm-quarter observation panel merging fundamentals, ratings, and macro conditions at `qdate`:
- Primary Features: Firm financials (known at `qdate`), macro series (known at `qdate`), sector (`sector_ff12`), current rating (`rating_num`, `rating_bucket`).
- Target Labels:
  - `fa_h` (int64): Fallen Angel over next h quarters (1 if `is_ig == 1` and `rating_num_{t+h} >= 11`, 0 otherwise).
  - `downgrade_h` (int64): 1 if downgraded by >= 1 notch over next h quarters.
  - `rating_num_h` (int64): Rating level at `t+h`.
  - `migr_cat_h` (int64): Migration scale (0: Upgrade, 1: Stable, 2: Neg Watch/Outlook only, 3: 1-notch Downgrade, 4: Multi-notch/FA/Default).
- Split: `train` (<= 2014), `validation` (2015-2019), `test` (2020-2025).
