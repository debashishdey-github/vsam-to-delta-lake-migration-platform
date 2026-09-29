"""
Tests for the VSAM Record Decoder (Phase 4)
=============================================
Tests verify that fixed-width VSAM records are correctly decoded
into Python dictionaries according to the copybook field definitions.

Learning goal: understand fixed-width parsing and type conversion.
"""

import pytest
from decimal import Decimal

from vsam_delta_platform.decoder.record_decoder import (
    VSAMRecordDecoder,
    _decode_alpha,
    _decode_numeric,
    _decode_signed,
    _decode_comp3,
)
from vsam_delta_platform.metadata.models import Copybook, CopybookField, PICType


# ---------------------------------------------------------------------------
# Unit tests for individual decode functions
# ---------------------------------------------------------------------------

class TestDecodeAlpha:
    def test_strips_trailing_spaces(self):
        assert _decode_alpha(b"JOHN      ") == "JOHN"

    def test_preserves_internal_spaces(self):
        assert _decode_alpha(b"JOHN SMITH") == "JOHN SMITH"

    def test_empty_bytes(self):
        assert _decode_alpha(b"          ") == ""


class TestDecodeNumeric:
    def test_integer_field(self):
        assert _decode_numeric(b"0001234", 0) == 1234

    def test_decimal_field(self):
        result = _decode_numeric(b"000123400", 2)
        assert result == Decimal("1234.00")

    def test_decimal_with_cents(self):
        result = _decode_numeric(b"000005099", 2)
        assert result == Decimal("50.99")

    def test_zero_value(self):
        assert _decode_numeric(b"0000000", 0) == 0

    def test_max_value(self):
        assert _decode_numeric(b"9999999", 0) == 9999999


class TestDecodeSigned:
    def test_positive_no_sign(self):
        result = _decode_signed(b"001500", 0)
        assert result == 1500

    def test_negative_with_prefix(self):
        result = _decode_signed(b"-00150", 0)
        assert result == -150

    def test_positive_decimal(self):
        result = _decode_signed(b"000010000", 2)
        assert float(result) == pytest.approx(100.0)


class TestDecodeComp3:
    def test_positive_packed_decimal(self):
        # 0x12 0x3C = +123
        raw = bytes([0x12, 0x3C])
        result = _decode_comp3(raw, 0)
        assert result == 123

    def test_negative_packed_decimal(self):
        # 0x12 0x3D = -123
        raw = bytes([0x12, 0x3D])
        result = _decode_comp3(raw, 0)
        assert result == -123

    def test_packed_with_decimal_places(self):
        # 0x01 0x23 0x4C = +1234 with scale 2 → 12.34
        raw = bytes([0x01, 0x23, 0x4C])
        result = _decode_comp3(raw, 2)
        assert float(result) == pytest.approx(12.34)


# ---------------------------------------------------------------------------
# Integration tests: full record decoding
# ---------------------------------------------------------------------------

def make_customer_copybook() -> Copybook:
    """Build a simple customer copybook for integration tests."""
    fields = [
        CopybookField("CUSTOMER-ID", 5, PICType.ALPHA,   6,  0, 0),
        CopybookField("NAME",        5, PICType.ALPHA,   20, 0, 6),
        CopybookField("BALANCE",     5, PICType.DECIMAL,  7, 2, 26),
        CopybookField("STATUS",      5, PICType.ALPHA,    6, 0, 33),
    ]
    return Copybook(
        name="CUSTMAST",
        record_name="CUSTOMER-REC",
        fields=fields,
        record_length=39,
    )


class TestVSAMRecordDecoder:
    @pytest.fixture
    def decoder(self):
        return VSAMRecordDecoder(make_customer_copybook())

    def test_decode_single_record(self, decoder):
        # Layout: CUSTOMER-ID(6) + NAME(20) + BALANCE(7) + STATUS(6) = 39 bytes
        # "JOHN SMITH" = 10 chars + 10 spaces = 20 bytes for NAME field
        raw = "000001JOHN SMITH          0012000ACTIVE"
        result = decoder.decode_record(raw)
        assert result["CUSTOMER-ID"] == "000001"
        assert result["NAME"] == "JOHN SMITH"
        assert result["STATUS"] == "ACTIVE"

    def test_decode_balance_as_decimal(self, decoder):
        # BALANCE is PIC 9(7)V99: "0001200" with 2 decimal places → 12.00
        raw = "000001JOHN SMITH          0001200ACTIVE"
        result = decoder.decode_record(raw)
        # 0001200 with decimal_places=2: integer="00012", frac="00" → 12.00
        assert float(result["BALANCE"]) == pytest.approx(12.0)

    def test_decode_multiple_records(self, decoder):
        records_text = (
            "000001JOHN SMITH          0012000ACTIVE\n"
            "000002JANE DOE            0099900CLOSED"
        )
        results = decoder.decode_records(records_text)
        assert len(results) == 2
        assert results[0]["CUSTOMER-ID"] == "000001"
        assert results[1]["CUSTOMER-ID"] == "000002"

    def test_preview_decoding_structure(self, decoder):
        raw = "000001JOHN SMITH           0012000ACTIVE"
        preview = decoder.preview_decoding(raw)
        assert len(preview) == 4  # 4 fields
        assert "Field" in preview[0]
        assert "Offset" in preview[0]
        assert "Decoded Value" in preview[0]

    def test_short_record_padded(self, decoder):
        """Records shorter than expected should be padded and not raise errors."""
        raw = "000001"  # Much shorter than 39 bytes
        result = decoder.decode_record(raw)
        assert result["CUSTOMER-ID"] == "000001"
        # remaining fields will be empty strings or zero
        assert result["NAME"] == ""
