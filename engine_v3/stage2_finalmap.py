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
    main = df[["Pri-Columns", "Effective Date", "Expiration Date", "Rate", "_ap_row"]].copy()

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
            sd_out = sd[["Pri-Columns", "Effective Date", "Expiration Date", "Rate", "_ap_row"]]
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
    out = df[["Pri-Columns", "Effective Date", "Expiration Date", "Rate", "_ap_row"]]
    return out.drop_duplicates().reset_index(drop=True)


def build_ap_master_generic_noitem(ap_df: pd.DataFrame) -> pd.DataFrame:
    """
    AP Master Generic (without item type) — FLAT fallback
    Pri-Columns2 → Eff/Exp/Rate. filter GENERIC + FLAT charge
    """
    mask = ap_df.apply(
        lambda r: _not_custpickup(r) and _is_generic(r) and _not_stop(r)
        and keys.is_flat_fallback(r.get("Charge Code")),
        axis=1,
    )
    df = ap_df[mask].copy()
    df["Pri-Columns2"] = df.apply(keys.ap_pri_columns_noitem, axis=1)
    out = df[["Pri-Columns2", "Effective Date", "Expiration Date", "Rate", "_ap_row"]]
    return out.drop_duplicates().reset_index(drop=True)


def build_ap_master_child_noitem(ap_df: pd.DataFrame) -> pd.DataFrame:
    """
    AP Master Child (without item type) — FLAT fallback
    """
    mask = ap_df.apply(
        lambda r: _not_custpickup(r) and (not _is_generic(r)) and _not_stop(r)
        and keys.is_flat_fallback(r.get("Charge Code")),
        axis=1,
    )
    df = ap_df[mask].copy()
    df["Pri-Columns2"] = df.apply(keys.ap_pri_columns_noitem, axis=1)
    out = df[["Pri-Columns2", "Effective Date", "Expiration Date", "Rate", "_ap_row"]]
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
    out = df[["Pri-Columns", "EFFECTIVEDATE", "EXPIRATIONDATE", "RATE", "_ar_row"]]
    return out.drop_duplicates().reset_index(drop=True)


# =============================================================================
# Date-range join (หัวใจ M-Code APFinal/ARFinal)
# =============================================================================
def _finalmap_full(main, master, main_key, master_key, suffix,
                   eff_col="Effective Date", exp_col="Expiration Date",
                   rate_col="Rate", row_col="_ap_row", row_prefix="AP",
                   final_key_name="Final key", pickup_col="PickupConfirmed Date"):
    """
    date-range map → return ครบ: Final key + Rate + Eff + Exp + RateFrom
    (แต่ละ column มี suffix บอก type เช่น _CHILD, _GEN, _CHILD_NI, _GEN_NI)
    เลือกแถวแรก (row_col น้อยสุด)
    """
    grp = main[[main_key, pickup_col]].dropna(subset=[main_key]).drop_duplicates()
    cols = [master_key, eff_col, exp_col, rate_col]
    has_row = row_col in master.columns
    if has_row:
        cols.append(row_col)
    m = master[cols].copy()
    m[eff_col] = pd.to_datetime(m[eff_col], errors="coerce")
    m[exp_col] = pd.to_datetime(m[exp_col], errors="coerce")

    merged = grp.merge(m, left_on=main_key, right_on=master_key, how="left")
    pk = pd.to_datetime(merged[pickup_col], errors="coerce").dt.normalize()
    eff = pd.to_datetime(merged[eff_col], errors="coerce").dt.normalize()
    exp = pd.to_datetime(merged[exp_col], errors="coerce").dt.normalize()
    active = (pk >= eff) & (pk <= exp)
    result = merged[active].copy()

    result["_pkstr"] = pd.to_datetime(result[pickup_col], errors="coerce").dt.strftime("%d/%m/%Y")
    result[final_key_name] = result[main_key].astype(str) + result["_pkstr"].fillna("")

    # เอาแถวแรก
    sort_cols = [main_key, "_pkstr"] + ([row_col] if has_row else [])
    result = result.sort_values(sort_cols)
    first = result.drop_duplicates(subset=[final_key_name], keep="first").copy()

    if first.empty:
        return pd.DataFrame(columns=[final_key_name, f"Rate{suffix}",
                                     f"Eff{suffix}", f"Exp{suffix}", f"From{suffix}"])

    if has_row:
        first[f"From{suffix}"] = first[row_col].apply(lambda r: f"{row_prefix}-{int(r)}")
    else:
        first[f"From{suffix}"] = ""

    out = first[[final_key_name, rate_col, eff_col, exp_col, f"From{suffix}"]].copy()
    out = out.rename(columns={
        rate_col: f"Rate{suffix}",
        eff_col:  f"Eff{suffix}",
        exp_col:  f"Exp{suffix}",
    })
    return out.reset_index(drop=True)


