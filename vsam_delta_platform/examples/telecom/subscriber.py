"""
Telecom Example: Subscriber Master
=====================================
KSDS — Mobile Number (MSISDN) is the unique key.
Demonstrates a large COMP-3 (packed decimal) usage for call charges.
"""

from vsam_delta_platform.metadata.models import (
    Copybook, CopybookField, PICType,
    VSAMDataset, VSAMKey, VSAMType
)

SUBSCRIBER_COPYBOOK_TEXT = """\
01 SUBSCRIBER-REC.
   05 MSISDN              PIC 9(15).
   05 SUBSCRIBER-NAME     PIC X(40).
   05 PLAN-CODE           PIC X(8).
   05 ACTIVATION-DATE     PIC 9(8).
   05 MONTHLY-CHARGE      PIC 9(7)V99 COMP-3.
   05 DATA-USAGE-MB       PIC 9(9).
   05 VOICE-MINUTES       PIC 9(6).
   05 SMS-COUNT           PIC 9(5).
   05 ACCOUNT-STATUS      PIC X(2).
   05 ROAMING-FLAG        PIC X(1).
"""

def build_subscriber_copybook() -> Copybook:
    fields = [
        CopybookField("MSISDN",           5, PICType.NUMERIC, 15, 0,  0),
        CopybookField("SUBSCRIBER-NAME",  5, PICType.ALPHA,   40, 0, 15),
        CopybookField("PLAN-CODE",        5, PICType.ALPHA,    8, 0, 55),
        CopybookField("ACTIVATION-DATE",  5, PICType.NUMERIC,  8, 0, 63),
        CopybookField("MONTHLY-CHARGE",   5, PICType.COMP3,    5, 2, 71),  # COMP-3: 5 bytes = 9 digits
        CopybookField("DATA-USAGE-MB",    5, PICType.NUMERIC,  9, 0, 76),
        CopybookField("VOICE-MINUTES",    5, PICType.NUMERIC,  6, 0, 85),
        CopybookField("SMS-COUNT",        5, PICType.NUMERIC,  5, 0, 91),
        CopybookField("ACCOUNT-STATUS",   5, PICType.ALPHA,    2, 0, 96),
        CopybookField("ROAMING-FLAG",     5, PICType.ALPHA,    1, 0, 98),
    ]
    return Copybook(
        name="SUBSCRIB",
        record_name="SUBSCRIBER-REC",
        fields=fields,
        record_length=99,
        raw_text=SUBSCRIBER_COPYBOOK_TEXT,
    )

def build_subscriber_dataset() -> VSAMDataset:
    cb = build_subscriber_copybook()
    key = VSAMKey(field_name="MSISDN", offset=0, length=15)
    ds = VSAMDataset(
        name="PROD.TELECOM.SUBSCRIBER.KSDS",
        vsam_type=VSAMType.KSDS,
        record_length=99,
        copybook=cb,
        primary_key=key,
        record_count=10_000_000,
        description="Telecom Subscriber Master — 10M subscribers",
    )
    ds.target_table = "subscriber_master"
    ds.target_location = "/delta/telecom/subscriber_master"
    return ds

EXPLANATION = """
## Telecom Subscriber: COMP-3 (Packed Decimal) Deep Dive

### What is COMP-3?

COMP-3 (Computational-3) is PACKED DECIMAL storage — the most space-efficient
numeric format in COBOL. It packs TWO decimal digits into ONE byte.

```
Field: PIC 9(7)V99 COMP-3
Digits: 9 total (7 integer + 2 decimal)
Bytes:  ⌈(9+1)/2⌉ = 5 bytes

Example value: $299.99 (monthly charge)
As packed decimal: 02 99 99 00 0C
Hex:               02999900 0C
                   ^^^^^^^  ^
                   digits   C = positive sign nibble
```

### How we decode COMP-3 in Python

```python
def decode_comp3(raw_bytes, decimal_places):
    hex_str = raw_bytes.hex().upper()
    sign_nibble = hex_str[-1]          # 'C' or 'F' = positive, 'D' = negative
    digits = hex_str[:-1]              # all digit nibbles
    sign = -1 if sign_nibble == 'D' else 1
    integer_part = digits[:-decimal_places]
    frac_part = digits[-decimal_places:]
    return Decimal(f"{integer_part}.{frac_part}") * sign
```

### Why COMP-3 is everywhere in financial/telecom mainframe systems

- COBOL in the 1960s-1980s had very limited memory and disk space
- COMP-3 stores 18 digits in 9 bytes vs. 18 bytes in display format
- Every IBM System/360 had hardware decimal arithmetic (DAA instruction)
- Result: virtually ALL monetary fields in legacy mainframe systems are COMP-3
"""
