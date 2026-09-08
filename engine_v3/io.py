# =============================================================================
# engine_v3/io.py — อ่านไฟล์ Input ทั้ง 3 (Load Confirm, AP Data, AR Data)
# รองรับ Excel (.xlsx .xls .xlsb) และ CSV (auto-detect + Thai encoding)
# =============================================================================

import pandas as pd
from pathlib import Path

from engine_v3.config import AP_RAW_COLUMNS, AP_DROP_COLUMNS


# ── Core reader ──────────────────────────────────────────────────────────────
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
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
    df.attrs["original_cols"] = original_cols
    return df


# ── AP Data ──────────────────────────────────────────────────────────────────
def read_ap_data(file) -> pd.DataFrame:
    """
    AP Data — 18 raw columns, drop 3 unused, parse dates
    """
    df = read_any(file)
    # ถ้า header ไม่ตรง ใช้ตำแหน่ง 18 คอลัมน์แรก
    if "Charge Code" not in df.columns and df.shape[1] >= 18:
        df = df.iloc[:, :18]
        df.columns = AP_RAW_COLUMNS
    df = df.drop(columns=[c for c in AP_DROP_COLUMNS if c in df.columns], errors="ignore")
    for col in ["Effective Date", "Expiration Date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
    return df


# ── AR Data ──────────────────────────────────────────────────────────────────
def read_ar_data(file) -> pd.DataFrame:
    """
    AR Data — promote headers, parse dates
    """
    df = read_any(file)
    for col in ["EFFECTIVEDATE", "EXPIRATIONDATE"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
    return df
