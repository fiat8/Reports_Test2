# =============================================================================
# engine_v3/io.py — อ่านไฟล์ Input ทั้ง 3 (Load Confirm, AP Data, AR Data)
# รองรับ Excel (.xlsx .xls .xlsb) และ CSV (auto-detect + Thai encoding)
# =============================================================================

import pandas as pd
from pathlib import Path

from engine_v3.config import AP_RAW_COLUMNS, AP_DROP_COLUMNS


# ── Core reader ──────────────────────────────────────────────────────────────
def _parse_date(series):
    """
    แปลงวันที่อย่างฉลาด — รองรับทั้ง:
      1. datetime อยู่แล้ว → ใช้เลย
      2. Excel serial number (.xlsb คืนแบบนี้ เช่น 46200) → แปลงจาก 1899-12-30
      3. string DD/MM/YYYY → parse dayfirst

    หมายเหตุ .xlsb: pyxlsb คืน date เป็น serial number ดิบ (ไม่แปลงให้)
    """
    s = pd.Series(series)

    # datetime อยู่แล้ว
    if pd.api.types.is_datetime64_any_dtype(s):
        return s

    num = pd.to_numeric(s, errors="coerce")
    numeric_ratio = num.notna().mean() if len(num) else 0

    if numeric_ratio > 0.5:
        # Excel serial — ช่วงวันที่สมเหตุสมผล: 36526 (2000) ถึง 54789 (2050)
        # ป้องกันเลขที่ไม่ใช่วันที่ (เช่น rate/qty ปน)
        valid_serial = (num >= 20000) & (num <= 80000)  # ~1954 ถึง ~2119
        result = pd.to_datetime(num.where(valid_serial), origin="1899-12-30",
                                unit="D", errors="coerce")
        return result

    # string → dayfirst
    return pd.to_datetime(s, dayfirst=True, errors="coerce")


def read_any(file) -> pd.DataFrame:
    """
    อ่านไฟล์จาก path หรือ Streamlit UploadedFile
    auto-detect นามสกุล + Thai encoding fallback สำหรับ CSV
    """
    ext = _ext_of(file)

    if ext == ".csv":
        return _read_csv_thai(file)
    elif ext == ".xlsb":
        return pd.read_excel(file, engine="pyxlsb")
    elif ext == ".xls":
        return pd.read_excel(file, engine="xlrd")
    else:  # .xlsx หรือไม่มี ext
        return pd.read_excel(file, engine="openpyxl")


def _read_csv_thai(file) -> pd.DataFrame:
    """CSV รองรับ encoding ไทย: utf-8-sig → utf-8 → tis-620 → cp874 → latin-1"""
    for enc in ["utf-8-sig", "utf-8", "tis-620", "cp874", "latin-1"]:
        try:
            if hasattr(file, "seek"):
                file.seek(0)
            return pd.read_csv(file, encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("อ่านไฟล์ CSV ไม่ได้ — กรุณาบันทึกเป็น UTF-8")


def _ext_of(file) -> str:
    if isinstance(file, (str, Path)):
        return Path(file).suffix.lower()
    return Path(getattr(file, "name", "")).suffix.lower()


# ── Load Confirm ─────────────────────────────────────────────────────────────
def read_load_confirm(file) -> pd.DataFrame:
    """
    Load Confirm Data (main) — promote headers + parse dates
    เก็บชื่อคอลัมน์ต้นฉบับไว้ใน df.attrs['original_cols'] สำหรับ styling ตอน export
    """
    df = read_any(file)
    # เก็บคอลัมน์ต้นฉบับ (ก่อนเพิ่ม key/status)
    original_cols = list(df.columns)
    # parse date columns ที่มี (dayfirst)
    for col in ["PickupConfirmed Date", "Load Created Date",
                "Completed Date", "POD Date", "Shipment Early Picked Date"]:
        if col in df.columns:
            df[col] = _parse_date(df[col])
    df.attrs["original_cols"] = original_cols
    return df


# ── AP Data ──────────────────────────────────────────────────────────────────
def read_ap_data(file) -> pd.DataFrame:
    """
    AP Data — 18 raw columns, drop 3 unused, parse dates
    + เพิ่ม _ap_row = เลขแถวต้นฉบับ (เริ่ม 1, ไม่นับ header)
    """
    df = read_any(file)
    # ถ้า header ไม่ตรง ใช้ตำแหน่ง 18 คอลัมน์แรก
    if "Charge Code" not in df.columns and df.shape[1] >= 18:
        df = df.iloc[:, :18]
        df.columns = AP_RAW_COLUMNS
    df = df.drop(columns=[c for c in AP_DROP_COLUMNS if c in df.columns], errors="ignore")
    for col in ["Effective Date", "Expiration Date"]:
        if col in df.columns:
            df[col] = _parse_date(df[col])
    # เลขแถวต้นฉบับ (สำหรับ Row Indicator) — เริ่มนับ 1
    df = df.reset_index(drop=True)
    df["_ap_row"] = range(1, len(df) + 1)
    return df


# ── AR Data ──────────────────────────────────────────────────────────────────
def read_ar_data(file) -> pd.DataFrame:
    """
    AR Data — promote headers, parse dates
    + เพิ่ม _ar_row = เลขแถวต้นฉบับ (เริ่ม 1)
    """
    df = read_any(file)
    for col in ["EFFECTIVEDATE", "EXPIRATIONDATE"]:
        if col in df.columns:
            df[col] = _parse_date(df[col])
    df = df.reset_index(drop=True)
    df["_ar_row"] = range(1, len(df) + 1)
    return df
