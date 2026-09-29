"""
Tests for the Validation Engine (Phase 8)
===========================================
Validate that the engine correctly checks record counts, duplicate keys,
null values, and numeric fields.
"""

import pytest
from vsam_delta_platform.validation.validator import ValidationEngine
from vsam_delta_platform.metadata.models import (
    Copybook, CopybookField, PICType, VSAMDataset, VSAMKey, VSAMType
)


def make_dataset_with_key() -> VSAMDataset:
    fields = [
        CopybookField("CUSTOMER-ID", 5, PICType.ALPHA,   6, 0, 0),
        CopybookField("NAME",        5, PICType.ALPHA,  20, 0, 6),
        CopybookField("BALANCE",     5, PICType.DECIMAL, 7, 2, 26),
    ]
    cb = Copybook("TEST", "CUSTOMER-REC", fields=fields, record_length=33)
    key = VSAMKey("CUSTOMER-ID", 0, 6)
    return VSAMDataset("TEST.KSDS", VSAMType.KSDS, 33, cb, key, 0)


def make_records(n: int, start: int = 1) -> list:
    return [
        {"CUSTOMER-ID": f"{i:06d}", "NAME": f"CUSTOMER {i}", "BALANCE": 100.00 * i}
        for i in range(start, start + n)
    ]


class TestRecordCountValidation:
    def test_count_match_passes(self):
        ds = make_dataset_with_key()
        engine = ValidationEngine(ds)
        records = make_records(100)
        report = engine.validate(records, target_count=100)
        count_check = next(r for r in report.field_results if r.check_type == "RECORD_COUNT")
        assert count_check.passed is True

    def test_count_mismatch_fails(self):
        ds = make_dataset_with_key()
        engine = ValidationEngine(ds)
        records = make_records(100)
        report = engine.validate(records, target_count=95)
        count_check = next(r for r in report.field_results if r.check_type == "RECORD_COUNT")
        assert count_check.passed is False

    def test_empty_records_fails(self):
        ds = make_dataset_with_key()
        engine = ValidationEngine(ds)
        report = engine.validate([])
        assert report.overall_passed is False


class TestDuplicateKeyValidation:
    def test_no_duplicates_passes(self):
        ds = make_dataset_with_key()
        engine = ValidationEngine(ds)
        records = make_records(10)
        report = engine.validate(records)
        dup_check = next((r for r in report.field_results if r.check_type == "DUPLICATE_KEY"), None)
        assert dup_check is not None
        assert dup_check.passed is True
        assert report.duplicate_key_count == 0

    def test_duplicates_detected(self):
        ds = make_dataset_with_key()
        engine = ValidationEngine(ds)
        records = make_records(5) + make_records(3)  # first 3 are duplicated
        report = engine.validate(records)
        dup_check = next(r for r in report.field_results if r.check_type == "DUPLICATE_KEY")
        assert dup_check.passed is False
        assert report.duplicate_key_count > 0


class TestNullValidation:
    def test_null_in_key_fails(self):
        ds = make_dataset_with_key()
        engine = ValidationEngine(ds)
        records = [
            {"CUSTOMER-ID": None, "NAME": "Test", "BALANCE": 100.0},
            {"CUSTOMER-ID": "000002", "NAME": "Test2", "BALANCE": 200.0},
        ]
        report = engine.validate(records)
        key_null_check = next(
            (r for r in report.field_results
             if r.check_type == "NULL_CHECK" and r.field_name == "CUSTOMER-ID"),
            None
        )
        assert key_null_check is not None
        assert key_null_check.passed is False

    def test_no_nulls_passes(self):
        ds = make_dataset_with_key()
        engine = ValidationEngine(ds)
        records = make_records(5)
        report = engine.validate(records)
        null_checks = [r for r in report.field_results if r.check_type == "NULL_CHECK"]
        assert all(r.passed for r in null_checks)


class TestReportStructure:
    def test_report_has_summary(self):
        ds = make_dataset_with_key()
        engine = ValidationEngine(ds)
        records = make_records(10)
        report = engine.validate(records)
        assert report.summary
        assert "Validation Report" in report.summary

    def test_report_to_dict(self):
        ds = make_dataset_with_key()
        engine = ValidationEngine(ds)
        records = make_records(10)
        report = engine.validate(records)
        d = report.to_dict()
        assert "source_count" in d
        assert "target_count" in d
        assert "overall_passed" in d
        assert isinstance(d["field_results"], list)
