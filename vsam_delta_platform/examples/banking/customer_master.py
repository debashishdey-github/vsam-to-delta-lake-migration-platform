"""
Banking Example 1: Customer Master File
========================================
The Customer Master is typically a KSDS because:
  - Every customer has a unique ID (natural key → VSAM key)
  - Random access by customer ID is the dominant access pattern
  - Records are updated (address, phone, status) but rarely deleted

Copybook: CUSTMAST
Record length: 100 bytes
Key field: CUSTOMER-ID (bytes 0-9)
"""

from vsam_delta_platform.metadata.models import (
    Copybook, CopybookField, FieldStatus, PICType,
    VSAMDataset, VSAMKey, VSAMType
)

# ---------------------------------------------------------------------------
# Copybook definition
# ---------------------------------------------------------------------------

CUSTOMER_COPYBOOK_TEXT = """\
01 CUSTOMER-REC.
   05 CUSTOMER-ID         PIC X(10).
   05 CUSTOMER-NAME       PIC X(30).
   05 ADDRESS-LINE1       PIC X(30).
   05 CITY                PIC X(15).
   05 STATE               PIC X(2).
   05 ZIP-CODE            PIC X(5).
   05 ACCOUNT-BALANCE     PIC 9(9)V99.
   05 CUSTOMER-STATUS     PIC X(1).
   05 OPEN-DATE           PIC 9(8).
"""

# ---------------------------------------------------------------------------
# Pre-built copybook object (what the parser would produce)
# ---------------------------------------------------------------------------

def build_customer_copybook() -> Copybook:
    fields = [
        CopybookField("CUSTOMER-ID",      5, PICType.ALPHA,   10, 0,  0),
        CopybookField("CUSTOMER-NAME",    5, PICType.ALPHA,   30, 0, 10),
        CopybookField("ADDRESS-LINE1",    5, PICType.ALPHA,   30, 0, 40),
        CopybookField("CITY",             5, PICType.ALPHA,   15, 0, 70),
        CopybookField("STATE",            5, PICType.ALPHA,    2, 0, 85),
        CopybookField("ZIP-CODE",         5, PICType.ALPHA,    5, 0, 87),
        CopybookField("ACCOUNT-BALANCE",  5, PICType.DECIMAL, 11, 2, 92),
        CopybookField("CUSTOMER-STATUS",  5, PICType.ALPHA,    1, 0,103),
        CopybookField("OPEN-DATE",        5, PICType.NUMERIC,  8, 0,104),
    ]
    return Copybook(
        name="CUSTMAST",
        record_name="CUSTOMER-REC",
        fields=fields,
        record_length=112,
        raw_text=CUSTOMER_COPYBOOK_TEXT,
    )


# ---------------------------------------------------------------------------
# Dataset definition
# ---------------------------------------------------------------------------

def build_customer_dataset() -> VSAMDataset:
    cb = build_customer_copybook()
    key = VSAMKey(field_name="CUSTOMER-ID", offset=0, length=10)
    ds = VSAMDataset(
        name="PROD.BANKING.CUSTOMER.KSDS",
        vsam_type=VSAMType.KSDS,
        record_length=112,
        copybook=cb,
        primary_key=key,
        record_count=500_000,
        description="Banking Customer Master File — contains all active customers",
    )
    ds.target_table = "customer_master"
    ds.target_location = "/delta/banking/customer_master"
    return ds


# ---------------------------------------------------------------------------
# Sample VSAM records (ASCII simulation of mainframe flat file)
# ---------------------------------------------------------------------------

SAMPLE_RECORDS = [
    "0000000001JOHN A SMITH                ADDRESS LINE 1                CHICAGO        IL60601000123456A20230101",
    "0000000002MARY J JOHNSON              123 OAK AVENUE                NEW YORK       NY10001000987651A20220515",
    "0000000003ROBERT BROWN                456 PINE STREET               LOS ANGELES    CA90001001500000A20210301",
    "0000000004LINDA WHITE                 789 ELM ROAD                  HOUSTON        TX77001000050001I20240101",
    "0000000005DAVID JONES                 321 MAPLE BLVD                PHOENIX        AZ85001002000002A20200615",
]

# ---------------------------------------------------------------------------
# Learning explanation
# ---------------------------------------------------------------------------

EXPLANATION = """
## Banking Customer Master: VSAM KSDS

### Why KSDS for Customer Master?

The Customer Master is the quintessential KSDS use case:

1. **Unique key** — Every customer has a unique CUSTOMER-ID (like a primary key in SQL).
   VSAM KSDS enforces uniqueness at the index level, preventing duplicate keys.

2. **Random access** — The banking system looks up a customer by ID thousands of times
   per second (balance inquiries, transaction validation, statement generation).
   KSDS provides O(log n) key lookup via the B-tree index.

3. **Sequential scanning** — Month-end batch jobs read all customers in key order
   for interest calculation, statements, and regulatory reports. KSDS supports both.

4. **Updates** — Address changes, phone number updates, and status changes (A=Active,
   I=Inactive, C=Closed) are applied as in-place record updates in VSAM KSDS.

### Migration Strategy

```
VSAM KSDS CUSTOMER.KSDS
    ↓  (REPRO to flat file → transfer → iconv)
Flat file (fixed-width ASCII)
    ↓  (spark.read.text() + substr())
Spark DataFrame
    ↓  (.write.format("delta").mode("overwrite"))
Delta Table: customer_master
    ↓  (OPTIMIZE + ZORDER BY customer_id)
Optimised for key-based lookups
```

### ACCOUNT-BALANCE field

The balance field `PIC 9(9)V99` means:
  - 9 integer digits + 2 decimal places
  - Total 11 bytes in the record (V = virtual decimal, no byte consumed)
  - Must be decoded as `substr(93,9) || "." || substr(102,2)` then cast to DECIMAL(11,2)
  - In Delta Lake: `DecimalType(11, 2)` — exact precision, no floating point errors

### Delta Lake advantages over KSDS

| Capability | VSAM KSDS | Delta Lake |
|---|---|---|
| Random read by key | ✓ (B-tree index) | ✓ (Z-ORDER + data skipping) |
| Sequential read | ✓ | ✓ (Parquet scan) |
| ACID updates | ✓ (record-level) | ✓ (MERGE statement) |
| Historical versions | ✗ | ✓ (VERSION AS OF) |
| Analytics / SQL | ✗ (COBOL batch only) | ✓ (any SQL engine) |
| Scale | Mainframe only | Multi-cloud |
| Schema evolution | Manual reorg | ALTER TABLE ADD COLUMN |
"""
