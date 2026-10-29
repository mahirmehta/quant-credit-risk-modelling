"""
Shared helper utilities for credit risk modelling pipeline.
Provides configuration loading, results registry serialization,
and Fama-French 12 sector mapping.
"""

import os
import json
import yaml
import numpy as np
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]


def load_yaml(rel_path: str) -> dict:
    """Load a YAML config file relative to the project root."""
    path = ROOT_DIR / rel_path
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_result_metric(
    key: str,
    value: float,
    ci: tuple = None,
    n: int = None,
    spec: str = "",
    notes: str = "",
    filename: str = None
):
    """
    Save a numerical result metric to the results registry.
    Strictly adheres to Section 6.4: No hand-typed numbers in report/slides.
    """
    res_dir = ROOT_DIR / "results" / "json"
    res_dir.mkdir(parents=True, exist_ok=True)
    
    if filename is None:
        filename = f"{key}.json"
    elif not filename.endswith(".json"):
        filename = f"{filename}.json"
        
    data = {
        "metric_key": key,
        "value": float(value) if isinstance(value, (int, float, np.floating, np.integer)) else value,
        "ci": [float(x) for x in ci] if ci is not None else None,
        "n": int(n) if n is not None else None,
        "spec": spec,
        "notes": notes
    }
    
    out_path = res_dir / filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return out_path


def load_results_registry() -> dict:
    """Load all JSON metric files from results/json into a unified dictionary."""
    res_dir = ROOT_DIR / "results" / "json"
    registry = {}
    if not res_dir.exists():
        return registry
    for f in res_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as jf:
                d = json.load(jf)
                registry[d["metric_key"]] = d
        except Exception:
            pass
    return registry


def assign_ff12_sector(sic_code: int) -> str:
    """
    Map 4-digit SIC code to Fama-French 12 Industry sectors.
    Excludes Financials (6000-6999) and Utilities (4900-4999) in core sample.
    """
    if pd.isna(sic_code):
        return "Other"
    sic = int(sic_code)
    
    # 1 Consumer Non-Durables: Food, Tobacco, Textiles, Apparel, Leather, Toys
    if (100 <= sic <= 999) or (2000 <= sic <= 2399) or (2700 <= sic <= 2749) or (2770 <= sic <= 2799) or (3100 <= sic <= 3199) or (3940 <= sic <= 3989):
        return "NoDur"
    # 2 Consumer Durables: Cars, TVs, Furniture, Household Appliances
    elif (2500 <= sic <= 2519) or (2590 <= sic <= 2599) or (3630 <= sic <= 3659) or (3710 <= sic <= 3711) or (3714 <= sic <= 3714) or (3716 <= sic <= 3716) or (3750 <= sic <= 3751) or (3792 <= sic <= 3792) or (3900 <= sic <= 3939) or (3990 <= sic <= 3999):
        return "Durbl"
    # 3 Manufacturing: Machinery, Trucks, Planes, Chemicals, Off Furn, Paper, Com Printing
    elif (2520 <= sic <= 2589) or (2600 <= sic <= 2699) or (2750 <= sic <= 2769) or (3000 <= sic <= 3099) or (3200 <= sic <= 3569) or (3580 <= sic <= 3629) or (3700 <= sic <= 3709) or (3712 <= sic <= 3713) or (3715 <= sic <= 3715) or (3717 <= sic <= 3749) or (3752 <= sic <= 3791) or (3793 <= sic <= 3799) or (3830 <= sic <= 3839) or (3860 <= sic <= 3899):
        return "Manuf"
    # 4 Oil, Gas, and Coal Extraction and Products
    elif (1200 <= sic <= 1399) or (2900 <= sic <= 2999):
        return "Enrgy"
    # 5 Chemicals and Allied Products
    elif (2800 <= sic <= 2829) or (2840 <= sic <= 2899):
        return "Chems"
    # 6 Business Equipment: Computers, Software, and Electronic Equipment
    elif (3570 <= sic <= 3579) or (3660 <= sic <= 3692) or (3694 <= sic <= 3699) or (3810 <= sic <= 3829) or (7370 <= sic <= 7379):
        return "BusEq"
    # 7 Telephone and Television Transmission
    elif (4800 <= sic <= 4899):
        return "Telcm"
    # 8 Utilities
    elif (4900 <= sic <= 4949):
        return "Utils"
    # 9 Wholesale, Retail, and Some Services (Laundries, Repair Shops)
    elif (5000 <= sic <= 5999) or (7200 <= sic <= 7299) or (7600 <= sic <= 7699):
        return "Shops"
    # 10 Healthcare, Medical Equipment, and Drugs
    elif (2830 <= sic <= 2836) or (3693 <= sic <= 3693) or (3840 <= sic <= 3859) or (8000 <= sic <= 8099):
        return "Hlth"
    # 11 Finance
    elif (6000 <= sic <= 6999):
        return "Money"
    # 12 Other: Mines, Constr, BldMt, Trans, Hotels, Bus Serv, Entertainment
    else:
        return "Other"
