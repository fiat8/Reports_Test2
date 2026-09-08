# =============================================================================
# engine_v3/trace.py — Trace helper สำหรับหน้า UI
# หา AP/AR Data ทุกแถวที่ match กับ Load ID ที่เลือก
# (แสดงทุก rate ที่ key ตรง + date ตรง — ไม่ใช่แค่แถวแรก)
# =============================================================================

import pandas as pd
from engine_v3 import keys
from engine_v3.keys import s
from engine_v3.config import EXCLUDE_RATE_TARIFF, STOP_CODES


def _not_custpickup(row):
    return s(row.get("Rate Tariff ID")) != EXCLUDE_RATE_TARIFF


def trace_ap(result_row, ap_raw: pd.DataFrame) -> pd.DataFrame:
    """
    หา AP Data ทุกแถวที่ match กับ Load นี้
    เงื่อนไข: Pri-Columns == Pri-AP (ของ Load)
             AND Effective ≤ Pickup ≤ Expiration
    Returns: AP Data (ทุก column ต้นฉบับ) เฉพาะแถวที่ match
    """
    if ap_raw is None or ap_raw.empty:
        return pd.DataFrame()

    pri_ap = result_row.get("Pri-AP")
    pri_ap2 = result_row.get("Pri-AP2")   # fallback without item
    pickup = pd.to_datetime(result_row.get("PickupConfirmed Date"), errors="coerce")

    df = ap_raw.copy()
    # สร้าง key ทั้ง with + without item
    df["_pricol"]  = df.apply(keys.ap_pri_columns, axis=1)
    df["_pricol2"] = df.apply(keys.ap_pri_columns_noitem, axis=1)

    # match key (with หรือ without)
    key_match = (df["_pricol"] == pri_ap)
    if pri_ap2:
        key_match = key_match | (df["_pricol2"] == pri_ap2)

    hit = df[key_match].copy()
    if hit.empty:
        return pd.DataFrame()

    # date filter
    if pd.notna(pickup) and "Effective Date" in hit.columns:
        eff = pd.to_datetime(hit["Effective Date"], errors="coerce")
        exp = pd.to_datetime(hit["Expiration Date"], errors="coerce")
        date_ok = (pickup >= eff) & (pickup <= exp)
        hit = hit[date_ok]

    # ลบ helper columns
    drop = ["_pricol", "_pricol2", "_ap_row"]
    return hit.drop(columns=[c for c in drop if c in hit.columns], errors="ignore").reset_index(drop=True)


def trace_ar(result_row, ar_raw: pd.DataFrame) -> pd.DataFrame:
    """
    หา AR Data ทุกแถวที่ match กับ Load นี้
    เงื่อนไข: Pri-Columns == AR-Pri AND date ตรง
    """
    if ar_raw is None or ar_raw.empty:
        return pd.DataFrame()

    ar_pri = result_row.get("AR-Pri")
    pickup = pd.to_datetime(result_row.get("PickupConfirmed Date"), errors="coerce")

    df = ar_raw.copy()
    df["_pricol"] = df.apply(keys.ar_pri_columns, axis=1)

    hit = df[df["_pricol"] == ar_pri].copy()
    if hit.empty:
        return pd.DataFrame()

    # date filter
    if pd.notna(pickup) and "EFFECTIVEDATE" in hit.columns:
        eff = pd.to_datetime(hit["EFFECTIVEDATE"], errors="coerce")
        exp = pd.to_datetime(hit["EXPIRATIONDATE"], errors="coerce")
        date_ok = (pickup >= eff) & (pickup <= exp)
        hit = hit[date_ok]

    drop = ["_pricol", "_ar_row"]
    return hit.drop(columns=[c for c in drop if c in hit.columns], errors="ignore").reset_index(drop=True)
