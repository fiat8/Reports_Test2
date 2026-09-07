# =============================================================================
# engine_v3/stage2_finalmap.py — Stage 2: Final Map (date-range)
#
# สร้าง rate lookup table แบบ M-Code APFinal/ARFinal:
#   1. เตรียม AP Master (Generic/Child) + AR Master (Normal) จาก AP/AR Data
#   2. SDFLAT: transform → append เข้า Generic (2.5 → 2.6)
#   3. date-range join กับ Load Confirm (Pri-AP + Pickup ∈ [Eff, Exp])
#   4. Final key = Pri-AP + PickupDate
# =============================================================================

import pandas as pd
from engine_v3 import keys
from engine_v3.keys import s
from engine_v3.config import (
    EXCLUDE_RATE_TARIFF, STOP_CODES, GENERIC_MARKER,
    SDFLAT_PREFIX, SDFLAT_START,
)


# ── helpers ──────────────────────────────────────────────────────────────────
def _is_generic(row) -> bool:
    return GENERIC_MARKER in s(row.get("Rate Tariff ID")).upper()


def _not_custpickup(row) -> bool:
    return s(row.get("Rate Tariff ID")) != EXCLUDE_RATE_TARIFF


def _not_stop(row) -> bool:
    return s(row.get("Charge Code")) not in STOP_CODES


# =============================================================================
# 2.4-2.6 AP Master (Generic) + SDFLAT append
# =============================================================================
def build_ap_master_generic(ap_df: pd.DataFrame) -> pd.DataFrame:
    """
    AP Master (All Generic): Pri-Columns → Eff/Exp/Rate
    filter: ≠CUSTPICKUP AND TYPE=GENERIC AND ≠STOP
    + append SDFLAT (2.5→2.6): Rate Code เริ่ม SDFLAT → ตัด SDFLAT_ ออก
    """
    # main generic
    mask = ap_df.apply(
        lambda r: _not_custpickup(r) and _is_generic(r) and _not_stop(r),
        axis=1,
    )
    df = ap_df[mask].copy()
    df["Pri-Columns"] = df.apply(keys.ap_pri_columns, axis=1)
    main = df[["Pri-Columns", "Effective Date", "Expiration Date", "Rate"]].copy()

    # 2.5 SDFLAT transform → append (2.6)
    sd = ap_df[ap_df["Rate Code"].apply(lambda x: s(x).startswith(SDFLAT_START))].copy()
    if not sd.empty:
        sd["Rate Code"] = sd["Rate Code"].apply(lambda x: s(x).replace(SDFLAT_PREFIX, ""))
        sd_mask = sd.apply(
            lambda r: _not_custpickup(r) and _is_generic(r) and _not_stop(r),
            axis=1,
        )
        sd = sd[sd_mask]
        if not sd.empty:
            sd["Pri-Columns"] = sd.apply(keys.ap_pri_columns, axis=1)
            sd_out = sd[["Pri-Columns", "Effective Date", "Expiration Date", "Rate"]]
            main = pd.concat([main, sd_out], ignore_index=True)

    return main.drop_duplicates().reset_index(drop=True)


def build_ap_master_child(ap_df: pd.DataFrame) -> pd.DataFrame:
    """
    AP Master (All Child): filter ≠CUSTPICKUP AND TYPE≠GENERIC AND ≠STOP
    """
    mask = ap_df.apply(
        lambda r: _not_custpickup(r) and (not _is_generic(r)) and _not_stop(r),
        axis=1,
    )
    df = ap_df[mask].copy()
    df["Pri-Columns"] = df.apply(keys.ap_pri_columns, axis=1)
    out = df[["Pri-Columns", "Effective Date", "Expiration Date", "Rate"]]
    return out.drop_duplicates().reset_index(drop=True)


# =============================================================================
# 2.7 AR Master (Normal)
# =============================================================================
def build_ar_master_normal(ar_df: pd.DataFrame) -> pd.DataFrame:
    """
    AR Master (ALL): Pri-Columns → Eff/Exp/Rate
    filter: CHARGE_ID ≠ STOP codes
    """
    mask = ar_df.apply(lambda r: s(r.get("CHARGE_ID")) not in STOP_CODES, axis=1)
    df = ar_df[mask].copy()
    df["Pri-Columns"] = df.apply(keys.ar_pri_columns, axis=1)
    out = df[["Pri-Columns", "EFFECTIVEDATE", "EXPIRATIONDATE", "RATE"]]
    return out.drop_duplicates().reset_index(drop=True)


