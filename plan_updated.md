# plan.md — Macro-Sensitivity of Corporate Credit Ratings & Fallen-Angel Early Warning

**Course:** Quant Analysis of Financial Markets (SMU MSc Quantitative Finance)
**Owner:** Mahir (solo project) · **Created:** 2026-10-29 · **Execution:** start now; do not wait for a deadline or other contributors
**Deliverables:** (1) 25-page report PDF · (2) 20–22-slide presentation (PPTX + PDF export) · (3) Python code, data-extraction scripts, documentation, and reproducibility package
**Scope:** US-domiciled corporate issuers and US macro-financial conditions only · **Primary language:** Python only · **Data access:** SMU university WRDS login

---

## 0. How to use this file (read first, every agent)

1. This is a **solo project**. The task blocks in §7 are workstreams for one researcher, not separate agents or parallel contributors.
2. Work in dependency order: environment and WRDS access → data audit → raw extracts → cleaned data → firm-quarter panel → baseline models → validation → stress scenarios → report and slides.
3. Keep raw licensed data local and out of public Git repositories. Commit code, schemas, documentation, and only those derived/sample data that WRDS and vendor licences permit.
4. Use Python for every computational step. Do not require R, Stata, LaTeX, or a multi-agent workflow. The report can be authored in Markdown/Quarto or Word and exported to PDF; the presentation should be generated or maintained as PPTX.
5. **No result number is typed manually into the report or slides.** Generate result tables, figures, and a results registry from Python outputs in `results/`.
6. Start with a small end-to-end vertical slice (one WRDS extract, one macro pull, one joined panel, one baseline model) before expanding to the full specification.

---

## 1. Research design: what makes this more than a routine ordered-probit project

The baseline proposal (ordered probit + binary logit + stress test) is a sound but standard design. The professor confirmed the model choice ("ordered probit/logit looks fine") and asked for two extensions: **(i) bond data from Datastream (via WRDS or SMU library)** and **(ii) CreditWatch (positive/negative), not just upgrades/downgrades**. We go further.

**Core research question.**
How far do rating agencies lag the macro-financial cycle, and does a macro-augmented, point-in-time model anticipate fallen-angel crossings (BBB- → BB+) and CreditWatch/Outlook actions earlier and more accurately than fundamentals alone?

### Hypotheses
| ID | Hypothesis | Primary test |
|----|-----------|--------------|
| H1 | Agencies adjust slowly ("through-the-cycle"): a point-in-time *shadow rating* leads actual rating changes | Partial-adjustment speed λ and half-life; shadow-rating gap predicts next-12m downgrades |
| H2 | Macro-financial variables carry incremental information for downgrade / fallen-angel risk beyond firm fundamentals and current rating | Block LR/Wald test on macro coefficients; out-of-sample AUC, Brier and log-score gain |
| H3 | Macro sensitivity is heterogeneous: stronger for high-leverage, low-coverage firms and for rate-sensitive sectors | Macro × firm-characteristic interactions; sector-level marginal effects |
| H4 | CreditWatch/Outlook are informative intermediate states; modelling them sharpens fallen-angel prediction and lead time | Multi-state/augmented ordinal model (M2); lead time of model vs. agency Watch |
| H5 | (Tier 2) Predicted fallen-angel risk has economic value around the forced-selling window | Event-time excess bond returns; sorted-portfolio backtest |

