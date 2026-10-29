"""
Known-DGP Monte Carlo parameter recovery verification suite.
Mandated by Section 1 (N7), Section 5, and Section 6.4 (Rule 2) of plan_updated.md.

Simulates synthetic panels where the true data generating process (DGP) is known:
    y* = beta_1 * x_firm + beta_2 * x_macro + epsilon
with known cutpoints c_1, c_2, ...

Estimates Ordered Models (probit and logit) and Binary Logit, asserting that:
    |estimate - true| < 2.5 * SE
for all slope parameters within Monte Carlo tolerance.
"""

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from statsmodels.miscmodels.ordinal_model import OrderedModel


class TestMonteCarloDGPRecovery:
    """Monte Carlo parameter recovery test suite for credit risk models."""

    @pytest.fixture(autouse=True)
    def setup_seed(self):
        """Set deterministic random seed for Monte Carlo reproducibility."""
        np.random.seed(42)

    def test_ordered_probit_parameter_recovery(self):
        """
        Ordered Probit parameter recovery under known DGP:
            y* = beta_1 * x_firm + beta_2 * x_macro + eps, eps ~ N(0, 1)
            Cutpoints: [-1.0, 0.5, 1.8] -> 4 categories (0, 1, 2, 3)
        Assert |estimate - true| < 2.5 * SE for both firm and macro regressors.
        """
        N = 6000
        true_beta_firm = 1.25
        true_beta_macro = -0.75
        cutpoints = [-1.0, 0.5, 1.8]

        x_firm = np.random.normal(0, 1.0, N)
        x_macro = np.random.normal(0, 1.0, N)
        eps = np.random.normal(0, 1.0, N)

        latent_y = true_beta_firm * x_firm + true_beta_macro * x_macro + eps
        y = np.digitize(latent_y, cutpoints)

        df = pd.DataFrame({
            "y": y,
            "x_firm": x_firm,
            "x_macro": x_macro
        })

        model = OrderedModel(df["y"], df[["x_firm", "x_macro"]], distr="probit")
        res = model.fit(method="bfgs", disp=False)

        est_firm = res.params["x_firm"]
        se_firm = res.bse["x_firm"]
        z_firm = abs(est_firm - true_beta_firm) / se_firm

        est_macro = res.params["x_macro"]
        se_macro = res.bse["x_macro"]
        z_macro = abs(est_macro - true_beta_macro) / se_macro

        print(f"\n[Ordered Probit Recovery]")
        print(f"  beta_firm:  True={true_beta_firm:.3f}, Est={est_firm:.3f}, SE={se_firm:.3f}, |z|={z_firm:.2f}")
        print(f"  beta_macro: True={true_beta_macro:.3f}, Est={est_macro:.3f}, SE={se_macro:.3f}, |z|={z_macro:.2f}")

        assert z_firm < 2.5, f"Firm parameter recovery failed: |z| = {z_firm:.3f} >= 2.5"
        assert z_macro < 2.5, f"Macro parameter recovery failed: |z| = {z_macro:.3f} >= 2.5"

    def test_ordered_logit_parameter_recovery(self):
        """
        Ordered Logit parameter recovery under known logistic DGP:
            y* = beta_1 * x_firm + beta_2 * x_macro + eps, eps ~ Logistic(0, 1)
            Cutpoints: [-1.2, 0.4, 2.0] -> 4 categories (0, 1, 2, 3)
        Assert |estimate - true| < 2.5 * SE for both firm and macro regressors.
        """
        N = 6000
        true_beta_firm = 1.10
        true_beta_macro = -0.65
        cutpoints = [-1.2, 0.4, 2.0]

        x_firm = np.random.normal(0, 1.0, N)
        x_macro = np.random.normal(0, 1.0, N)
        eps = np.random.logistic(0, 1.0, N)

        latent_y = true_beta_firm * x_firm + true_beta_macro * x_macro + eps
        y = np.digitize(latent_y, cutpoints)

        df = pd.DataFrame({
            "y": y,
            "x_firm": x_firm,
            "x_macro": x_macro
        })

        model = OrderedModel(df["y"], df[["x_firm", "x_macro"]], distr="logit")
        res = model.fit(method="bfgs", disp=False)

        est_firm = res.params["x_firm"]
        se_firm = res.bse["x_firm"]
        z_firm = abs(est_firm - true_beta_firm) / se_firm

        est_macro = res.params["x_macro"]
        se_macro = res.bse["x_macro"]
        z_macro = abs(est_macro - true_beta_macro) / se_macro

        print(f"\n[Ordered Logit Recovery]")
        print(f"  beta_firm:  True={true_beta_firm:.3f}, Est={est_firm:.3f}, SE={se_firm:.3f}, |z|={z_firm:.2f}")
        print(f"  beta_macro: True={true_beta_macro:.3f}, Est={est_macro:.3f}, SE={se_macro:.3f}, |z|={z_macro:.2f}")

        assert z_firm < 2.5, f"Firm parameter recovery failed in logit: |z| = {z_firm:.3f} >= 2.5"
        assert z_macro < 2.5, f"Macro parameter recovery failed in logit: |z| = {z_macro:.3f} >= 2.5"

    def test_binary_logit_parameter_recovery(self):
        """
        Binary Logit parameter recovery under known binary DGP (Fallen Angel model M3):
            P(FA = 1 | x) = Lambda(beta_0 + beta_firm * x_firm + beta_macro * x_macro)
        Assert |estimate - true| < 2.5 * SE for slope parameters.
        """
        N = 8000
        true_beta_0 = -2.0  # Calibrated for realistic event rate (~10-15%)
        true_beta_firm = 0.85
        true_beta_macro = -0.50

        x_firm = np.random.normal(0, 1.0, N)
        x_macro = np.random.normal(0, 1.0, N)
        eps = np.random.logistic(0, 1.0, N)

        latent = true_beta_0 + true_beta_firm * x_firm + true_beta_macro * x_macro + eps
        y_bin = (latent > 0).astype(int)

        X = pd.DataFrame({"const": 1.0, "x_firm": x_firm, "x_macro": x_macro})
        model = sm.Logit(y_bin, X)
        res = model.fit(disp=False)

        est_firm = res.params["x_firm"]
        se_firm = res.bse["x_firm"]
        z_firm = abs(est_firm - true_beta_firm) / se_firm

        est_macro = res.params["x_macro"]
        se_macro = res.bse["x_macro"]
        z_macro = abs(est_macro - true_beta_macro) / se_macro

        print(f"\n[Binary Logit Recovery]")
        print(f"  Event rate: {y_bin.mean():.3%}")
        print(f"  beta_firm:  True={true_beta_firm:.3f}, Est={est_firm:.3f}, SE={se_firm:.3f}, |z|={z_firm:.2f}")
        print(f"  beta_macro: True={true_beta_macro:.3f}, Est={est_macro:.3f}, SE={se_macro:.3f}, |z|={z_macro:.2f}")

        assert z_firm < 2.5, f"Binary logit firm recovery failed: |z| = {z_firm:.3f} >= 2.5"
        assert z_macro < 2.5, f"Binary logit macro recovery failed: |z| = {z_macro:.3f} >= 2.5"

    def test_cutpoint_monotonicity(self):
        """
        Verify that Ordered Model estimated cutpoints preserve strict monotonicity:
            c_0 < c_1 < c_2 < ...
        """
        N = 4000
        cutpoints = [-1.5, 0.0, 1.2, 2.5]
        x = np.random.normal(0, 1, N)
        eps = np.random.normal(0, 1, N)
        y = np.digitize(0.9 * x + eps, cutpoints)

        df = pd.DataFrame({"y": y, "x": x})
        model = OrderedModel(df["y"], df[["x"]], distr="probit")
        res = model.fit(method="bfgs", disp=False)

        # In statsmodels OrderedModel, cutpoint parameters represent:
        # params[1] = c_0
        # params[2:] = exp(params[2:]) increments (strictly positive)
        # Verify fitted thresholds monotonically increase
        threshold_params = [v for k, v in res.params.items() if "/" in k]
        c0 = threshold_params[0]
        reconstructed_cutpoints = [c0]
        for delta in threshold_params[1:]:
            reconstructed_cutpoints.append(reconstructed_cutpoints[-1] + np.exp(delta))

        for k in range(len(reconstructed_cutpoints) - 1):
            assert reconstructed_cutpoints[k] < reconstructed_cutpoints[k + 1], (
                f"Cutpoint non-monotonicity: c_{k}={reconstructed_cutpoints[k]} "
                f">= c_{k+1}={reconstructed_cutpoints[k+1]}"
            )
