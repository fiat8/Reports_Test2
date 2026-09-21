# =============================================================================
# engine_v3/step.py — STEP Rate (Sub-flow แยก)
#
# Concept:
#   1. กรอง Charge Code = "STEP"
#   2. Load Qty = SUM(Shpm Pieces) group by Load ID
#   3. Master STEP: มี Range To ในไฟล์ → สร้าง Range From เอง
#      (sort Range To min→max ต่อ Pri-Columns, From = prev To + 1, ตัวแรก = 0)
#   4. หา rate: Date Criteria (Eff≤Pickup≤Exp) AND STEP Criteria (From≤LoadQty≤To)
#   5. Total = Load Qty × Rate (ทุกแถวใน Load เท่ากัน)
#      AP Total ไม่ × fuel, AR Total × fuel
# =============================================================================

import pandas as pd
from engine_v3 import keys
from engine_v3.keys import s
from engine_v3.config import EXCLUDE_RATE_TARIFF

STEP_CODE = "STEP"


def _not_custpickup(row):
    return s(row.get("Rate Tariff ID")) != EXCLUDE_RATE_TARIFF


# =============================================================================
# สร้าง Master STEP + Range From
# =============================================================================
def build_step_master(rate_df: pd.DataFrame, side: str) -> pd.DataFrame:
    """
    สร้าง STEP master จาก AP/AR rate
    side: "AP" หรือ "AR"
    เพิ่ม Range From (จาก Range To ที่มีในไฟล์)

    AP: Pri-Columns = keys.ap_pri_columns, cols = Effective/Expiration/Rate/Range To
    AR: Pri-Columns = keys.ar_pri_columns, cols = EFFECTIVEDATE/EXPIRATIONDATE/RATE
        (AR อาจไม่มี Range To — เช็คก่อน)
    """
    df = rate_df.copy()

    if side == "AP":
        # filter STEP charge + ≠CUSTPICKUP
        df = df[df["Charge Code"].apply(lambda x: s(x) == STEP_CODE)]
        df = df[df.apply(_not_custpickup, axis=1)]
        if df.empty:
            return pd.DataFrame(columns=["Pri-Columns", "Effective Date", "Expiration Date",
                                         "Rate", "Range From", "Range To"])
        df["Pri-Columns"] = df.apply(keys.ap_pri_columns, axis=1)
        eff, exp, rate, rangeto = "Effective Date", "Expiration Date", "Rate", "Range To"
    else:  # AR
        df = df[df["CHARGE_ID"].apply(lambda x: s(x) == STEP_CODE)]
        if df.empty:
            return pd.DataFrame(columns=["Pri-Columns", "EFFECTIVEDATE", "EXPIRATIONDATE",
                                         "RATE", "Range From", "Range To"])
        df["Pri-Columns"] = df.apply(keys.ar_pri_columns, axis=1)
        eff, exp, rate, rangeto = "EFFECTIVEDATE", "EXPIRATIONDATE", "RATE", "Range To"

    # Range To เป็นตัวเลข
    df[rangeto] = pd.to_numeric(df[rangeto], errors="coerce")

    # สร้าง Range From ต่อ Pri-Columns (sort Range To → From = prev+1, ตัวแรก=0)
    out_rows = []
    for pricol, grp in df.groupby("Pri-Columns"):
        g = grp.sort_values(rangeto).reset_index(drop=True)
        prev_to = -1  # ทำให้ตัวแรก From = 0
        for _, r in g.iterrows():
            rf = prev_to + 1
            out_rows.append({
                "Pri-Columns": pricol,
                eff: r[eff], exp: r[exp], rate: r[rate],
                "Range From": rf, "Range To": r[rangeto],
            })
            prev_to = r[rangeto]

    return pd.DataFrame(out_rows)


# =============================================================================
# Load Qty (SUM Shpm Pieces group by Load ID) — เฉพาะ STEP
# =============================================================================
def compute_load_qty(main: pd.DataFrame) -> pd.Series:
    """
    Load Qty = SUM(Shpm Pieces) group by Load ID (ทุกแถว STEP)
    คืน Series ที่ index ตรงกับ main
    """
    pieces = pd.to_numeric(main.get("Shpm Pieces"), errors="coerce").fillna(0)
    tmp = main.copy()
    tmp["_pieces"] = pieces
    load_qty = tmp.groupby("Load ID")["_pieces"].transform("sum")
    return load_qty