### Novel elements (what we claim as distinctive)
- **N1 – Shadow-rating gap & rating half-life.** Fit a point-in-time latent-index model; the gap between the shadow rating and the published rating is the measurable "agency lag". Estimate the speed of adjustment and its dependence on the cycle.
- **N2 – Watch/Outlook as states, not footnotes.** Augmented ordinal migration scale and competing-risks hazard with Watch as an intermediate state (directly answers the professor's feedback).
- **N3 – Real-time macro (ALFRED vintages).** Use GDP/CPI as first-released/available at the time to avoid revision look-ahead.
- **N4 – Internally consistent stress scenarios.** Scenario paths come from VAR conditional forecasts, not one-variable-at-a-time shocks (FFR, 10Y, HY spread and GDP are jointly determined; shocking one in isolation is not a coherent counterfactual).
- **N5 – Reverse stress test.** Smallest macro shock (in a Mahalanobis sense under the VAR) that pushes the predicted fallen-angel rate to a target level (e.g., a GFC-like rate).
- **N6 – Early-warning lead time.** For every realised fallen angel, how many quarters before the event did the model cross a threshold vs. when the agency placed the issuer on Watch?
- **N7 – Verification rigor.** Known-DGP Monte Carlo (parameter recovery), independent Python validation (Python estimator validation), leakage unit tests, placebo tests, claim ledger (§6.4).

**Tiering (protects the schedule).**
- **Tier 1 (mandatory):** M1, M2, M3, shadow-rating lag (N1), Watch/Outlook (N2), VAR scenarios (N4), sector stress test, full report + slides + reproducible code.
- **Tier 2 (stretch, only if gates G2 pass on time):** M4 hazard/competing risks, M5 ML benchmark, market-based predictors (spreads, distance-to-default), economic-value backtest (H5), reverse stress test (N5).

---

## 2. Traceability matrix (every proposal point and feedback item is covered)

| Source item | Where it is implemented | Agent | Deliverable evidence |
|---|---|---|---|
| Obj.: rating agencies lag ("through-the-cycle") | N1 shadow gap, half-life; H1 | A5 | Report §Results-1; Fig: shadow vs actual |
| Obj.: anticipate downgrades across BBB-/BB+ | M3, N6 lead time | A6 | Report §Results-3 |
| Obj.: early-warning signal for investors / avoid forced-selling losses | H5 economic value; threshold/lead-time analysis | A6, A8 | Report §Results-6 |
| Target: ordinal ratings AAA→CCC/D | Rating scale mapping §3.3 | A1, A4 | `ratings_*.parquet`, data dictionary |
| Firm predictors: Debt/EBITDA, liquidity, interest coverage, ROA | §4.3 variable definitions | A2 | `fundamentals_q.parquet` |
| Macro predictors: FFR, 10Y, inflation, GDP, HY spreads | §4.2 series table | A3 | `macro_q.parquet` |
| Sources: FRED, Kaggle/EDGAR | §4.1 (FRED/ALFRED primary; EDGAR cross-check; Kaggle pilot only) | A2, A3 | `docs/data_audit.md` |
| **Feedback:** Datastream bonds via WRDS/SMU library | §4.1 priority-1 source | A1 | `bonds_monthly.parquet` |
| **Feedback:** Credit Watch (positive/negative), not just up/downgrades | M2, M4, N2 | A1, A5, A6 | `watch_outlook_intervals.parquet`; Results-2 |
| **Feedback:** ordered probit/logit fine | M1, M3 | A5, A6 | Model tables |
| Method: ordered probit (transition probabilities) | M1, M2 | A5 | Tables, AME |
| Method: binary logit, 12-month fallen angel | M3 | A6 | Tables, OOS metrics |
| Method: macro stress testing (rate & GDP shocks, sector-specific migration) | VAR scenarios + sector heatmap | A3, A7 | Report §Stress |
| Takeaway: quantify agency lag | N1 | A5 | half-life estimate with CI |
| Takeaway: marginal effects of macro shocks | AME in M1–M3 | A5, A6 | Marginal-effects tables |
| Takeaway: vulnerable sectors under tightening | A7 sector analysis | A7 | Sector heatmap + table |
| Report PDF / presentation / code+data | §9 | A9, A10, A0, A11 | `report/main.pdf`, `slides/`, repo |

---

## 3. Scope decisions & definitions (frozen at Gate G0 → `config/definitions.yaml`)

### 3.1 Universe and sample
- **Universe:** US-domiciled, USD-reporting non-financial, non-utility corporates with an S&P long-term issuer credit rating (financials SIC 6000–6999 and regulated utilities SIC 4900–4999 excluded in the main sample; included only as a clearly labelled robustness check if feasible). All primary analysis is US-only; no international issuer panel or non-US macro block.
- **Sample window:** target 2002Q1–2025Q4 (confirm after the data audit; extend earlier only if ratings *and* Watch history exist). Hard requirement: covers 2008–09, 2020 and the 2022–23 tightening so the out-of-sample test contains genuine regime changes.
- **Unit of observation:** firm-quarter. Prediction date `t` = quarter-end; every feature must be *knowable* at `t` (§6.5).
- **Horizon:** h = 4 quarters (12 months) primary; h = 2 and 8 robustness.

### 3.2 Event definitions
- **Fallen angel (FA):** `rating_num_t ≤ 10` (IG) and `rating_num_{t+h} ≥ 11` (HY) on the S&P issuer rating (primary). Robustness: Moody's, and the index-style "middle of three agencies" convention if multi-agency data are available.
- **Downgrade / upgrade:** change in `rating_num` over the horizon (notches); multi-notch separately.
- **Watch/Outlook states:** Positive/Negative/Developing CreditWatch and Positive/Negative/Stable Outlook as of `t`, plus actions in `(t, t+h]`.
- **Exits (competing events):** default (SD/D), rating withdrawn (NR), acquisition/delisting. Exits are **not dropped silently**: treated as censoring or competing events and reported in an attrition table.

### 3.3 Rating scale (numeric mapping; unit-tested)
`AAA=1, AA+=2, AA=3, AA-=4, A+=5, A=6, A-=7, BBB+=8, BBB=9, BBB-=10 | BB+=11, BB=12, BB-=13, B+=14, B=15, B-=16, CCC+=17, CCC=18, CCC-=19, CC=20, C=21, SD/D=22`.
Investment grade ⇔ `rating_num ≤ 10`.

**Ordered-model buckets (provisional, finalise from cell counts):** `{AAA–AA-}, {A+–A-}, BBB+, BBB, BBB-, BB+, BB, BB-, B+, B, {B- and below}`. Rule: collapse adjacent categories until each has ≥ ~100 firm-quarters; keep BBB-/BB+ separate (the boundary of interest).

### 3.4 Cleaning rules
- Winsorise at 1%/99% with **cutoffs estimated on the training window only** (expanding-window transformer, no full-sample cutoffs).
- Debt/EBITDA with EBITDA ≤ 0 → flag `ebitda_nonpos`, set leverage to the winsorisation ceiling, and use Debt/Assets in parallel specs.
- Interest coverage with zero interest expense → flag and cap; use a bounded transform (e.g., `cov/(1+cov)` or `asinh`).
- All ratios computed on trailing-four-quarter (TTM) flows over period-end stocks.

---

## 4. Data plan

### 4.1 Sources (priority and fallbacks)
| Pri | Source | Provides | Access | Risk / action |
|---|---|---|---|---|
| 1 | **WRDS – Compustat Quarterly (`fundq`)** | Fundamentals, report date `rdq` | SMU WRDS | Confirm access in G0 |
| 1 | **LSEG Datastream (SMU library / WRDS)** — *professor-suggested* | Bond prices, yields, spreads, bond static data; possibly ratings fields | SMU library | Confirm coverage, ratings history, bond-level identifiers |
| 1 | **Issuer rating history with Outlook / CreditWatch** | Rating actions, Watch/Outlook intervals | Candidates: (a) WRDS S&P ratings tables, (b) Mergent FISD ratings, (c) Datastream/LSEG, (d) Bloomberg terminal if available on campus | **Biggest data risk.** Verify (i) coverage end date (the legacy Compustat ratings table is known to stop around 2017 — check before relying on it), (ii) whether Watch/Outlook history exists. Decide at G0 |
| 1 | **FRED + ALFRED API** | Macro series and real-time vintages | Free API key | Check licence-truncated series (below) |
| 2 | SEC EDGAR XBRL (company facts / Financial Statement Data Sets) | Free fundamentals fallback + cross-check | Free | Spot-check ≥ 50 firm-quarters against Compustat |
| 2 | CRSP + CCM link | Equity returns/volatility, GVKEY–PERMNO link, distance-to-default | SMU WRDS | Tier 2 |
| 2 | Enhanced TRACE (WRDS), if licensed | Better bond returns than Datastream composites | SMU WRDS | Tier 2 / H5 |
| 3 | Kaggle "Corporate Credit Rating" dataset | Small, short-window | Free | **Pilot / unit-test only; never used for headline results** |

If Watch/Outlook history is **not** obtainable for the full window → fallback ladder: (1) restrict M2/M4 to the sub-period where it exists and state this openly; (2) otherwise drop to ratings-only and use the shadow-gap and momentum features as the "pre-action signal". Decide at G0, never silently.

### 4.2 Macro series (A3)
| Concept | FRED ID | Transformations |
|---|---|---|
| Fed funds rate | `FEDFUNDS` (monthly), `DFF` | level; 4Q change (bp) |
| 10Y Treasury | `DGS10` | level; 4Q change |
| Term spread | `T10Y2Y` (also `T10Y3M`) | level |
| CPI inflation | `CPIAUCSL` | YoY % |
| Real GDP | `GDPC1` | QoQ annualised, YoY; **ALFRED vintages** |
| HY OAS | `BAMLH0A0HYM2` | level; 4Q change |
| BBB OAS | `BAMLC0A4CBBB` | level |
| Baa − 10Y (fallback) | `BAA10Y` | level |
| Unemployment | `UNRATE` | level, change |
| Equity vol | `VIXCLS` | quarter average |
| Fin. conditions (optional) | `NFCI` | level |
| Recession flag | `USREC` | regime indicator |

**Licensing check:** ICE BofA index series on FRED have had redistribution restrictions on history length. Verify the full history is returned by the API. If truncated, use `BAA10Y` and/or Datastream spread series, and say so in the Data section.
Stationarity (ADF/KPSS) and multicollinearity (VIF; FFR, 10Y, HY spread are highly correlated) are tested and documented; models use changes or orthogonalised blocks where needed.

### 4.3 Firm variables (A2, Compustat quarterly item names to be confirmed in the audit)
| Concept | Construction |
|---|---|
| Leverage | (`dlcq`+`dlttq`) / TTM EBITDA (`oibdpq`); also Debt/Assets, Net debt/EBITDA |
| Liquidity | Current ratio `actq/lctq`; cash/assets `cheq/atq` |
| Interest coverage | TTM EBIT (`oiadpq`) / TTM interest (`xintq`) |
| Profitability | TTM `niq` / average `atq` (ROA); EBITDA margin |
| Size | ln(`atq`) |
| Tangibility, volatility | `ppentq/atq`; std. dev. of EBITDA margin over 8 quarters |
| Tier 2 market-based | 12m equity return, equity volatility, Merton-style distance-to-default, market-to-book |
Availability date = `rdq` (earnings report date). If `rdq` is missing, use `datadate + 90 days` (conservative).

---

## 5. Methodology specification

**Notation:** `i` firm, `t` quarter-end, `h` horizon, `X` firm block, `M` macro block, `W` Watch/Outlook state, `S` sector (Fama–French 12/17 via SIC, no GICS licence needed).

### M1 — Ordered probit/logit on rating level ("rating determinants", Kaplan–Urwitz tradition)
`rating_bucket_it = k  ⇔  c_{k-1} < X_it'β + M_t'γ + S'δ + ε_it ≤ c_k`
- Spec ladder: (a) firm only → (b) macro only → (c) firm+macro → (d) +firm×macro interactions (e.g., leverage × ΔFFR) → (e) +sector effects → (f, Tier 2) +market-based.
- Reports: coefficients, cutpoints, McFadden R², LR test of macro block, **average marginal effects (AME) on each category probability**, with emphasis on `P(IG)`, `P(BBB-)`, `P(BB+)`.
- Inference: SEs clustered by firm **and** quarter (macro regressors vary only by time → effective macro sample is small; also report block bootstrap by time).
- Diagnostics: Brant / proportional-odds test; if rejected, report generalised ordered logit and multinomial logit as checks.
- Logit vs probit reported side by side (the professor said both fine).

### M1b — Transition version (dynamic)
Same as M1 with current-rating bucket dummies (and Watch state) as regressors, outcome = rating bucket at `t+h`. Present M1 (shadow/determinants) and M1b (transition) separately; M1b is dominated by persistence, which is itself the lag evidence.

### N1 — Shadow-rating gap & agency lag
1. Fit M1 (firm + macro [+ market]) on the **training window**; define the continuous latent index `z_it = X'β + M'γ`.
2. Map `z` to a *shadow rating* via the estimated cutpoints; `gap_it = shadow_it − rating_it` (in notches / latent units).
3. **Partial adjustment:** `Δrating_{i,t+1} = λ·gap_it + controls + u`, estimate λ; **half-life = ln(0.5)/ln(1−λ)** quarters. Heterogeneity: by cycle (recession/tightening), sector, rating band.
4. Test whether `gap_it` predicts downgrades/FA in `(t, t+h]` conditional on the current rating (feeds M3).

### M2 — Augmented ordinal migration scale (Watch/Outlook as states)
Outcome over `(t, t+h]`, ordered: `Upgrade < Stable < Negative Outlook/Watch only < Downgrade < Multi-notch downgrade/default`. Ordered probit/logit with firm, macro, current Watch/Outlook, current rating band. Final category definitions fixed after counts (G0/G1). Reports AME of macro variables on each migration probability.

### M3 — Binary fallen-angel model (core of the early-warning claim)
- Population: IG at `t` (main) and BBB band (BBB+/BBB/BBB-) as the economically relevant subsample.
- Outcome: `FA_{i,t→t+h}`. Logit and probit.
- **Rare-event handling:** Firth penalised logistic regression (Firth 1993) as primary-or-robustness; no accuracy metric (class imbalance).
- Spec ladder: S1 rating+Watch only → S2 +firm → S3 +macro → S4 +interactions → S5 (Tier 2) +market → S6 (Tier 2) ML.
- Tests: LR/Wald for macro block; DeLong for AUC differences; Diebold–Mariano on log/Brier loss.

### M4 (Tier 2) — Discrete-time hazard with competing risks
Quarterly person-period data (Shumway 2001 style): events = {FA, other downgrade, upgrade, Watch-neg, exit}; multinomial logit with duration dependence (time-in-rating) and time-varying covariates; exits handled as competing risks.

### M5 (Tier 2) — Machine-learning benchmark
Regularised logit and gradient boosting (monotone constraints where sensible) as a *ceiling check*: if ML adds little over M3-S4, linear structure is adequate (a result worth stating).

### Validation protocol (applies to M3/M4/M5, and OOS parts of M1/M2)
- **Temporal splits only** (no random K-fold). Expanding window, annual refit, **embargo of h quarters** between train end and test start (labels overlap in time).
- Default windows (adjust at G1 to event counts): train ≤ 2014, validation 2015–2019, **test 2020–2025** (COVID shock, 2022–23 tightening). Also a rolling-origin evaluation from 2010.
- Metrics: ROC-AUC, PR-AUC, Brier, log-loss, calibration slope/intercept and reliability plots, top-decile capture rate/lift; ordinal: ranked probability score, mean absolute notch error, weighted kappa.
- Calibration (Platt/isotonic) fitted on validation only.
- **Early-warning lead time (N6):** threshold chosen on validation (e.g., fixed false-positive rate); for each test-period FA, lead time = quarters between model alert and event vs. between Watch placement and event.

### Robustness battery (A5/A6 each own their models; A11 verifies it ran)
Alternative horizon (2/8q); Moody's-based FA; include financials/utilities; exclude 2008–09 and exclude 2020; alternative macro transformations (levels vs changes); drop interactions; firm fixed-effects conditional logit (caveat: drops firms without events); sector-clustered SE; **placebo: permute macro block across time and confirm gain vanishes**; **negative control: shuffled FA labels give AUC ≈ 0.5**.

### Stress testing (A3 scenario engine + A7)
- **Scenario generation:** VAR (or BVAR) on `[ΔFFR or FFR, term spread, inflation, GDP growth, HY OAS]`; lag order by BIC; check stability (roots inside unit circle) and report IRFs (flag any counter-intuitive sign instead of hiding it). Scenarios imposed as **conditional forecasts** (Waggoner–Zha 1999) so all variables co-move consistently.
- **Scenarios (paths over 4–8 quarters):** S0 baseline; S1 monetary tightening (FFR +300bp, 2022-like); S2 hard landing (GDP −3% cumulative, HY OAS +400bp, GFC-lite); S3 stagflation (inflation +3pp, GDP −1%, FFR +150bp); S4 easing/soft landing (symmetry check).
- **Application:** apply M3 (and M2) to the latest firm-snapshot with *static balance sheets* (primary); optional dynamic satellite (EBITDA sensitivity to GDP; coverage sensitivity to rates) as extension.
- **Outputs:** ΔP(FA) and expected FA count/rate per scenario; sector heatmap (FF12) with parameter-uncertainty bands (cluster bootstrap or draws from the asymptotic distribution of β); amount of IG debt at risk (par outstanding from A1 bond data, if available); ranking of sectors most vulnerable to tightening.
- **Reverse stress test (N5, Tier 2):** minimum-norm shock path producing a target FA rate.

---

## 6. Engineering & accuracy protocol (shared rules)

### 6.1 Stack
Python 3.11+ only: `pandas`, `pyarrow`, `numpy`, `statsmodels` (including `OrderedModel` and `VAR`), `scikit-learn`, `scipy`, `requests` or `fredapi`, `wrds`, `matplotlib`/`seaborn`, `openpyxl`, and a Python PDF/PPTX toolchain such as `python-docx`/`python-pptx` or Quarto. Use a pinned `requirements.txt` (or `uv.lock`) and fixed random seeds in `config/config.yaml`. No R replication or R dependency. For rare-event logistic regression, start with regularised logistic regression and treat Firth logistic regression as optional only if a reliable Python implementation installs and passes tests; clearly disclose the estimator actually used.

### 6.2 Repository layout and ownership
```
credit-macro/
  plan.md  README.md  Makefile
  config/        config.yaml  definitions.yaml  splits.yaml        # A0
  docs/          data_audit.md  data_dictionary.md  lineage.md    # A1,A2,A3,A4
  data/raw/      (licensed data: gitignored)                     # A1,A2,A3
  data/interim/  data/processed/  data/external/                 # A1–A4
  src/credit/
    data_ratings/ data_fund/ data_macro/                           # A1 / A2 / A3
    panel/                                                         # A4
    models_ordinal/                                                # A5
    models_binary/                                                 # A6
    stress/                                                        # A7
    econ_value/                                                    # A8
    utils/                                                         # A0 (shared helpers only)
  tests/         unit/ simulation/ leakage/          # A11 (+ unit tests by each owner)
  results/       tables/ figures/ json/ tex/                      # written by code only
  report/        main.tex  sections/  refs.bib                     # A9
  slides/        deck source + export                              # A10
  handoff/       A0..A11_handoff.md
  status/        board.md                                          # all (append-only)
```

### 6.3 Data contracts (parquet; columns are binding)
| File | Key | Required columns |
|---|---|---|
| `ratings_events.parquet` (A1) | `gvkey, action_date, agency` | `rating_str, rating_num, action_type` (upgrade/downgrade/affirm/…), `source` |
| `watch_outlook_intervals.parquet` (A1) | `gvkey, start_date, end_date, agency` | `kind` (CreditWatch/Outlook), `direction` (POS/NEG/DEV/STA), `source` |
| `ratings_quarterly.parquet` (A1) | `gvkey, qdate` | `rating_num, rating_str, outlook, watch, exit_flag, exit_reason` (as known at `qdate`) |
| `bonds_monthly.parquet` (A1) | `bond_id, month` | `gvkey, price, yield, spread, duration, amt_out, ret, excess_ret` |
| `id_crosswalk.parquet` (A1) | `gvkey` | `cusip6, permno, isin_list, issuer_name, match_method, match_confidence` |
| `fundamentals_q.parquet` (A2) | `gvkey, datadate` | raw items, `avail_date`, TTM ratios, flags (§4.3) |
| `macro_q.parquet` (A3) | `qdate` | all transforms in §4.2, `asof_date`, `vintage_flag` |
| `scenarios.parquet` (A3) | `scenario, h` | macro path columns as in `macro_q`, `scenario_desc` |
| `panel_firmq.parquet` (A4) | `gvkey, qdate` | features, labels (`y_bucket_h`, `fa_h`, `watch_neg_h`, `migr_cat_h`), `sector_ff12`, `in_sample_flag`, `split` |
| `results/json/*.json` (A5–A8) | — | `{"metric": value, "ci": [lo,hi], "n": ..., "spec": "...", "code_commit": "..."}` |

### 6.4 Accuracy rules (non-negotiable)
1. **No hand-typed numbers.** Code → `results/json` + `results/tex` (auto-generated macros/tables) → report/slides. A **claim ledger** (`docs/claim_ledger.csv`: claim text, report location, results file, key) is maintained by A9 and audited by A11.
2. **Known-DGP Monte Carlo:** simulate a panel with known ordered-probit/logit parameters and cutpoints, run our estimators and marginal-effect code, and assert parameter recovery within Monte-Carlo tolerance (A11 builds, A5/A6 must pass).
3. **Cross-software replication:** ordered probit and Firth-logit coefficients and AMEs reproduced in R; max abs diff < 1e-4 (coefficients) and < 1e-3 (AMEs), else investigate.
4. **Leakage tests (automated):** every feature's `avail_date ≤ qdate`; macro `asof_date ≤ qdate`; labels use only data in `(t, t+h]`; winsorisation/standardisation/scaling fit on training window; embargo respected; no firm-quarter in both train and test with overlapping label windows.
5. **Stylised-fact checks:** empirical annual transition matrix vs published agency transition studies (diagonal persistence, IG→HY frequency, default rates by rating) — qualitative agreement required; discrepancies explained.
6. **Data lineage:** every raw pull logged (source, query/params, date pulled, row count, hash) in `docs/lineage.md`.
7. **Row-count and attrition tables** at every merge (who is lost and why).
8. **Reproducibility:** `make all` regenerates data-derived tables, figures, report numbers from raw inputs; `make test` runs unit, simulation, leakage tests.
9. **Reference hygiene:** every citation is verified against the actual source before use; the list in §11 is a starting point, not a verified bibliography.
10. **Licensing:** WRDS/Datastream data usually cannot be redistributed. Ship (a) free data (FRED/ALFRED, EDGAR-derived) in full, (b) licensed-data **extraction scripts + schema + a small anonymised sample/derived-feature panel only where the licence permits**. A0 checks terms in G0 and documents it in README.

### 6.5 Point-in-time discipline (summary)
Rating at `t` = last action effective on or before `t`. Fundamentals: only filings with `avail_date ≤ t`. Macro: values/vintages published by `t` (ALFRED). Labels: strictly after `t`. Winsorisation, scaling and imputation: training window only.

---

## 7. Solo execution workstreams (run in this order)

These workstreams replace the former multi-agent assignment model. They are ordered by dependencies and should be completed by the project owner. Do not wait for parallel agents or handoffs.

### W0 — Environment, repository, and WRDS access
- [ ] Create the repository and folders in §6.2.
- [ ] Set up Python environment and install dependencies from `requirements.txt`.
- [ ] Log into WRDS through the SMU-approved university access route and verify which products are enabled for the account.
- [ ] Test the Python `wrds` connection using the university-approved authentication method. Do not put passwords, tokens, or cookies in source code, notebooks, logs, or Git.
- [ ] In WRDS, inspect the available libraries and table schemas before writing extraction queries. Do not assume that a specific S&P ratings, Mergent FISD, TRACE, or Datastream table is licensed for this account.
- [ ] Save a source-access audit in `docs/data_audit.md`: database/table, coverage dates, identifiers, rating fields, Watch/Outlook fields, row count, and limitations.
- [ ] Freeze the US universe, rating mapping, sample dates, target definitions, and deliverable formats in `config/definitions.yaml`.

**Gate G0:** Python environment works; WRDS login works; available data products and licensing restrictions are documented. If issuer rating/Watch history is unavailable, record the fallback before modelling.

### W1 — Data extraction and audit
- [ ] Pull Compustat Quarterly (`fundq`) fundamentals for US firms.
- [ ] Audit issuer-rating history, effective dates, agency, outlook and CreditWatch data using the WRDS products actually available through SMU.
- [ ] If available and licensed, pull Datastream/LSEG bond data and/or Mergent FISD / Enhanced TRACE fields needed for the optional market-value extension.
- [ ] Pull FRED series and ALFRED vintages using Python.
- [ ] Write every query's parameters, extraction timestamp, row count, date range, and file hash to `docs/lineage.md`.
- [ ] Store raw licensed data under `data/raw/` and ensure Git ignores it.
- [ ] Produce coverage, missingness, duplicate, identifier, and year-by-year event-count reports.

**Gate G1:** Data coverage is known; a viable rating history exists; the sample is not silently restricted by missing years. Continue with the best supported source stack and disclose gaps.

### W2 — Cleaning and firm-quarter panel
- [ ] Map issuer identifiers to GVKEY and audit unmatched records.
- [ ] Convert ratings to the numeric scale in §3.3 and construct point-in-time quarterly ratings.
- [ ] Construct Watch/Outlook states and action intervals where source history permits.
- [ ] Compute firm fundamentals, TTM ratios, availability dates, and flags under §3.4/§4.3.
- [ ] Build macro quarterly features with release/vintage-aware dates.
- [ ] Merge into `panel_firmq.parquet`; build labels for 2-, 4-, and 8-quarter horizons.
- [ ] Apply the US issuer filters and FF12 sector mapping; produce an attrition table and descriptive statistics.
- [ ] Run leakage checks: no feature may be used before its availability date; labels must occur after the prediction date; train/validation/test windows must not overlap through labels.

**Gate G2:** Panel contract passes, labels and event counts are plausible, and leakage tests pass. If the number of test-period fallen angels is too small for stable inference, report confidence intervals and use BBB-band downgrade/negative-Watch events as secondary outcomes rather than overselling precision.

### W3 — Core models and early-warning validation
- [ ] Estimate M1 ordered probit and ordered logit, beginning with firm-only, then macro-only, then firm + macro.
- [ ] Estimate M1b transition models and M2 Watch/Outlook migration model if the required histories exist.
- [ ] Estimate N1 shadow-rating gap, partial-adjustment speed, and half-life with uncertainty intervals.
- [ ] Estimate M3 12-month fallen-angel logit/probit for the IG sample and BBB subsample.
- [ ] Use expanding-window temporal validation with embargo; do not use random train/test splits.
- [ ] Report ROC-AUC, PR-AUC, Brier score, log loss, calibration, top-decile capture/lift, and threshold-based lead time.
- [ ] Run the core robustness checks and placebo/negative-control tests.
- [ ] Save every result as machine-readable JSON/CSV/Parquet and every figure under `results/figures/`.

**Gate G3:** The core estimates run end-to-end, results are reproducible, and positive or null findings are both reported honestly.

### W4 — Macro stress testing and sector analysis
- [ ] Fit and diagnose a VAR using the macro series supported by the data audit.
- [ ] Generate baseline, tightening, hard-landing, stagflation, and easing scenarios as coherent conditional paths where technically supported.
- [ ] Apply the fitted fallen-angel model to the latest usable firm snapshot under each scenario.
- [ ] Aggregate changes in predicted risk by FF12 sector and report uncertainty bands.
- [ ] Compare model implications with realised 2008–09, 2020, and 2022–23 periods where sample coverage permits.
- [ ] Label static-balance-sheet assumptions and other limitations clearly.

**Gate G4:** Stress paths, diagnostics, sector summaries, and uncertainty estimates are generated from code.

### W5 — Report, slides, and final reproducibility
- [ ] Draft the report to the fixed 25-page specification in §9.1.
- [ ] Build a 20–22-slide presentation following §9.2.
- [ ] Pull all figures and result values from the Python-generated results registry.
- [ ] Complete `docs/claim_ledger.csv`: every quantitative claim maps to a result file and key.
- [ ] Run `python -m pytest`, run the full pipeline from a clean environment, and verify that the report and slides can be regenerated.
- [ ] Check page count, slide count, citations, licensing, and all limitations before final export.

**Gate G5:** 25-page report, 20–22-slide deck, Python code, runbook, and permitted data artifacts are complete and reproducible.

---

## 8. Execution order and working rules

There is no deadline-driven schedule in this plan. Begin at W0 immediately and move to the next workstream only when its gate is met. Prioritise a working minimum end-to-end pipeline over building every stretch feature at once.

**Mandatory core:** US data audit; rating and firm fundamentals; US macro data; point-in-time panel; ordered rating model; fallen-angel logit/probit; macro incremental-value tests; Watch/Outlook analysis where data supports it; stress scenarios; validation; report and slides.

**Optional extensions, only after the mandatory core works:** bond-return event study, market-based predictors, competing-risks hazard model, gradient boosting benchmark, reverse stress test, and detailed portfolio backtest. If data access or time/compute constraints block an extension, document it rather than substituting unverified data.

### WRDS access and running Python scripts

1. **Sign in first.** Open WRDS using the SMU library/university access route and authenticate with your university account. Follow SMU/WRDS instructions for any institutional VPN or single-sign-on requirement. Access is determined by the products licensed to SMU and enabled for your account.
2. **Check products and schemas.** In the WRDS web interface, confirm access to Compustat North America Fundamentals Quarterly and inspect available ratings/bond products. Table names and field availability vary by subscription; use the WRDS data dictionary and query builder to confirm them before writing SQL.
3. **Prepare a local project folder.** Use a supported Python 3.11+ installation and create a virtual environment:
   ```bash
   python -m venv .venv
   ```
   Activate it on Windows PowerShell:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   On macOS/Linux:
   ```bash
   source .venv/bin/activate
   ```
4. **Install project dependencies.** Once `requirements.txt` is created, run:
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
5. **Configure credentials safely.** Use the current WRDS-supported Python authentication method for your account. Prefer an interactive login or a local credentials file outside the repository with restrictive permissions, if supported by WRDS. Never paste a password into a notebook, Python script, command history, `.env` committed to Git, or this plan. Do not assume that legacy username/password examples work for every institution.
6. **Test connection before a large pull.** Create `src/credit/data_ratings/test_wrds_connection.py` (or the equivalent small test script) to authenticate, list accessible libraries/tables, and fetch a tiny sample from a table confirmed in the WRDS interface. Avoid `SELECT *` on large tables.
7. **Extract in small batches.** Use explicit columns and date filters. Start with a small year or a limited set of GVKEYs, validate the returned rows and dates, then expand the query. Save query text/parameters and metadata, not credentials, in `docs/lineage.md`.
8. **Run scripts from the repository root.** The intended command sequence will be:
   ```bash
   python -m src.credit.data_ratings.extract_ratings
   python -m src.credit.data_fund.extract_fundamentals
   python -m src.credit.data_macro.extract_macro
   python -m src.credit.panel.build_panel
   python -m src.credit.models_ordinal.fit_ordinal
   python -m src.credit.models_binary.fit_fallen_angel
   python -m src.credit.stress.run_scenarios
   python -m src.credit.reporting.build_outputs
   ```
   These are the planned module entry points; create each script before running it. If package imports require it, include `__init__.py` files in the `src/credit/` subdirectories and use a consistent package layout.
9. **Check outputs after every step.** Confirm the file exists, row count is nonzero where expected, date coverage is correct, identifiers are unique at the intended key, and the log reports no unexpected drops. Do not run all models on unverified merged data.
10. **Keep licensed data private.** Add `data/raw/`, credentials, local config files, and large licensed extracts to `.gitignore`. Share only extraction code, data schemas, documentation, and derived data explicitly permitted by the applicable licence.

**Common troubleshooting**
- **WRDS login/authentication fails:** re-check SMU access, institutional login/VPN requirements, and the currently supported WRDS Python authentication instructions; test web login first.
- **A library/table is missing:** the account may not have that subscription or the table may have a different name. Verify in WRDS and update the data audit; do not guess a table name.
- **A query returns no rows:** test one known identifier and date range, inspect field types, and confirm the product contains the requested years.
- **A pull is too large or times out:** filter by date, use explicit columns, and extract year-by-year or in manageable batches.
- **Ratings or Watch history ends early:** restrict the Watch/Outlook model to its documented coverage or use the ratings-only fallback in §4.1. Do not fabricate historical states.
- **Python package installation fails:** verify the active interpreter with `python --version` and `python -m pip --version`, then install into the active virtual environment.

---

## 9. Deliverable specifications

### 9.1 Report PDF — exactly 25 pages

The final report must be **25 pages total**, including references and appendices unless the course's submission rules explicitly define the page count differently. Verify the exported PDF page count programmatically. Use a compact, readable layout; do not inflate pages with oversized figures or empty space.

Recommended page budget:
1. Title page and abstract
2–3. Introduction, research question, hypotheses, contributions
4–5. Literature and institutional background
6–8. Data sources, US sample construction, coverage, attrition, descriptive statistics
9–11. Methodology and point-in-time/validation design
12–16. Core results: rating determinants, agency lag, Watch/Outlook, fallen-angel forecasting
17–18. Heterogeneity and sector vulnerability
19–20. Macro stress scenarios and historical comparison
21–22. Robustness, placebo tests, and model diagnostics
23. Limitations and conclusion
24–25. References and concise appendix (variable definitions / additional results)

Adjust page allocations only if necessary to meet course formatting rules. The final document must contain the actual results, not placeholder numbers. If the evidence does not support a proposed claim, report the null or inconclusive result.

### 9.2 Presentation — 20–22 slides

Target **21 slides** (within the required 20–22 range), with the following narrative:
1. Title and team/author
2. Motivation: rating agency lag and the BBB−/BB+ cliff
3. Research question and hypotheses
4. Contribution and what is new
5. US sample and data sources
6. Rating, Watch, and Outlook definitions
7. Sample construction and descriptive statistics
8. Empirical design and point-in-time safeguards
9. Ordered rating model: baseline
10. Macro block: incremental explanatory power
11. Shadow rating and agency-lag measure
12. CreditWatch/Outlook migration results
13. Fallen-angel prediction setup
14. Out-of-sample performance and calibration
15. Early-warning lead time
16. Heterogeneity by leverage/coverage
17. Sector vulnerability
18. Macro stress scenarios
19. Robustness, placebo tests, and diagnostics
20. Limitations and interpretation
21. Conclusion and Q&A

Use one primary message per slide. Figures should come from `results/figures/`; numerical claims should come from the results registry. Keep technical diagnostics and secondary model specifications in speaker notes or backup material only if the final slide count allows.

### 9.3 Python code and data package
- `README.md`: project overview, prerequisites, exact run order, expected runtime, data licensing restrictions.
- `requirements.txt` or `uv.lock`: pinned Python dependencies.
- `src/credit/`: modular Python extraction, cleaning, panel, modelling, stress, and reporting scripts.
- `config/`: dates, US universe, rating map, horizons, seeds, and split definitions.
- `docs/`: data audit, data dictionary, lineage, WRDS runbook, QA log, claim ledger.
- `tests/`: Python unit, simulation, and leakage tests.
- `results/`: machine-readable metrics, tables, and figures generated by scripts.
- Licensed raw WRDS/Datastream data must not be committed or redistributed unless the licence explicitly permits it.

## 10. Risk register

| Risk | Impact | Mitigation | Owner |
|---|---|---|---|
| Watch/Outlook history unavailable or short | M2/M4/N2 weakened | Early audit (G0); sub-period analysis; ratings-only fallback with explicit statement | A1/A0 |
| Too few fallen-angel events in test window | Low power for AUC/lead time | Report CIs; add BBB-band downgrade/Watch as secondary targets; rolling-origin evaluation | A4/A6 |
| Ratings table stops before our sample ends (legacy Compustat ratings) | Truncated sample | Source alternatives (§4.1); document coverage | A1 |
| ICE BofA series truncated on FRED | HY spread unavailable for full history | `BAA10Y` and Datastream spreads | A3 |
| Macro variables collinear; effective macro N small | Unstable γ, overconfident SE | Changes/orthogonalisation; time-block bootstrap; report both inference types | A3/A5 |
| Overlapping 12m labels → serial correlation, leakage | Inflated OOS performance | Embargo; clustered SE; leakage tests | A4/A11 |
| Look-ahead via fundamentals/macro revisions | Spurious results | `avail_date`, ALFRED, training-only transforms | A2/A3/A4 |
| Identifier mismatches (rating ↔ GVKEY) | Selection bias | Crosswalk audit, match-rate reporting | A1 |
| Datastream bond pricing noise | H5 unreliable | Label exploratory; TRACE if available | A8 |
| Scope creep | Late delivery | Tiering + slip policy (§8) | A0 |
| Redistribution restrictions on licensed data | Package incomplete | Share scripts, schemas, documentation, and only permitted derived/sample data (§6.4.10) | Solo owner |

---

## 11. Starting reference list (verify each against the source before citing)
- Kaplan & Urwitz (1979), *Statistical models of bond ratings*, Journal of Business.
- Blume, Lim & MacKinlay (1998), *The declining credit quality of U.S. corporate debt*, Journal of Finance.
- Nickell, Perraudin & Varotto (2000), *Stability of rating transitions*, Journal of Banking & Finance.
- Bangia, Diebold, Kronimus, Schagen & Schuermann (2002), *Ratings migration and the business cycle*, JBF.
- Amato & Furfine (2004), *Are credit ratings procyclical?*, JBF.
- Löffler (2004), *An anatomy of rating through the cycle*, JBF.
- Altman & Rijken (2004), *How rating agencies achieve rating stability*, JBF.
- Jarrow, Lando & Turnbull (1997), *A Markov model for the term structure of credit risk spreads*, RFS.
- Frydman & Schuermann (2008), *Credit rating dynamics and Markov mixture models*, JBF.
- Shumway (2001), *Forecasting bankruptcy more accurately: a simple hazard model*, Journal of Business.
- Campbell, Hilscher & Szilagyi (2008), *In search of distress risk*, JF.
- Duffie, Saita & Wang (2007), *Multi-period corporate default prediction with stochastic covariates*, JFE.
- Holthausen & Leftwich (1986), *The effect of bond rating changes on common stock prices*, JFE.
- Hand, Holthausen & Leftwich (1992), *The effect of bond rating agency announcements on bond and stock prices*, JF.
- Ellul, Jotikasthira & Lundblad (2011), *Regulatory pressure and fire sales in the corporate bond market*, JFE.
- Gilchrist & Zakrajšek (2012), *Credit spreads and business cycle fluctuations*, AER.
- Firth (1993), *Bias reduction of maximum likelihood estimates*, Biometrika.
- Brant (1990), *Assessing proportionality in the proportional odds model*, Biometrics.
- Waggoner & Zha (1999), *Conditional forecasts in dynamic multivariate models*, Review of Economics and Statistics.
- S&P Global Ratings, *Annual Global Corporate Default and Rating Transition Study* (benchmark for transition-matrix sanity check).

---

## 12. Open decisions for Mahir (resolve at G0)
1. **Deadline, report page limit, presentation length and format** (PPTX vs Beamer) — these set the back-scheduling in §8.
2. **Actual data access:** which of Compustat, CRSP, S&P/Capital IQ ratings, Mergent FISD, Enhanced TRACE, Datastream, Bloomberg you can reach through SMU. This determines the source stack in §4.1.
3. **US-only vs global:** default US-only (matches FRED macro). Global via Datastream is possible but needs region-specific macro and is a scope increase.
4. **Tier 2 appetite:** confirm which stretch items you want attempted if G2 is on time.
5. **Software expectations:** Python primary with R replication (proposed). If the course expects Stata/R as the main deliverable, A5/A6 outputs must be mirrored there.


---

## 13. Update log
- 2026-10-29: Converted the plan from a multi-agent, deadline-back-scheduled design to a solo Python workflow; fixed report length at 25 pages and presentation length at 20–22 slides; froze scope to the US market; added practical WRDS login, extraction, execution, and troubleshooting instructions; removed R replication requirements.
