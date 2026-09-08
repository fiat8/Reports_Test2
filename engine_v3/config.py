# =============================================================================
# engine_v3/config.py — Framework V3 constants
# Base: Mapping 3 files (Load Confirm, AP Data, AR Data) → date-range match
# =============================================================================

# ── AP Data raw columns (18) ─────────────────────────────────────────────────
AP_RAW_COLUMNS = [
    "Tariff ID", "Rate Tariff ID", "Rate Code", "Charge Code", "Condition/Option",
    "Service ID", "Range Code", "Effective Date", "Expiration Date", "Carrier ID",
    "Item Type", "Origin Zone Code", "Dest. Zone Code", "Range To", "Rate",
    "Lane ID", "Origin Zone Desc.", "Dest. Zone Desc.",
]

# columns ที่ M-Code ทิ้งหลัง promote
AP_DROP_COLUMNS = ["Lane ID", "Origin Zone Desc.", "Dest. Zone Desc."]

# ── AR Data raw columns (key ตัวหลัก) ────────────────────────────────────────
AR_KEY_COLUMNS = [
    "CUST_CD", "SERVICE_ID", "CHARGE_ID", "RATECODE",
    "EFFECTIVEDATE", "EXPIRATIONDATE", "RATE",
]

# ── Filter rules ─────────────────────────────────────────────────────────────
EXCLUDE_RATE_TARIFF = "CUSTPICKUP"       # ตัดออกทุก AP query
STOP_CODES          = {"STEP", "STOP", "STOP_3PL"}
STOP_ONLY_CODES     = {"STOP", "STOP_3PL"}
GENERIC_MARKER      = "GENERIC"          # Rate Tariff ID มีคำนี้ = Generic

# SDFLAT special handling
SDFLAT_PREFIX = "SDFLAT_"
SDFLAT_START  = "SDFLAT"

# ── FLAT Fallback (without item type) ────────────────────────────────────────
# Trigger: charge code ที่ Left 4 = "FLAT" (FLAT, FLATM, FLATP, FLATB, ...)
# หมายเหตุ: SDFLAT ขึ้นต้น "SDFL" จึงไม่เข้าเงื่อนไขนี้ (ถูกต้อง)
FLAT_FALLBACK_PREFIX = "FLAT"    # Left 4 characters
STATUS_WITH    = "Active with"
STATUS_WITHOUT = "Active without"

# ── Key building (Load Confirm side) ─────────────────────────────────────────
# Pri-AP = OrigZone + DestZone + Carrier + Service + ItemType + Charge + RateCode
DRAFTFLAT_CODE   = "DRAFTFLAT"
DRAFTFLAT_FROM   = "DFTCASE"
DRAFTFLAT_TO     = "DFTFLAT"
CO_CODE          = "CO"
AR_CO_MARKER     = "AR_CO"

# ── Date format ──────────────────────────────────────────────────────────────
DATE_DAYFIRST = True                     # DD/MM/YYYY (Thai Excel)
DATE_EN_AU    = "%d/%m/%Y"               # Final key date format

# ── Load Confirm key column names (source) ───────────────────────────────────
LC = {
    "orig_zone":    "Shpm Lane Origin Zone/Hub",
    "dest_zone":    "Shpm Lane Dest Zone/Hub",
    "carrier":      "Carrier ID",
    "service":      "Load Service ID",
    "item_type":    "Shpm Item Type",
    "charge_code":  "Load Charge Code",
    "rate_code":    "Shpm Rate Code",
    "applied_code": "Applied RateCode",
    "cust_code":    "Shpm Customer Code",
    "cust_service": "Shpm Customer Service ID",
    "pickup_date":  "PickupConfirmed Date",
}

# ── Output ───────────────────────────────────────────────────────────────────
PREVIEW_ROWS = 50
