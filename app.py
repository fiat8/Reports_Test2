# =============================================================================
# app.py — BRF Billing Reconcile V3 (+ FLAT Fallback + Live Timer)
# =============================================================================

import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from io import BytesIO

from engine_v3 import io as v3io
from engine_v3 import pipeline

st.set_page_config(page_title="Billing Reconcile", page_icon="📊", layout="wide")

st.title("📊 Billing Reconcile")
st.caption("AR/AP Mapping — BRF Logistics Co., Ltd.")

# ── Sidebar: upload 3 files ──────────────────────────────────────────────────
st.sidebar.header("📂 อัปโหลดข้อมูล 3 ไฟล์")
lc_file = st.sidebar.file_uploader("1. Load Confirm Data (หลัก) *",
                                   type=["xlsx","xls","xlsb","csv"], key="lc")
ap_file = st.sidebar.file_uploader("2. AP Data *",
                                   type=["xlsx","xls","xlsb","csv"], key="ap")
ar_file = st.sidebar.file_uploader("3. AR Data *",
                                   type=["xlsx","xls","xlsb","csv"], key="ar")

all_ready = all([lc_file, ap_file, ar_file])
if not all_ready:
    st.info("👈 อัปโหลดครบ 3 ไฟล์ทางซ้าย แล้วกด Run Mapping")
    st.stop()


def _fmt_elapsed(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m} นาที {s} วินาที" if m > 0 else f"{s} วินาที"


def _live_timer_html():
    """JavaScript timer เดินสด MM:SS บน browser (ไม่รอ Python)"""
    return """
    <div style="font-family:'Segoe UI',sans-serif;padding:14px 18px;
                background:linear-gradient(135deg,#4f8ef7,#7c5cbf);
                border-radius:10px;color:white;display:inline-block;">
      <span style="font-size:13px;opacity:0.9;">⏱️ เวลาประมวลผล</span><br>
      <span id="tmr" style="font-size:32px;font-weight:700;letter-spacing:1px;">00:00</span>
    </div>
    <script>
      var sec = 0;
      var el = document.getElementById('tmr');
      var iv = setInterval(function(){
        sec++;
        var m = String(Math.floor(sec/60)).padStart(2,'0');
        var s = String(sec%60).padStart(2,'0');
        if(el) el.textContent = m + ':' + s;
      }, 1000);
    </script>
    """


# ── Run ──────────────────────────────────────────────────────────────────────
if st.button("▶ Run Mapping", type="primary", use_container_width=True):
    start_ts = time.time()

    # Live timer (เดินสดระหว่าง Python ประมวลผล)
    timer_slot = st.empty()
    with timer_slot:
        components.html(_live_timer_html(), height=90)

    try:
        with st.status("กำลังประมวลผล...", expanded=True) as box:
            st.write("📂 อ่านไฟล์ทั้ง 3...")
            lc_df = v3io.read_load_confirm(lc_file)
            ap_df = v3io.read_ap_data(ap_file)
            ar_df = v3io.read_ar_data(ar_file)
            st.write(f"   Load Confirm: {len(lc_df):,} แถว | AP: {len(ap_df):,} | AR: {len(ar_df):,}")

            st.write("⚙️ Stage 1 → 2 → 3 (Pre-map → Final map → Return)...")
            result = pipeline.run(lc_df, ap_df, ar_df)

            st.write("📊 สรุปผล...")
            kpi = pipeline.get_kpi(result)

            elapsed = time.time() - start_ts
            st.session_state["result"]  = result
            st.session_state["kpi"]     = kpi
            st.session_state["elapsed"] = elapsed
            box.update(label=f"✅ เสร็จสิ้น! ใช้เวลา {_fmt_elapsed(elapsed)}", state="complete")

        # หยุด timer → แสดงเวลารวมนิ่ง
        timer_slot.empty()
        st.toast(f"✅ ประมวลผลเสร็จ! ใช้เวลา {_fmt_elapsed(elapsed)}", icon="🎉")
        st.success(f"🎉 ประมวลผลเสร็จสิ้น — ใช้เวลาทั้งหมด **{_fmt_elapsed(elapsed)}** ({elapsed:.1f} วินาที)")
        st.balloons()

    except Exception as e:
        timer_slot.empty()
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")
        st.stop()

# ── Results ──────────────────────────────────────────────────────────────────
if "result" in st.session_state:
    result = st.session_state["result"]
    kpi = st.session_state["kpi"]

    if "elapsed" in st.session_state:
        st.caption(f"⏱️ เวลาประมวลผลล่าสุด: {_fmt_elapsed(st.session_state['elapsed'])}")

    st.divider()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📋 Total", f"{kpi['total']:,}")
    c2.metric("✅ Matched", f"{kpi['matched']:,}", delta=f"{kpi['match_pct']}%")
    c3.metric("❌ Unmatched", f"{kpi['unmatched']:,}")
    c4.metric("🔄 Fallback", f"{kpi.get('fallback', 0):,}")
    c5.metric("📈 Match Rate", f"{kpi['match_pct']}%")

    st.divider()
    st.subheader(f"Preview (50 แถวแรก จาก {len(result):,})")
    st.dataframe(result.head(50), use_container_width=True)

    st.divider()

    def _to_excel(df):
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Result")
        return buf.getvalue()

    st.download_button("📥 ดาวน์โหลดรายงาน (.xlsx)", data=_to_excel(result),
        file_name="Reconcile_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True)
