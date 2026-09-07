# =============================================================================
# engine_v3/stage1_premap.py — Stage 1: Pre-Mapping (สร้าง lookup tables)
#
# 1.1 AP Data  → 6 status: Prime(Normal), Prime(Child), Mandatory,
#                          Truck, Carrier, Stop
# 1.2 AR Data  → 2 status: Prime(Normal), Stop
# 1.3 Load Confirm → สร้าง keys (main data — ปลายทาง)
# =============================================================================

import pandas as pd
from engine_v3 import keys
from engine_v3.config import (
    EXCLUDE_RATE_TARIFF, STOP_CODES, STOP_ONLY_CODES, GENERIC_MARKER,
)
from engine_v3.keys import s


# ── helper: TYPE = GENERIC / CHILD ───────────────────────────────────────────
def _is_generic(row) -> bool:
    return GENERIC_MARKER in s(row.get("Rate Tariff ID")).upper()


def _not_custpickup(row) -> bool:
    return s(row.get("Rate Tariff ID")) != EXCLUDE_RATE_TARIFF


def _not_stop(row) -> bool:
    return s(row.get("Charge Code")) not in STOP_CODES


# =============================================================================
# 1.1 AP Data → 6 status tables
# =============================================================================
def ap_prime(ap_df: pd.DataFrame) -> pd.DataFrame:
    """Prime (Normal): Pri-Columns → Active. filter ≠CUSTPICKUP"""
    df = ap_df[ap_df.apply(_not_custpickup, axis=1)].copy()
    df["Pri-Columns"] = df.apply(keys.ap_pri_columns, axis=1)
    out = df[["Pri-Columns"]].drop_duplicates().copy()
    out["Prime Status"] = "Active"
    return out.reset_index(drop=True)


def ap_prime_child(ap_df: pd.DataFrame) -> pd.DataFrame:
    """Prime (Child): TYPE≠GENERIC AND ≠CUSTPICKUP AND ≠STOP"""
    mask = ap_df.apply(
        lambda r: _not_custpickup(r) and (not _is_generic(r)) and _not_stop(r),
        axis=1,
    )
    df = ap_df[mask].copy()
    df["Pri-Columns"] = df.apply(keys.ap_pri_columns, axis=1)
    out = df[["Pri-Columns"]].drop_duplicates().copy()
    out["Child Status"] = "Active"
    return out.reset_index(drop=True)


def ap_mandatory(ap_df: pd.DataFrame) -> pd.DataFrame:
    df = ap_df[ap_df.apply(_not_custpickup, axis=1)].copy()
    df["Mandate-key"] = df.apply(keys.ap_mandate_key, axis=1)
    out = df[["Mandate-key"]].drop_duplicates().copy()
    out["Mandatory Status"] = "Active"
    return out.reset_index(drop=True)


def ap_carrier(ap_df: pd.DataFrame) -> pd.DataFrame:
    df = ap_df[ap_df.apply(_not_custpickup, axis=1)].copy()
    df["Sub-key2"] = df.apply(keys.ap_sub_key2, axis=1)
    out = df[["Sub-key2"]].drop_duplicates().copy()
    out["Carrier Status"] = "Active"
    return out.reset_index(drop=True)


def ap_truck(ap_df: pd.DataFrame) -> pd.DataFrame:
    df = ap_df[ap_df.apply(_not_custpickup, axis=1)].copy()
    df["Sub-key1"] = df.apply(keys.ap_sub_key1, axis=1)
    out = df[["Sub-key1"]].drop_duplicates().copy()
    out["Truck Status"] = "Active"
    return out.reset_index(drop=True)


def ap_stop(ap_df: pd.DataFrame) -> pd.DataFrame:
    """Stop: Charge Code IN {STOP, STOP_3PL} AND ≠CUSTPICKUP → Rate"""
    mask = ap_df.apply(
        lambda r: s(r.get("Charge Code")) in STOP_ONLY_CODES and _not_custpickup(r),
        axis=1,
    )
    df = ap_df[mask].copy()
    df["Stop-Columns"] = df.apply(keys.ap_stop_columns, axis=1)
    out = df[["Stop-Columns", "Rate"]].drop_duplicates(subset=["Stop-Columns"]).copy()
    out = out.rename(columns={"Rate": "AP Stop Charge"})
    return out.reset_index(drop=True)


# =============================================================================
# 1.2 AR Data → 2 status tables
# =============================================================================
def ar_prime(ar_df: pd.DataFrame) -> pd.DataFrame:
    """Prime (Normal): Pri-Columns → Active"""
    df = ar_df.copy()
    df["Pri-Columns"] = df.apply(keys.ar_pri_columns, axis=1)
    out = df[["Pri-Columns"]].drop_duplicates().copy()
    out["AR Prime Status"] = "Active"
    return out.reset_index(drop=True)


def ar_stop(ar_df: pd.DataFrame) -> pd.DataFrame:
    """Stop: CHARGE_ID IN {STOP, STOP_3PL} AND RATE≠0 → RATE"""
    mask = ar_df.apply(
        lambda r: s(r.get("CHARGE_ID")) in STOP_ONLY_CODES
        and pd.to_numeric(r.get("RATE"), errors="coerce") != 0,
        axis=1,
    )
    df = ar_df[mask].copy()
    df["Stop-Columns"] = df.apply(keys.ar_stop_columns, axis=1)
    out = df[["Stop-Columns", "RATE"]].drop_duplicates(subset=["Stop-Columns"]).copy()
    out = out.rename(columns={"RATE": "AR Stop Charge"})
    return out.reset_index(drop=True)


# =============================================================================
# 1.3 Load Confirm → keys (main data)
# =============================================================================
def load_confirm_keys(lc_df: pd.DataFrame) -> pd.DataFrame:
    """สร้าง key ทุกตัวเข้า main data"""
    return keys.add_load_confirm_keys(lc_df)


# =============================================================================
# รวม Stage 1
# =============================================================================
def run(lc_df, ap_df, ar_df) -> dict:
    """
    Returns dict ของ lookup tables + main (keyed)
    """
    return {
        # 1.1 AP
        "ap_prime":       ap_prime(ap_df),
        "ap_prime_child": ap_prime_child(ap_df),
        "ap_mandatory":   ap_mandatory(ap_df),
        "ap_carrier":     ap_carrier(ap_df),
        "ap_truck":       ap_truck(ap_df),
        "ap_stop":        ap_stop(ap_df),
        # 1.2 AR
        "ar_prime":       ar_prime(ar_df),
        "ar_stop":        ar_stop(ar_df),
        # 1.3 main
        "main":           load_confirm_keys(lc_df),
    }
