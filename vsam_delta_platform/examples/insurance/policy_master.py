"""
Insurance Example: Policy Master File
=======================================
KSDS — Policy number is the unique key.
"""

from vsam_delta_platform.metadata.models import (
    Copybook, CopybookField, PICType,
    VSAMDataset, VSAMKey, VSAMType
)

POLICY_COPYBOOK_TEXT = """\
01 POLICY-REC.
   05 POLICY-NUMBER       PIC X(12).
   05 POLICYHOLDER-NAME   PIC X(40).
   05 POLICY-TYPE         PIC X(5).
   05 EFFECTIVE-DATE      PIC 9(8).
   05 EXPIRY-DATE         PIC 9(8).
   05 PREMIUM-AMOUNT      PIC 9(9)V99.
   05 SUM-ASSURED         PIC 9(11)V99.
   05 POLICY-STATUS       PIC X(2).
   05 AGENT-CODE          PIC X(6).
"""

def build_policy_copybook() -> Copybook:
    fields = [
        CopybookField("POLICY-NUMBER",      5, PICType.ALPHA,   12, 0,  0),
        CopybookField("POLICYHOLDER-NAME",  5, PICType.ALPHA,   40, 0, 12),
        CopybookField("POLICY-TYPE",        5, PICType.ALPHA,    5, 0, 52),
        CopybookField("EFFECTIVE-DATE",     5, PICType.NUMERIC,  8, 0, 57),
        CopybookField("EXPIRY-DATE",        5, PICType.NUMERIC,  8, 0, 65),
        CopybookField("PREMIUM-AMOUNT",     5, PICType.DECIMAL, 11, 2, 73),
        CopybookField("SUM-ASSURED",        5, PICType.DECIMAL, 13, 2, 84),
        CopybookField("POLICY-STATUS",      5, PICType.ALPHA,    2, 0, 97),
        CopybookField("AGENT-CODE",         5, PICType.ALPHA,    6, 0, 99),
    ]
    return Copybook(
        name="POLMAST",
        record_name="POLICY-REC",
        fields=fields,
        record_length=105,
        raw_text=POLICY_COPYBOOK_TEXT,
    )

def build_policy_dataset() -> VSAMDataset:
    cb = build_policy_copybook()
    key = VSAMKey(field_name="POLICY-NUMBER", offset=0, length=12)
    ds = VSAMDataset(
        name="PROD.INSUR.POLICY.KSDS",
        vsam_type=VSAMType.KSDS,
        record_length=105,
        copybook=cb,
        primary_key=key,
        record_count=2_000_000,
        description="Insurance Policy Master — all active and closed policies",
    )
    ds.target_table = "policy_master"
    ds.target_location = "/delta/insurance/policy_master"
    return ds

SAMPLE_RECORDS = [
    "POL-2024-00001ALICE GREEN                              LIFE 202301012025010100050000000500000000AC AG1234",
    "POL-2024-00002BOB WILLIAMS                             AUTO 202201012024010100012000000025000000ACAG5678",
    "POL-2024-00003CAROL DAVIS                              HOME 202101012024010100025000000150000000CLBR9012",
]

EXPLANATION = """
## Insurance Policy Master: VSAM KSDS

### Field Analysis

- **POLICY-NUMBER** (PIC X(12)): Alphanumeric business key — includes year and sequence.
- **PREMIUM-AMOUNT** (PIC 9(9)V99): 9 integer + 2 decimal = DecimalType(11, 2).
- **SUM-ASSURED** (PIC 9(11)V99): 11 integer + 2 decimal = DecimalType(13, 2).
  This is the insured amount — MUST use exact decimal to avoid rounding errors.
- **POLICY-STATUS**: AC=Active, CL=Closed, LA=Lapsed, SU=Surrendered.

### Why precision matters for insurance fields

VSAM stores PREMIUM-AMOUNT as exactly 11 bytes: "00005000000" = 50000.00.
If you stored this in a Spark DoubleType, floating-point rounding could corrupt
the cent values. Always use DecimalType for monetary fields.

```python
# WRONG — loses pennies
.cast("double")

# CORRECT — exact decimal arithmetic
.cast(DecimalType(11, 2))
```
"""
