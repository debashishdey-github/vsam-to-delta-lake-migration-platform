"""
Streamlit UI — VSAM → Delta Lake Migration Platform
=====================================================
A fully interactive web application for the learning platform.

Run:
    streamlit run vsam_delta_platform/ui/app.py

Tabs:
  1. Learn VSAM Concepts
  2. Copybook Parser
  3. Record Decoder
  4. Spark Schema Generator
  5. Delta Lake Code Generator
  6. Validation Engine
  7. Lineage Viewer
  8. Industry Examples
  9. Documentation
"""

import json
import sys
import os

# Ensure the project root is on the path when running via streamlit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd

from vsam_delta_platform.parser.copybook_parser import CopybookParser
from vsam_delta_platform.decoder.record_decoder import VSAMRecordDecoder
from vsam_delta_platform.schema_generator.spark_schema import SparkSchemaGenerator
from vsam_delta_platform.delta_generator.delta_code_gen import DeltaCodeGenerator
from vsam_delta_platform.validation.validator import ValidationEngine
from vsam_delta_platform.lineage.lineage_engine import LineageEngine
from vsam_delta_platform.docs.doc_generator import DocumentationGenerator
from vsam_delta_platform.metadata.models import (
    VSAMDataset, VSAMType, VSAMKey, Copybook
)

# Example scenarios
from vsam_delta_platform.examples.banking.customer_master import (
    build_customer_dataset, CUSTOMER_COPYBOOK_TEXT, SAMPLE_RECORDS as BANK_CUST_RECORDS, EXPLANATION as BANK_CUST_EXP
)
from vsam_delta_platform.examples.banking.transaction_history import (
    build_transaction_dataset, TRANSACTION_COPYBOOK_TEXT, SAMPLE_RECORDS as BANK_TRANS_RECORDS, EXPLANATION as BANK_TRANS_EXP
)
from vsam_delta_platform.examples.insurance.policy_master import (
    build_policy_dataset, POLICY_COPYBOOK_TEXT, EXPLANATION as INS_EXP
)
from vsam_delta_platform.examples.retail.product_catalog import (
    build_product_dataset, PRODUCT_COPYBOOK_TEXT, EXPLANATION as RETAIL_EXP
)
from vsam_delta_platform.examples.telecom.subscriber import (
    build_subscriber_dataset, SUBSCRIBER_COPYBOOK_TEXT, EXPLANATION as TELECOM_EXP
)
from vsam_delta_platform.examples.logistics.shipment_tracking import (
    build_shipment_dataset, SHIPMENT_COPYBOOK_TEXT, EXPLANATION as LOGISTICS_EXP
)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="VSAM → Delta Lake Migration Platform",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🏭 VSAM → Delta Lake")
    st.markdown("**Migration Learning Platform**")
    st.divider()

    tab_choice = st.radio(
        "Navigate",
        [
            "📚 Learn VSAM",
            "🔍 Copybook Parser",
            "📖 Record Decoder",
            "⚡ Spark Schema",
            "🔷 Delta Generator",
            "✅ Validation",
            "🔗 Lineage",
            "🏭 Industry Examples",
            "📄 Documentation",
        ],
    )

    st.divider()
    st.markdown("""
    **Learning Phases**
    - Phase 1: VSAM Concepts
    - Phase 2: Copybook Parser
    - Phase 3: Metadata Model
    - Phase 4: Record Decoder
    - Phase 5: Spark Schema
    - Phase 6: Delta Generator
    - Phase 7: Concept Mapping
    - Phase 8: Validation
    - Phase 9: Lineage
    - Phase 10: Documentation
    """)


# ===========================================================================
# Tab 1: Learn VSAM
# ===========================================================================

