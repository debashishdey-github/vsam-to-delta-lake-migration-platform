"""
Phase 5 — Spark Schema Generator
==================================
Apache Spark represents data schemas as StructType objects.  Each field in a
copybook maps to a StructField with an appropriate DataType.

The mapping follows this logic:

  PIC X(n)          → StringType()
  PIC 9(n)          → IntegerType() if n<=9, LongType() if n<=18, DecimalType otherwise
  PIC 9(n)V9(d)     → DecimalType(precision=n+d, scale=d)
  PIC S9(n)         → Same as 9(n) but nullable=True for potential negatives
  PIC 9(n) COMP-3   → DecimalType or LongType depending on size

Why StructType?
---------------
Spark's StructType is the equivalent of a SQL table schema or a JSON schema.
When reading VSAM data, you either:
  a) infer the schema from the copybook (this generator does that), or
  b) read everything as strings and cast later (simpler but less efficient).

Using a proper schema upfront enables:
  - Columnar storage optimisation in Parquet/Delta
  - Predicate pushdown at the reader level
  - Type-safe transformations in Spark SQL
"""

from __future__ import annotations

from typing import List

from vsam_delta_platform.metadata.models import Copybook, CopybookField, FieldStatus, PICType


# ---------------------------------------------------------------------------
# PIC → Spark DataType string mapping
# ---------------------------------------------------------------------------

def _pic_to_spark_type(field: CopybookField) -> str:
    """Return a PySpark DataType expression string for a CopybookField."""
    t = field.pic_type

    if t == PICType.ALPHA:
        return "StringType()"

    if t == PICType.DECIMAL:
        precision = field.length  # total digits (integer + decimal)
        scale = field.decimal_places
        return f"DecimalType({precision}, {scale})"

    if t in (PICType.NUMERIC, PICType.SIGNED):
        digits = field.length
        if digits <= 4:
            return "IntegerType()"
        if digits <= 9:
            return "LongType()"
        return f"DecimalType({digits}, 0)"

    if t == PICType.COMP3:
        # COMP-3 stores two digits per byte; reconstruct digit count
        # ⌊bytes * 2⌋ digits approximately
        approx_digits = field.length * 2 - 1
        if field.decimal_places > 0:
            return f"DecimalType({approx_digits}, {field.decimal_places})"
        if approx_digits <= 9:
            return "LongType()"
        return f"DecimalType({approx_digits}, 0)"

    return "StringType()"


def _pic_to_spark_type_nullable(field: CopybookField) -> bool:
    """
    Fields are generally nullable in Delta Lake unless declared as the VSAM key.
    Signed fields could hold NULL if the source record was all spaces.
    """
    return True


# ---------------------------------------------------------------------------
# Schema generator
# ---------------------------------------------------------------------------

