# =============================================================================
# app.py — Billing Reconcile V3 (lightweight)
# Preview 50 rows + Export (ทุกคอลัมน์ + สี 3 โซน + Rate From)
# UI trace ตัดออกชั่วคราว (แก้ memory limit) — ค่อยพัฒนาใหม่
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

# ── Sidebar upload ───────────────────────────────────────────────────────────
st.sidebar.header("📂 อัปโหลดข้อมูล 3 ไฟล์")
lc_file = st.sidebar.file_uploader("1. Load Confirm Data (หลัก) *", type=["xlsx","xls","xlsb","csv"], key="lc")
ap_file = st.sidebar.file_uploader("2. AP Data *", type=["xlsx","xls","xlsb","csv"], key="ap")
ar_file = st.sidebar.file_uploader("3. AR Data *", type=["xlsx","xls","xlsb","csv"], key="ar")

st.sidebar.divider()
st.sidebar.subheader("⚙️ Parameters")
draftflat_rate = st.sidebar.number_input(
    "DRAFTFLAT AR Rate (constant)",
    min_value=0.0, value=0.0, step=0.01, format="%.2f",
    help="ค่า rate สำหรับ DRAFTFLAT ฝั่ง AR (AR-Pri = DRAFTDRAFTFLAT). ใส่ 0 = ไม่เติม",
)

st.sidebar.divider()
st.sidebar.subheader("⛽ Fuel Price")
st.sidebar.caption("กรอกราคาน้ำมันตามวันที่ (เพิ่มแถวได้) — Surcharge = (Price-27)×1.75%")
fuel_df = st.sidebar.data_editor(
    pd.DataFrame({"Date": ["", "", ""], "Price": [None, None, None]}),
    num_rows="dynamic",
    use_container_width=True,
    key="fuel_editor",
    column_config={
        "Date": st.column_config.TextColumn("Date (DD/MM/YYYY)"),
        "Price": st.column_config.NumberColumn("Price", format="%.2f"),
    },
)

if not all([lc_file, ap_file, ar_file]):
    st.info("👈 อัปโหลดครบ 3 ไฟล์ทางซ้าย แล้วกด Run Mapping")
    st.stop()


def _fmt(sec):
    m, s = divmod(int(round(sec)), 60)
    return f"{m} นาที {s} วินาที" if m > 0 else f"{s} วินาที"


def _arrow_safe(df):
    """กัน ArrowInvalid — แปลง object เป็น string"""
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == "object":
            out[col] = out[col].astype(str).replace("nan", "").replace("None", "")
    return out


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
if st.button("▶ Run Mapping", type="primary", width="stretch"):
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
            original_cols = list(lc_df.attrs.get("original_cols", lc_df.columns))
            ap_df = v3io.read_ap_data(ap_file)
            ar_df = v3io.read_ar_data(ar_file)
            st.write(f"   Load Confirm: {len(lc_df):,} | AP: {len(ap_df):,} | AR: {len(ar_df):,}")

            # เตรียม fuel_df (กรองแถวว่าง)
            fuel_input = fuel_df.dropna(subset=["Price"]) if fuel_df is not None else None
            fuel_input = fuel_input[fuel_input["Date"].astype(str).str.strip() != ""] if fuel_input is not None and len(fuel_input) else None

            result = pipeline.run(lc_df, ap_df, ar_df, progress=_prog,
                                  draftflat_rate=(draftflat_rate if draftflat_rate > 0 else None),
                                  fuel_df=fuel_input)
            kpi = pipeline.get_kpi(result)

            # ── เตรียม Excel ทันที แล้วเก็บเฉพาะ bytes (ไม่เก็บ df ดิบ = ประหยัด RAM) ──
            excel_bytes = to_styled_excel(result, original_cols=original_cols)

            # preview 50 แถว — จัดคอลัมน์ให้ตรงกับ Excel (3 โซน)
            from engine_v3.excel_export import _arrange
            arranged_preview, _ = _arrange(result.head(50).copy(), original_cols)
            preview_50 = arranged_preview

            elapsed = time.time() - start
            st.session_state["excel"]      = excel_bytes
            st.session_state["preview"]    = preview_50
            st.session_state["kpi"]        = kpi
            st.session_state["elapsed"]    = elapsed

            # ปล่อย memory ตัวใหญ่
            del lc_df, ap_df, ar_df, result
            import gc; gc.collect()

            box.update(label=f"✅ เสร็จ! ใช้เวลา {_fmt(elapsed)}", state="complete")
        tslot.empty()
        st.toast(f"✅ เสร็จ! {_fmt(elapsed)}", icon="🎉")
        st.success(f"🎉 ประมวลผลเสร็จ — ใช้เวลา **{_fmt(elapsed)}**")
    except Exception as e:
        tslot.empty()
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")
        st.stop()


# ── Results ──────────────────────────────────────────────────────────────────
if "excel" in st.session_state:
    kpi = st.session_state["kpi"]

    if "elapsed" in st.session_state:
        st.caption(f"⏱️ เวลาประมวลผลล่าสุด: {_fmt(st.session_state['elapsed'])}")

    st.divider()
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📋 Total", f"{kpi['total']:,}")
    c2.metric("✅ Matched", f"{kpi['matched']:,}", delta=f"{kpi['match_pct']}%")
    c3.metric("❌ Unmatched", f"{kpi['unmatched']:,}")
    c4.metric("🔄 Fallback", f"{kpi.get('fallback',0):,}")
    c5.metric("📈 Match Rate", f"{kpi['match_pct']}%")

    st.divider()
    st.download_button("📥 ดาวน์โหลดรายงาน (.xlsx)", data=st.session_state["excel"],
        file_name="Reconcile_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch")

    st.divider()
    st.subheader("🔍 Preview (50 แถวแรก)")
    st.dataframe(_arrow_safe(st.session_state["preview"]), width="stretch")