if tab_choice == "📚 Learn VSAM":
    st.title("📚 Phase 1: VSAM Fundamentals")
    st.markdown("""
    VSAM (Virtual Storage Access Method) is IBM's proprietary file system for z/OS mainframes.
    Introduced in the 1970s, it remains the backbone of banking, insurance, telecom, and
    government mainframe systems worldwide.

    Understanding VSAM is essential for any mainframe modernisation project.
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 🔑 KSDS")
        st.markdown("**Key Sequenced Data Set**")
        st.info("""
**Best for:** Master files, reference data

**Key features:**
- Primary key (unique identifier)
- B-tree index for fast key lookups
- Sequential access in key order
- Random access by key value
- Supports updates and deletes

**Real-world examples:**
- Customer Master
- Account Master
- Employee Master
- Product Catalog

**Delta equivalent:**
Delta Table + Z-ORDER by key column
        """)

    with col2:
        st.markdown("### 📋 ESDS")
        st.markdown("**Entry Sequenced Data Set**")
        st.success("""
**Best for:** Transaction logs, audit trails

**Key features:**
- Records stored in arrival order
- No primary key (RBA is implicit key)
- Append-only (no updates/deletes)
- Sequential scan access
- Immutable record history

**Real-world examples:**
- Transaction History
- Audit Log
- Event Stream
- Shipment Events

**Delta equivalent:**
Append-only Delta Table, partitioned by date
        """)

    with col3:
        st.markdown("### 🔢 RRDS")
        st.markdown("**Relative Record Data Set**")
        st.warning("""
**Best for:** Fixed-slot arrays, lookup tables

**Key features:**
- Fixed-size record slots
- Addressed by slot number (RRN)
- Slots can be empty
- Direct slot access by RRN
- Less common than KSDS/ESDS

**Real-world examples:**
- Code/Status tables
- Day-of-week tables
- Fixed-size lookup arrays

**Delta equivalent:**
Delta Table + row_number integer column
        """)

    st.divider()
    st.markdown("### VSAM vs Modern Data Lake: Concept Mapping")
    mapping = {
        "VSAM Concept": ["KSDS Dataset", "ESDS Dataset", "RRDS Dataset", "Copybook (.cpy)", "Fixed-Width Record",
                         "ICF Catalog", "KSDS UPDATE", "KSDS INSERT", "KSDS DELETE", "REPRO (bulk export)", "LISTCAT"],
        "Delta Lake Equivalent": ["Delta Table + Z-ORDER", "Append-only Delta Table", "Delta Table + row_number",
                                   "StructType Schema", "Parquet Row", "Hive/Unity Catalog", "MERGE matchedUpdate",
                                   "MERGE notMatchedInsert", "MERGE matchedDelete", "Initial OVERWRITE load",
                                   "spark.table().count()"],
        "Key Difference": [
            "Delta adds time travel & ACID", "Delta adds partitioning & SQL access",
            "Delta adds analytics SQL access", "Delta adds type enforcement",
            "Parquet is columnar (VSAM is row-based)", "Metastore enables multi-engine access",
            "Delta MERGE is ACID transactional", "Delta INSERT is idempotent with MERGE",
            "Delta supports soft-delete pattern", "Delta enables incremental loads too",
            "Delta count is eventually consistent"
        ],
    }
    st.dataframe(pd.DataFrame(mapping), use_container_width=True)

    st.divider()
    st.markdown("### VSAM Architecture Diagram")
    st.code("""
VSAM Dataset Structure (KSDS example)
======================================

                    ┌─────────────────────────────┐
                    │    ICF CATALOG ENTRY          │
                    │  PROD.CUSTOMER.KSDS           │
                    │  Type: KSDS                   │
                    │  Key: CUSTOMER-ID (0,10)      │
                    │  RecordSize: 200              │
                    └─────────────┬───────────────┘
                                  │
                ┌─────────────────┴──────────────────┐
                │                                    │
     ┌──────────▼───────┐              ┌─────────────▼──────┐
     │   INDEX COMPONENT │              │   DATA COMPONENT   │
     │  (B-tree Index)   │              │  (Ordered Records) │
     │                   │              │                    │
     │  CUSTOMER-ID      │   points to  │  000001 JOHN ...   │
     │  000001 ──────────┼──────────────▶  000002 JANE ...   │
     │  000002 ──────────┼──────────────▶  000003 BOB  ...   │
     │  000003           │              │  ...               │
     └───────────────────┘              └────────────────────┘

Each record is:
  ├── bytes 0-9:   CUSTOMER-ID    (PIC X(10))
  ├── bytes 10-39: NAME           (PIC X(30))
  ├── bytes 40-69: ADDRESS        (PIC X(30))
  └── bytes 70-79: BALANCE        (PIC 9(8)V99)
    """, language="text")


# ===========================================================================
# Tab 2: Copybook Parser
# ===========================================================================

elif tab_choice == "🔍 Copybook Parser":
    st.title("🔍 Phase 2: VSAM Copybook Parser")
    st.markdown("""
    A COBOL copybook defines the **byte-by-byte record layout** of a VSAM dataset.
    Think of it as the equivalent of a SQL `CREATE TABLE` statement.

    Paste your copybook below and the parser will extract field names, types, lengths, and byte offsets.
    """)

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("### Input: COBOL Copybook")
        default_copybook = """01 CUSTOMER-REC.
   05 CUSTOMER-ID         PIC X(10).
   05 CUSTOMER-NAME       PIC X(30).
   05 ADDRESS-LINE1       PIC X(30).
   05 CITY                PIC X(15).
   05 STATE               PIC X(2).
   05 ZIP-CODE            PIC X(5).
   05 ACCOUNT-BALANCE     PIC 9(7)V99.
   05 CREDIT-LIMIT        PIC 9(9)V99 COMP-3.
   05 CUSTOMER-STATUS     PIC X(1).
   05 OPEN-DATE           PIC 9(8)."""

        copybook_text = st.text_area(
            "Paste COBOL copybook",
            value=default_copybook,
            height=320,
            help="Standard COBOL copybook syntax. Supports PIC X, PIC 9, PIC 9Vn, COMP-3, OCCURS."
        )
        copybook_name = st.text_input("Copybook Name", value="CUSTMAST")

        parse_btn = st.button("🔍 Parse Copybook", type="primary")

    with col_right:
        st.markdown("### PIC Clause Quick Reference")
        st.markdown("""
| PIC Clause | Type | Bytes | Example |
|---|---|---|---|
| `PIC X(n)` | String | n | `PIC X(30)` = 30 chars |
| `PIC 9(n)` | Integer | n | `PIC 9(7)` = 7 digits |
| `PIC 9(n)V9(d)` | Decimal | n+d | `PIC 9(7)V99` = 9 bytes |
| `PIC S9(n)` | Signed Int | n | `PIC S9(5)` = ±5 digits |
| `PIC 9(n) COMP-3` | Packed Dec | ⌈(n+1)/2⌉ | `PIC 9(7) COMP-3` = 4 bytes |
        """)

    if parse_btn and copybook_text:
        parser = CopybookParser()
        copybook = parser.parse(copybook_text, name=copybook_name)

        st.success(f"✓ Parsed {len(copybook.fields)} fields | Total record length: **{copybook.record_length} bytes**")

        st.markdown("### Parsed Field Schema")
        schema_data = parser.schema_summary(copybook)
        if schema_data:
            st.dataframe(pd.DataFrame(schema_data), use_container_width=True)

        st.markdown("### Copybook → Spark Schema JSON")
        st.json(copybook.to_dict())

        # Store in session state for use in other tabs
        st.session_state["parsed_copybook"] = copybook
        st.session_state["copybook_text"] = copybook_text


# ===========================================================================
# Tab 3: Record Decoder
# ===========================================================================

elif tab_choice == "📖 Record Decoder":
    st.title("📖 Phase 4: VSAM Record Decoder")
    st.markdown("""
    VSAM records are **fixed-width byte strings**. Each field occupies a precise byte range
    defined by the copybook. This tab lets you paste raw VSAM records and see them decoded.
    """)

    if "parsed_copybook" not in st.session_state:
        st.warning("⚠️ Parse a copybook first in the **Copybook Parser** tab.")
        st.stop()

    copybook: Copybook = st.session_state["parsed_copybook"]
    st.info(f"Using copybook: **{copybook.name}** | Record length: **{copybook.record_length} bytes**")

    default_record = "0000000001JOHN A SMITH                ADDRESS LINE 1                CHICAGO        IL60601" + "0001234560012345A20230101"
    raw_records = st.text_area(
        "Paste VSAM records (one per line)",
        value=default_record,
        height=200,
        help="Each line should be one fixed-width VSAM record."
    )

    if st.button("🔓 Decode Records", type="primary"):
        decoder = VSAMRecordDecoder(copybook)
        records = decoder.decode_records(raw_records)

        st.success(f"✓ Decoded {len(records)} records")

        if records:
            st.markdown("### Decoded Records")
            st.dataframe(pd.DataFrame(records), use_container_width=True)

            st.markdown("### Field-by-Field Breakdown (first record)")
            preview = decoder.preview_decoding(raw_records.splitlines()[0])
            st.dataframe(pd.DataFrame(preview), use_container_width=True)

            st.session_state["decoded_records"] = records


# ===========================================================================
# Tab 4: Spark Schema
# ===========================================================================

elif tab_choice == "⚡ Spark Schema":
    st.title("⚡ Phase 5: Spark Schema Generator")
    st.markdown("""
    Generate PySpark **StructType** schema code from your copybook.
    This is the schema you'll use to create typed Spark DataFrames.
    """)

    if "parsed_copybook" not in st.session_state:
        st.warning("⚠️ Parse a copybook first in the **Copybook Parser** tab.")
        st.stop()

    copybook = st.session_state["parsed_copybook"]
    gen = SparkSchemaGenerator()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Generated StructType Code")
        schema_code = gen.generate_struct_type_code(copybook)
        st.code(schema_code, language="python")

    with col2:
        st.markdown("### Generated DataFrame Read Code")
        file_path = st.text_input("VSAM extract file path", value="/data/vsam_extract.txt")
        read_code = gen.generate_dataframe_read_code(copybook, file_path)
        st.code(read_code, language="python")

    st.markdown("### Field Type Mapping Table")
    mapping_table = gen.generate_field_mapping_table(copybook)
    if mapping_table:
        st.dataframe(pd.DataFrame(mapping_table), use_container_width=True)


# ===========================================================================
# Tab 5: Delta Generator
# ===========================================================================

elif tab_choice == "🔷 Delta Generator":
    st.title("🔷 Phase 6 & 7: Delta Lake Code Generator")
    st.markdown("""
    Generate complete **PySpark + Delta Lake** migration code for your dataset.
    Select the VSAM type and provide metadata to generate the full migration script.
    """)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### Dataset Configuration")
        ds_name = st.text_input("VSAM Dataset Name", value="PROD.CUSTOMER.KSDS")
        vsam_type_sel = st.selectbox("VSAM Type", ["KSDS", "ESDS", "RRDS"])
        record_length = st.number_input("Record Length (bytes)", value=200, min_value=1)
        record_count = st.number_input("Record Count", value=500000, min_value=0)
        target_table = st.text_input("Target Delta Table Name", value="customer_master")
        target_location = st.text_input("Delta Storage Location", value="/delta/customer_master")
        key_field = st.text_input("Primary Key Field (KSDS only)", value="CUSTOMER-ID")

    with col2:
        st.markdown("### About Delta Lake")
        st.markdown("""
**Delta Lake** adds ACID transactions to Apache Spark's data lake.

Key capabilities:
- **ACID** — writes are atomic; no partial data
- **Schema enforcement** — rejects wrong columns
- **Time travel** — query any historical version
- **MERGE** — upsert in one SQL statement
- **OPTIMIZE** — compact small files automatically
- **Z-ORDER** — cluster data for fast key lookups
        """)

    generate_btn = st.button("🔷 Generate Migration Code", type="primary")

    if generate_btn:
        vsam_type = VSAMType(vsam_type_sel)
        copybook = st.session_state.get("parsed_copybook", None)
        key = VSAMKey(key_field, 0, 10) if vsam_type == VSAMType.KSDS and key_field else None

        ds = VSAMDataset(
            name=ds_name,
            vsam_type=vsam_type,
            record_length=record_length,
            copybook=copybook,
            primary_key=key,
            record_count=record_count,
        )
        ds.target_table = target_table
        ds.target_location = target_location

        code_gen = DeltaCodeGenerator()

        tab_initial, tab_sql, tab_merge, tab_optimize, tab_travel, tab_full = st.tabs([
            "Initial Load", "CREATE TABLE SQL", "MERGE Upsert", "OPTIMIZE", "Time Travel", "Full Script"
        ])

        with tab_initial:
            st.code(code_gen.generate_initial_load(ds), language="python")

        with tab_sql:
            st.code(code_gen.generate_create_table_sql(ds), language="sql")

        with tab_merge:
            st.code(code_gen.generate_merge_upsert(ds), language="python")

        with tab_optimize:
            st.code(code_gen.generate_optimize_and_zorder(ds), language="sql")

        with tab_travel:
            st.code(code_gen.generate_time_travel_query(ds), language="sql")

        with tab_full:
            st.code(code_gen.generate_full_migration_script(ds), language="python")

        st.session_state["current_dataset"] = ds


# ===========================================================================
# Tab 6: Validation
# ===========================================================================

elif tab_choice == "✅ Validation":
    st.title("✅ Phase 8: Data Quality Validation")
    st.markdown("""
    After migrating VSAM records to Delta Lake, validate the data quality.
    **Record count reconciliation** is the critical sign-off gate.
    """)

    if "decoded_records" not in st.session_state:
        st.warning("⚠️ Decode records first in the **Record Decoder** tab, or use a demo dataset below.")
        use_demo = st.button("Use Banking Customer Demo Data")
        if use_demo:
            ds = build_customer_dataset()
            from vsam_delta_platform.decoder.record_decoder import VSAMRecordDecoder
            decoder = VSAMRecordDecoder(ds.copybook)
            from vsam_delta_platform.examples.banking.customer_master import SAMPLE_RECORDS
            records = [decoder.decode_record(r) for r in SAMPLE_RECORDS]
            st.session_state["decoded_records"] = records
            st.session_state["current_dataset"] = ds
            st.rerun()
    else:
        records = st.session_state["decoded_records"]
        dataset = st.session_state.get("current_dataset", build_customer_dataset())

        st.info(f"Validating **{len(records)}** records from dataset: **{dataset.name}**")

        target_count = st.number_input(
            "Expected record count in Delta (for reconciliation)",
            value=len(records),
            min_value=0,
        )

        if st.button("▶ Run Validation", type="primary"):
            engine = ValidationEngine(dataset)
            report = engine.validate(records, target_count=target_count)

            if report.overall_passed:
                st.success("✅ VALIDATION PASSED")
            else:
                st.error("❌ VALIDATION FAILED")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Source Records", f"{report.source_count:,}")
            col2.metric("Target Records", f"{report.target_count:,}")
            col3.metric("Duplicate Keys", report.duplicate_key_count)
            col4.metric("Overall", "PASSED" if report.overall_passed else "FAILED")

            st.markdown("### Validation Results")
            results_df = pd.DataFrame([r.to_dict() for r in report.field_results])
            st.dataframe(results_df, use_container_width=True)

            st.markdown("### Full Validation Report")
            st.code(report.summary, language="text")

            st.markdown("### Generated Spark Validation Code")
            st.code(engine.generate_validation_spark_code(), language="python")


# ===========================================================================
# Tab 7: Lineage
# ===========================================================================

elif tab_choice == "🔗 Lineage":
    st.title("🔗 Phase 9: Data Lineage")
    st.markdown("""
    Data lineage answers **"Where did this data come from?"**
    Critical for regulatory compliance (BCBS 239, GDPR, SOX) and impact analysis.
    """)

    dataset = st.session_state.get("current_dataset", build_customer_dataset())

    engine = LineageEngine()
    doc = engine.generate(dataset)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### Migration Flow Diagram")
        st.markdown(engine.generate_mermaid(doc))
        st.caption("Render at mermaid.live or any Mermaid-compatible viewer")

        st.markdown("### VSAM ↔ Delta Concept Map")
        st.markdown(engine.generate_vsam_concept_map_mermaid())

    with col2:
        st.markdown("### Lineage JSON Document")
        st.json(doc.to_dict())

    if doc.field_lineage:
        st.markdown("### Field-Level Lineage")
        st.markdown(engine.generate_field_lineage_markdown(doc))


# ===========================================================================
# Tab 8: Industry Examples
# ===========================================================================

elif tab_choice == "🏭 Industry Examples":
    st.title("🏭 Industry Migration Examples")

    industry = st.selectbox(
        "Select Industry / Dataset",
        [
            "🏦 Banking — Customer Master (KSDS)",
            "🏦 Banking — Transaction History (ESDS)",
            "🏛️ Insurance — Policy Master (KSDS)",
            "🛒 Retail — Product Catalog (KSDS)",
            "📱 Telecom — Subscriber Master (KSDS + COMP-3)",
            "🚚 Logistics — Shipment Tracking (ESDS)",
        ],
    )

    examples = {
        "🏦 Banking — Customer Master (KSDS)": (
            build_customer_dataset, CUSTOMER_COPYBOOK_TEXT, BANK_CUST_RECORDS, BANK_CUST_EXP
        ),
        "🏦 Banking — Transaction History (ESDS)": (
            build_transaction_dataset, TRANSACTION_COPYBOOK_TEXT, BANK_TRANS_RECORDS, BANK_TRANS_EXP
        ),
        "🏛️ Insurance — Policy Master (KSDS)": (
            build_policy_dataset, POLICY_COPYBOOK_TEXT, [], INS_EXP
        ),
        "🛒 Retail — Product Catalog (KSDS)": (
            build_product_dataset, PRODUCT_COPYBOOK_TEXT, [], RETAIL_EXP
        ),
        "📱 Telecom — Subscriber Master (KSDS + COMP-3)": (
            build_subscriber_dataset, SUBSCRIBER_COPYBOOK_TEXT, [], TELECOM_EXP
        ),
        "🚚 Logistics — Shipment Tracking (ESDS)": (
            build_shipment_dataset, SHIPMENT_COPYBOOK_TEXT, [], LOGISTICS_EXP
        ),
    }

    build_fn, copybook_text, sample_records, explanation = examples[industry]
    dataset = build_fn()

    tab_overview, tab_copybook, tab_schema, tab_records, tab_spark, tab_explain = st.tabs([
        "Overview", "Copybook", "Schema", "Sample Records", "Spark Code", "Learning Notes"
    ])

    with tab_overview:
        st.markdown(f"### {dataset.name}")
        col1, col2, col3 = st.columns(3)
        col1.metric("VSAM Type", dataset.vsam_type.value)
        col2.metric("Record Length", f"{dataset.record_length} bytes")
        col3.metric("Record Count", f"{dataset.record_count:,}")
        st.markdown(f"**Description:** {dataset.description}")
        if dataset.primary_key:
            st.markdown(f"**Primary Key:** `{dataset.primary_key.field_name}` (offset {dataset.primary_key.offset}, length {dataset.primary_key.length})")
        st.markdown(f"**Target Table:** `{dataset.delta_table_name}`")
        st.markdown(f"**Target Location:** `{dataset.delta_location}`")

    with tab_copybook:
        st.code(copybook_text, language="cobol")
        if dataset.copybook:
            parser = CopybookParser()
            summary = parser.schema_summary(dataset.copybook)
            st.dataframe(pd.DataFrame(summary), use_container_width=True)

    with tab_schema:
        if dataset.copybook:
            gen = SparkSchemaGenerator()
            st.code(gen.generate_struct_type_code(dataset.copybook), language="python")
            st.dataframe(pd.DataFrame(gen.generate_field_mapping_table(dataset.copybook)), use_container_width=True)

    with tab_records:
        if sample_records:
            st.markdown("**Raw VSAM records (fixed-width):**")
            for rec in sample_records:
                st.code(rec, language="text")

            if dataset.copybook:
                st.markdown("**Decoded records:**")
                decoder = VSAMRecordDecoder(dataset.copybook)
                decoded = [decoder.decode_record(r) for r in sample_records]
                st.dataframe(pd.DataFrame(decoded), use_container_width=True)
        else:
            st.info("Sample records not included for this dataset. Add them in the examples module.")

    with tab_spark:
        code_gen = DeltaCodeGenerator()
        tab_a, tab_b, tab_c = st.tabs(["Initial Load", "CREATE TABLE", "MERGE"])
        with tab_a:
            st.code(code_gen.generate_initial_load(dataset), language="python")
        with tab_b:
            st.code(code_gen.generate_create_table_sql(dataset), language="sql")
        with tab_c:
            st.code(code_gen.generate_merge_upsert(dataset), language="python")

    with tab_explain:
        st.markdown(explanation)


# ===========================================================================
# Tab 9: Documentation
# ===========================================================================

elif tab_choice == "📄 Documentation":
    st.title("📄 Phase 10: Migration Documentation Generator")
    st.markdown("Automatically generate a complete migration specification document.")

    dataset = st.session_state.get("current_dataset", build_customer_dataset())
    doc_gen = DocumentationGenerator()

    tab_migration, tab_arch = st.tabs(["Migration Document", "Architecture Overview"])

    with tab_migration:
        st.markdown(f"**Generating document for: {dataset.name}**")
        migration_doc = doc_gen.generate_migration_doc(dataset)
        st.markdown(migration_doc)

        st.download_button(
            "⬇ Download as Markdown",
            data=migration_doc,
            file_name=f"{dataset.delta_table_name}_migration_doc.md",
            mime="text/markdown",
        )

    with tab_arch:
        arch_doc = doc_gen.generate_architecture_overview()
        st.markdown(arch_doc)
