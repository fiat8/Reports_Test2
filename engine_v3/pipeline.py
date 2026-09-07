# =============================================================================
# engine_v3/pipeline.py — Orchestrator: Stage 1 → 2 → 3
# =============================================================================

import pandas as pd
from engine_v3 import stage1_premap, stage2_finalmap, stage3_return


def run(lc_df: pd.DataFrame, ap_df: pd.DataFrame, ar_df: pd.DataFrame) -> pd.DataFrame:
    """
    Full V3 pipeline:
      Stage 1: pre-map (status + keys)
      Stage 2: final map (date-range)
      Stage 3: return เข้า main
    Returns: final DataFrame
    """
    # Stage 1
    s1 = stage1_premap.run(lc_df, ap_df, ar_df)

    # Stage 2 (ใช้ main ที่มี key แล้วจาก stage 1)
    s2 = stage2_finalmap.run(s1["main"], ap_df, ar_df)

    # Stage 3
    result = stage3_return.run(s1, s2)
    return result


def get_kpi(df: pd.DataFrame) -> dict:
    return stage3_return.get_kpi(df)
