"""
Retail Example: Product Catalog
================================
KSDS — SKU is the unique key.
This example demonstrates OCCURS (array fields) for product categories.
"""

from vsam_delta_platform.metadata.models import (
    Copybook, CopybookField, PICType,
    VSAMDataset, VSAMKey, VSAMType
)

PRODUCT_COPYBOOK_TEXT = """\
01 PRODUCT-REC.
   05 SKU-NUMBER          PIC X(12).
   05 PRODUCT-NAME        PIC X(50).
   05 DEPARTMENT          PIC X(20).
   05 UNIT-PRICE          PIC 9(7)V99.
   05 COST-PRICE          PIC 9(7)V99.
   05 STOCK-QTY           PIC 9(6).
   05 REORDER-LEVEL       PIC 9(6).
   05 SUPPLIER-CODE       PIC X(8).
   05 PRODUCT-STATUS      PIC X(1).
"""

def build_product_copybook() -> Copybook:
    fields = [
        CopybookField("SKU-NUMBER",     5, PICType.ALPHA,   12, 0,  0),
        CopybookField("PRODUCT-NAME",   5, PICType.ALPHA,   50, 0, 12),
        CopybookField("DEPARTMENT",     5, PICType.ALPHA,   20, 0, 62),
        CopybookField("UNIT-PRICE",     5, PICType.DECIMAL,  9, 2, 82),
        CopybookField("COST-PRICE",     5, PICType.DECIMAL,  9, 2, 91),
        CopybookField("STOCK-QTY",      5, PICType.NUMERIC,  6, 0,100),
        CopybookField("REORDER-LEVEL",  5, PICType.NUMERIC,  6, 0,106),
        CopybookField("SUPPLIER-CODE",  5, PICType.ALPHA,    8, 0,112),
        CopybookField("PRODUCT-STATUS", 5, PICType.ALPHA,    1, 0,120),
    ]
    return Copybook(
        name="PRODCAT",
        record_name="PRODUCT-REC",
        fields=fields,
        record_length=121,
        raw_text=PRODUCT_COPYBOOK_TEXT,
    )

def build_product_dataset() -> VSAMDataset:
    cb = build_product_copybook()
    key = VSAMKey(field_name="SKU-NUMBER", offset=0, length=12)
    ds = VSAMDataset(
        name="PROD.RETAIL.PRODUCT.KSDS",
        vsam_type=VSAMType.KSDS,
        record_length=121,
        copybook=cb,
        primary_key=key,
        record_count=250_000,
        description="Retail Product Catalog — all active and discontinued products",
    )
    ds.target_table = "product_catalog"
    ds.target_location = "/delta/retail/product_catalog"
    return ds

SAMPLE_RECORDS = [
    "SKU-001-AAAA01WIRELESS BLUETOOTH HEADPHONES      ELECTRONICS         0005999000350010000020SUPP-001A",
    "SKU-002-BBBB01ORGANIC GREEN TEA (100 BAGS)       FOOD & BEVERAGE     0000899000450050000500SUPP-002A",
    "SKU-003-CCCC01RUNNING SHOES SIZE 10              FOOTWEAR            0007999000480001000050SUPP-003D",
]

EXPLANATION = """
## Retail Product Catalog: VSAM KSDS

### UNIT-PRICE field: PIC 9(7)V99

The price field "0005999" with 2 decimal places means $59.99.
The V (virtual decimal) means the decimal point is NOT stored — it's implied.

```
Raw bytes : "0005999"
Implied decimal after byte 5: 0005999 → 59.99
```

In Spark:
```python
F.concat(
    F.substr("value", 83, 7),  # integer part
    F.lit("."),
    F.substr("value", 90, 2)   # decimal part
).cast(DecimalType(9, 2))
```

### PRODUCT-STATUS codes
- A = Active
- D = Discontinued
- S = Seasonal
- O = Out of Stock (permanent)
"""
