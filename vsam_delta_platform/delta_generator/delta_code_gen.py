"""
Phase 6 — Delta Lake Code Generator
=====================================
Delta Lake is an open-source storage format built on Parquet that adds:

  1. ACID transactions        — writes are atomic; readers always see a consistent snapshot
  2. Schema enforcement       — Delta rejects writes with unexpected columns or types
  3. Schema evolution         — you can ADD columns safely with ALTER TABLE
  4. Time travel              — every write creates a versioned snapshot; query any version
  5. Audit log                — the _delta_log/ folder is a JSON transaction log (like a WAL)
  6. MERGE / UPSERT           — efficient upsert without full table rewrites
  7. Optimised file layout    — Z-ORDER, OPTIMIZE compact small Parquet files

VSAM → Delta Lake concept mapping
-----------------------------------
  VSAM KSDS              ↔  Delta Table with primary key column (Z-ORDER by key)
  VSAM ESDS              ↔  Append-only Delta Table (no MERGE, INSERT only)
  VSAM RRDS              ↔  Delta Table with row_number integer column as surrogate key
  VSAM Copybook          ↔  Delta schema (StructType)
  VSAM REPRO unload      ↔  Initial OVERWRITE write
  VSAM KSDS UPDATE       ↔  Delta MERGE (matched UPDATE, not-matched INSERT)
  VSAM KSDS DELETE       ↔  Delta MERGE (matched DELETE)
  ICF Catalog entry      ↔  Hive Metastore / Unity Catalog table registration
"""

from __future__ import annotations

from typing import List, Optional

from vsam_delta_platform.metadata.models import Copybook, CopybookField, FieldStatus, VSAMDataset, VSAMType


# ---------------------------------------------------------------------------
# Delta Lake write code generator
# ---------------------------------------------------------------------------

