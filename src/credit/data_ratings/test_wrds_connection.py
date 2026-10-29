"""
Test WRDS Python connection and audit accessible libraries.
Complies with Section 7 W0 and Section 8.5/8.6:
Never hardcode passwords or credentials. Uses pgpass or interactive auth if available.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]


def check_wrds():
    print("[WRDS Audit] Checking WRDS Python connector...")
    try:
        import wrds
        print(f"  [OK] WRDS package installed.")
    except ImportError:
        print("  [FAIL] wrds package not installed.")
        return False
        
    home = Path.home()
    pgpass = home / ".pgpass"
    wrds_key = home / ".wrds_key"
    
    print(f"  [Info] User home: {home}")
    print(f"  [Info] .pgpass exists: {pgpass.exists()}")
    print(f"  [Info] .wrds_key exists: {wrds_key.exists()}")
    
    if not pgpass.exists() and "WRDS_USERNAME" not in os.environ:
        print("  [Notice] No automated WRDS credentials found in environment or .pgpass.")
        print("  [Notice] To configure automated login, run: wrds.Connection(wrds_username='your_username').create_pgpass_file()")
        return False
        
    try:
        db = wrds.Connection()
        print("  [OK] Successfully connected to WRDS PostgreSQL server!")
        # Audit key libraries
        libs = db.list_libraries()
        key_libs = ["comp", "crsp", "fisd", "ciq", "datastream"]
        print("  [Libraries] Available matching key subscriptions:")
        for kl in key_libs:
            matches = [lib for lib in libs if kl in lib.lower()]
            print(f"    - {kl}: {matches}")
        db.close()
        return True
    except Exception as e:
        print(f"  [Notice] WRDS connection attempt returned: {e}")
        return False


if __name__ == "__main__":
    check_wrds()
