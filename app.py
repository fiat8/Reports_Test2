# =============================================================================
# app.py — Billing Reconcile V3
# Preview + Trace (คลิก/Search Load ID) + Stage Progress + Styled Export
# =============================================================================

import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from engine_v3 import io as v3io
from engine_v3 import pipeline
from engine_v3.excel_export import to_styled_excel

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


def _fmt_elapsed(sec):
    m, s = divmod(int(round(sec)), 60)
    return f"{m} นาที {s} วินาที" if m > 0 else f"{s} วินาที"


def _live_timer_html():
    return """
    <div style="font-family:'Segoe UI',sans-serif;padding:12px 16px;
                background:linear-gradient(135deg,#4f8ef7,#7c5cbf);
                border-radius:10px;color:white;display:inline-block;">
      <span style="font-size:12px;opacity:0.9;">⏱️ เวลาประมวลผล</span><br>
      <span id="tmr" style="font-size:28px;font-weight:700;">00:00</span>
    </div>
    <script>
      var sec=0, el=document.getElementById('tmr');
      setInterval(function(){sec++;var m=String(Math.floor(sec/60)).padStart(2,'0');
        var s=String(sec%60).padStart(2,'0');if(el)el.textContent=m+':'+s;},1000);
    </script>
    """


# ── Run ──────────────────────────────────────────────────────────────────────
if st.button("▶ Run Mapping", type="primary", use_container_width=True):
    start_ts = time.time()
    timer_slot = st.empty()
    with timer_slot:
        components.html(_live_timer_html(), height=80)

    prog_slot = st.empty()
    steps_done = []

    def _progress(n, msg):
        steps_done.append(f"{'✅' if n>3 else '⚙️'} {msg}")
        prog_slot.markdown("\n\n".join(f"- {s}" for s in steps_done))

    try:
        with st.status("กำลังประมวลผล...", expanded=True) as box:
            st.write("📂 อ่านไฟล์ทั้ง 3...")
            lc_df = v3io.read_load_confirm(lc_file)
            ap_df = v3io.read_ap_data(ap_file)
            ar_df = v3io.read_ar_data(ar_file)
            st.write(f"   Load Confirm: {len(lc_df):,} | AP: {len(ap_df):,} | AR: {len(ar_df):,}")

            result = pipeline.run(lc_df, ap_df, ar_df, progress=_progress)

            kpi = pipeline.get_kpi(result)
            elapsed = time.time() - start_ts
            st.session_state["result"]  = result
            st.session_state["kpi"]     = kpi
            st.session_state["elapsed"] = elapsed
            st.session_state["ap_raw"]  = ap_df   # เก็บดิบสำหรับ trace
            st.session_state["ar_raw"]  = ar_df
            box.update(label=f"✅ เสร็จสิ้น! ใช้เวลา {_fmt_elapsed(elapsed)}", state="complete")

        timer_slot.empty()
        st.toast(f"✅ เสร็จ! {_fmt_elapsed(elapsed)}", icon="🎉")
        st.success(f"🎉 ประมวลผลเสร็จ — ใช้เวลา **{_fmt_elapsed(elapsed)}**")
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

    # ── KPI ──
    st.divider()
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📋 Total", f"{kpi['total']:,}")
    c2.metric("✅ Matched", f"{kpi['matched']:,}", delta=f"{kpi['match_pct']}%")
    c3.metric("❌ Unmatched", f"{kpi['unmatched']:,}")
    c4.metric("🔄 Fallback", f"{kpi.get('fallback',0):,}")
    c5.metric("📈 Match Rate", f"{kpi['match_pct']}%")

    # ── Download ──
    st.divider()
    original_cols = result.attrs.get("original_cols", [])
    excel_bytes = to_styled_excel(result, original_cols=original_cols)
    st.download_button("📥 ดาวน์โหลดรายงาน (.xlsx)", data=excel_bytes,
        file_name="Reconcile_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True)

    # ── Preview (Load Confirm เท่านั้น) ──
    st.divider()
    st.subheader(f"🔍 Preview & Trace — {len(result):,} แถว")

    # เลือกเฉพาะ column Load Confirm เดิม + สรุปผล สำหรับ preview
    preview_cols = [c for c in original_cols if c in result.columns]
    summary_cols = [c for c in ["Prime Status","AP Rate Charge","AP Rate From",
                                "AR Prime Status","AR Rate Charge","AR Rate From"]
                    if c in result.columns]
    show_cols = preview_cols + summary_cols

    # Search box
    search = st.text_input("🔎 ค้นหา Load ID (พิมพ์แล้ว Enter)", "")

    preview_df = result[show_cols].copy() if show_cols else result.copy()

    if search.strip():
        # filter ตาม Load ID
        if "Load ID" in preview_df.columns:
            mask = preview_df["Load ID"].astype(str).str.contains(search.strip(), na=False)
            preview_df = preview_df[mask]

    # แสดงตาราง + เลือก row ได้
    st.caption(f"แสดง {min(len(preview_df), 50000):,} แถว (คลิกที่แถวเพื่อดู AP/AR ที่ใช้)")
    event = st.dataframe(
        preview_df.head(50000),
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="preview_table",
    )

    # ── Trace: หา Load ID ที่เลือก (จากคลิก หรือ search) ──
    selected_load_id = None
    sel_rows = event.selection.rows if event and event.selection else []
    if sel_rows:
        ridx = sel_rows[0]
        if "Load ID" in preview_df.columns:
            selected_load_id = preview_df.iloc[ridx]["Load ID"]
    elif search.strip() and len(preview_df) == 1 and "Load ID" in preview_df.columns:
        selected_load_id = preview_df.iloc[0]["Load ID"]

    # ── แสดง AP/AR ที่ใช้ ──
    if selected_load_id is not None:
        st.divider()
        st.subheader(f"📌 รายละเอียด Load ID: {selected_load_id}")

        row = result[result["Load ID"] == selected_load_id].iloc[0]

        ap_raw = st.session_state.get("ap_raw")
        ar_raw = st.session_state.get("ar_raw")

        col_ap, col_ar = st.columns(2)

        # AP
        with col_ap:
            st.markdown("#### 🟦 AP Data ที่ใช้")
            ap_from = row.get("AP Rate From")
            if ap_from and ap_raw is not None:
                # ดึงเลขแถวจาก "AP-123 (พบ N)"
                import re
                m = re.search(r"AP-(\d+)", str(ap_from))
                if m:
                    rnum = int(m.group(1))
                    ap_hit = ap_raw[ap_raw["_ap_row"] == rnum]
                    st.caption(f"Rate มาจาก: {ap_from}")
                    st.dataframe(ap_hit.drop(columns=["_ap_row"], errors="ignore").T,
                                 use_container_width=True)
                else:
                    st.info("ไม่พบเลขแถว AP")
            else:
                st.info("ไม่มี AP rate ที่ map เจอ")

        # AR
        with col_ar:
            st.markdown("#### 🟩 AR Data ที่ใช้")
            ar_from = row.get("AR Rate From")
            if ar_from and ar_raw is not None:
                import re
                m = re.search(r"AR-(\d+)", str(ar_from))
                if m:
                    rnum = int(m.group(1))
                    ar_hit = ar_raw[ar_raw["_ar_row"] == rnum]
                    st.caption(f"Rate มาจาก: {ar_from}")
                    st.dataframe(ar_hit.drop(columns=["_ar_row"], errors="ignore").T,
                                 use_container_width=True)
                else:
                    st.info("ไม่พบเลขแถว AR")
            else:
                st.info("ไม่มี AR rate ที่ map เจอ")
