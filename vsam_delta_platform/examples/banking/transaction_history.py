"""
Banking Example 2: Transaction History
========================================
Transaction history is an ESDS because:
  - Transactions are written in arrival order (append-only)
  - Records are NEVER modified or deleted (regulatory requirement)
  - No natural primary key — the RBA (Relative Byte Address) is the implicit key
  - Sequential scans by date range dominate the access pattern

Copybook: TRANSHST
Record length: 80 bytes
"""

from vsam_delta_platform.metadata.models import (
    Copybook, CopybookField, PICType,
    VSAMDataset, VSAMType
)

TRANSACTION_COPYBOOK_TEXT = """\
01 TRANSACTION-REC.
   05 ACCOUNT-NO          PIC X(12).
   05 TRANS-DATE          PIC 9(8).
   05 TRANS-TIME          PIC 9(6).
   05 TRANS-TYPE          PIC X(3).
   05 TRANS-AMOUNT        PIC S9(9)V99.
   05 BALANCE-AFTER       PIC S9(9)V99.
   05 BRANCH-CODE         PIC X(5).
   05 TELLER-ID           PIC X(4).
   05 DESCRIPTION         PIC X(20).
"""

def build_transaction_copybook() -> Copybook:
    fields = [
        CopybookField("ACCOUNT-NO",    5, PICType.ALPHA,   12, 0,  0),
        CopybookField("TRANS-DATE",    5, PICType.NUMERIC,  8, 0, 12),
        CopybookField("TRANS-TIME",    5, PICType.NUMERIC,  6, 0, 20),
        CopybookField("TRANS-TYPE",    5, PICType.ALPHA,    3, 0, 26),
        CopybookField("TRANS-AMOUNT",  5, PICType.SIGNED,  11, 2, 29),
        CopybookField("BALANCE-AFTER", 5, PICType.SIGNED,  11, 2, 40),
        CopybookField("BRANCH-CODE",   5, PICType.ALPHA,    5, 0, 51),
        CopybookField("TELLER-ID",     5, PICType.ALPHA,    4, 0, 56),
        CopybookField("DESCRIPTION",   5, PICType.ALPHA,   20, 0, 60),
    ]
    return Copybook(
        name="TRANSHST",
        record_name="TRANSACTION-REC",
        fields=fields,
        record_length=80,
        raw_text=TRANSACTION_COPYBOOK_TEXT,
    )

def build_transaction_dataset() -> VSAMDataset:
    cb = build_transaction_copybook()
    ds = VSAMDataset(
        name="PROD.BANKING.TRANS.ESDS",
        vsam_type=VSAMType.ESDS,
        record_length=80,
        copybook=cb,
        record_count=50_000_000,
        description="Banking Transaction History — append-only, 5-year retention",
    )
    ds.target_table = "transaction_history"
    ds.target_location = "/delta/banking/transaction_history"
    return ds

SAMPLE_RECORDS = [
    "ACC001234567820240115143022DEP000050000000001500000BR001TEL1SALARY DEPOSIT       ",
    "ACC001234567820240115160055WDR-000010000000001490000BR001ATM2ATM WITHDRAWAL      ",
    "ACC009876543220240116090033TRF-000025000000003750000BR002TEL3WIRE TRANSFER OUT   ",
    "ACC001234567820240117120000DEP000100000000001590000BR001TEL1CHEQUE DEPOSIT       ",
]

EXPLANATION = """
## Banking Transaction History: VSAM ESDS

### Why ESDS for Transaction History?

Transactions are the one dataset type where **ESDS is the right choice**:

1. **Append-only** — Transactions are immutable by regulation (SOX, Basel III).
   VSAM ESDS enforces this: you can only WRITE to the end, never update or delete.

2. **No natural key** — A transaction is identified by its position (RBA), not a business key.
   Multiple transactions on the same account at the same millisecond are valid.

3. **Sequential scan dominance** — Statement generation, fraud detection, and regulatory
   reporting all read ranges of transactions by date. Sequential scan is optimal.

4. **Massive volume** — A retail bank may have 50M+ transactions. ESDS grows linearly.

### ESDS → Delta Lake: Append-only Table

```python
# Never use overwrite — transactions cannot be deleted
df.write \\
    .format("delta") \\
    .mode("append") \\
    .partitionBy("trans_date") \\  # partition by date for range scan efficiency
    .save("/delta/banking/transaction_history")
```

### Key insight: TRANS-AMOUNT is PIC S9(9)V99 (SIGNED)

```
VSAM byte pattern:  000010000}
The } character is EBCDIC overpunch for "0" with positive sign
Decoded: +100.00

VSAM byte pattern:  000010000{
The { character is overpunch for "0" with negative sign
Decoded: -100.00
```

In our ASCII simulation, we use '-' prefix for negative amounts.

### Why Delta Lake is BETTER than ESDS for analytics

ESDS on the mainframe can only be read by COBOL batch programs.
Delta Lake exposes the same data to SQL engines, Spark, Python, Power BI, etc.
Partitioning by date makes range queries 100x faster than a full ESDS scan.
"""
