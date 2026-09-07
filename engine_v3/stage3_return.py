# =============================================================================
# engine_v3/stage3_return.py — Stage 3: Return ค่ากลับเข้า main (1.3)
#
# รวมทุก lookup + final map กลับเข้า Load Confirm (main):
#   - Stage 1 status (6 AP + 2 AR) join บน key ต่างๆ
#   - Stage 2 final map (Generic/Child/AR) join บน Final key
#   → output สุดท้าย
# =============================================================================

import pandas as pd


def _merge(main, ref, left_key, right_key, keep_cols):
    """merge safe — ถ้า ref ว่างก็เติม None"""
    if ref is None or ref.empty:
        for c in keep_cols:
            if c not in main.columns:
                main[c] = None
        return main
    right = ref.rename(columns={right_key: left_key})
    use = [left_key] + [c for c in keep_cols if c in right.columns]
    return main.merge(right[use].drop_duplicates(subset=[left_key]),
                      on=left_key, how="left")


def run(stage1: dict, stage2: dict) -> pd.DataFrame:
    """
    รวมทุกอย่างกลับเข้า main
    """
    main = stage1["main"].copy()

    # ── Stage 1: AP 6 status ──────────────────────────────────────────────
    main = _merge(main, stage1["ap_prime"],       "Pri-AP",      "Pri-Columns", ["Prime Status"])
    main = _merge(main, stage1["ap_prime_child"], "Pri-AP",      "Pri-Columns", ["Child Status"])
    main = _merge(main, stage1["ap_mandatory"],   "Mandate Key", "Mandate-key", ["Mandatory Status"])
    main = _merge(main, stage1["ap_carrier"],     "Sup-Carrier", "Sub-key2",    ["Carrier Status"])
    main = _merge(main, stage1["ap_truck"],       "Sup-Truck",   "Sub-key1",    ["Truck Status"])
    main = _merge(main, stage1["ap_stop"],        "AP Stop",     "Stop-Columns",["AP Stop Charge"])

    # ── Stage 1: AR 2 status ──────────────────────────────────────────────
    main = _merge(main, stage1["ar_prime"], "AR-Pri",  "Pri-Columns",  ["AR Prime Status"])
    main = _merge(main, stage1["ar_stop"],  "AR Stop", "Stop-Columns", ["AR Stop Charge"])

    # ── Stage 2: final map rate (join บน Final key) ───────────────────────
    main = _merge(main, stage2["ap_final_generic"], "Final key",    "Final key",    ["AP Rate Charge (Generic)"])
    main = _merge(main, stage2["ap_final_child"],   "Final key",    "Final key",    ["AP Rate Charge (Child)"])
    main = _merge(main, stage2["ar_final_normal"],  "AR-Final key", "AR-Final key", ["AR Rate Charge"])

    # ── AP Rate Charge: เลือก Child > Generic ─────────────────────────────
    def _pick_ap_rate(row):
        if pd.notna(row.get("AP Rate Charge (Child)")):
            return row.get("AP Rate Charge (Child)")
        return row.get("AP Rate Charge (Generic)")
    main["AP Rate Charge"] = main.apply(_pick_ap_rate, axis=1)

    # ── AP Rate Type ──────────────────────────────────────────────────────
    def _rate_type(row):
        if row.get("Child Status") == "Active":
            return "Child"
        elif row.get("Prime Status") == "Active":
            return "Generic"
        return ""
    main["AP Rate Type"] = main.apply(_rate_type, axis=1)

    # ── ลบ working columns ────────────────────────────────────────────────
    main = main.drop(columns=["_pickup_str"], errors="ignore")

    return main


def get_kpi(df: pd.DataFrame) -> dict:
    total   = len(df)
    matched = (df.get("Prime Status", pd.Series(dtype=object)) == "Active").sum()
    return {
        "total":     int(total),
        "matched":   int(matched),
        "unmatched": int(total - matched),
        "match_pct": round(matched / total * 100, 1) if total else 0,
    }
