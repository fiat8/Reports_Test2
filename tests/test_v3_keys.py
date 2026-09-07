import sys; sys.path.insert(0, ".")
import pandas as pd
from engine_v3 import keys
from engine_v3.config import LC

BASE = {
    LC["orig_zone"]: "BKK", LC["dest_zone"]: "CNX",
    LC["carrier"]: "100", LC["service"]: "FTL",
    LC["item_type"]: "CASE", LC["charge_code"]: "FLAT",
    LC["rate_code"]: "RC001", LC["applied_code"]: None,
    LC["cust_code"]: "9001", LC["cust_service"]: "STD",
    LC["pickup_date"]: pd.Timestamp("2026-05-16"),
}

def test_pri_ap():
    assert keys.build_pri_ap(BASE) == "BKKCNX100FTLCASEFLATRC001"

def test_draftflat_replace():
    row = {**BASE, LC["charge_code"]: "DRAFTFLAT", LC["rate_code"]: "DFTCASE-1"}
    assert "DFTFLAT" in keys.build_pri_ap(row)

def test_co_clears_item():
    row = {**BASE, LC["charge_code"]: "CO"}
    assert "CASE" not in keys.build_pri_ap(row)

def test_ar_pri_co():
    row = {**BASE, LC["charge_code"]: "CO"}
    assert "AR_CO" in keys.build_ar_pri(row)

def test_mandate_no_carrier():
    # mandate ไม่มี carrier/service
    m = keys.build_mandate_lc(BASE)
    assert "100" not in m and "FTL" not in m

def test_carrier_has_carrier():
    assert keys.build_carrier_lc(BASE).endswith("100")

def test_pickup_str_format():
    assert keys.pickup_str(BASE) == "16/05/2026"