class SparkSchemaGenerator:
    """
    Converts a parsed Copybook into PySpark StructType schema code.

    Why generate code instead of actual StructType objects?
    -------------------------------------------------------
    This is a learning platform — we want users to see the generated code,
    understand it, copy it into their notebooks, and modify it.  A code
    generator is more educational than a runtime StructType object.
    """

    def generate_struct_type_code(self, copybook: Copybook, indent: int = 4) -> str:
        """
        Generate PySpark StructType code from a Copybook.

        Returns a string that can be pasted into a PySpark notebook or script.
        """
        pad = " " * indent
        lines = [
            "from pyspark.sql.types import (",
            f"{pad}StructType, StructField,",
            f"{pad}StringType, IntegerType, LongType, DecimalType",
            ")",
            "",
            "# Auto-generated from COBOL copybook",
            f"# Copybook: {copybook.name}",
            f"# Record:   {copybook.record_name}",
            f"# Length:   {copybook.record_length} bytes",
            "",
            f"{copybook.record_name.lower()}_schema = StructType([",
        ]

        active_fields = [f for f in copybook.fields if f.status == FieldStatus.ACTIVE]
        for i, field in enumerate(active_fields):
            spark_type = _pic_to_spark_type(field)
            nullable = _pic_to_spark_type_nullable(field)
            comma = "," if i < len(active_fields) - 1 else ""
            comment = f"  # PIC {field.pic_type.value} len={field.length}"
            if field.decimal_places:
                comment += f" dec={field.decimal_places}"
            lines.append(
                f"{pad}StructField(\"{field.name.lower()}\", {spark_type}, {nullable}){comma}{comment}"
            )

        lines.append("])")
        return "\n".join(lines)

    def generate_dataframe_read_code(self, copybook: Copybook, file_path: str = "/data/vsam_extract.txt") -> str:
        """
        Generate PySpark code to read the flat VSAM extract file using the schema.

        The VSAM unload file is a fixed-width text file; we read it with
        spark.read.text() and then use substr() to extract each field.
        This is the most transparent approach for learning — students can see
        exactly which bytes map to which columns.
        """
        schema_var = f"{copybook.record_name.lower()}_schema"
        active_fields = [f for f in copybook.fields if f.status == FieldStatus.ACTIVE]

        lines = [
            "# Step 1: Read the fixed-width VSAM extract file",
            f'raw_df = spark.read.text("{file_path}")',
            "",
            "# Step 2: Extract each field using its byte offset and length",
            "# substr(start, length) — PySpark substr is 1-based!",
            "from pyspark.sql import functions as F",
            "from pyspark.sql.types import DecimalType",
            "",
            "parsed_df = raw_df.select(",
        ]

        for i, field in enumerate(active_fields):
            start = field.offset + 1  # 1-based for PySpark substr
            length = field.length
            col_name = field.name.lower()
            spark_type = _pic_to_spark_type(field)
            comma = "," if i < len(active_fields) - 1 else ""

            if field.pic_type == PICType.ALPHA:
                expr = f'    F.trim(F.substr("value", {start}, {length})).alias("{col_name}"){comma}'
            elif field.pic_type in (PICType.NUMERIC, PICType.SIGNED, PICType.COMP3):
                if "Integer" in spark_type:
                    expr = f'    F.substr("value", {start}, {length}).cast("integer").alias("{col_name}"){comma}'
                elif "Long" in spark_type:
                    expr = f'    F.substr("value", {start}, {length}).cast("long").alias("{col_name}"){comma}'
                else:
                    expr = f'    F.substr("value", {start}, {length}).cast({spark_type}).alias("{col_name}"){comma}'
            elif field.pic_type == PICType.DECIMAL:
                # Insert implied decimal point before casting
                dec = field.decimal_places
                int_len = length - dec
                expr = (
                    f'    F.concat(\n'
                    f'        F.substr("value", {start}, {int_len}),\n'
                    f'        F.lit("."),\n'
                    f'        F.substr("value", {start + int_len}, {dec})\n'
                    f'    ).cast({spark_type}).alias("{col_name}"){comma}'
                )
            else:
                expr = f'    F.substr("value", {start}, {length}).alias("{col_name}"){comma}'

            lines.append(expr)

        lines.append(")")
        return "\n".join(lines)

    def generate_field_mapping_table(self, copybook: Copybook) -> List[dict]:
        """Return a list of dicts showing the copybook → Spark mapping for display."""
        active_fields = [f for f in copybook.fields if f.status == FieldStatus.ACTIVE]
        rows = []
        for field in active_fields:
            rows.append({
                "COBOL Field": field.name,
                "PIC Clause": field.pic_type.value.upper(),
                "Byte Length": field.length,
                "Decimal Places": field.decimal_places,
                "Byte Offset": f"{field.offset}–{field.offset + field.length - 1}",
                "Spark Type": _pic_to_spark_type(field),
            })
        return rows


# Convenience: need PICType imported for generate_dataframe_read_code
from vsam_delta_platform.metadata.models import PICType  # noqa: E402