def _daterange_finalmap(
    main: pd.DataFrame,
    master: pd.DataFrame,
    main_key: str,
    master_key: str,
    eff_col: str,
    exp_col: str,
    rate_col: str,
    row_col: str = "_ap_row",
    row_prefix: str = "AP",
    pickup_col: str = "PickupConfirmed Date",
) -> pd.DataFrame:
    """
    date-range map + Row Indicator
    Returns: Final key + Rate + Rate From (เช่น "AP-123 (พบ 3)")

    Logic:
      1. join master → filter date ตรง (Eff ≤ Pickup ≤ Exp)
      2. เอาแถวแรกตามลำดับต้นฉบับ (row_col น้อยสุด = บนสุด)
      3. นับจำนวนที่ match (count) → ถ้า >1 ใส่ remark "(พบ N)"
    """
    grp = main[[main_key, pickup_col]].dropna(subset=[main_key]).drop_duplicates()

    cols = [master_key, eff_col, exp_col, rate_col]
    if row_col in master.columns:
        cols.append(row_col)
    m = master[cols].copy()
    m[eff_col] = pd.to_datetime(m[eff_col], errors="coerce")
    m[exp_col] = pd.to_datetime(m[exp_col], errors="coerce")

    merged = grp.merge(m, left_on=main_key, right_on=master_key, how="left")
    pk = pd.to_datetime(merged[pickup_col], errors="coerce").dt.normalize()
    eff = pd.to_datetime(merged[eff_col], errors="coerce").dt.normalize()
    exp = pd.to_datetime(merged[exp_col], errors="coerce").dt.normalize()
    active = (pk >= eff) & (pk <= exp)
    result = merged[active].copy()

    # Final key = key + PickupDate
    result["_pkstr"] = pd.to_datetime(result[pickup_col], errors="coerce").dt.strftime("%d/%m/%Y")
    result["Final key"] = result[main_key].astype(str) + result["_pkstr"].fillna("")

    if row_col not in result.columns:
        # ไม่มี row → คืน rate อย่างเดียว
        out = result[["Final key", rate_col]].drop_duplicates(subset=["Final key"])
        return out.reset_index(drop=True)

    # เรียงตาม row ต้นฉบับ (บนลงล่าง) เพื่อเอาแถวแรก
    result = result.sort_values([main_key, "_pkstr", row_col])

    # นับจำนวน match ต่อ Final key
    counts = result.groupby("Final key").size()

    # เอาแถวแรก (row น้อยสุด)
    first = result.drop_duplicates(subset=["Final key"], keep="first").copy()

    # ถ้าว่าง คืน empty ที่มี column ครบ
    if first.empty:
        return pd.DataFrame(columns=["Final key", rate_col, "_RateFrom"])

    # สร้าง Rate From + remark
    def _mk_from(row):
        return f"{row_prefix}-{int(row[row_col])}"
    first["_RateFrom"] = first.apply(_mk_from, axis=1)

    out = first[["Final key", rate_col, "_RateFrom"]].reset_index(drop=True)
    return out


