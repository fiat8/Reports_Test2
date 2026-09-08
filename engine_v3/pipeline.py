# =============================================================================
# engine_v3/pipeline.py — Orchestrator: Stage 1 → 2 → 3
# =============================================================================

import pandas as pd
from engine_v3 import stage1_premap, stage2_finalmap, stage3_return


def run(lc_df: pd.DataFrame, ap_df: pd.DataFrame, ar_df: pd.DataFrame,
        progress=None) -> pd.DataFrame:
    """
    Full V3 pipeline:
      Stage 1: pre-map (status + keys)
      Stage 2: final map (date-range)
      Stage 3: return เข้า main
    progress: optional callback(stage_no, message) สำหรับแสดง step ใน UI
    Returns: final DataFrame
    """
    def _p(n, msg):
        if progress:
            progress(n, msg)

    # Stage 1
    _p(1, "Stage 1: Pre-mapping (สร้าง key + status)")
    s1 = stage1_premap.run(lc_df, ap_df, ar_df)

    # Stage 2 (ใช้ main ที่มี key แล้วจาก stage 1)
    _p(2, "Stage 2: Final map (date-range matching)")
    s2 = stage2_finalmap.run(s1["main"], ap_df, ar_df)

    # Stage 3
    _p(3, "Stage 3: Return ค่ากลับรายงานหลัก")
    result = stage3_return.run(s1, s2)
    # พา original Load Confirm columns ไปด้วย (สำหรับ styling ตอน export)
    result.attrs["original_cols"] = lc_df.attrs.get("original_cols", [])
    _p(4, "เสร็จสิ้น")
    return result


def get_kpi(df: pd.DataFrame) -> dict:
    return stage3_return.get_kpi(df)
