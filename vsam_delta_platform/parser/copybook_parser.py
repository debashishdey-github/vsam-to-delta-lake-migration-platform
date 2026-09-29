"""
Phase 2 — Copybook Parser
==========================
A COBOL copybook (.cpy) is a text file that describes the byte-by-byte layout
of a VSAM record.  Every field is declared with a PIC (Picture) clause that
encodes data type and length.

How PIC clauses map to bytes
-----------------------------
  PIC X(10)        → 10 bytes  (alphanumeric / string)
  PIC 9(7)         → 7 bytes   (unsigned integer, one digit per byte in display format)
  PIC 9(7)V99      → 9 bytes   (implied decimal; V = virtual decimal point, not a byte)
  PIC S9(5)        → 5 bytes   (signed integer, sign stored as overpunch on last digit)
  PIC 9(5) COMP-3  → 3 bytes   (packed BCD: ⌈(digits+1)/2⌉ bytes)

This parser handles the most common patterns encountered in real migrations.
Enterprise copybooks can be thousands of lines; this parser teaches the concepts.

Supported features
------------------
  ✓  PIC X(n)            alphanumeric
  ✓  PIC 9(n)            unsigned integer
  ✓  PIC 9(n)V9(d)       implied decimal
  ✓  PIC S9(n)           signed integer
  ✓  PIC 9(n) COMP-3     packed decimal
  ✓  OCCURS n TIMES      simple fixed-count arrays
  ✓  REDEFINES           detected and annotated (not expanded)
  ✗  DEPENDING ON        variable-length arrays (not supported)
  ✗  USAGE BINARY / COMP-4  (out of scope for learning platform)
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from vsam_delta_platform.metadata.models import (
    Copybook,
    CopybookField,
    FieldStatus,
    PICType,
)


# ---------------------------------------------------------------------------
# Regex patterns for PIC clause parsing
# ---------------------------------------------------------------------------

# PIC X(n) or PIC XX…  (alphanumeric)
_RE_ALPHA = re.compile(
    r"PIC\s+X+(?:\((\d+)\))?",
    re.IGNORECASE,
)

# PIC 9(n)V9(d) — decimal with explicit counts
_RE_DECIMAL_EXPLICIT = re.compile(
    r"PIC\s+S?9+(?:\((\d+)\))?V9*(?:\((\d+)\))?",
    re.IGNORECASE,
)

# PIC S9(n) — signed integer (no V)
_RE_SIGNED = re.compile(
    r"PIC\s+S9+(?:\((\d+)\))?(?!\s*V)",
    re.IGNORECASE,
)

# Detect COMP-3 / COMPUTATIONAL-3
_RE_COMP3 = re.compile(
    r"\bCOMP(?:UTATIONAL)?-3\b",
    re.IGNORECASE,
)

# Detect OCCURS n TIMES
_RE_OCCURS = re.compile(
    r"\bOCCURS\s+(\d+)\s+(?:TIMES\s+)?",
    re.IGNORECASE,
)

# Detect REDEFINES clause
_RE_REDEFINES = re.compile(
    r"\bREDEFINES\s+(\S+)",
    re.IGNORECASE,
)

# Level-number + name at the start of a copybook line
_RE_LEVEL = re.compile(
    r"^\s*(\d{2})\s+(\S+)\s*(.*)?$",
)


# ---------------------------------------------------------------------------
# Helper: expand X… or 9… shorthand (PIC XXX → PIC X(3))
# ---------------------------------------------------------------------------

def _count_chars(pattern: str, char: str) -> int:
    """Count consecutive instances of char in pattern (e.g. 'XX' → 2)."""
    return len([c for c in pattern if c.upper() == char.upper()])


# ---------------------------------------------------------------------------
# PIC clause analyser
# ---------------------------------------------------------------------------

def _parse_pic(raw_clause: str) -> Tuple[PICType, int, int]:
    """
    Parse a PIC clause string and return (pic_type, byte_length, decimal_places).

    Examples
    --------
    "PIC X(10)"         → (ALPHA,   10, 0)
    "PIC 9(7)V99"       → (DECIMAL,  9, 2)
    "PIC S9(5)"         → (SIGNED,   5, 0)
    "PIC 9(5) COMP-3"   → (COMP3,    3, 0)
    "PIC 9(7)"          → (NUMERIC,  7, 0)
    "PIC XXXX"          → (ALPHA,    4, 0)
    """
    is_comp3 = bool(_RE_COMP3.search(raw_clause))

    # --- Check decimal first (has V) ---
    v_match = re.search(r"PIC\s+S?9+(?:\((\d+)\))?V(9*)(?:\((\d+)\))?", raw_clause, re.IGNORECASE)
    if v_match:
        int_digits_str, dec_chars, dec_digits_str = v_match.group(1), v_match.group(2), v_match.group(3)
        int_digits = int(int_digits_str) if int_digits_str else _count_chars(
            raw_clause[:raw_clause.upper().find("V")], "9"
        )
        dec_digits = int(dec_digits_str) if dec_digits_str else (len(dec_chars) if dec_chars else 0)
        total_bytes = int_digits + dec_digits
        if is_comp3:
            total_bytes = (int_digits + dec_digits + 1) // 2
            return (PICType.COMP3, total_bytes, dec_digits)
        return (PICType.DECIMAL, total_bytes, dec_digits)

    # --- Signed integer (S9 without V) ---
    if re.search(r"PIC\s+S9", raw_clause, re.IGNORECASE):
        m = re.search(r"S9+(?:\((\d+)\))?", raw_clause, re.IGNORECASE)
        digits_str = m.group(1) if m else None
        digits = int(digits_str) if digits_str else _count_chars(
            raw_clause[raw_clause.upper().find("S"):], "9"
        )
        if is_comp3:
            return (PICType.COMP3, (digits + 1) // 2, 0)
        return (PICType.SIGNED, digits, 0)

    # --- Unsigned numeric PIC 9(n) ---
    if re.search(r"PIC\s+9", raw_clause, re.IGNORECASE):
        m = re.search(r"9+(?:\((\d+)\))?", raw_clause, re.IGNORECASE)
        digits_str = m.group(1) if m else None
        digits = int(digits_str) if digits_str else len(re.findall(r"9", raw_clause, re.IGNORECASE))
        if is_comp3:
            return (PICType.COMP3, (digits + 1) // 2, 0)
        return (PICType.NUMERIC, digits, 0)

    # --- Alphanumeric PIC X(n) ---
    if re.search(r"PIC\s+X", raw_clause, re.IGNORECASE):
        m = re.search(r"X+(?:\((\d+)\))?", raw_clause, re.IGNORECASE)
        length_str = m.group(1) if m else None
        length = int(length_str) if length_str else _count_chars(
            raw_clause[raw_clause.upper().find("X"):], "X"
        )
        return (PICType.ALPHA, length, 0)

    # Fallback: treat as 1-byte string
    return (PICType.ALPHA, 1, 0)


# ---------------------------------------------------------------------------
# Main parser class
# ---------------------------------------------------------------------------

class CopybookParser:
    """
    Parses a COBOL copybook text and produces a list of CopybookField objects
    with resolved byte offsets.

    Learning note
    -------------
    The copybook defines the record layout from byte 0 to byte N-1.  Fields
    are laid out in declaration order.  There is no padding unless PIC clauses
    explicitly include filler bytes (FILLER).  The parser walks the fields in
    order and accumulates the running byte offset.
    """

    def parse(self, text: str, name: str = "UNKNOWN") -> Copybook:
        """
        Parse copybook text and return a Copybook object.

        Parameters
        ----------
        text : str
            Raw copybook content (multi-line COBOL copybook text).
        name : str
            Copybook name (usually the filename without extension).
        """
        lines = self._preprocess(text)
        fields: List[CopybookField] = []
        record_name = "RECORD"
        offset = 0

        for line in lines:
            m = _RE_LEVEL.match(line)
            if not m:
                continue

            level_str, field_name, remainder = m.group(1), m.group(2), m.group(3).strip()
            level = int(level_str)
            field_name = field_name.rstrip(".")

            # 01-level is the record root — capture its name, no bytes
            if level == 1:
                record_name = field_name
                continue

            # Skip group-level items (no PIC clause) — they are structural containers
            if not re.search(r"\bPIC\b", remainder, re.IGNORECASE):
                # Still check for OCCURS at group level (rare but possible)
                continue

            # --- Detect REDEFINES ---
            redefines = None
            red_m = _RE_REDEFINES.search(remainder)
            if red_m:
                redefines = red_m.group(1)

            # --- Detect OCCURS ---
            occurs = 1
            occ_m = _RE_OCCURS.search(remainder)
            if occ_m:
                occurs = int(occ_m.group(1))

            # --- Parse PIC ---
            pic_type, byte_len, dec_places = _parse_pic(remainder)

            # REDEFINES fields overlay previously allocated space
            status = FieldStatus.REDEFINED if redefines else FieldStatus.ACTIVE
            field_offset = offset

            cf = CopybookField(
                name=field_name,
                level=level,
                pic_type=pic_type,
                length=byte_len * occurs,
                decimal_places=dec_places,
                offset=field_offset,
                occurs=occurs,
                redefines=redefines,
                status=status,
            )
            fields.append(cf)

            # REDEFINES does not advance offset (it overlays existing bytes)
            if not redefines:
                offset += byte_len * occurs

        cb = Copybook(
            name=name,
            record_name=record_name,
            fields=fields,
            record_length=offset,
            raw_text=text,
        )
        return cb

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _preprocess(self, text: str) -> List[str]:
        """
        Normalise the copybook text:
          1. Join continuation lines (COBOL cols 7-72 rule simplified here)
          2. Strip comment lines (lines with * in column 7 in standard COBOL)
          3. Remove blank lines
          4. Collapse multiple spaces
        """
        cleaned = []
        for raw_line in text.splitlines():
            # Remove sequence numbers (cols 1-6) if present (fixed-format copybooks)
            line = raw_line
            if len(line) > 6 and line[:6].strip().isdigit():
                line = line[6:]
            # Skip comment lines (* in col 7 becomes col 1 after slicing above)
            stripped = line.strip()
            if not stripped or stripped.startswith("*"):
                continue
            # Collapse whitespace
            cleaned.append(" ".join(stripped.split()))
        return cleaned

    def schema_summary(self, copybook: Copybook) -> List[dict]:
        """Return a simplified list of field dictionaries for display."""
        return [
            {
                "Field": f.name,
                "Level": f.level,
                "Type": f.pic_type.value,
                "Length": f.length,
                "Decimal": f.decimal_places,
                "Offset": f.offset,
                "Spark Type": f.spark_type(),
            }
            for f in copybook.fields
        ]
