# Framework V3 — Mapping Architecture

## หลักการ
งานคือ **Mapping** ข้อมูลจาก 3 ไฟล์ → คืนค่ากลับ Load Confirm (main)

## Input (upload ผ่าน UI ทุกงวด)
- Load Confirm Data (หลัก)
- AP Data
- AR Data
รองรับ Excel (.xlsx .xls .xlsb) และ CSV (auto-detect + Thai encoding)

## 3 Stages

### Stage 1 — Pre-Mapping (สร้าง lookup tables)
- 1.1 AP → 6 status: Prime(Normal), Prime(Child), Mandatory, Truck, Carrier, Stop
- 1.2 AR → 2 status: Prime(Normal), Stop
- 1.3 Load Confirm → สร้าง keys (main data ปลายทาง)

### Stage 2 — Final Map (date-range)
- สร้าง AP Master (Generic/Child) + AR Master (Normal) จาก AP/AR Data
- SDFLAT: transform → append เข้า Generic (2.5→2.6)
- date-range join: Pri-AP == Pri-Columns AND Eff ≤ Pickup ≤ Exp
- Final key = Pri-AP + PickupDate (DD/MM/YYYY)

### Stage 3 — Return
- merge status + rate กลับเข้า main (join บน key/Final key)
- AP Rate: เลือก Child > Generic

## Filter rules
- ตัด Rate Tariff ID = CUSTPICKUP ออกทุก AP query
- TYPE = GENERIC ถ้า Rate Tariff ID มี "GENERIC" ไม่งั้น CHILD
- STOP codes = {STEP, STOP, STOP_3PL}
- SDFLAT: Rate Code เริ่ม "SDFLAT" → ตัด "SDFLAT_" (ใน Generic)

## โครงสร้างไฟล์
```
engine_v3/
├── config.py         ค่าคงที่ + filter rules
├── io.py             อ่าน 3 ไฟล์
├── keys.py           สร้าง key ทุกแบบ (รวมศูนย์)
├── stage1_premap.py  pre-map status + keys
├── stage2_finalmap.py date-range map + SDFLAT
├── stage3_return.py  merge กลับ main
└── pipeline.py       orchestrator
```

## Column ที่ใช้
- AP Data: 18 raw columns (Tariff ID, Rate Tariff ID, Rate Code, Charge Code, ...)
- AR Data: CUST_CD, SERVICE_ID, CHARGE_ID, RATECODE, EFFECTIVEDATE, EXPIRATIONDATE, RATE
- Load Confirm: 48 columns (main)

## Tier 2 (ยังไม่ทำ — เฟสถัดไป)
location1/2, fuel price, draft parameters — จะเพิ่มภายหลัง
