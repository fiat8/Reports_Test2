# =============================================================================
# engine_v3/totals.py — คำนวณ AP Total / AR Total ตาม Charge Type
#
# CASE:
#   Type 1 (ปกติ):          Shpm Pieces × Rate
#   Type 2 (Charge=PALLET): Shpm Palletes × Rate
# FLAT (เหมาจ่าย):
#   MAX ของ Rate ดิบ group by Load ID (ทุกแถวใส่ค่า MAX เท่ากัน)
# COMPOUND:
#   Constant (DRAFTFLAT): ใช้ AR Rate Charge เดิม (constant×pieces ทำแล้ว)
#   Rate return: ใช้วิธี FLAT (MAX group by Load)
#
# AR Total × (1 + fuel surcharge%)  |  AP Total ไม่คูณ fuel
# =============================================================================

import pandas as pd


def _to_num(series, index=None):
    if series is None:
        return pd.Series([0] * (len(index) if index is not None else 0), index=index)
    if not isinstance(series, pd.Series):
        series = pd.Series(series, index=index)
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _calc_side(df: pd.DataFrame, rate_col: str, total_col: str,
               apply_fuel: bool = False) -> pd.DataFrame:
    """
    คำนวณ Total ฝั่งหนึ่ง (AP หรือ AR) ตาม Charge Type
    df ต้องมี: Charge Type, Load Charge Code, Shpm Pieces, Shpm Palletes,
               Load ID, rate_col, (Fuel Surcharge ถ้า apply_fuel)
    """
    df = df.copy()
    rate = _to_num(df.get(rate_col), df.index)
    pieces = _to_num(df.get("Shpm Pieces"), df.index)
    pallets = _to_num(df.get("Shpm Palletes"), df.index)
    ctype = df.get("Charge Type", pd.Series([""] * len(df))).fillna("")
    charge = df.get("Load Charge Code", pd.Series([""] * len(df))).fillna("")

    total = pd.Series([None] * len(df), index=df.index, dtype="object")

    # ── CASE ──────────────────────────────────────────────────────────────
    is_case = ctype == "CASE"
    is_pallet_charge = charge.astype(str) == "PALLET"
    # Type 2: CASE + Charge Code = PALLET → Pallets × Rate
    case_pallet = is_case & is_pallet_charge
    total[case_pallet] = (pallets * rate)[case_pallet]
    # Type 1: CASE ปกติ → Pieces × Rate
    case_normal = is_case & (~is_pallet_charge)
    total[case_normal] = (pieces * rate)[case_normal]

    # ── FLAT + COMPOUND (rate return) → MAX ของ Rate ดิบ group by Load ID ──
    is_flat_compound = ctype.isin(["FLAT", "COMPOUND"])
    if is_flat_compound.any():
        sub = df[is_flat_compound].copy()
        sub["_rate"] = rate[is_flat_compound]
        # MAX rate ต่อ Load ID
        max_by_load = sub.groupby("Load ID")["_rate"].transform("max")
        total[is_flat_compound] = max_by_load.values

    df[total_col] = total

    # ── AR: × fuel surcharge ───────────────────────────────────────────────
    if apply_fuel:
        surcharge = _to_num(df.get("Fuel Surcharge"), df.index)  # เช่น 0.0175 = 1.75%
        # AR Total × (1 + surcharge)
        base = pd.to_numeric(df[total_col], errors="coerce")
        df[total_col] = (base * (1 + surcharge)).where(base.notna(), None)

    return df


def add_totals(df: pd.DataFrame) -> pd.DataFrame:
    """
    เพิ่ม AP Total + AR Total
    AP Total: ไม่คูณ fuel
    AR Total: × (1 + fuel surcharge)
    """
    df = _calc_side(df, rate_col="AP Rate Charge", total_col="AP Total", apply_fuel=False)
    df = _calc_side(df, rate_col="AR Rate Charge", total_col="AR Total", apply_fuel=True)
    return df
