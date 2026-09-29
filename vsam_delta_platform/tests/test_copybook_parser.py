"""
Tests for the Copybook Parser (Phase 2)
========================================
These tests verify that the copybook parser correctly extracts field definitions
from COBOL copybook text, including PIC types, lengths, and byte offsets.

Learning goal: understand how PIC clauses map to field types and byte lengths.
"""

import pytest
from vsam_delta_platform.parser.copybook_parser import CopybookParser
from vsam_delta_platform.metadata.models import PICType


@pytest.fixture
def parser():
    return CopybookParser()


# ---------------------------------------------------------------------------
# Basic PIC X (alphanumeric) parsing
# ---------------------------------------------------------------------------

class TestAlphanumericFields:
    def test_pic_x_with_explicit_length(self, parser):
        """PIC X(10) should produce a 10-byte alphanumeric field."""
        copybook = parser.parse("""
        01 TEST-REC.
           05 CUSTOMER-ID PIC X(10).
        """, name="TEST")
        assert len(copybook.fields) == 1
        f = copybook.fields[0]
        assert f.name == "CUSTOMER-ID"
        assert f.pic_type == PICType.ALPHA
        assert f.length == 10
        assert f.offset == 0

    def test_pic_x_repeated(self, parser):
        """PIC XXX should be 3 bytes."""
        copybook = parser.parse("""
        01 TEST-REC.
           05 FLAG PIC XXX.
        """, name="TEST")
        assert copybook.fields[0].length == 3

    def test_multiple_alpha_fields_accumulate_offsets(self, parser):
        """Offsets must accumulate correctly across fields."""
        copybook = parser.parse("""
        01 TEST-REC.
           05 FIELD-A PIC X(5).
           05 FIELD-B PIC X(10).
           05 FIELD-C PIC X(3).
        """, name="TEST")
        assert copybook.fields[0].offset == 0
        assert copybook.fields[1].offset == 5
        assert copybook.fields[2].offset == 15
        assert copybook.record_length == 18


# ---------------------------------------------------------------------------
# Numeric fields (PIC 9)
# ---------------------------------------------------------------------------

class TestNumericFields:
    def test_pic_9_simple(self, parser):
        """PIC 9(7) should be 7 bytes, NUMERIC type."""
        copybook = parser.parse("""
        01 TEST-REC.
           05 AMOUNT PIC 9(7).
        """, name="TEST")
        f = copybook.fields[0]
        assert f.pic_type == PICType.NUMERIC
        assert f.length == 7
        assert f.decimal_places == 0

    def test_pic_9_decimal(self, parser):
        """PIC 9(7)V99 should be 9 bytes total (no byte for V), scale=2."""
        copybook = parser.parse("""
        01 TEST-REC.
           05 BALANCE PIC 9(7)V99.
        """, name="TEST")
        f = copybook.fields[0]
        assert f.pic_type == PICType.DECIMAL
        assert f.length == 9
        assert f.decimal_places == 2

    def test_pic_s9_signed(self, parser):
        """PIC S9(5) should be SIGNED type."""
        copybook = parser.parse("""
        01 TEST-REC.
           05 TRANS-AMOUNT PIC S9(5).
        """, name="TEST")
        f = copybook.fields[0]
        assert f.pic_type == PICType.SIGNED
        assert f.length == 5


# ---------------------------------------------------------------------------
# COMP-3 (packed decimal)
# ---------------------------------------------------------------------------

class TestComp3Fields:
    def test_comp3_byte_calculation(self, parser):
        """PIC 9(7)V99 COMP-3: (9+1)/2 = 5 bytes."""
        copybook = parser.parse("""
        01 TEST-REC.
           05 PACKED-AMT PIC 9(7)V99 COMP-3.
        """, name="TEST")
        f = copybook.fields[0]
        assert f.pic_type == PICType.COMP3
        assert f.length == 5  # ceil((9+1)/2) = 5
        assert f.decimal_places == 2


# ---------------------------------------------------------------------------
# Mixed records (typical real-world copybook)
# ---------------------------------------------------------------------------

class TestMixedRecord:
    def test_customer_record(self, parser):
        """Full customer record: fields, offsets, types all correct."""
        copybook = parser.parse("""
        01 CUSTOMER-REC.
           05 CUSTOMER-ID     PIC X(10).
           05 NAME            PIC X(30).
           05 BALANCE         PIC 9(7)V99.
           05 STATUS          PIC X(1).
        """, name="CUSTMAST")

        assert copybook.name == "CUSTMAST"
        assert copybook.record_name == "CUSTOMER-REC"
        assert len(copybook.fields) == 4

        fnames = [f.name for f in copybook.fields]
        assert "CUSTOMER-ID" in fnames
        assert "NAME" in fnames
        assert "BALANCE" in fnames

        # BALANCE offset: after CUSTOMER-ID (10) + NAME (30) = 40
        balance = next(f for f in copybook.fields if f.name == "BALANCE")
        assert balance.offset == 40
        assert balance.decimal_places == 2

        # Total record length: 10 + 30 + 9 + 1 = 50
        assert copybook.record_length == 50

    def test_schema_summary_returns_list(self, parser):
        """schema_summary() should return one dict per field."""
        copybook = parser.parse("""
        01 REC.
           05 FIELD-A PIC X(5).
           05 FIELD-B PIC 9(3).
        """, name="TESTREC")
        summary = parser.schema_summary(copybook)
        assert len(summary) == 2
        assert "Field" in summary[0]
        assert "Spark Type" in summary[0]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_copybook(self, parser):
        copybook = parser.parse("", name="EMPTY")
        assert len(copybook.fields) == 0
        assert copybook.record_length == 0

    def test_group_level_skipped(self, parser):
        """Group-level items (no PIC) should not appear as fields."""
        copybook = parser.parse("""
        01 ROOT-REC.
           05 GROUP-A.
              10 FIELD-X PIC X(5).
        """, name="TEST")
        # Only FIELD-X has a PIC — GROUP-A should not be in fields
        field_names = [f.name for f in copybook.fields]
        assert "GROUP-A" not in field_names
        assert "FIELD-X" in field_names

    def test_copybook_to_dict(self, parser):
        copybook = parser.parse("""
        01 TEST-REC.
           05 ID PIC X(5).
        """, name="TEST")
        d = copybook.to_dict()
        assert d["name"] == "TEST"
        assert len(d["fields"]) == 1
