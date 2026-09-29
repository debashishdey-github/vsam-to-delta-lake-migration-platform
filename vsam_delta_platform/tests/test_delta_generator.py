"""
Tests for the Delta Lake Code Generator (Phase 6)
===================================================
Verify that generated Spark/Delta code strings are syntactically
meaningful and contain the expected elements.
"""

import pytest
from vsam_delta_platform.delta_generator.delta_code_gen import DeltaCodeGenerator
from vsam_delta_platform.metadata.models import (
    Copybook, CopybookField, PICType,
    VSAMDataset, VSAMKey, VSAMType
)


def make_ksds_dataset() -> VSAMDataset:
    fields = [CopybookField("CUSTOMER-ID", 5, PICType.ALPHA, 10, 0, 0)]
    cb = Copybook("TEST", "TEST-REC", fields=fields, record_length=10)
    key = VSAMKey("CUSTOMER-ID", 0, 10)
    ds = VSAMDataset("PROD.CUSTOMER.KSDS", VSAMType.KSDS, 10, cb, key, 1000)
    ds.target_table = "customer_delta"
    ds.target_location = "/delta/customer"
    return ds


def make_esds_dataset() -> VSAMDataset:
    ds = VSAMDataset("PROD.TRANS.ESDS", VSAMType.ESDS, 80, None, None, 50000)
    ds.target_table = "transaction_history"
    ds.target_location = "/delta/transactions"
    return ds


class TestInitialLoad:
    @pytest.fixture
    def gen(self):
        return DeltaCodeGenerator()

    def test_ksds_uses_overwrite(self, gen):
        ds = make_ksds_dataset()
        code = gen.generate_initial_load(ds)
        assert '"overwrite"' in code

    def test_esds_uses_append(self, gen):
        ds = make_esds_dataset()
        code = gen.generate_initial_load(ds)
        assert '"append"' in code

    def test_code_uses_delta_format(self, gen):
        ds = make_ksds_dataset()
        code = gen.generate_initial_load(ds)
        assert '"delta"' in code

    def test_code_references_target_location(self, gen):
        ds = make_ksds_dataset()
        code = gen.generate_initial_load(ds)
        assert "/delta/customer" in code


class TestCreateTableSQL:
    @pytest.fixture
    def gen(self):
        return DeltaCodeGenerator()

    def test_sql_uses_delta(self, gen):
        ds = make_ksds_dataset()
        sql = gen.generate_create_table_sql(ds)
        assert "USING DELTA" in sql

    def test_sql_has_table_name(self, gen):
        ds = make_ksds_dataset()
        sql = gen.generate_create_table_sql(ds)
        assert "customer_delta" in sql

    def test_sql_has_location(self, gen):
        ds = make_ksds_dataset()
        sql = gen.generate_create_table_sql(ds)
        assert "/delta/customer" in sql


class TestMergeUpsert:
    @pytest.fixture
    def gen(self):
        return DeltaCodeGenerator()

    def test_ksds_merge_contains_merge_keyword(self, gen):
        ds = make_ksds_dataset()
        code = gen.generate_merge_upsert(ds)
        assert ".merge(" in code

    def test_ksds_merge_references_key(self, gen):
        ds = make_ksds_dataset()
        code = gen.generate_merge_upsert(ds)
        assert "customer-id" in code.lower() or "customer_id" in code.lower()

    def test_esds_merge_returns_not_applicable(self, gen):
        ds = make_esds_dataset()
        code = gen.generate_merge_upsert(ds)
        assert "MERGE is only applicable" in code


class TestOptimize:
    @pytest.fixture
    def gen(self):
        return DeltaCodeGenerator()

    def test_optimize_sql_present(self, gen):
        ds = make_ksds_dataset()
        sql = gen.generate_optimize_and_zorder(ds)
        assert "OPTIMIZE" in sql

    def test_zorder_with_key(self, gen):
        ds = make_ksds_dataset()
        sql = gen.generate_optimize_and_zorder(ds)
        assert "ZORDER BY" in sql


class TestFullScript:
    def test_full_script_has_spark_session(self):
        gen = DeltaCodeGenerator()
        ds = make_ksds_dataset()
        script = gen.generate_full_migration_script(ds)
        assert "SparkSession" in script
        assert "delta" in script.lower()