def ap_final_generic(main, ap_master_generic) -> pd.DataFrame:
    """2.1 → 3.1: AP Generic final map → Final key + Rate + Rate From"""
    out = _daterange_finalmap(
        main, ap_master_generic,
        main_key="Pri-AP", master_key="Pri-Columns",
        eff_col="Effective Date", exp_col="Expiration Date", rate_col="Rate",
        row_col="_ap_row", row_prefix="AP",
    )
    return out.rename(columns={"Rate": "AP Rate Charge (Generic)",
                               "_RateFrom": "AP Rate From (Generic)"})


def ap_final_child(main, ap_master_child) -> pd.DataFrame:
    """2.2 → 3.2: AP Child final map → Final key + Rate + Rate From"""
    out = _daterange_finalmap(
        main, ap_master_child,
        main_key="Pri-AP", master_key="Pri-Columns",
        eff_col="Effective Date", exp_col="Expiration Date", rate_col="Rate",
        row_col="_ap_row", row_prefix="AP",
    )
    return out.rename(columns={"Rate": "AP Rate Charge (Child)",
                               "_RateFrom": "AP Rate From (Child)"})


def ar_final_normal(main, ar_master_normal) -> pd.DataFrame:
    """2.3 → 3.3: AR Normal final map → AR-Final key + Rate + Rate From"""
    grp = main[["AR-Pri", "PickupConfirmed Date"]].dropna(subset=["AR-Pri"]).drop_duplicates()
    cols = ["Pri-Columns", "EFFECTIVEDATE", "EXPIRATIONDATE", "RATE"]
    if "_ar_row" in ar_master_normal.columns:
        cols.append("_ar_row")
    m = ar_master_normal[cols].copy()
    m["EFFECTIVEDATE"]  = pd.to_datetime(m["EFFECTIVEDATE"], errors="coerce")
    m["EXPIRATIONDATE"] = pd.to_datetime(m["EXPIRATIONDATE"], errors="coerce")

    merged = grp.merge(m, left_on="AR-Pri", right_on="Pri-Columns", how="left")
    pk = pd.to_datetime(merged["PickupConfirmed Date"], errors="coerce").dt.normalize()
    eff = pd.to_datetime(merged["EFFECTIVEDATE"], errors="coerce").dt.normalize()
    exp = pd.to_datetime(merged["EXPIRATIONDATE"], errors="coerce").dt.normalize()
    active = (pk >= eff) & (pk <= exp)
    result = merged[active].copy()
    result["_pkstr"] = pk[active].dt.strftime("%d/%m/%Y")
    result["AR-Final key"] = result["AR-Pri"].astype(str) + result["_pkstr"].fillna("")

    if "_ar_row" in result.columns:
        result = result.sort_values(["AR-Pri", "_pkstr", "_ar_row"])
        counts = result.groupby("AR-Final key").size()
        first = result.drop_duplicates(subset=["AR-Final key"], keep="first").copy()
        def _mk(row):
            return f"AR-{int(row['_ar_row'])}"
        first["AR Rate From"] = first.apply(_mk, axis=1)
        out = first[["AR-Final key", "RATE", "AR Rate From"]].reset_index(drop=True)
        return out.rename(columns={"RATE": "AR Rate Charge"})

    result = result[["AR-Final key", "RATE"]].drop_duplicates(subset=["AR-Final key"])
    return result.rename(columns={"RATE": "AR Rate Charge"}).reset_index(drop=True)


# =============================================================================
# รวม Stage 2
# =============================================================================
def ap_final_generic_noitem(main, ap_master_generic_ni) -> pd.DataFrame:
    """FLAT fallback: AP Generic without item type → Final key2 + Rate"""
    out = _daterange_finalmap(
        main, ap_master_generic_ni,
        main_key="Pri-AP2", master_key="Pri-Columns2",
        eff_col="Effective Date", exp_col="Expiration Date", rate_col="Rate",
    )
    return out.rename(columns={"Rate": "AP Rate Charge (Generic) NoItem",
                               "Final key": "Final key2"})


