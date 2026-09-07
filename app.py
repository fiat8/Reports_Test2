# =============================================================================
# app.py — BRF Billing Reconcile V3
# Framework ใหม่: Mapping 3 files (Load Confirm, AP Data, AR Data)
# =============================================================================

import time
import streamlit as st
import pandas as pd
from io import BytesIO

from engine_v3 import io as v3io
from engine_v3 import pipeline

st.set_page_config(page_title="BRF Billing Reconcile V3", page_icon="📊", layout="wide")

st.title("📊 BRF Billing Reconcile")
st.caption("AR/AP Mapping — BRF Logistics Co., Ltd. (Framework V3)")

# ── Sidebar: upload 3 files ──────────────────────────────────────────────────
st.sidebar.header("📂 อัปโหลดข้อมูล 3 ไฟล์")

lc_file = st.sidebar.file_uploader(
    "1. Load Confirm Data (หลัก) *",
    type=["xlsx", "xls", "xlsb", "csv"], key="lc",
)
ap_file = st.sidebar.file_uploader(
    "2. AP Data *",
    type=["xlsx", "xls", "xlsb", "csv"], key="ap",
)
ar_file = st.sidebar.file_uploader(
    "3. AR Data *",
    type=["xlsx", "xls", "xlsb", "csv"], key="ar",
)

all_ready = all([lc_file, ap_file, ar_file])

if not all_ready:
    st.info("👈 อัปโหลดครบ 3 ไฟล์ทางซ้าย แล้วกด Run Mapping")
    st.stop()


def _fmt_elapsed(seconds: float) -> str:
    """แปลงวินาที → 'X นาที Y วินาที' หรือ 'Y วินาที'"""
    m, s = divmod(int(round(seconds)), 60)
    if m > 0:
        return f"{m} นาที {s} วินาที"
    return f"{s} วินาที"


# ── Run ──────────────────────────────────────────────────────────────────────
if st.button("▶ Run Mapping", type="primary", use_container_width=True):
    start_ts = time.time()
    timer_box = st.empty()

    try:
        with st.status("⏱️ กำลังประมวลผล...", expanded=True) as box:

            timer_box.markdown("### ⏱️ 0.0 วินาที")
            st.write("📂 อ่านไฟล์ทั้ง 3...")
            lc_df = v3io.read_load_confirm(lc_file)
            ap_df = v3io.read_ap_data(ap_file)
            ar_df = v3io.read_ar_data(ar_file)
            st.write(f"   Load Confirm: {len(lc_df):,} แถว | AP: {len(ap_df):,} | AR: {len(ar_df):,}")
            timer_box.markdown(f"### ⏱️ {_fmt_elapsed(time.time() - start_ts)}")

            st.write("⚙️ Stage 1 → 2 → 3 (Pre-map → Final map → Return)...")
            result = pipeline.run(lc_df, ap_df, ar_df)
            timer_box.markdown(f"### ⏱️ {_fmt_elapsed(time.time() - start_ts)}")

            st.write("📊 สรุปผล...")
            kpi = pipeline.get_kpi(result)

            elapsed = time.time() - start_ts
            st.session_state["result"]  = result
            st.session_state["kpi"]     = kpi
            st.session_state["elapsed"] = elapsed

            box.update(label=f"✅ เสร็จสิ้น! ใช้เวลา {_fmt_elapsed(elapsed)}", state="complete")

        timer_box.empty()
        try:
            st.toast(f"✅ ประมวลผลเสร็จ! ใช้เวลา {_fmt_elapsed(elapsed)}", icon="🎉")
        except Exception:
            pass
        st.success(f"🎉 ประมวลผลเสร็จสิ้น — ใช้เวลาทั้งหมด **{_fmt_elapsed(elapsed)}** "
                   f"({elapsed:.1f} วินาที)")
        st.balloons()

    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")
        st.stop()

# ── Results ──────────────────────────────────────────────────────────────────
if "result" in st.session_state:
    result = st.session_state["result"]
    kpi = st.session_state["kpi"]

    if "elapsed" in st.session_state:
        st.caption(f"⏱️ เวลาประมวลผลล่าสุด: {_fmt_elapsed(st.session_state['elapsed'])}")

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 Total", f"{kpi['total']:,}")
    c2.metric("✅ Matched", f"{kpi['matched']:,}", delta=f"{kpi['match_pct']}%")
    c3.metric("❌ Unmatched", f"{kpi['unmatched']:,}")
    c4.metric("📈 Match Rate", f"{kpi['match_pct']}%")

    st.divider()
    st.subheader(f"Preview (50 แถวแรก จาก {len(result):,})")
    st.dataframe(result.head(50), use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)

    def _to_excel(df):
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Result")
        return buf.getvalue()

    with col1:
        st.download_button(
            "📥 ดาวน์โหลดทั้งหมด (.xlsx)",
            data=_to_excel(result),
            file_name="Reconcile_Output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col2:
        unmatched = result[result.get("Prime Status", pd.Series(dtype=object)) != "Active"]
        st.download_button(
            f"⚠️ ดาวน์โหลด Unmatched ({len(unmatched):,})",
            data=_to_excel(unmatched),
            file_name="Reconcile_Unmatched.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