# =============================================================================
# หา STEP rate (Date + STEP Criteria)
# =============================================================================
def find_step_rate(main: pd.DataFrame, master: pd.DataFrame, side: str,
                   load_qty: pd.Series,
                   pickup_col: str = "PickupConfirmed Date") -> pd.DataFrame:
    """
    หา rate สำหรับแต่ละแถว STEP:
      key match (Pri-Columns) AND
      Date: Eff ≤ Pickup ≤ Exp AND
      STEP: Range From ≤ Load Qty ≤ Range To
    คืน DataFrame index ตรง main: [step_rate, step_eff, step_exp]
    """
    n = len(main)
    result = pd.DataFrame({
        "STEP Rate": [None]*n, "STEP Eff": [None]*n, "STEP Exp": [None]*n,
    }, index=main.index)

    if master is None or master.empty:
        return result

    if side == "AP":
        main_key = main.apply(keys.build_pri_ap, axis=1)   # Load Confirm side
        eff, exp, rate = "Effective Date", "Expiration Date", "Rate"
    else:
        main_key = main.apply(keys.build_ar_pri, axis=1)    # Load Confirm side
        eff, exp, rate = "EFFECTIVEDATE", "EXPIRATIONDATE", "RATE"

    pk = pd.to_datetime(main[pickup_col], errors="coerce").dt.normalize()

    # เตรียม master lookup
    m = master.copy()
    m[eff] = pd.to_datetime(m[eff], errors="coerce").dt.normalize()
    m[exp] = pd.to_datetime(m[exp], errors="coerce").dt.normalize()

    # loop แต่ละแถว main (STEP มีไม่เยอะ)
    for idx in main.index:
        k = main_key[idx]
        lq = load_qty[idx]
        p = pk[idx]
        cand = m[m["Pri-Columns"] == k]
        if cand.empty:
            continue
        # Date + STEP criteria
        hit = cand[
            (p >= cand[eff]) & (p <= cand[exp]) &
            (lq >= cand["Range From"]) & (lq <= cand["Range To"])
        ]
        if not hit.empty:
            row = hit.iloc[0]
            result.at[idx, "STEP Rate"] = row[rate]
            result.at[idx, "STEP Eff"]  = row[eff]
            result.at[idx, "STEP Exp"]  = row[exp]

    return result


# =============================================================================
# รวม STEP flow → คืน column ที่จะ merge เข้า main
# =============================================================================
def run(main: pd.DataFrame, ap_df: pd.DataFrame, ar_df: pd.DataFrame,
        fuel_surcharge_col: str = "Fuel Surcharge") -> pd.DataFrame:
    """
    ประมวลผล STEP แล้วคืน main พร้อม column:
      AP Rate Charge, AP Total (เฉพาะแถว STEP)
      AR Rate Charge, AR Total (เฉพาะแถว STEP, × fuel)
      Load Qty
    ทำเฉพาะแถวที่ Load Charge Code = STEP
    """
    main = main.copy()
    is_step = main.get("Load Charge Code", pd.Series([""]*len(main))).apply(lambda x: s(x) == STEP_CODE)

    if not is_step.any():
        return main  # ไม่มี STEP

    # Load Qty (เฉพาะ STEP)
    load_qty = compute_load_qty(main)
    main.loc[is_step, "Load Qty"] = load_qty[is_step]

    # Master STEP
    ap_master = build_step_master(ap_df, "AP")
    ar_master = build_step_master(ar_df, "AR")

    # หา rate
    ap_step = find_step_rate(main, ap_master, "AP", load_qty)
    ar_step = find_step_rate(main, ar_master, "AR", load_qty)

    # เติมค่าเฉพาะแถว STEP
    fuel_raw = main.get(fuel_surcharge_col)
    if fuel_raw is None:
        fuel_sur = pd.Series([0]*len(main), index=main.index)
    else:
        fuel_sur = pd.to_numeric(pd.Series(fuel_raw, index=main.index), errors="coerce").fillna(0)

    # cast columns ที่จะเขียนเป็น object (กัน dtype string เดิม)
    for col in ["AP Rate Charge", "AP Effective Date", "AP Expiration Date",
                "AP Rate Source", "AP Total", "AR Rate Charge", "AR Total"]:
        if col in main.columns:
            main[col] = main[col].astype(object)

    for idx in main.index[is_step]:
        lq = load_qty[idx]
        # AP
        ap_rate = ap_step.at[idx, "STEP Rate"]
        if pd.notna(ap_rate):
            main.at[idx, "AP Rate Charge"]     = ap_rate
            main.at[idx, "AP Effective Date"]  = ap_step.at[idx, "STEP Eff"]
            main.at[idx, "AP Expiration Date"] = ap_step.at[idx, "STEP Exp"]
            main.at[idx, "AP Rate Source"]     = "STEP"
            main.at[idx, "AP Total"]           = lq * ap_rate  # Load Qty × Rate
        # AR (× fuel)
        ar_rate = ar_step.at[idx, "STEP Rate"]
        if pd.notna(ar_rate):
            main.at[idx, "AR Rate Charge"] = ar_rate
            main.at[idx, "AR Total"]       = lq * ar_rate * (1 + fuel_sur[idx])

    return main
