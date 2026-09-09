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

    # ── Stage 2: AP final map (4 types) — merge ทั้งหมด (มี date + from) ────
    # WITH item → join Final key ; WITHOUT item → join Final key2
    main = _merge(main, stage2["ap_child_full"], "Final key",  "Final key",
                  ["Rate_CHILD", "Eff_CHILD", "Exp_CHILD", "From_CHILD"])
    main = _merge(main, stage2["ap_gen_full"],   "Final key",  "Final key",
                  ["Rate_GEN", "Eff_GEN", "Exp_GEN", "From_GEN"])
    main = _merge(main, stage2["ap_child_ni_full"], "Final key2", "Final key2",
                  ["Rate_CHILD_NI", "Eff_CHILD_NI", "Exp_CHILD_NI", "From_CHILD_NI"])
    main = _merge(main, stage2["ap_gen_ni_full"],   "Final key2", "Final key2",
                  ["Rate_GEN_NI", "Eff_GEN_NI", "Exp_GEN_NI", "From_GEN_NI"])
    main = _merge(main, stage2["ar_final_normal"],  "AR-Final key", "AR-Final key",
                  ["AR Rate Charge", "AR Rate From"])

    # ── เลือก 1 ชุดตาม Priority: Child(with) > Child(without) > Generic(with) > Generic(without)
    # return 3 คอลัมน์: AP Effective Date, AP Expiration Date, AP Rate Charge + AP Rate From
    # NoItem ใช้เฉพาะ FLAT (fallback)
    def _pick_ap(row):
        is_flat = row.get("_is_flat")
        # ลำดับ (suffix, ต้องเป็น flat ไหม, ชื่อ source)
        seq = [
            ("_CHILD",    False, "Child"),        # Child with
            ("_CHILD_NI", True,  "Child-NI"),     # Child without (flat only)
            ("_GEN",      False, "Generic"),      # Generic with
            ("_GEN_NI",   True,  "Generic-NI"),   # Generic without (flat only)
        ]
        for suf, need_flat, src in seq:
            if need_flat and not is_flat:
                continue
            rate = row.get(f"Rate{suf}")
            if pd.notna(rate):
                return pd.Series({
                    "AP Effective Date":  row.get(f"Eff{suf}"),
                    "AP Expiration Date": row.get(f"Exp{suf}"),
                    "AP Rate Charge":     rate,
                    "AP Rate Source":     src,
                    "AP Rate From":       row.get(f"From{suf}"),
                })
        return pd.Series({
            "AP Effective Date": None, "AP Expiration Date": None,
            "AP Rate Charge": None, "AP Rate Source": "", "AP Rate From": None,
        })

    picked = main.apply(_pick_ap, axis=1)
    main["AP Effective Date"]  = picked["AP Effective Date"]
    main["AP Expiration Date"] = picked["AP Expiration Date"]
    main["AP Rate Charge"]     = picked["AP Rate Charge"]
    main["AP Rate Source"]     = picked["AP Rate Source"]
    main["AP Rate From"]       = picked["AP Rate From"]

    # ── Prime Status: mark with / without (เฉพาะ FLAT) ────────────────────
    def _prime_status(row):
        if row.get("Prime Status") == "Active":
            return "Active with" if row.get("_is_flat") else "Active"
        if row.get("_is_flat") and row.get("Prime Status NoItem") == "Active":
            return "Active without"
        return row.get("Prime Status")
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

    # ── ลบ working columns (intermediate rate/date/from ทั้ง 4 ชุด) ────────
    drop_cols = ["_pickup_str", "Prime Status NoItem"]
    for suf in ["_CHILD", "_GEN", "_CHILD_NI", "_GEN_NI"]:
        drop_cols += [f"Rate{suf}", f"Eff{suf}", f"Exp{suf}", f"From{suf}"]
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