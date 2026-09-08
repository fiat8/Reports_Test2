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
    # FLAT fallback: prime without item type
    if "ap_prime_noitem" in stage1:
        main = _merge(main, stage1["ap_prime_noitem"], "Pri-AP2", "Pri-Columns2",
                      ["Prime Status NoItem"])
    main = _merge(main, stage1["ap_prime_child"], "Pri-AP",      "Pri-Columns", ["Child Status"])
    main = _merge(main, stage1["ap_mandatory"],   "Mandate Key", "Mandate-key", ["Mandatory Status"])
    main = _merge(main, stage1["ap_carrier"],     "Sup-Carrier", "Sub-key2",    ["Carrier Status"])
    main = _merge(main, stage1["ap_truck"],       "Sup-Truck",   "Sub-key1",    ["Truck Status"])
    main = _merge(main, stage1["ap_stop"],        "AP Stop",     "Stop-Columns",["AP Stop Charge"])

    # ── Stage 1: AR 2 status ──────────────────────────────────────────────
    main = _merge(main, stage1["ar_prime"], "AR-Pri",  "Pri-Columns",  ["AR Prime Status"])
    main = _merge(main, stage1["ar_stop"],  "AR Stop", "Stop-Columns", ["AR Stop Charge"])

    # ── Stage 2: final map rate (join บน Final key) — WITH item type ───────
    main = _merge(main, stage2["ap_final_generic"], "Final key",    "Final key",    ["AP Rate Charge (Generic)", "AP Rate From (Generic)"])
    main = _merge(main, stage2["ap_final_child"],   "Final key",    "Final key",    ["AP Rate Charge (Child)", "AP Rate From (Child)"])
    main = _merge(main, stage2["ar_final_normal"],  "AR-Final key", "AR-Final key", ["AR Rate Charge", "AR Rate From"])

    # ── Stage 2: FLAT fallback rate (join บน Final key2) — WITHOUT item ────
    if "ap_final_generic_noitem" in stage2:
        main = _merge(main, stage2["ap_final_generic_noitem"], "Final key2", "Final key2",
                      ["AP Rate Charge (Generic) NoItem"])
    if "ap_final_child_noitem" in stage2:
        main = _merge(main, stage2["ap_final_child_noitem"], "Final key2", "Final key2",
                      ["AP Rate Charge (Child) NoItem"])

    # ── AP Rate Charge + AP Rate From: Child > Generic, with > without ────
    def _pick_ap_rate(row):
        if pd.notna(row.get("AP Rate Charge (Child)")):
            return row.get("AP Rate Charge (Child)")
        if pd.notna(row.get("AP Rate Charge (Generic)")):
            return row.get("AP Rate Charge (Generic)")
        if row.get("_is_flat"):
            if pd.notna(row.get("AP Rate Charge (Child) NoItem")):
                return row.get("AP Rate Charge (Child) NoItem")
            if pd.notna(row.get("AP Rate Charge (Generic) NoItem")):
                return row.get("AP Rate Charge (Generic) NoItem")
        return None
    main["AP Rate Charge"] = main.apply(_pick_ap_rate, axis=1)

    def _pick_ap_from(row):
        # เลือก Rate From ให้ตรงกับ rate ที่เลือก
        if pd.notna(row.get("AP Rate Charge (Child)")):
            return row.get("AP Rate From (Child)")
        if pd.notna(row.get("AP Rate Charge (Generic)")):
            return row.get("AP Rate From (Generic)")
        return None   # fallback noitem ยังไม่มี row indicator (เฟสถัดไป)
    main["AP Rate From"] = main.apply(_pick_ap_from, axis=1)

    # ── Prime Status: mark with / without (เฉพาะ FLAT) ────────────────────
    # M-Code: Prime Status เดิม = Active/None
    #   ถ้า match with item type       → "Active with"
    #   ถ้า fallback without item type  → "Active without"
    def _prime_status(row):
        with_active = row.get("Prime Status") == "Active"
        if with_active:
            # ถ้าเป็น FLAT ที่ผ่าน fallback path ให้ระบุ with
            if row.get("_is_flat"):
                return "Active with"
            return "Active"
        # with ไม่เจอ — ลอง fallback (เฉพาะ FLAT)
        if row.get("_is_flat") and row.get("Prime Status NoItem") == "Active":
            return "Active without"
        return row.get("Prime Status")  # None / เดิม
    main["Prime Status"] = main.apply(_prime_status, axis=1)

    # ── AP Rate Type ──────────────────────────────────────────────────────
    def _rate_type(row):
        ps = row.get("Prime Status")
        if row.get("Child Status") == "Active":
            return "Child"
        elif ps in ("Active", "Active with", "Active without"):
            return "Generic"
        return ""
    main["AP Rate Type"] = main.apply(_rate_type, axis=1)

    # ── ลบ working columns ────────────────────────────────────────────────
    # ── ลบ working columns ────────────────────────────────────────────────
    drop_cols = [
        "_pickup_str", "Prime Status NoItem",
        "AP Rate From (Generic)", "AP Rate From (Child)",  # รวมเป็น AP Rate From แล้ว
    ]
    main = main.drop(columns=[c for c in drop_cols if c in main.columns], errors="ignore")

    return main


def get_kpi(df: pd.DataFrame) -> dict:
    total  = len(df)
    ps     = df.get("Prime Status", pd.Series(dtype=object))
    active_vals = {"Active", "Active with", "Active without"}
    matched = ps.isin(active_vals).sum()
    fallback = (ps == "Active without").sum()
    return {
        "total":     int(total),
        "matched":   int(matched),
        "unmatched": int(total - matched),
        "fallback":  int(fallback),
        "match_pct": round(matched / total * 100, 1) if total else 0,
    }