def ap_final_child_noitem(main, ap_master_child_ni) -> pd.DataFrame:
    """FLAT fallback: AP Child without item type → Final key2 + Rate"""
    out = _daterange_finalmap(
        main, ap_master_child_ni,
        main_key="Pri-AP2", master_key="Pri-Columns2",
        eff_col="Effective Date", exp_col="Expiration Date", rate_col="Rate",
    )
    return out.rename(columns={"Rate": "AP Rate Charge (Child) NoItem",
                               "Final key": "Final key2"})


def _daterange_finalmap_key2(main, master, main_key, master_key,
                             eff_col, exp_col, rate_col,
                             pickup_col="PickupConfirmed Date"):
    """เหมือน _daterange_finalmap แต่ output ชื่อ Final key2"""
    grp = main[[main_key, pickup_col]].dropna(subset=[main_key]).drop_duplicates()
    m = master[[master_key, eff_col, exp_col, rate_col]].copy()
    m[eff_col] = pd.to_datetime(m[eff_col], errors="coerce")
    m[exp_col] = pd.to_datetime(m[exp_col], errors="coerce")
    merged = grp.merge(m, left_on=main_key, right_on=master_key, how="left")
    pk = pd.to_datetime(merged[pickup_col], errors="coerce").dt.normalize()
    eff = pd.to_datetime(merged[eff_col], errors="coerce").dt.normalize()
    exp = pd.to_datetime(merged[exp_col], errors="coerce").dt.normalize()
    active = (pk >= eff) & (pk <= exp)
    result = merged[active].copy()
    result["_pkstr"] = pd.to_datetime(result[pickup_col], errors="coerce").dt.strftime("%d/%m/%Y")
    result["Final key2"] = result[main_key].astype(str) + result["_pkstr"].fillna("")
    result = result[["Final key2", rate_col]].drop_duplicates(subset=["Final key2"])
    return result.reset_index(drop=True)


def run(main: pd.DataFrame, ap_df: pd.DataFrame, ar_df: pd.DataFrame) -> dict:
    ap_gen = build_ap_master_generic(ap_df)
    ap_chd = build_ap_master_child(ap_df)
    ar_nrm = build_ar_master_normal(ar_df)

    # FLAT fallback masters (without item type)
    ap_gen_ni = build_ap_master_generic_noitem(ap_df)
    ap_chd_ni = build_ap_master_child_noitem(ap_df)

    # ── AP final maps (4 types) — return ครบ rate+eff+exp+from + suffix ──
    # WITH item type → join บน Final key (Pri-AP)
    ap_child_full = _finalmap_full(main, ap_chd, "Pri-AP", "Pri-Columns", "_CHILD",
                                   final_key_name="Final key")
    ap_gen_full   = _finalmap_full(main, ap_gen, "Pri-AP", "Pri-Columns", "_GEN",
                                   final_key_name="Final key")
    # WITHOUT item type → join บน Final key2 (Pri-AP2)
    ap_child_ni_full = _finalmap_full(main, ap_chd_ni, "Pri-AP2", "Pri-Columns2", "_CHILD_NI",
                                      final_key_name="Final key2")
    ap_gen_ni_full   = _finalmap_full(main, ap_gen_ni, "Pri-AP2", "Pri-Columns2", "_GEN_NI",
                                      final_key_name="Final key2")

    return {
        "ap_child_full":    ap_child_full,     # Final key + Rate_CHILD + Eff_CHILD + Exp_CHILD + From_CHILD
        "ap_gen_full":      ap_gen_full,
        "ap_child_ni_full": ap_child_ni_full,  # Final key2 + ...
        "ap_gen_ni_full":   ap_gen_ni_full,
        "ar_final_normal":  ar_final_normal(main, ar_nrm),
    }