# VSAM → Delta Lake Migration Platform

A hands-on educational platform for mainframe modernisation engineers.
Learn how VSAM datasets are analysed, decoded, and migrated into Delta Lake tables using Apache Spark.

---

## What You Will Learn

| Concept | What The Platform Teaches |
|---|---|
| VSAM Architecture | KSDS / ESDS / RRDS — structures, access patterns, real-world use cases |
| Copybook Parsing | PIC clauses → Python types → Spark StructType |
| Fixed-Width Decoding | Byte offsets, COMP-3, signed numerics, implied decimals |
| Spark DataFrames | Schema-driven reads, `substr()` extraction, type casting |
| Delta Lake | ACID, time travel, MERGE, OPTIMIZE, Z-ORDER |
| Migration Patterns | KSDS → upsert table, ESDS → append table, RRDS → indexed table |
| Validation | Record count reconciliation, null checks, duplicate key detection |
| Lineage | Mermaid diagrams, field-level lineage, OpenLineage-compatible JSON |
| Documentation | Auto-generated migration spec documents |

---

## Quick Start

```bash
# 1. Clone / open the project
cd "VSAM → Delta Lake Migration Platform"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the Streamlit UI
streamlit run vsam_delta_platform/ui/app.py

# 4. Run the test suite
pytest
```

---

## Project Structure

```
vsam_delta_platform/
│
├── metadata/           Phase 3 — VSAMDataset, Copybook, CopybookField models
├── parser/             Phase 2 — COBOL copybook parser (PIC X, 9, V, COMP-3, OCCURS)
├── decoder/            Phase 4 — Fixed-width VSAM record decoder
├── schema_generator/   Phase 5 — Spark StructType code generator
├── delta_generator/    Phase 6 — Delta Lake PySpark + SQL code generator
├── validation/         Phase 8 — Record count, null, duplicate key validation
├── lineage/            Phase 9 — Mermaid + JSON data lineage generator
├── docs/               Phase 10 — Migration document generator
│
├── examples/
│   ├── banking/        Customer Master (KSDS), Transaction History (ESDS)
│   ├── insurance/      Policy Master (KSDS)
│   ├── retail/         Product Catalog (KSDS)
│   ├── telecom/        Subscriber Master (KSDS + COMP-3)
│   └── logistics/      Shipment Tracking (ESDS)
│
├── ui/                 Streamlit application (9 tabs)
└── tests/              62 pytest unit tests
```

---

## The 10 Phases

### Phase 1 — VSAM Fundamentals
Three VSAM dataset types with visual ASCII diagrams:

| Type | Structure | Delta Equivalent |
|---|---|---|
| **KSDS** | B-tree indexed, random key access | Delta Table + Z-ORDER |
| **ESDS** | Append-only, arrival order | Append-only Delta Table |
| **RRDS** | Slot-addressed by RRN | Delta Table + row_number |

### Phase 2 — Copybook Parser
Parses COBOL copybook text into structured field metadata:

```cobol
01 CUSTOMER-REC.
   05 CUSTOMER-ID     PIC X(10).
   05 NAME            PIC X(30).
   05 BALANCE         PIC 9(7)V99.
   05 STATUS          PIC X(1).
```
→ Extracts name, type, length, decimal places, byte offset for every field.

**Supported PIC clauses:** `PIC X`, `PIC 9`, `PIC 9Vn`, `PIC S9`, `PIC 9 COMP-3`, `OCCURS n TIMES`, `REDEFINES`

### Phase 3 — Metadata Model
Python dataclasses representing the VSAM catalog:
- `VSAMDataset` — name, type, key, record length
- `Copybook` — record layout with all fields
- `CopybookField` — name, PIC type, offset, length, decimal places
- `VSAMKey` — primary key field and position

### Phase 4 — Record Decoder
Decodes fixed-width VSAM records into Python dicts:

```
"000001JOHN SMITH              0001200ACTIVE"
  ↓
{
  "CUSTOMER_ID": "000001",
  "NAME": "JOHN SMITH",
  "BALANCE": Decimal("12.00"),
  "STATUS": "ACTIVE"
}
```

Supports: alphanumeric, display numeric, decimal (V), signed overpunch, COMP-3 packed decimal.

### Phase 5 — Spark Schema Generator
Generates ready-to-use PySpark code:

```python
customer_rec_schema = StructType([
    StructField("customer_id", StringType(), True),
    StructField("name", StringType(), True),
    StructField("balance", DecimalType(9, 2), True),
    StructField("status", StringType(), True),
])
```

Also generates `spark.read.text()` + `F.substr()` extraction code.

### Phase 6 — Delta Lake Code Generator
Generates the full migration Spark script:

```python
# Initial load (KSDS → overwrite)
parsed_df.write.format("delta").mode("overwrite").save("/delta/customer")

# Incremental (MERGE for updates/inserts/deletes)
target.alias("t").merge(source.alias("s"), "t.customer_id = s.customer_id") \
    .whenMatchedDelete(condition="s.operation = 'D'") \
    .whenMatchedUpdate(...) \
    .whenNotMatchedInsert(...) \
    .execute()
```

Also generates: `CREATE TABLE ... USING DELTA`, `OPTIMIZE ... ZORDER BY`, time travel queries.

### Phase 7 — VSAM → Delta Concept Mapping
Built into every generator and the UI concept map tab.

### Phase 8 — Validation Engine
Post-migration data quality checks:
- ✓ Record count reconciliation (source = target)
- ✓ Duplicate primary key detection
- ✓ Null / empty field analysis
- ✓ Numeric range statistics (min/max/sum)
- Generates equivalent PySpark validation code

### Phase 9 — Lineage Engine
Produces:
- Mermaid flowchart (renderable in GitHub/Notion/VSCode)
- Field-level lineage table (source field → target column + transformation)
- OpenLineage-compatible JSON document

### Phase 10 — Documentation Generator
Generates a full migration specification in Markdown:
- Source dataset attributes
- Record layout table (from copybook)
- Migration strategy
- VSAM → Delta concept mapping
- Step-by-step migration runbook
- Sign-off checklist

---

## Industry Examples

Five complete migration scenarios with copybook, sample records, schema, Spark code, and learning notes:

| Domain | Dataset | Type | Records |
|---|---|---|---|
| Banking | Customer Master | KSDS | 500,000 |
| Banking | Transaction History | ESDS | 50,000,000 |
| Insurance | Policy Master | KSDS | 2,000,000 |
| Retail | Product Catalog | KSDS | 250,000 |
| Telecom | Subscriber Master | KSDS + COMP-3 | 10,000,000 |
| Logistics | Shipment Tracking | ESDS | 100,000,000 |

---

## Running the Tests

```bash
pytest -v
# 62 tests covering:
#   - Copybook parser (12 tests)
#   - Record decoder (15 tests)
#   - Schema generator (9 tests)
#   - Delta generator (11 tests)
#   - Validation engine (9 tests)
#   - Delta metadata models (6 tests)
```

---

## Roadmap — MVP to Advanced Platform

### MVP (This Release)
- [x] All 10 phases implemented
- [x] 5 industry examples
- [x] Streamlit UI with 9 tabs
- [x] 62 unit tests passing

### Phase 11 — Stretch Goals
- [ ] COMP-3 to Parquet binary direct conversion (no ASCII intermediate)
- [ ] EBCDIC to UTF-8 conversion pipeline
- [ ] Incremental load simulation (CDC delta extraction)
- [ ] Delta MERGE CDC pipeline generator
- [ ] Data profiling dashboard (column cardinality, nulls, distributions)
- [ ] Migration complexity scoring (1-5 stars per dataset)
- [ ] Apache Iceberg comparison module
- [ ] AI-generated migration assessment narrative

---

## Key Learning Takeaways

1. **VSAM is not a database** — it's a file system with indexed access. No SQL, no joins.
2. **Copybooks are the schema** — without the copybook, VSAM bytes are meaningless.
3. **COMP-3 is everywhere in financial systems** — always decode before storing.
4. **The implied decimal (V) is the biggest gotcha** — "0001200" with PIC 9(7)V99 = 12.00, not 1200.
5. **Delta Lake gives VSAM capabilities + more** — ACID + time travel + SQL + cloud scale.
6. **Record count reconciliation is non-negotiable** — it's the sign-off gate for every migration.
7. **KSDS maps to Delta MERGE** — the VSAM update-in-place pattern → Delta MERGE upsert.
8. **ESDS maps to append + partition** — arrival order → date partitioning in Delta.

---

*Built as a learning platform for mainframe engineers transitioning to cloud data engineering.*