# =============================================================================
# Date-range join (หัวใจ M-Code APFinal/ARFinal)
# =============================================================================
def _daterange_finalmap(
    main: pd.DataFrame,
    master: pd.DataFrame,
    main_key: str,
    master_key: str,
    eff_col: str,
    exp_col: str,
    rate_col: str,
    pickup_col: str = "PickupConfirmed Date",
) -> pd.DataFrame:
    """
    2.1-2.3 + 3.x: filter Load Confirm ที่ map เจอ AND date ตรง
    Returns: main_key(distinct) + PickupDate + Rate + Final key
             (เฉพาะแถวที่ Active = date ตรง)

    M-Code:
      Group by [key, PickupDate] → join master → Custom="Active"
      ถ้า Eff ≤ Pickup ≤ Exp → filter Active → Final key
    """
    # distinct [key, pickup]
    grp = main[[main_key, pickup_col]].dropna(subset=[main_key]).drop_duplicates()

    m = master[[master_key, eff_col, exp_col, rate_col]].copy()
    m[eff_col] = pd.to_datetime(m[eff_col], errors="coerce")
    m[exp_col] = pd.to_datetime(m[exp_col], errors="coerce")

    merged = grp.merge(m, left_on=main_key, right_on=master_key, how="left")
    pk = pd.to_datetime(merged[pickup_col], errors="coerce")
    active = (pk >= merged[eff_col]) & (pk <= merged[exp_col])
    result = merged[active].copy()

    # Final key = key + PickupDate (DD/MM/YYYY)
    result["_pkstr"] = pd.to_datetime(result[pickup_col], errors="coerce").dt.strftime("%d/%m/%Y")
    result["Final key"] = result[main_key].astype(str) + result["_pkstr"].fillna("")
    result = result[["Final key", rate_col]].drop_duplicates(subset=["Final key"])
    return result.reset_index(drop=True)


def ap_final_generic(main, ap_master_generic) -> pd.DataFrame:
    """2.1 → 3.1: AP Generic final map → Final key + Rate"""
    out = _daterange_finalmap(
        main, ap_master_generic,
        main_key="Pri-AP", master_key="Pri-Columns",
        eff_col="Effective Date", exp_col="Expiration Date", rate_col="Rate",
    )
    return out.rename(columns={"Rate": "AP Rate Charge (Generic)"})


def ap_final_child(main, ap_master_child) -> pd.DataFrame:
    """2.2 → 3.2: AP Child final map → Final key + Rate"""
    out = _daterange_finalmap(
        main, ap_master_child,
        main_key="Pri-AP", master_key="Pri-Columns",
        eff_col="Effective Date", exp_col="Expiration Date", rate_col="Rate",
    )
    return out.rename(columns={"Rate": "AP Rate Charge (Child)"})


def ar_final_normal(main, ar_master_normal) -> pd.DataFrame:
    """2.3 → 3.3: AR Normal final map → AR-Final key + Rate"""
    # AR ใช้ AR-Pri + pickup
    grp = main[["AR-Pri", "PickupConfirmed Date"]].dropna(subset=["AR-Pri"]).drop_duplicates()
    m = ar_master_normal.copy()
    m["EFFECTIVEDATE"]  = pd.to_datetime(m["EFFECTIVEDATE"], errors="coerce")
    m["EXPIRATIONDATE"] = pd.to_datetime(m["EXPIRATIONDATE"], errors="coerce")

    merged = grp.merge(m, left_on="AR-Pri", right_on="Pri-Columns", how="left")
    pk = pd.to_datetime(merged["PickupConfirmed Date"], errors="coerce")
    active = (pk >= merged["EFFECTIVEDATE"]) & (pk <= merged["EXPIRATIONDATE"])
    result = merged[active].copy()
    result["_pkstr"] = pk[active].dt.strftime("%d/%m/%Y")
    result["AR-Final key"] = result["AR-Pri"].astype(str) + result["_pkstr"].fillna("")
    result = result[["AR-Final key", "RATE"]].drop_duplicates(subset=["AR-Final key"])
    result = result.rename(columns={"RATE": "AR Rate Charge"})
    return result.reset_index(drop=True)


# =============================================================================
# รวม Stage 2
# =============================================================================
def run(main: pd.DataFrame, ap_df: pd.DataFrame, ar_df: pd.DataFrame) -> dict:
    ap_gen = build_ap_master_generic(ap_df)
    ap_chd = build_ap_master_child(ap_df)
    ar_nrm = build_ar_master_normal(ar_df)

    return {
        "ap_final_generic": ap_final_generic(main, ap_gen),
        "ap_final_child":   ap_final_child(main, ap_chd),
        "ar_final_normal":  ar_final_normal(main, ar_nrm),
    }
