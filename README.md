# Macro-Sensitivity of Corporate Credit Ratings & Fallen-Angel Early Warning

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Pytest](https://img.shields.io/badge/pytest-22%20passed%20(100%25)-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/license-Academic-lightgrey.svg)](LICENSE)

---

## 1. Executive Summary & Research Questions

Credit rating agencies declare their ratings to be formulated "through-the-cycle" (TTC), designed to filter out transient business cycle fluctuations. However, this creates a systematic **agency adjustment lag** that leaves institutional investors vulnerable to sudden downgrades across the investment-grade (IG) to high-yield (HY) threshold—the **fallen-angel cliff (BBB− to BB+)**—triggering mandatory institutional divestment and fire-sale price discounts.

This repository implements a quantitative research framework addressing:
1. **Agency Lag Quantification (H1):** Does a point-in-time (PIT) latent shadow rating lead published agency actions, and what is the empirical rating adjustment half-life ($t_{1/2}$)?
2. **Incremental Macro Value (H2):** Does a macroeconomic block (FFR, term spread, credit spread, CPI, GDP) provide statistically significant incremental explanatory power beyond firm balance sheets?
3. **Balance Sheet Vulnerability (H3):** How do monetary tightening and credit shocks interact with corporate leverage and interest coverage across Fama-French 12 sectors?
4. **CreditWatch Dynamics (H4):** Does modeling CreditWatch/Outlook placements as intermediate states sharpen multi-notch migration forecasting?
5. **Early-Warning Lead Time (N6):** Can an out-of-sample point-in-time model anticipate fallen-angel crossings earlier than agency CreditWatch placements?

---

## 2. Key Empirical Findings

- **Agency Lag ($t_{1/2}$):** In active rating reviews, the rating adjustment speed is $\lambda = 0.0214$ per quarter, yielding an adjustment half-life of **32.1 quarters (~8.0 years)**. The point-in-time shadow rating gap significantly predicts next-12-month downgrades ($\beta = +0.0225, p = 0.0137$, Odds Ratio $= 1.023\times$ per notch of lag).
- **Macro Incremental Value:** Block Likelihood Ratio test on macro regressors yields $\chi^2 = 20.40$ ($df = 5, p = 0.00105$), rejecting macro orthogonality at the 0.1% level.
- **Out-of-Sample Performance (2020–2025 Test Window):**
  - **Full Investment Grade:** ROC-AUC of **0.9212** (Firth Penalized: **0.9214**), Brier score of **0.0256**, top-decile capture rate of **61.76%** (**6.18x lift**).
  - **BBB-Band Subsample:** ROC-AUC of **0.8023** on the BBB-band cliff edge.
- **Early-Warning Lead Time:** Across 63 realized fallen-angel events in the 2020–2025 test window, the macro-augmented model triggered an alert an average of **5.71 quarters (~17.1 months)** prior to downgrade, providing an average **+0.73 to +1.88 quarter lead-time advantage** over rating agency CreditWatch placements.
- **Macro Stress Testing & Sector Vulnerability:** Under an 8-quarter +300bp monetary tightening shock (S1), the 12-month fallen-angel rate rises from 2.23% to 2.58% in aggregate, and from 13.53% to **15.80%** for BBB− boundary issuers. Top vulnerable sectors: `Shops` (+0.50 pp), `NoDur` (+0.48 pp), and `Manuf` (+0.47 pp).

---

## 3. Current Repository Assets

| Asset | Path | Details |
|---|---|---|
| **Quantitative Claim Ledger** | [`docs/claim_ledger.csv`](docs/claim_ledger.csv) | **30 individual numerical claims** audited against machine-readable JSON metrics in `results/json/`. |
| **Test Suite** | [`tests/`](tests/) | **22/22 unit, leakage, and Monte Carlo tests passing (100%)**. |
| **Empirical Results Registry** | [`results/json/`](results/json/) | Machine-readable metrics, likelihood ratios, pseudo-$R^2$, and half-life estimates. |
| **Statistical Tables** | [`results/tables/`](results/tables/) | Clean CSV tables (Tables 1–10) covering attrition, summary stats, models, and stress tests. |
| **Publication Figures** | [`results/figures/`](results/figures/) | 300 DPI visualizations (ROC/PR curves, lead times, VAR scenarios, sector heatmaps). |

---

## 4. Repository Structure

```
quant-credit-risk-modelling/
├── Makefile                          # Complete pipeline automation
├── README.md                         # Project documentation and reproduction guide
├── requirements.txt                  # Pinned Python dependencies
├── plan_updated.md                   # Full research design and execution plan
├── .gitignore                        # Git ignore rules
├── config/
│   ├── config.yaml                   # Global seeds, paths, model settings
│   ├── definitions.yaml              # Rating scale, SIC exclusions, horizon definitions
│   └── splits.yaml                   # Train (<=2014), Val (2015-2019), Test (2020-2025)
├── docs/
│   ├── claim_ledger.csv              # Audited mapping of paper claims to results/json
│   ├── data_audit.md                 # WRDS/FRED source audit and credential policies
│   ├── data_dictionary.md            # Data contract definitions and schemas
│   └── lineage.md                    # Extraction parameters, timestamps, record counts
├── data/
│   └── processed/
│       ├── macro_q.csv               # 104 quarters of processed FRED macro series
│       ├── ratings_quarterly.csv     # Calibrated S&P rating histories & Watch/Outlook
│       ├── fundamentals_q.csv        # Compustat quarterly financial ratios & rdq dates
│       ├── panel_firmq.csv           # Merged 67,406 firm-quarter panel with forward labels
│       ├── panel_with_shadow.csv     # Panel augmented with PIT shadow ratings & lag gaps
│       └── scenarios.csv             # 8-quarter conditional VAR scenario paths (S0-S4)
├── src/credit/
│   ├── data_macro/                   # Live FRED macro extraction & transformations
│   ├── data_ratings/                 # S&P rating history extraction & WRDS connectors
│   ├── data_fund/                    # Compustat quarterly fundamentals & ratios
│   ├── panel/                        # Panel assembly & point-in-time leakage safeguards
│   ├── models_ordinal/               # M1 Probit/Logit ladder, N1 Shadow Rating, M2 Migration
│   ├── models_binary/                # M3 Fallen-Angel Firth Logit & N6 Early-Warning
│   ├── stress/                       # VAR(2) estimation, Waggoner-Zha paths, Reverse Stress
│   ├── reporting/                    # Report and presentation generator scripts (to run later)
│   └── utils/                        # Shared helpers, metrics registry, FF12 mapper
├── tests/
│   ├── leakage/                      # Point-in-time leakage tests (avail_date <= qdate)
│   ├── simulation/                   # Known-DGP Monte Carlo recovery & Placebo tests
│   └── unit/                         # Data contract schemas & rating scale unit tests
└── results/
    ├── figures/                      # Publication-grade figures (300 DPI PNG)
    ├── tables/                       # Empirical results CSV tables (Tables 1-10)
    └── json/                         # Machine-readable metric registry files
```

---

## 5. Execution Guide

### Prerequisites
- Python 3.11+
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

### Run Models and Verification Pipeline
Execute via `Makefile`:
```bash
# Run data extraction, modeling, stress testing, and test verification
make all
```

Or execute individual stages:
```bash
# 1. Macro and panel data generation
make data

# 2. Econometric and binary models
make models

# 3. Macro VAR stress scenarios & reverse stress test
make stress

# 4. Run automated test suite (22/22 tests)
make test
```

### On-Demand Deliverable Generation (To Run Later)
When ready to produce the report and presentation files:
```bash
# Compile the 25-page academic PDF report into report/main.pdf
make report

# Compile the 21-slide presentation deck into slides/presentation.pptx
make slides
```

---

## 6. Verification and Testing Standards

The pipeline enforces non-negotiable quantitative standards:
1. **Zero Point-in-Time Leakage:** Every firm fundamental is merged strictly on `avail_date <= qdate` (filing date `rdq`). Macro variables are matched on publication date `asof_date <= qdate`. Forward labels strictly evaluate ratings at $t+h > t$.
2. **Embargo Discipline:** A 4-quarter embargo is strictly enforced between train ($\le 2014$), validation ($2015–2019$), and test ($2020–2025$), preventing label overlap.
3. **Training-Window Winsorization:** 1%/99% winsorization cutoffs are fitted exclusively on the training partition and applied outward.
4. **Monte Carlo Known-DGP Parameter Recovery:** Synthetic panels with known coefficients confirm that estimators recover true parameters within $2.5\times \text{SE}$.
5. **Placebo Controls:** Permuting macroeconomic time-series eliminates predictive gains ($p = 0.8038$); shuffling labels collapses ROC-AUC to $0.4948 \approx 0.50$.
