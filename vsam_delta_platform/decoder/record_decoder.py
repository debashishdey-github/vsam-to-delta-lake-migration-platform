"""
Phase 4 — VSAM Record Decoder
==============================
VSAM records are stored as fixed-width byte strings on the mainframe.
Each field occupies a precise byte range defined by the copybook.

Example:
  Raw record (80 bytes):  "000001JOHN SMITH              0001200ACTIVE    "
  After decoding:
    {
      "CUSTOMER_ID": "000001",
      "NAME":        "JOHN SMITH",
      "BALANCE":     1200.00,
      "STATUS":      "ACTIVE"
    }

The key challenge in migration is understanding these data representations:

  Display numeric (PIC 9):
    Stored as ASCII/EBCDIC digit characters, one byte per digit.
    "0001200" decoded as integer → 1200 (if PIC 9(7)) or 12.00 (if PIC 9(5)V99).

  Signed overpunch (PIC S9):
    The sign is stored in the last digit byte using EBCDIC zone bits.
    This is rarely needed in learning projects; we simulate with a leading sign.

  Packed Decimal COMP-3 (PIC 9(n) COMP-3):
    Two BCD digits per byte, sign nibble in the last half-byte.
    0x123C = +123,  0x123D = -123.
    This is extremely common in financial systems.

  Alphanumeric (PIC X):
    Stored as-is in EBCDIC on the mainframe; our simulation uses ASCII.
    Trailing spaces are stripped during conversion.

This decoder works on ASCII-simulated VSAM records (typical for test files
exported from mainframe emulators or converted with ICONV).  Real migration
projects need EBCDIC→ASCII conversion first.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from vsam_delta_platform.metadata.models import Copybook, CopybookField, FieldStatus, PICType


# ---------------------------------------------------------------------------
# Field-level decoder functions
# ---------------------------------------------------------------------------

def _decode_alpha(raw: bytes) -> str:
    """
    Alphanumeric field: decode bytes as ASCII and strip trailing spaces.
    On a real mainframe this would be EBCDIC→ASCII conversion first.
    """
    return raw.decode("ascii", errors="replace").rstrip()


def _decode_numeric(raw: bytes, decimal_places: int = 0) -> Any:
    """
    Display numeric (PIC 9): each byte is an ASCII digit.
    The decimal point is implied (virtual — not stored in the record).

    e.g.  b"0001200" with decimal_places=2  →  Decimal("12.00")
          b"0001200" with decimal_places=0  →  1200
    """
    text = raw.decode("ascii", errors="replace").strip()
    # Remove any non-digit characters that might appear in corrupt data
    digits = re.sub(r"[^0-9]", "0", text)
    if not digits:
        digits = "0" * len(text)
    if decimal_places > 0:
        integer_part = digits[:-decimal_places] or "0"
        fractional_part = digits[-decimal_places:]
        try:
            return Decimal(f"{integer_part}.{fractional_part}")
        except InvalidOperation:
            return Decimal("0")
    try:
        return int(digits)
    except ValueError:
        return 0


def _decode_signed(raw: bytes, decimal_places: int = 0) -> Any:
    """
    Signed numeric (PIC S9): the sign is encoded in the last byte via EBCDIC
    zone bits (overpunch).  In ASCII-simulated files a leading '+' or '-' is
    sometimes used.  This implementation handles both.
    """
    text = raw.decode("ascii", errors="replace").strip()

    sign = 1
    if text.startswith("-"):
        sign = -1
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]

    # EBCDIC overpunch map for last digit (simplified positive/negative detection)
    # In real data: last byte ∈ {p, q, r, s, t, u, v, w, x, y} = negative overpunch
    overpunch_neg = set("pqrstuvwxy")
    overpunch_pos = set("{}ABCDEFGHI")

    if text and text[-1].lower() in overpunch_neg:
        sign = -1
        # Map the overpunch character to its digit
        neg_map = dict(zip("pqrstuvwxy", "1234567890"))
        text = text[:-1] + neg_map.get(text[-1].lower(), "0")
    elif text and text[-1] in overpunch_pos:
        pos_map = dict(zip("{}ABCDEFGHI", "0123456789"))
        text = text[:-1] + pos_map.get(text[-1], "0")

    digits = re.sub(r"[^0-9]", "0", text) or "0"
    if decimal_places > 0:
        integer_part = digits[:-decimal_places] or "0"
        frac_part = digits[-decimal_places:] if decimal_places <= len(digits) else "0" * decimal_places
        val = Decimal(f"{integer_part}.{frac_part}")
    else:
        val = int(digits)
    return val * sign if sign == -1 else val


def _decode_comp3(raw: bytes, decimal_places: int = 0) -> Any:
    """
    Packed Decimal (COMP-3 / COMPUTATIONAL-3):
    Two BCD digits are packed into one byte.  The last nibble (half-byte) is
    the sign: C or F = positive, D = negative.

    Example: Hex bytes 0x12 0x3C  →  "+123"
             Hex bytes 0x45 0x6D  →  "-456"

    This is the most important conversion for financial mainframe data because
    virtually all monetary fields use COMP-3 to save storage.
    """
    hex_str = raw.hex().upper()

    # Last nibble is sign
    sign_nibble = hex_str[-1]
    digit_nibbles = hex_str[:-1]  # everything except the sign nibble

    sign = -1 if sign_nibble == "D" else 1
    digits = digit_nibbles  # each character is already a decimal digit

    if not digits:
        digits = "0"

    if decimal_places > 0:
        if decimal_places >= len(digits):
            integer_part = "0"
            frac_part = digits.zfill(decimal_places)
        else:
            integer_part = digits[:-decimal_places]
            frac_part = digits[-decimal_places:]
        val = Decimal(f"{integer_part}.{frac_part}")
    else:
        val = int(digits) if digits else 0

    return val * sign if (isinstance(val, int) and sign == -1) else (
        -val if sign == -1 and isinstance(val, Decimal) else val
    )


# ---------------------------------------------------------------------------
# Main decoder class
# ---------------------------------------------------------------------------

class VSAMRecordDecoder:
    """
    Decodes fixed-width VSAM records into Python dictionaries using a Copybook
    as the schema descriptor.

    Typical migration workflow:
    1.  VSAM dataset is unloaded to a sequential file (REPRO to flat file).
    2.  File is transferred from mainframe to Linux/cloud.
    3.  EBCDIC→ASCII conversion (iconv or mainframe FTP with BINARY+iconv).
    4.  This decoder reads each fixed-width record and extracts fields.
    5.  Records are converted to Spark Row objects and written to Delta Lake.
    """

    def __init__(self, copybook: Copybook):
        self.copybook = copybook
        # Only decode active (non-redefined) fields
        self.active_fields = [f for f in copybook.fields if f.status == FieldStatus.ACTIVE]

    def decode_record(self, raw_record: str) -> Dict[str, Any]:
        """
        Decode one fixed-width record string into a field dictionary.

        Parameters
        ----------
        raw_record : str
            A single flat record string (ASCII representation of mainframe record).
            Length should match copybook.record_length.

        Returns
        -------
        dict mapping field_name (uppercase) → Python value
        """
        # Pad or truncate to expected length to be tolerant of test data
        expected_len = self.copybook.record_length
        record_bytes = raw_record.encode("ascii", errors="replace")
        if len(record_bytes) < expected_len:
            record_bytes = record_bytes.ljust(expected_len, b" ")

        result: Dict[str, Any] = {}

        for field in self.active_fields:
            start = field.offset
            end = start + field.length
            raw_bytes = record_bytes[start:end]

            # Handle OCCURS: split into individual occurrences
            if field.occurs > 1:
                occurrence_len = field.length // field.occurs
                values = []
                for i in range(field.occurs):
                    occ_bytes = raw_bytes[i * occurrence_len:(i + 1) * occurrence_len]
                    values.append(self._decode_field(field, occ_bytes))
                result[field.name.upper()] = values
            else:
                result[field.name.upper()] = self._decode_field(field, raw_bytes)

        return result

    def decode_records(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Decode a multi-record flat file where each line is one VSAM record.
        Blank lines are skipped.
        """
        records = []
        for line in raw_text.splitlines():
            if line.strip():
                records.append(self.decode_record(line))
        return records

    def _decode_field(self, field: CopybookField, raw: bytes) -> Any:
        if field.pic_type == PICType.ALPHA:
            return _decode_alpha(raw)
        if field.pic_type == PICType.NUMERIC:
            return _decode_numeric(raw, field.decimal_places)
        if field.pic_type == PICType.DECIMAL:
            return _decode_numeric(raw, field.decimal_places)
        if field.pic_type == PICType.SIGNED:
            return _decode_signed(raw, field.decimal_places)
        if field.pic_type == PICType.COMP3:
            return _decode_comp3(raw, field.decimal_places)
        return _decode_alpha(raw)

    def preview_decoding(self, raw_record: str) -> List[dict]:
        """
        Return a field-by-field breakdown useful for educational display.
        Shows the raw bytes, decoded value, and field metadata side-by-side.
        """
        record_bytes = raw_record.encode("ascii", errors="replace")
        rows = []
        for field in self.active_fields:
            start = field.offset
            end = start + field.length
            raw_slice = record_bytes[start:end]
            decoded = self._decode_field(field, raw_slice)
            rows.append({
                "Field": field.name,
                "Offset": f"{start}–{end-1}",
                "Raw Bytes": raw_slice.decode("ascii", errors="?"),
                "Type": field.pic_type.value,
                "Decoded Value": decoded,
                "Python Type": type(decoded).__name__,
            })
        return rows
