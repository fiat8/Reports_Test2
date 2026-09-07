# =============================================================================
# engine_v3/keys.py — รวมศูนย์การสร้าง key ทุกแบบ
# ใช้ทั้ง 3 stage:
#   - Load Confirm side: Pri-AP, Mandate, Carrier, Truck, Stop, AR-Pri, AR-Stop
#   - AP Data side: Pri-Columns, Mandate-key, Sub-key1/2, Stop-Columns
#   - AR Data side: Pri-Columns, Stop-Columns
# =============================================================================

import pandas as pd
from engine_v3.config import (
    LC, DRAFTFLAT_CODE, DRAFTFLAT_FROM, DRAFTFLAT_TO,
    CO_CODE, AR_CO_MARKER, DATE_EN_AU,
)


def s(val) -> str:
    """null/NaN → '' ; float ที่เป็นจำนวนเต็ม → ตัด .0"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val)


# =============================================================================
# LOAD CONFIRM SIDE — สร้าง key จาก main data
# =============================================================================
def _rate_code_lc(row) -> str:
    """DRAFTFLAT: replace DFTCASE→DFTFLAT"""
    raw = s(row.get(LC["rate_code"]))
    if s(row.get(LC["charge_code"])) == DRAFTFLAT_CODE:
        return raw.replace(DRAFTFLAT_FROM, DRAFTFLAT_TO)
    return raw


def _ap_item_type_lc(row) -> str:
    """CO: item type = ''"""
    if s(row.get(LC["charge_code"])) == CO_CODE:
        return ""
    return s(row.get(LC["item_type"]))


def build_pri_ap(row) -> str:
    """Pri-AP = OrigZone+DestZone+Carrier+Service+ItemType+Charge+RateCode"""
    return (
        s(row.get(LC["orig_zone"])) + s(row.get(LC["dest_zone"]))
        + s(row.get(LC["carrier"])) + s(row.get(LC["service"]))
        + _ap_item_type_lc(row) + s(row.get(LC["charge_code"]))
        + _rate_code_lc(row)
    )


def build_mandate_lc(row) -> str:
    """Mandate = OrigZone+DestZone+ItemType+Charge+RateCode"""
    return (
        s(row.get(LC["orig_zone"])) + s(row.get(LC["dest_zone"]))
        + _ap_item_type_lc(row) + s(row.get(LC["charge_code"]))
        + _rate_code_lc(row)
    )


def build_carrier_lc(row) -> str:
    """Sup-Carrier = Mandate + Carrier"""
    return build_mandate_lc(row) + s(row.get(LC["carrier"]))


def build_truck_lc(row) -> str:
    """Sup-Truck = Mandate + Service"""
    return build_mandate_lc(row) + s(row.get(LC["service"]))


def build_ap_stop_lc(row) -> str:
    """AP Stop = Carrier+Service+(AppliedRate ถ้ามี ไม่งั้น RateCode)"""
    applied = s(row.get(LC["applied_code"]))
    tail = applied if applied != "" else _rate_code_lc(row)
    return s(row.get(LC["carrier"])) + s(row.get(LC["service"])) + tail


def build_ar_pri(row) -> str:
    """
    AR-Pri 3 cases:
      DRAFTFLAT: itemType + chargeCode
      CO:        custCode + custService + AR_CO + rateCodeRaw
      normal:    custCode + custService + chargeCode + rateCodeRaw
    """
    charge = s(row.get(LC["charge_code"]))
    raw = s(row.get(LC["rate_code"]))
    if charge == DRAFTFLAT_CODE:
        return s(row.get(LC["item_type"])) + charge
    elif charge == CO_CODE:
        return (s(row.get(LC["cust_code"])) + s(row.get(LC["cust_service"]))
                + AR_CO_MARKER + raw)
    else:
        return (s(row.get(LC["cust_code"])) + s(row.get(LC["cust_service"]))
                + charge + raw)


def build_ar_stop_lc(row) -> str:
    """AR Stop = custCode + custService + rateCodeRaw"""
    return (s(row.get(LC["cust_code"])) + s(row.get(LC["cust_service"]))
            + s(row.get(LC["rate_code"])))


def pickup_str(row) -> str:
    """PickupConfirmed Date → DD/MM/YYYY (en-AU)"""
    pk = row.get(LC["pickup_date"])
    if pk is None or (isinstance(pk, float) and pd.isna(pk)):
        return ""
    try:
        return pd.Timestamp(pk).strftime(DATE_EN_AU)
    except Exception:
        return ""


def add_load_confirm_keys(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stage 1.3: เพิ่ม key ทุกตัวเข้า Load Confirm (main)
    """
    df = df.copy()
    df["Pri-AP"]       = df.apply(build_pri_ap, axis=1)
    df["Mandate Key"]  = df.apply(build_mandate_lc, axis=1)
    df["Sup-Carrier"]  = df.apply(build_carrier_lc, axis=1)
    df["Sup-Truck"]    = df.apply(build_truck_lc, axis=1)
    df["AP Stop"]      = df.apply(build_ap_stop_lc, axis=1)
    df["AR-Pri"]       = df.apply(build_ar_pri, axis=1)
    df["AR Stop"]      = df.apply(build_ar_stop_lc, axis=1)
    df["_pickup_str"]  = df.apply(pickup_str, axis=1)
    df["Final key"]    = df["Pri-AP"] + df["_pickup_str"]
    df["AR-Final key"] = df["AR-Pri"] + df["_pickup_str"]
    return df


# =============================================================================
# AP DATA SIDE — สร้าง key จากไฟล์ AP (raw columns)
# =============================================================================
def ap_pri_columns(row) -> str:
    """Pri-Columns = OrigZone+DestZone+Carrier+Service+Item+Charge+RateCode"""
    return "".join(s(row.get(c)) for c in [
        "Origin Zone Code", "Dest. Zone Code", "Carrier ID",
        "Service ID", "Item Type", "Charge Code", "Rate Code",
    ])


def ap_mandate_key(row) -> str:
    return "".join(s(row.get(c)) for c in [
        "Origin Zone Code", "Dest. Zone Code",
        "Item Type", "Charge Code", "Rate Code",
    ])


def ap_sub_key2(row) -> str:
    """Carrier: mandate + Carrier"""
    return ap_mandate_key(row) + s(row.get("Carrier ID"))


def ap_sub_key1(row) -> str:
    """Truck: mandate + Service"""
    return ap_mandate_key(row) + s(row.get("Service ID"))


def ap_stop_columns(row) -> str:
    return "".join(s(row.get(c)) for c in ["Carrier ID", "Service ID", "Rate Code"])


# =============================================================================
# AR DATA SIDE
# =============================================================================
def ar_pri_columns(row) -> str:
    return "".join(s(row.get(c)) for c in
                   ["CUST_CD", "SERVICE_ID", "CHARGE_ID", "RATECODE"])


def ar_stop_columns(row) -> str:
    return "".join(s(row.get(c)) for c in ["CUST_CD", "SERVICE_ID", "RATECODE"])
