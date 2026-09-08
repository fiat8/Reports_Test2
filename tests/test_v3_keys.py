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


# ── FLAT Fallback tests ──────────────────────────────────────────────────────
def test_is_flat_fallback():
    assert keys.is_flat_fallback("FLAT") == True
    assert keys.is_flat_fallback("FLATM") == True
    assert keys.is_flat_fallback("FLATP") == True
    assert keys.is_flat_fallback("SDFLAT") == False   # ขึ้นต้น SDFL
    assert keys.is_flat_fallback("CASE") == False
    assert keys.is_flat_fallback("CO") == False
    assert keys.is_flat_fallback("DRAFTFLAT") == False

def test_pri_ap_noitem_removes_item():
    row = {**BASE, LC["charge_code"]: "FLATM"}
    with_item = keys.build_pri_ap(row)
    without = keys.build_pri_ap_noitem(row)
    assert "CASE" in with_item
    assert "CASE" not in without

def test_noitem_no_replace():
    # DRAFTFLAT ไม่เข้า fallback (ไม่ใช่ Left4=FLAT)
    assert keys.is_flat_fallback("DRAFTFLAT") == False