class DeltaCodeGenerator:
    """
    Generates PySpark + Delta Lake code for the migration of a VSAM dataset.

    All methods return code as a string intended to be displayed to the user,
    copied into a notebook, or written to a .py script.
    """

    # ------------------------------------------------------------------
    # Core write code
    # ------------------------------------------------------------------

    def generate_initial_load(self, dataset: VSAMDataset) -> str:
        """
        Generate the initial full-load (OVERWRITE) write.
        This is the equivalent of a REPRO from VSAM to flat file followed by
        a bulk INSERT into the target table.

        For a KSDS the first write is always OVERWRITE; subsequent runs use MERGE.
        For an ESDS it is always APPEND.
        """
        tbl = dataset.delta_table_name
        loc = dataset.delta_location
        mode = "append" if dataset.vsam_type == VSAMType.ESDS else "overwrite"

        lines = [
            f"# -------------------------------------------------------",
            f"# Initial Load: {dataset.name} → {tbl}",
            f"# VSAM Type   : {dataset.vsam_type.value}",
            f"# Mode        : {mode.upper()}",
            f"# -------------------------------------------------------",
            "",
            f"# 'parsed_df' was built by the Spark schema generator step",
            f"(",
            f"    parsed_df",
            f"    .write",
            f'    .format("delta")',
            f'    .mode("{mode}")',
        ]

        if dataset.primary_key and dataset.vsam_type == VSAMType.KSDS:
            key = dataset.primary_key.field_name.lower()
            lines.append(f'    .option("overwriteSchema", "true")')

        lines += [
            f'    .save("{loc}")',
            ")",
            "",
            f"print(f\"Written to Delta Lake: {loc}\")",
        ]
        return "\n".join(lines)

    def generate_create_table_sql(self, dataset: VSAMDataset) -> str:
        """
        Generate the SQL DDL to register the Delta table in the metastore.
        This makes it queryable via Spark SQL, Databricks SQL, or Athena.
        """
        tbl = dataset.delta_table_name
        loc = dataset.delta_location

        comment_map = {
            VSAMType.KSDS: f"Migrated from VSAM KSDS {dataset.name}. Primary key: {dataset.primary_key.field_name if dataset.primary_key else 'none'}.",
            VSAMType.ESDS: f"Migrated from VSAM ESDS {dataset.name}. Append-only sequential dataset.",
            VSAMType.RRDS: f"Migrated from VSAM RRDS {dataset.name}. Original slot-addressed with row_number as surrogate key.",
        }
        comment = comment_map.get(dataset.vsam_type, "Migrated VSAM dataset.")

        lines = [
            f"-- Register the Delta table in the Hive/Unity Catalog metastore",
            f"-- After registration, the table is queryable via Spark SQL.",
            "",
            f"CREATE TABLE IF NOT EXISTS {tbl}",
            f"USING DELTA",
            f"LOCATION '{loc}'",
            f"COMMENT '{comment}';",
        ]

        if dataset.copybook:
            active_fields = [f for f in dataset.copybook.fields if f.status == FieldStatus.ACTIVE]
            if active_fields:
                col_lines = []
                for f in active_fields:
                    col_lines.append(f"  -- {f.name}: {f.pic_type.value}, {f.length} bytes, offset {f.offset}")
                lines += ["", "-- Column reference (from copybook):"] + col_lines

        return "\n".join(lines)

    def generate_schema_check(self, dataset: VSAMDataset) -> str:
        """Generate code to inspect the Delta table schema and version history."""
        tbl = dataset.delta_table_name
        loc = dataset.delta_location

        return "\n".join([
            f"# -------------------------------------------------------",
            f"# Inspect the migrated Delta table",
            f"# -------------------------------------------------------",
            "",
            f"from delta.tables import DeltaTable",
            "",
            f"# Load the table object",
            f"dt = DeltaTable.forPath(spark, \"{loc}\")",
            "",
            f"# Show table schema",
            f"dt.toDF().printSchema()",
            "",
            f"# Show first 10 records",
            f"spark.table(\"{tbl}\").show(10, truncate=False)",
            "",
            f"# Show Delta transaction history (time travel audit log)",
            f"dt.history().select(",
            f"    \"version\", \"timestamp\", \"operation\", \"operationMetrics\"",
            f").show(truncate=False)",
            "",
            f"# Count records",
            f'print(f"Record count: {{spark.table(\"{tbl}\").count()}}")',
        ])

    def generate_merge_upsert(self, dataset: VSAMDataset) -> str:
        """
        Generate a MERGE statement for incremental loads.
        This is the Delta Lake equivalent of the VSAM KSDS record update operation.

        VSAM KSDS UPDATE → Delta MERGE (matchedUpdate)
        VSAM KSDS INSERT → Delta MERGE (notMatchedInsert)
        VSAM KSDS DELETE → Delta MERGE (matchedDelete)

        In CDC-based incremental loads, a change record includes an operation flag:
          'U' = UPDATE, 'I' = INSERT, 'D' = DELETE
        """
        if dataset.vsam_type != VSAMType.KSDS or not dataset.primary_key:
            return (
                f"# MERGE is only applicable to KSDS datasets with a primary key.\n"
                f"# {dataset.name} is {dataset.vsam_type.value} — use append mode instead.\n"
            )

        key = dataset.primary_key.field_name.lower()
        tbl = dataset.delta_table_name
        loc = dataset.delta_location

        if dataset.copybook:
            active_fields = [f for f in dataset.copybook.fields if f.status == FieldStatus.ACTIVE]
            non_key_fields = [f for f in active_fields if f.name.upper() != dataset.primary_key.field_name.upper()]
            update_exprs = {f.name.lower(): f"source.{f.name.lower()}" for f in non_key_fields}
        else:
            update_exprs = {"<column>": "source.<column>"}

        update_str = ",\n            ".join(
            f'"{k}": "{v}"' for k, v in list(update_exprs.items())[:5]
        )
        if len(update_exprs) > 5:
            update_str += f'\n            # ... {len(update_exprs) - 5} more columns'

        insert_star = "source.*"  # shorthand for INSERT all columns

        return "\n".join([
            f"# -------------------------------------------------------",
            f"# Incremental Load (MERGE / UPSERT)",
            f"# Source: VSAM KSDS {dataset.name}",
            f"# Key:    {key}",
            f"# -------------------------------------------------------",
            "",
            f"from delta.tables import DeltaTable",
            "",
            f"# Load the existing Delta table",
            f"target = DeltaTable.forPath(spark, \"{loc}\")",
            "",
            f"# 'incremental_df' contains the new/changed records extracted",
            f"# from the VSAM change log or a differential REPRO.",
            f"# It must include an 'operation' column: I=Insert, U=Update, D=Delete",
            "",
            f"(",
            f"    target.alias(\"target\")",
            f"    .merge(",
            f"        incremental_df.alias(\"source\"),",
            f"        \"target.{key} = source.{key}\"",
            f"    )",
            f"    .whenMatchedDelete(condition=\"source.operation = 'D'\")",
            f"    .whenMatchedUpdate(",
            f"        condition=\"source.operation = 'U'\",",
            f"        set={{",
            f"            {update_str}",
            f"        }}",
            f"    )",
            f"    .whenNotMatchedInsert(",
            f"        condition=\"source.operation = 'I'\",",
            f"        values={insert_star!r}",
            f"    )",
            f"    .execute()",
            f")",
        ])

    def generate_optimize_and_zorder(self, dataset: VSAMDataset) -> str:
        """
        Generate OPTIMIZE + Z-ORDER command for the Delta table.

        Z-ORDER clusters data by the key column so range scans and equality
        lookups are fast — important for KSDS-like access patterns.

        OPTIMIZE also compacts small Parquet files (the "small file problem"
        that affects streaming and incremental loads).
        """
        tbl = dataset.delta_table_name
        key_col = ""
        if dataset.primary_key:
            key_col = dataset.primary_key.field_name.lower()

        lines = [
            f"-- Optimise the Delta table layout",
            f"-- OPTIMIZE compacts small Parquet files into larger ones.",
            f"-- Z-ORDER clusters rows by the key column for fast lookups.",
            f"-- Run this after the initial load and periodically after bulk updates.",
            "",
            f"OPTIMIZE {tbl}",
        ]
        if key_col:
            lines.append(f"ZORDER BY ({key_col});")
        else:
            lines[-1] += ";"

        lines += [
            "",
            f"-- View the result of the optimisation",
            f"DESCRIBE DETAIL {tbl};",
        ]
        return "\n".join(lines)

    def generate_time_travel_query(self, dataset: VSAMDataset) -> str:
        """
        Generate example time-travel queries.

        Delta Lake keeps every historical version of the table in the
        _delta_log/ directory.  You can query any version using VERSION AS OF
        or TIMESTAMP AS OF — a capability VSAM simply does not have.
        """
        tbl = dataset.delta_table_name
        return "\n".join([
            f"-- -------------------------------------------------------",
            f"-- Time Travel: Read historical versions of {tbl}",
            f"-- -------------------------------------------------------",
            "",
            f"-- Query the table as it was at version 0 (initial load)",
            f"SELECT * FROM {tbl} VERSION AS OF 0 LIMIT 10;",
            "",
            f"-- Query the table as it was yesterday",
            f"SELECT * FROM {tbl}",
            f"TIMESTAMP AS OF date_sub(current_timestamp(), 1)",
            f"LIMIT 10;",
            "",
            f"-- Compare current vs. version 0 (see what changed)",
            f"SELECT 'current' AS version, COUNT(*) AS record_count FROM {tbl}",
            f"UNION ALL",
            f"SELECT 'v0', COUNT(*) FROM {tbl} VERSION AS OF 0;",
        ])

    def generate_full_migration_script(self, dataset: VSAMDataset) -> str:
        """
        Assemble a complete, runnable migration script for one VSAM dataset.
        """
        sections = [
            "# ================================================================",
            f"# VSAM → Delta Lake Migration Script",
            f"# Source : {dataset.name}  ({dataset.vsam_type.value})",
            f"# Target : {dataset.delta_table_name}",
            f"# Location: {dataset.delta_location}",
            "# ================================================================",
            "",
            "# Prerequisites:",
            "#   pip install delta-spark pyspark",
            "#   Databricks Runtime 12+ already includes both.",
            "",
            "from pyspark.sql import SparkSession",
            "from pyspark.sql.types import *",
            "from pyspark.sql import functions as F",
            "",
            'spark = (',
            '    SparkSession.builder',
            '    .appName("VSAM_Delta_Migration")',
            '    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")',
            '    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")',
            '    .getOrCreate()',
            ')',
            "",
        ]

        # Include schema code stub
        if dataset.copybook:
            sections += [
                "# --- Schema (from copybook) ---",
                f"# Copybook: {dataset.copybook.name}",
                "# (Paste generated StructType code here)",
                "",
            ]

        sections += [
            "# --- Step 1: Read the VSAM extract file ---",
            self.generate_initial_load(dataset),
            "",
            "# --- Step 2: Register in metastore ---",
            self.generate_create_table_sql(dataset),
            "",
            "# --- Step 3: Inspect the table ---",
            self.generate_schema_check(dataset),
            "",
            "# --- Step 4: Optimise ---",
            self.generate_optimize_and_zorder(dataset),
        ]
        return "\n".join(sections)
