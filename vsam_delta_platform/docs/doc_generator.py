"""
Phase 10 — Documentation Generator
=====================================
Generates human-readable migration documentation for each VSAM dataset.

In a real migration project, documentation is a major deliverable:
  - Functional spec  : what the source data contains, business rules
  - Technical spec   : copybook, schema, transformation logic
  - Migration runbook: step-by-step execution instructions
  - Sign-off report  : validation results, record counts, business sign-off

This generator produces all of the above automatically from the metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from vsam_delta_platform.metadata.models import VSAMDataset, VSAMType
from vsam_delta_platform.metadata.models import FieldStatus


VSAM_TYPE_DESCRIPTIONS = {
    VSAMType.KSDS: (
        "Key Sequenced Data Set (KSDS) — The most common VSAM type, similar to a B-tree "
        "indexed table. Records are stored in key sequence and can be accessed randomly "
        "by key value or sequentially in key order. Ideal for master files where records "
        "are frequently looked up by ID (e.g., CUSTOMER-ID, ACCOUNT-NUMBER)."
    ),
    VSAMType.ESDS: (
        "Entry Sequenced Data Set (ESDS) — Records are stored in arrival order and cannot "
        "be reorganised. This is the VSAM equivalent of an append-only log. Access is "
        "sequential or by Relative Byte Address (RBA). Ideal for transaction history, "
        "audit trails, and event logs."
    ),
    VSAMType.RRDS: (
        "Relative Record Data Set (RRDS) — Records occupy fixed-size slots addressed by "
        "a Relative Record Number (RRN, starting at 1). Slots can be empty. This is similar "
        "to an array where you can access slot N directly. Used for datasets with predictable "
        "record positions."
    ),
}

DELTA_STRATEGY_DESCRIPTIONS = {
    VSAMType.KSDS: (
        "Delta Table with primary key Z-ORDER. Use OVERWRITE for initial load, MERGE for "
        "incremental updates. Enable OPTIMIZE and Z-ORDER on the key column for fast lookups. "
        "This matches the KSDS random-access-by-key pattern."
    ),
    VSAMType.ESDS: (
        "Append-only Delta Table. Write mode is always APPEND — never OVERWRITE. "
        "Partitioned by a date column derived from the record timestamp or arrival time. "
        "Query patterns are sequential scans by date range, so partition pruning is key."
    ),
    VSAMType.RRDS: (
        "Delta Table with a row_number surrogate key. The RRN becomes an integer column. "
        "Empty slots are represented as NULL rows. OPTIMIZE periodically to compact files."
    ),
}


class DocumentationGenerator:
    """
    Generates migration documentation for a VSAM → Delta migration.
    """

    def generate_migration_doc(self, dataset: VSAMDataset) -> str:
        """
        Generate a full markdown migration document for one dataset.
        """
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        cb = dataset.copybook
        key = dataset.primary_key

        lines = [
            f"# Migration Document: {dataset.name}",
            f"",
            f"**Generated:** {now}  ",
            f"**Status:** Draft  ",
            f"**Author:** VSAM → Delta Lake Migration Platform  ",
            f"",
            "---",
            "",
            "## 1. Source Dataset",
            "",
            f"| Attribute | Value |",
            f"|---|---|",
            f"| Dataset Name | `{dataset.name}` |",
            f"| VSAM Type | **{dataset.vsam_type.value}** |",
            f"| Record Length | {dataset.record_length} bytes |",
            f"| Record Count | {dataset.record_count:,} |",
            f"| Description | {dataset.description or 'N/A'} |",
            f"| Primary Key Field | {key.field_name if key else 'None (ESDS/RRDS)'} |",
            "",
            "### What is a VSAM " + dataset.vsam_type.value + "?",
            "",
            VSAM_TYPE_DESCRIPTIONS.get(dataset.vsam_type, ""),
            "",
        ]

        # Copybook section
        if cb:
            lines += [
                "---",
                "",
                "## 2. Record Layout (Copybook)",
                "",
                f"**Copybook:** `{cb.name}`  ",
                f"**Record Name:** `{cb.record_name}`  ",
                f"**Total Record Length:** {cb.record_length} bytes  ",
                "",
                "| # | Field Name | PIC Type | Length | Dec | Offset | Spark Type |",
                "|---|---|---|---|---|---|---|",
            ]
            active_fields = [f for f in cb.fields if f.status == FieldStatus.ACTIVE]
            for i, fld in enumerate(active_fields, 1):
                lines.append(
                    f"| {i} | `{fld.name}` | {fld.pic_type.value.upper()} "
                    f"| {fld.length} | {fld.decimal_places} "
                    f"| {fld.offset}–{fld.offset + fld.length - 1} "
                    f"| {fld.spark_type()} |"
                )
            lines.append("")

            if cb.raw_text:
                lines += [
                    "### Raw Copybook",
                    "```cobol",
                    cb.raw_text.strip(),
                    "```",
                    "",
                ]

        # Target section
        lines += [
            "---",
            "",
            "## 3. Target: Delta Lake",
            "",
            f"| Attribute | Value |",
            f"|---|---|",
            f"| Delta Table Name | `{dataset.delta_table_name}` |",
            f"| Storage Location | `{dataset.delta_location}` |",
            f"| Format | Delta Lake (Parquet + Transaction Log) |",
            f"| ACID | Yes |",
            f"| Time Travel | Yes |",
            "",
            "### Migration Strategy",
            "",
            DELTA_STRATEGY_DESCRIPTIONS.get(dataset.vsam_type, ""),
            "",
        ]

        # Migration steps
        lines += [
            "---",
            "",
            "## 4. Migration Steps",
            "",
            "```",
            "Step 1:  VSAM REPRO → Sequential flat file (on z/OS via IDCAMS)",
            "Step 2:  Transfer flat file from z/OS to Linux/cloud (FTP / SFTP)",
            "Step 3:  EBCDIC → ASCII conversion (iconv -f EBCDIC-CP-US -t UTF-8)",
            "Step 4:  Parse copybook → generate Spark StructType schema",
            "Step 5:  spark.read.text() + substr() to extract fields",
            "Step 6:  Write DataFrame as Delta table (overwrite / append)",
            "Step 7:  Register table in Hive/Unity Catalog metastore",
            "Step 8:  Run OPTIMIZE + ZORDER (for KSDS targets)",
            "Step 9:  Execute validation: record count, null check, dup key check",
            "Step 10: Produce sign-off report",
            "```",
            "",
        ]

        # VSAM → Delta concept map
        lines += [
            "---",
            "",
            "## 5. VSAM → Delta Lake Concept Mapping",
            "",
            "| VSAM Concept | Delta Lake Equivalent | Notes |",
            "|---|---|---|",
            "| KSDS Dataset | Delta Table (Z-ORDERed) | Primary key access pattern preserved |",
            "| ESDS Dataset | Append-only Delta Table | Arrival order preserved via partition |",
            "| RRDS Dataset | Delta Table + row_number | RRN → integer surrogate key |",
            "| Copybook | StructType schema | Field names, types, lengths |",
            "| Fixed-width record | Parquet row | Columnar, compressed |",
            "| ICF Catalog | Hive/Unity Metastore | Table registration |",
            "| VSAM KSDS UPDATE | Delta MERGE (matchedUpdate) | ACID guaranteed |",
            "| VSAM KSDS INSERT | Delta MERGE (notMatchedInsert) | |",
            "| VSAM KSDS DELETE | Delta MERGE (matchedDelete) | Soft-delete option |",
            "| LISTCAT count | spark.table().count() | Reconciliation gate |",
            "| No history | Time travel (VERSION AS OF) | New capability |",
            "",
        ]

        # Sign-off table
        lines += [
            "---",
            "",
            "## 6. Sign-Off Checklist",
            "",
            "| Item | Status |",
            "|---|---|",
            "| Copybook parsed correctly | ☐ |",
            "| Schema matches business requirements | ☐ |",
            "| Record count reconciled (VSAM = Flat = Delta) | ☐ |",
            "| No duplicate primary keys | ☐ |",
            "| Numeric fields validated | ☐ |",
            "| Null analysis reviewed | ☐ |",
            "| Table registered in metastore | ☐ |",
            "| OPTIMIZE executed | ☐ |",
            "| Business sign-off | ☐ |",
            "| Source system decommission approved | ☐ |",
            "",
        ]

        return "\n".join(lines)

    def generate_architecture_overview(self) -> str:
        """Generate a platform-level architecture document."""
        return "\n".join([
            "# VSAM → Delta Lake Migration Platform — Architecture",
            "",
            "## System Overview",
            "",
            "```",
            "┌──────────────────────────────────────────────────────────┐",
            "│                  IBM z/OS Mainframe                      │",
            "│   ┌─────────────┐  ┌─────────────┐  ┌──────────────┐   │",
            "│   │  VSAM KSDS  │  │  VSAM ESDS  │  │  VSAM RRDS  │   │",
            "│   └──────┬──────┘  └──────┬──────┘  └──────┬───────┘   │",
            "│          │ REPRO          │                  │           │",
            "│   ┌──────▼──────────────────────────────────▼───────┐   │",
            "│   │            Sequential Flat File                  │   │",
            "│   │         (Fixed-width, EBCDIC or ASCII)           │   │",
            "│   └──────────────────────┬───────────────────────────┘   │",
            "└─────────────────────────┼────────────────────────────────┘",
            "                          │ SFTP / AWS DataSync / MFT",
            "┌─────────────────────────▼────────────────────────────────┐",
            "│                   Cloud / On-Premises                     │",
            "│   ┌───────────────────────────────────────────────────┐  │",
            "│   │         VSAM → Delta Lake Migration Platform       │  │",
            "│   │                                                    │  │",
            "│   │  ┌────────────┐    ┌────────────┐                 │  │",
            "│   │  │  Copybook  │───▶│  Schema    │                 │  │",
            "│   │  │  Parser    │    │  Generator │                 │  │",
            "│   │  └────────────┘    └─────┬──────┘                │  │",
            "│   │                          │                         │  │",
            "│   │  ┌────────────┐    ┌─────▼──────┐                 │  │",
            "│   │  │  Record    │───▶│   Spark    │                 │  │",
            "│   │  │  Decoder   │    │ DataFrame  │                 │  │",
            "│   │  └────────────┘    └─────┬──────┘                │  │",
            "│   │                          │                         │  │",
            "│   │  ┌────────────┐    ┌─────▼──────┐                 │  │",
            "│   │  │ Validation │    │   Delta    │                 │  │",
            "│   │  │  Engine    │    │  Writer    │                 │  │",
            "│   │  └────────────┘    └─────┬──────┘                │  │",
            "│   │                          │                         │  │",
            "│   │  ┌────────────┐    ┌─────▼──────┐                 │  │",
            "│   │  │  Lineage   │    │   Delta    │                 │  │",
            "│   │  │  Engine    │    │   Table    │                 │  │",
            "│   │  └────────────┘    └────────────┘                 │  │",
            "│   └───────────────────────────────────────────────────┘  │",
            "│                                                           │",
            "│   ┌─────────────────────────────────────────────────┐    │",
            "│   │              Streamlit UI                        │    │",
            "│   │   Upload Copybook → Parse → Schema → Code →      │    │",
            "│   │              Validate → Report                   │    │",
            "│   └─────────────────────────────────────────────────┘    │",
            "└──────────────────────────────────────────────────────────┘",
            "```",
            "",
            "## Module Responsibilities",
            "",
            "| Module | Input | Output | Phase |",
            "|---|---|---|---|",
            "| `parser/copybook_parser.py` | COBOL copybook text | `Copybook` object | 2 |",
            "| `metadata/models.py` | — | Domain model classes | 3 |",
            "| `decoder/record_decoder.py` | Flat file + Copybook | Python dicts | 4 |",
            "| `schema_generator/spark_schema.py` | Copybook | PySpark code string | 5 |",
            "| `delta_generator/delta_code_gen.py` | VSAMDataset | Spark/SQL code string | 6 |",
            "| `validation/validator.py` | Decoded records | ValidationReport | 8 |",
            "| `lineage/lineage_engine.py` | VSAMDataset | Mermaid + JSON lineage | 9 |",
            "| `docs/doc_generator.py` | VSAMDataset | Markdown documentation | 10 |",
            "| `ui/app.py` | Browser input | All of the above rendered in Streamlit | UI |",
        ])
