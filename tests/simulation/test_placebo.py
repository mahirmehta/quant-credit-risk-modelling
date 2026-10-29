"""
Placebo tests and negative control verification suite.
Mandated by Section 1 (N7), Section 5 (Robustness Battery), and Section 6.4 of plan_updated.md.

Includes:
  1. Permuted macro block across time randomly (breaking time-series alignment):
     Incremental predictive power drops to zero; joint Wald test p > 0.05.
  2. Shuffled label negative control:
     Target label (fa_h) randomly permuted across observations; ROC-AUC collapses to ~0.50 (+/- 0.04).
  3. Likelihood ratio contrast:
     Demonstrates that genuine macro alignment delivers statistically significant explanatory gain,
     while time-permuted macro noise does not.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy.stats import chi2
from sklearn.metrics import roc_auc_score
import statsmodels.api as sm

ROOT_DIR = Path(__file__).resolve().parents[2]
PANEL_PATH = ROOT_DIR / "data" / "processed" / "panel_firmq.parquet"


@pytest.fixture(scope="module")
def train_dataset():
    """Load clean training dataset from processed firm-quarter panel."""
    assert PANEL_PATH.exists(), f"Panel parquet missing: {PANEL_PATH}"
    df = pd.read_parquet(PANEL_PATH)
    train_df = df[df["split"] == "train"].dropna(
        subset=[
            "fa_h", "leverage", "roa", "log_assets", "interest_coverage",
            "term_spread", "d4_fedfunds", "d4_hy_oas"
        ]
    ).copy()
    assert len(train_df) > 5000, f"Insufficient train observations: {len(train_df)}"
    return train_df


class TestPlaceboAndNegativeControls:
    """Robustness battery: placebo time-series breaks and negative controls."""

    def test_shuffled_label_auc_negative_control(self, train_dataset):
        """
        Negative control test (Section 5 Robustness Battery):
        When target labels (fa_h) are randomly permuted across observations,
        any fitted classification model must produce a discriminatory ROC-AUC
        that collapses to approximately 0.50 (+/- 0.04), indicating no spurious signal.
        """
        np.random.seed(12345)
        
        firm_features = ["leverage", "roa", "log_assets", "interest_coverage"]
        macro_features = ["term_spread", "d4_fedfunds"]
        all_features = firm_features + macro_features
        
        X = sm.add_constant(train_dataset[all_features])
        y_true = train_dataset["fa_h"].values
        
        # Fit baseline model on real data
        model = sm.Logit(y_true, X).fit(disp=False)
        pred_probs = model.predict(X)
        
        real_auc = roc_auc_score(y_true, pred_probs)
        assert real_auc > 0.52, f"Baseline model has non-informative AUC on real data: {real_auc:.4f}"
        
        # Shuffled labels negative control
        y_shuffled = np.random.permutation(y_true)
        shuffled_auc = roc_auc_score(y_shuffled, pred_probs)
        
        print(f"\n[Negative Control - Shuffled Labels]")
        print(f"  Real ROC-AUC:     {real_auc:.4f}")
        print(f"  Shuffled ROC-AUC: {shuffled_auc:.4f} (target: 0.50 +/- 0.04)")
        
        assert 0.46 <= shuffled_auc <= 0.54, (
            f"Shuffled label AUC {shuffled_auc:.4f} deviates significantly from random guess 0.50 (+/- 0.04)"
        )

    def test_permuted_macro_wald_test_null(self, train_dataset):
        """
        Placebo test (Section 5 Robustness Battery):
        Permute macro block across time randomly (breaking time-series alignment
        between macroeconomic cycles and firm credit events).
        Verify that the macro incremental predictive power drops to zero:
        Joint Wald test fails to reject H0: beta_macro = 0 (p-value > 0.05).
        """
        np.random.seed(2026)
        
        firm_vars = ["leverage", "roa", "log_assets"]
        macro_vars = ["term_spread", "d4_fedfunds"]
        
        # Extract unique quarter macro block
        macro_quarterly = train_dataset[["qdate"] + macro_vars].drop_duplicates("qdate").reset_index(drop=True)
        
        # Permute quarters across time
        unique_quarters = macro_quarterly["qdate"].values
        shuffled_quarters = np.random.permutation(unique_quarters)
        
        macro_permuted = macro_quarterly.copy()
        macro_permuted["qdate"] = shuffled_quarters
        
        # Merge permuted macro block back onto firm panel by quarter
        firm_slice = train_dataset[["gvkey", "qdate"] + firm_vars + ["fa_h"]]
        perm_data = firm_slice.merge(macro_permuted, on="qdate", how="left")
        
        X_perm = sm.add_constant(perm_data[firm_vars + macro_vars])
        y = perm_data["fa_h"]
        
        model_perm = sm.Logit(y, X_perm).fit(disp=False)
        
        # Joint Wald test on macro coefficients: [term_spread == 0, d4_fedfunds == 0]
        k_vars = firm_vars + macro_vars
        r_matrix = np.zeros((len(macro_vars), len(model_perm.params)))
        for i, m_var in enumerate(macro_vars):
            r_matrix[i, k_vars.index(m_var) + 1] = 1.0
            
        wald = model_perm.wald_test(r_matrix)
        wald_stat = float(wald.statistic)
        p_val = float(wald.pvalue)
        
        print(f"\n[Placebo - Permuted Macro Block across Time]")
        print(f"  Joint Wald test on permuted macro block: stat={wald_stat:.4f}, p-value={p_val:.4f}")
        print(f"  Macro coefficients under permuted timing:")
        for m_var in macro_vars:
            coef = model_perm.params[m_var]
            se = model_perm.bse[m_var]
            print(f"    {m_var}: coef={coef:.4f}, se={se:.4f}, z={coef/se:.3f}")
            
        assert p_val > 0.05, (
            f"Placebo test failed! Permuted macro block rejected null with p = {p_val:.4f} <= 0.05. "
            f"Expected p > 0.05 when time alignment is broken."
        )

    def test_genuine_vs_permuted_macro_lr_test(self, train_dataset):
        """
        Verify contrast between genuine macro timing vs placebo permuted timing:
        - Genuine macro additions produce statistically significant likelihood gains (p < 0.05).
        - Permuted placebo macro additions fail to provide significant likelihood gains (p > 0.05).
        """
        np.random.seed(999)
        firm_vars = ["leverage", "roa", "log_assets"]
        macro_vars = ["term_spread", "d4_fedfunds"]
        y = train_dataset["fa_h"]
        
        # 1. Restricted model (firm only)
        X_res = sm.add_constant(train_dataset[firm_vars])
        mod_res = sm.Logit(y, X_res).fit(disp=False)
        
        # 2. Genuine macro model
        X_gen = sm.add_constant(train_dataset[firm_vars + macro_vars])
        mod_gen = sm.Logit(y, X_gen).fit(disp=False)
        lr_stat_gen = 2.0 * (mod_gen.llf - mod_res.llf)
        lr_pval_gen = 1.0 - chi2.cdf(lr_stat_gen, df=len(macro_vars))
        
        # 3. Permuted macro model
        macro_block = train_dataset[["qdate"] + macro_vars].drop_duplicates("qdate").reset_index(drop=True)
        macro_block["qdate"] = np.random.permutation(macro_block["qdate"].values)
        perm_data = train_dataset[["gvkey", "qdate"] + firm_vars + ["fa_h"]].merge(macro_block, on="qdate", how="left")
        
        X_perm = sm.add_constant(perm_data[firm_vars + macro_vars])
        y_perm = perm_data["fa_h"]
        mod_perm = sm.Logit(y_perm, X_perm).fit(disp=False)
        lr_stat_perm = 2.0 * (mod_perm.llf - mod_res.llf)
        lr_pval_perm = 1.0 - chi2.cdf(max(0.0, lr_stat_perm), df=len(macro_vars))
        
        print(f"\n[LR Test Comparison: Genuine vs Permuted Macro]")
        print(f"  Genuine Macro:  LR Stat = {lr_stat_gen:.3f}, p-value = {lr_pval_gen:.4e}")
        print(f"  Permuted Macro: LR Stat = {lr_stat_perm:.3f}, p-value = {lr_pval_perm:.4f}")
        
        assert lr_pval_gen < 0.05, f"Genuine macro was not significant: p = {lr_pval_gen:.4f}"
        assert lr_pval_perm > 0.05, f"Permuted macro was spuriously significant: p = {lr_pval_perm:.4f}"
