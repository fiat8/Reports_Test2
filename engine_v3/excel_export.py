# =============================================================================
# engine_v3/excel_export.py — Export Excel + styled header + auto-width
#
# สี header 3 กลุ่ม:
#   - Load Confirm เดิม → เทาเข้ม
#   - คอลัมน์ AP (ใหม่)  → ฟ้า
#   - คอลัมน์ AR (ใหม่)  → เขียว
# ตัวอักษร header = ขาว, auto-width ทุกคอลัมน์
# =============================================================================

from io import BytesIO
import pandas as pd
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter


# ── สี (hex, ไม่มี #) ────────────────────────────────────────────────────────
COLOR_LOAD_CONFIRM = "374151"   # เทาเข้ม
COLOR_AP           = "2563EB"   # ฟ้า
COLOR_AR           = "059669"   # เขียว
FONT_WHITE         = "FFFFFF"

# ── คำที่บ่งชี้ว่าเป็นคอลัมน์ AP / AR ─────────────────────────────────────────
AP_HINTS = [
    "Pri-AP", "Mandate Key", "Sup-Carrier", "Sup-Truck", "AP Stop",
    "Final key",  # AP final
    "Prime Status", "Child Status", "Mandatory Status",
    "Carrier Status", "Truck Status",
    "AP Rate", "AP Stop Charge",
]
AR_HINTS = [
    "AR-Pri", "AR Stop", "AR-Final key",
    "AR Prime Status", "AR Rate", "AR Stop Charge",
]


def _classify_column(col: str, original_cols: set) -> str:
    """
    คืน 'LC' / 'AP' / 'AR' ตามที่มาของคอลัมน์
    - อยู่ใน original_cols → LC (Load Confirm เดิม)
    - มีคำ AR → AR (เช็ค AR ก่อน เพราะ AR-Final มีคำ Final เหมือน AP)
    - มีคำ AP → AP
    - อื่นๆ → LC
    """
    if col in original_cols:
        return "LC"
    # เช็ค AR ก่อน (เจาะจงกว่า)
    for hint in AR_HINTS:
        if hint in col:
            return "AR"
    for hint in AP_HINTS:
        if hint in col:
            return "AP"
    return "LC"


# ── คอลัมน์ภายในที่ซ่อน (เฉพาะ helper จริงๆ — key map ยังแสดง) ────────────────
HIDDEN_COLUMNS = {
    "_is_flat", "_pickup_str", "_ap_row", "_ar_row",
    "Prime Status NoItem",
    # intermediate rate (รวมเป็น AP Rate Charge แล้ว)
    "AP Rate Charge (Generic)", "AP Rate Charge (Child)",
    "AP Rate Charge (Generic) NoItem", "AP Rate Charge (Child) NoItem",
}


def arrange_columns(df, original_cols=None, hide_working=True):
    """
    จัดลำดับคอลัมน์เป็น 3 โซน:
      1. Load Confirm เดิม (ตามลำดับต้นฉบับ)
      2. AP (key/status/rate/from)
      3. AR (key/status/rate/from)
    + ซ่อน working columns (ถ้า hide_working=True)
    """
    original_cols = list(original_cols) if original_cols else []
    orig_set = set(original_cols)

    cols = list(df.columns)
    if hide_working:
        cols = [c for c in cols if c not in HIDDEN_COLUMNS]

    lc_cols, ap_cols, ar_cols = [], [], []
    for c in cols:
        g = _classify_column(str(c), orig_set)
        if g == "LC":
            lc_cols.append(c)
        elif g == "AP":
            ap_cols.append(c)
        else:
            ar_cols.append(c)

    # LC เรียงตามลำดับต้นฉบับก่อน แล้วตัวที่เหลือ
    lc_ordered = [c for c in original_cols if c in lc_cols]
    lc_ordered += [c for c in lc_cols if c not in orig_set]

    final_order = lc_ordered + ap_cols + ar_cols
    # เผื่อมีคอลัมน์ตกหล่น
    final_order += [c for c in df.columns if c in cols and c not in final_order]
    return df[final_order]


def to_styled_excel(df: pd.DataFrame, original_cols=None,
                    sheet_name: str = "Result", hide_working: bool = True) -> bytes:
    """
    Export DataFrame เป็น Excel พร้อม:
      - จัดลำดับคอลัมน์ 3 โซน (LC → AP → AR) + ซ่อน working keys
      - header สี 3 กลุ่ม (LC/AP/AR) ตัวอักษรขาว
      - auto-width ทุกคอลัมน์
    original_cols: set ของชื่อคอลัมน์ Load Confirm เดิม (ถ้า None = เดาจาก hint)
    """
    if original_cols is None:
        original_cols = set()
    else:
        original_cols = set(original_cols)

    # จัดลำดับ + ซ่อน working columns
    df = arrange_columns(df, original_cols=original_cols, hide_working=hide_working)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]

        fills = {
            "LC": PatternFill("solid", fgColor=COLOR_LOAD_CONFIRM),
            "AP": PatternFill("solid", fgColor=COLOR_AP),
            "AR": PatternFill("solid", fgColor=COLOR_AR),
        }
        white_bold = Font(color=FONT_WHITE, bold=True)
        center = Alignment(horizontal="center", vertical="center", wrap_text=False)

        # ── Style header row ──────────────────────────────────────────────
        for idx, col in enumerate(df.columns, start=1):
            cell = ws.cell(row=1, column=idx)
            group = _classify_column(str(col), original_cols)
            cell.fill = fills[group]
            cell.font = white_bold
            cell.alignment = center

        # ── Auto-width ────────────────────────────────────────────────────
        for idx, col in enumerate(df.columns, start=1):
            letter = get_column_letter(idx)
            # ความยาวสูงสุดระหว่าง header กับข้อมูล (sample 500 แถวแรกเพื่อความเร็ว)
            max_len = len(str(col))
            try:
                sample = df[col].head(500)
                # แปลงเป็น string อย่างปลอดภัย (รองรับ date, number, NaN, pyarrow)
                lengths = sample.apply(lambda v: len(str(v)) if v is not None and pd.notna(v) else 0)
                if len(lengths) > 0:
                    data_max = int(lengths.max())
                    max_len = max(max_len, data_max)
            except Exception:
                pass  # ถ้าคอลัมน์มีปัญหา ใช้ความกว้าง header อย่างเดียว
            # จำกัดกว้างสุด 50 กันคอลัมน์ยาวเกิน
            ws.column_dimensions[letter].width = min(max_len + 2, 50)

        # freeze header row
        ws.freeze_panes = "A2"

    return buf.getvalue()
