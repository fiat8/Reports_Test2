# =============================================================================
# app.py — Billing Reconcile V3
# Preview (100) + Trace (AP/AR Report แนวตั้ง) + Progress + Timer
# =============================================================================

import time, re
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from engine_v3 import io as v3io
from engine_v3 import pipeline, trace
from engine_v3.excel_export import to_styled_excel

st.set_page_config(page_title="Billing Reconcile", page_icon="📊", layout="wide")

st.title("📊 Billing Reconcile")
st.caption("AR/AP Mapping — BRF Logistics Co., Ltd.")

# ── Sidebar upload ───────────────────────────────────────────────────────────
st.sidebar.header("📂 อัปโหลดข้อมูล 3 ไฟล์")
lc_file = st.sidebar.file_uploader("1. Load Confirm Data (หลัก) *", type=["xlsx","xls","xlsb","csv"], key="lc")
ap_file = st.sidebar.file_uploader("2. AP Data *", type=["xlsx","xls","xlsb","csv"], key="ap")
ar_file = st.sidebar.file_uploader("3. AR Data *", type=["xlsx","xls","xlsb","csv"], key="ar")

if not all([lc_file, ap_file, ar_file]):
    st.info("👈 อัปโหลดครบ 3 ไฟล์ทางซ้าย แล้วกด Run Mapping")
    st.stop()


def _fmt(sec):
    m, s = divmod(int(round(sec)), 60)
    return f"{m} นาที {s} วินาที" if m > 0 else f"{s} วินาที"


def _timer_html():
    return """
    <div style="font-family:'Segoe UI',sans-serif;padding:12px 16px;
      background:linear-gradient(135deg,#4f8ef7,#7c5cbf);border-radius:10px;
      color:white;display:inline-block;">
      <span style="font-size:12px;opacity:0.9;">⏱️ เวลาประมวลผล</span><br>
      <span id="tmr" style="font-size:28px;font-weight:700;">00:00</span>
    </div>
    <script>var sec=0,el=document.getElementById('tmr');
    setInterval(function(){sec++;var m=String(Math.floor(sec/60)).padStart(2,'0');
    var s=String(sec%60).padStart(2,'0');if(el)el.textContent=m+':'+s;},1000);</script>
    """


# ── Run ──────────────────────────────────────────────────────────────────────
if st.button("▶ Run Mapping", type="primary", use_container_width=True):
    start = time.time()
    tslot = st.empty()
    with tslot:
        components.html(_timer_html(), height=80)
    pslot = st.empty()
    steps = []

    def _prog(n, msg):
        steps.append(f"{'✅' if n>3 else '⚙️'} {msg}")
        pslot.markdown("\n\n".join(f"- {x}" for x in steps))

    try:
        with st.status("กำลังประมวลผล...", expanded=True) as box:
            st.write("📂 อ่านไฟล์ทั้ง 3...")
            lc_df = v3io.read_load_confirm(lc_file)
            ap_df = v3io.read_ap_data(ap_file)
            ar_df = v3io.read_ar_data(ar_file)
            st.write(f"   Load Confirm: {len(lc_df):,} | AP: {len(ap_df):,} | AR: {len(ar_df):,}")
            result = pipeline.run(lc_df, ap_df, ar_df, progress=_prog)
            kpi = pipeline.get_kpi(result)
            elapsed = time.time() - start
            st.session_state.update({
                "result": result, "kpi": kpi, "elapsed": elapsed,
                "ap_raw": ap_df, "ar_raw": ar_df,
            })
            box.update(label=f"✅ เสร็จ! ใช้เวลา {_fmt(elapsed)}", state="complete")
        tslot.empty()
        st.toast(f"✅ เสร็จ! {_fmt(elapsed)}", icon="🎉")
        st.success(f"🎉 ประมวลผลเสร็จ — ใช้เวลา **{_fmt(elapsed)}**")
        st.balloons()
    except Exception as e:
        tslot.empty()
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")
        st.stop()


