# =============================================================================
# engine_v3/fuel.py — Fuel Price mapping (Independent Key)
# Input: ตาราง Date | Price
# Map: Pickup Date → range → Fuel Price
# Surcharge = (Fuel Price - BASE) × RATE%
# =============================================================================

import pandas as pd

FUEL_BASE = 27          # ราคาฐาน
FUEL_RATE = 1.75 / 100  # 1.75%
FUEL_EXTEND_DAYS = 365  # แถวสุดท้าย ครอบอนาคต


def build_fuel_ranges(fuel_df: pd.DataFrame) -> pd.DataFrame:
    """
    แปลง Date | Price → range (From, To, Price, Surcharge)
    fuel_df: columns = Date, Price
      From = Date[i]
      To   = Date[i+1] - 1 วัน (แถวสุดท้าย = From + FUEL_EXTEND_DAYS)
    """
    if fuel_df is None or fuel_df.empty:
        return pd.DataFrame(columns=["From", "To", "Fuel Price", "Fuel Surcharge"])

    df = fuel_df.copy()
    df["Date"]  = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    df = df.dropna(subset=["Date", "Price"]).sort_values("Date").reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=["From", "To", "Fuel Price", "Fuel Surcharge"])

    df["From"] = df["Date"]
    df["To"]   = df["Date"].shift(-1) - pd.Timedelta(days=1)
    last = df.index[-1]
    df.loc[last, "To"] = df.loc[last, "From"] + pd.Timedelta(days=FUEL_EXTEND_DAYS)

    df["Fuel Price"]     = df["Price"]
    df["Fuel Surcharge"] = ((df["Price"] - FUEL_BASE) * FUEL_RATE).round(6)

    return df[["From", "To", "Fuel Price", "Fuel Surcharge"]].reset_index(drop=True)


def map_fuel(main: pd.DataFrame, fuel_ranges: pd.DataFrame,
             pickup_col: str = "PickupConfirmed Date") -> pd.DataFrame:
    """
    เติม Fuel Price + Fuel Surcharge ให้ main
    ตาม Pickup Date อยู่ใน range ไหน (From ≤ Pickup ≤ To, normalize ตัดเวลา)
    """
    main = main.copy()
    main["Fuel Price"]     = None
    main["Fuel Surcharge"] = None

    if fuel_ranges is None or fuel_ranges.empty:
        return main

    pk = pd.to_datetime(main[pickup_col], errors="coerce").dt.normalize()
    fr = fuel_ranges.copy()
    fr["From"] = pd.to_datetime(fr["From"], errors="coerce").dt.normalize()
    fr["To"]   = pd.to_datetime(fr["To"], errors="coerce").dt.normalize()

    for _, row in fr.iterrows():
        mask = (pk >= row["From"]) & (pk <= row["To"])
        main.loc[mask, "Fuel Price"]     = row["Fuel Price"]
        main.loc[mask, "Fuel Surcharge"] = row["Fuel Surcharge"]

    return main
