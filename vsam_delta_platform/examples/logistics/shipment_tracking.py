"""
Logistics Example: Shipment Tracking
=======================================
ESDS — Shipment events are append-only (immutable audit trail).
Each event = one record; a shipment has multiple event records.
Demonstrates ESDS → partitioned Delta table pattern.
"""

from vsam_delta_platform.metadata.models import (
    Copybook, CopybookField, PICType,
    VSAMDataset, VSAMType
)

SHIPMENT_COPYBOOK_TEXT = """\
01 SHIPMENT-EVENT.
   05 TRACKING-NUMBER     PIC X(20).
   05 EVENT-DATE          PIC 9(8).
   05 EVENT-TIME          PIC 9(6).
   05 EVENT-CODE          PIC X(4).
   05 EVENT-DESCRIPTION   PIC X(40).
   05 LOCATION-CODE       PIC X(8).
   05 LOCATION-NAME       PIC X(30).
   05 CARRIER-CODE        PIC X(5).
   05 WEIGHT-KG           PIC 9(5)V99.
   05 STATUS-FLAG         PIC X(1).
"""

def build_shipment_copybook() -> Copybook:
    fields = [
        CopybookField("TRACKING-NUMBER",   5, PICType.ALPHA,   20, 0,  0),
        CopybookField("EVENT-DATE",        5, PICType.NUMERIC,  8, 0, 20),
        CopybookField("EVENT-TIME",        5, PICType.NUMERIC,  6, 0, 28),
        CopybookField("EVENT-CODE",        5, PICType.ALPHA,    4, 0, 34),
        CopybookField("EVENT-DESCRIPTION", 5, PICType.ALPHA,   40, 0, 38),
        CopybookField("LOCATION-CODE",     5, PICType.ALPHA,    8, 0, 78),
        CopybookField("LOCATION-NAME",     5, PICType.ALPHA,   30, 0, 86),
        CopybookField("CARRIER-CODE",      5, PICType.ALPHA,    5, 0,116),
        CopybookField("WEIGHT-KG",         5, PICType.DECIMAL,  7, 2,121),
        CopybookField("STATUS-FLAG",       5, PICType.ALPHA,    1, 0,128),
    ]
    return Copybook(
        name="SHIPTRK",
        record_name="SHIPMENT-EVENT",
        fields=fields,
        record_length=129,
        raw_text=SHIPMENT_COPYBOOK_TEXT,
    )

def build_shipment_dataset() -> VSAMDataset:
    cb = build_shipment_copybook()
    ds = VSAMDataset(
        name="PROD.LOGISTICS.SHIPMENT.ESDS",
        vsam_type=VSAMType.ESDS,
        record_length=129,
        copybook=cb,
        record_count=100_000_000,
        description="Shipment event tracking log — ESDS, 100M events, append-only",
    )
    ds.target_table = "shipment_events"
    ds.target_location = "/delta/logistics/shipment_events"
    return ds

SAMPLE_RECORDS = [
    "TRK-2024-US-0000120240115083000PICK  SHIPMENT PICKED UP              WH-US-01 US EAST WAREHOUSE            FDX  0002500A",
    "TRK-2024-US-0000120240115143000SORT  IN SORTING FACILITY             HUB-MEM  MEMPHIS SORT HUB               FDX  0002500T",
    "TRK-2024-US-0000120240116093000DEPT  DEPARTED FACILITY               HUB-MEM  MEMPHIS SORT HUB               FDX  0002500T",
    "TRK-2024-US-0000120240117113000DLVR  DELIVERED TO RECIPIENT          DEL-NYC  NEW YORK DELIVERY              FDX  0002500D",
]

EXPLANATION = """
## Logistics Shipment Tracking: VSAM ESDS

### Why ESDS for shipment events?

Shipment tracking is a perfect ESDS use case:
1. Events are immutable — you can't "un-deliver" a package
2. Events arrive in chronological order (perfect for ESDS)
3. One shipment has multiple events (PICK → SORT → DEPT → DLVR)
4. The tracking number is NOT the key — it repeats across events

### Delta Lake partitioning strategy

```python
# Partition by date for time-range query efficiency
df.write \\
    .format("delta") \\
    .mode("append") \\
    .partitionBy("event_date") \\
    .save("/delta/logistics/shipment_events")
```

**Query pattern**: "Show me all events for shipment TRK-2024-US-00001"
```sql
-- Without partitioning: full table scan (100M rows)
SELECT * FROM shipment_events WHERE tracking_number = 'TRK-2024-US-00001';

-- With date partition + Z-ORDER by tracking_number: much faster
OPTIMIZE shipment_events ZORDER BY (tracking_number);
SELECT * FROM shipment_events WHERE tracking_number = 'TRK-2024-US-00001';
```
"""