# ── Results ──────────────────────────────────────────────────────────────────
if "result" in st.session_state:
    result = st.session_state["result"]
    kpi = st.session_state["kpi"]
    original_cols = result.attrs.get("original_cols", [])

    if "elapsed" in st.session_state:
        st.caption(f"⏱️ เวลาประมวลผลล่าสุด: {_fmt(st.session_state['elapsed'])}")

    # KPI
    st.divider()
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📋 Total", f"{kpi['total']:,}")
    c2.metric("✅ Matched", f"{kpi['matched']:,}", delta=f"{kpi['match_pct']}%")
    c3.metric("❌ Unmatched", f"{kpi['unmatched']:,}")
    c4.metric("🔄 Fallback", f"{kpi.get('fallback',0):,}")
    c5.metric("📈 Match Rate", f"{kpi['match_pct']}%")

    # Download (ครบทุกคอลัมน์)
    st.divider()
    excel_bytes = to_styled_excel(result, original_cols=original_cols)
    st.download_button("📥 ดาวน์โหลดรายงาน (.xlsx)", data=excel_bytes,
        file_name="Reconcile_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True)

    # ── Load Confirm Preview (100 แถว) ──
    st.divider()
    st.subheader("🔍 Load Confirm Preview")

    search = st.text_input("🔎 ค้นหา Load ID", "", placeholder="พิมพ์ Load ID แล้ว Enter")

    # preview เฉพาะ column Load Confirm เดิม
    lc_cols = [c for c in original_cols if c in result.columns]
    preview_df = result[lc_cols].copy() if lc_cols else result.copy()

    if search.strip() and "Load ID" in preview_df.columns:
        mask = preview_df["Load ID"].astype(str).str.contains(search.strip(), na=False)
        preview_df = preview_df[mask]

    st.caption(f"แสดง {min(len(preview_df),100):,} จาก {len(preview_df):,} แถว (คลิกแถวเพื่อดู AP/AR)")
    event = st.dataframe(preview_df.head(100), use_container_width=True,
                         on_select="rerun", selection_mode="single-row", key="ptable")

    # หา Load ID ที่เลือก
    selected = None
    sel = event.selection.rows if event and event.selection else []
    if sel and "Load ID" in preview_df.columns:
        selected = preview_df.iloc[sel[0]]["Load ID"]
    elif search.strip() and len(preview_df) == 1 and "Load ID" in preview_df.columns:
        selected = preview_df.iloc[0]["Load ID"]

    # ── AP/AR Report (แนวตั้ง บน-ล่าง) แสดงเมื่อเลือกเท่านั้น ──
    if selected is not None:
        with st.spinner("🔄 กำลังค้นหา AP/AR ที่ใช้..."):
            row = result[result["Load ID"] == selected].iloc[0]
            ap_hit = trace.trace_ap(row, st.session_state.get("ap_raw"))
            ar_hit = trace.trace_ar(row, st.session_state.get("ar_raw"))

        st.divider()
        st.subheader(f"📌 Load ID: {selected}")

        # AP Report (เต็มกว้าง)
        st.markdown("#### 🟦 AP Report (rate ทั้งหมดที่ match)")
        if not ap_hit.empty:
            st.caption(f"พบ {len(ap_hit)} รายการ")
            st.dataframe(ap_hit, use_container_width=True)
        else:
            st.info("ไม่พบ AP rate ที่ match กับ Load นี้")

        # AR Report (เต็มกว้าง)
        st.markdown("#### 🟩 AR Report (rate ทั้งหมดที่ match)")
        if not ar_hit.empty:
            st.caption(f"พบ {len(ar_hit)} รายการ")
            st.dataframe(ar_hit, use_container_width=True)
        else:
            st.info("ไม่พบ AR rate ที่ match กับ Load นี้")
