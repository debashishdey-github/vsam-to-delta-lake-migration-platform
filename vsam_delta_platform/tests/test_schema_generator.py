"""
Tests for the Spark Schema Generator (Phase 5)
================================================
Verify that copybook fields are converted to correct PySpark DataType expressions.
"""

import pytest
from vsam_delta_platform.schema_generator.spark_schema import SparkSchemaGenerator
from vsam_delta_platform.metadata.models import Copybook, CopybookField, PICType


def make_copybook(*fields) -> Copybook:
    cb = Copybook(name="TEST", record_name="TEST-REC", fields=list(fields))
    offset = 0
    for f in cb.fields:
        f.offset = offset
        offset += f.length
    cb.record_length = offset
    return cb


class TestSparkTypeMapping:
    @pytest.fixture
    def gen(self):
        return SparkSchemaGenerator()

    def test_alpha_maps_to_string(self, gen):
        cb = make_copybook(CopybookField("NAME", 5, PICType.ALPHA, 30, 0, 0))
        code = gen.generate_struct_type_code(cb)
        assert "StringType()" in code

    def test_numeric_small_maps_to_integer(self, gen):
        cb = make_copybook(CopybookField("COUNT", 5, PICType.NUMERIC, 4, 0, 0))
        code = gen.generate_struct_type_code(cb)
        assert "IntegerType()" in code

    def test_numeric_large_maps_to_long(self, gen):
        cb = make_copybook(CopybookField("BIG-NUM", 5, PICType.NUMERIC, 9, 0, 0))
        code = gen.generate_struct_type_code(cb)
        assert "LongType()" in code

    def test_decimal_maps_to_decimal_type(self, gen):
        cb = make_copybook(CopybookField("BALANCE", 5, PICType.DECIMAL, 9, 2, 0))
        code = gen.generate_struct_type_code(cb)
        assert "DecimalType(9, 2)" in code

    def test_field_names_lowercased(self, gen):
        cb = make_copybook(CopybookField("CUSTOMER-ID", 5, PICType.ALPHA, 10, 0, 0))
        code = gen.generate_struct_type_code(cb)
        assert '"customer-id"' in code

    def test_struct_type_code_has_from_pyspark(self, gen):
        cb = make_copybook(CopybookField("ID", 5, PICType.ALPHA, 5, 0, 0))
        code = gen.generate_struct_type_code(cb)
        assert "from pyspark.sql.types import" in code
        assert "StructType" in code
        assert "StructField" in code

    def test_field_mapping_table(self, gen):
        cb = make_copybook(
            CopybookField("ID", 5, PICType.ALPHA, 5, 0, 0),
            CopybookField("AMT", 5, PICType.DECIMAL, 9, 2, 5),
        )
        table = gen.generate_field_mapping_table(cb)
        assert len(table) == 2
        assert table[0]["COBOL Field"] == "ID"
        assert table[1]["Spark Type"] == "DecimalType(9, 2)"


class TestDataframeReadCodeGeneration:
    @pytest.fixture
    def gen(self):
        return SparkSchemaGenerator()

    def test_read_code_uses_substr(self, gen):
        cb = make_copybook(CopybookField("NAME", 5, PICType.ALPHA, 20, 0, 0))
        code = gen.generate_dataframe_read_code(cb)
        assert "substr" in code.lower() or "substr" in code

    def test_read_code_mentions_file_path(self, gen):
        cb = make_copybook(CopybookField("ID", 5, PICType.ALPHA, 5, 0, 0))
        code = gen.generate_dataframe_read_code(cb, "/custom/path.txt")
        assert "/custom/path.txt" in code
