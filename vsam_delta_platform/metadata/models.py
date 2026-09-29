"""
Phase 3 — VSAM Metadata Model
==============================
VSAM datasets are catalogued on the mainframe in an Integrated Catalog Facility (ICF).
Each dataset has a name, type, record length, key definition, and associated copybook.

This module mirrors that catalog in Python so every downstream module can reason about
a VSAM dataset without touching the raw file bytes.

VSAM Dataset Types
------------------
KSDS  – Key Sequenced Data Set     (most common; like a B-tree indexed table)
ESDS  – Entry Sequenced Data Set   (append-only; like a sequential log file)
RRDS  – Relative Record Data Set   (fixed-size slots addressed by slot number)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class VSAMType(str, Enum):
    """The three VSAM organisation types."""
    KSDS = "KSDS"   # Key Sequenced Data Set
    ESDS = "ESDS"   # Entry Sequenced Data Set
    RRDS = "RRDS"   # Relative Record Data Set


class PICType(str, Enum):
    """
    COBOL PIC (Picture) clause categories.
    The PIC clause is the soul of a COBOL copybook — it tells you the data type
    and length of every field in the record.
    """
    ALPHA    = "alpha"       # PIC X(n)  — alphanumeric / string
    NUMERIC  = "numeric"     # PIC 9(n)  — integer
    DECIMAL  = "decimal"     # PIC 9(n)V9(d) — implied decimal point
    SIGNED   = "signed"      # PIC S9(n) — signed integer
    COMP3    = "comp3"       # PIC 9(n) COMP-3 — packed decimal (BCD)


class FieldStatus(str, Enum):
    ACTIVE   = "ACTIVE"
    REDEFINED = "REDEFINED"   # field is part of a REDEFINES group


# ---------------------------------------------------------------------------
# Core field model
# ---------------------------------------------------------------------------

@dataclass
class CopybookField:
    """
    Represents a single field from a COBOL copybook.

    On the mainframe every field is described by:
      - Level number   : 01 = record root, 05/10/… = subordinate group or elementary
      - Name           : the business name (CUSTOMER-ID, BALANCE, etc.)
      - PIC clause     : data type and length declaration
      - Offset         : byte position within the fixed-width record (0-based)
      - Length         : number of bytes consumed in the flat record
    """
    name: str
    level: int
    pic_type: PICType
    length: int                   # total byte length in the raw record
    decimal_places: int = 0       # only relevant for PICType.DECIMAL
    offset: int = 0               # byte offset computed by the parser
    occurs: int = 1               # for OCCURS n TIMES arrays
    redefines: Optional[str] = None   # name of field being redefined
    status: FieldStatus = FieldStatus.ACTIVE
    description: str = ""         # human-readable annotation

    def spark_type(self) -> str:
        """Return the equivalent PySpark DataType string for this field."""
        if self.pic_type in (PICType.ALPHA,):
            return "StringType()"
        if self.pic_type == PICType.DECIMAL:
            precision = self.length - self.decimal_places
            return f"DecimalType({self.length}, {self.decimal_places})"
        if self.pic_type in (PICType.NUMERIC, PICType.SIGNED, PICType.COMP3):
            if self.length <= 4:
                return "IntegerType()"
            if self.length <= 9:
                return "LongType()"
            return f"DecimalType({self.length}, 0)"
        return "StringType()"

    def python_type(self) -> str:
        if self.pic_type == PICType.ALPHA:
            return "str"
        if self.pic_type == PICType.DECIMAL:
            return "float"
        if self.pic_type in (PICType.NUMERIC, PICType.SIGNED, PICType.COMP3):
            return "int"
        return "str"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pic_type"] = self.pic_type.value
        d["status"] = self.status.value
        return d


# ---------------------------------------------------------------------------
# Copybook model
# ---------------------------------------------------------------------------

@dataclass
class Copybook:
    """
    A COBOL copybook (.cpy file) describes the record layout of a VSAM dataset.
    Think of it as the schema definition — the equivalent of a CREATE TABLE DDL.

    The copybook is included into COBOL programs with a COPY statement:
        COPY CUSTOMER-COPY.

    Fields are listed in declaration order; the parser resolves offsets.
    """
    name: str
    record_name: str              # 01-level name (e.g. CUSTOMER-REC)
    fields: List[CopybookField] = field(default_factory=list)
    record_length: int = 0        # total byte length of one record
    raw_text: str = ""            # original copybook text (for display)

    def get_field(self, name: str) -> Optional[CopybookField]:
        for f in self.fields:
            if f.name.upper() == name.upper():
                return f
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "record_name": self.record_name,
            "record_length": self.record_length,
            "fields": [f.to_dict() for f in self.fields],
        }


# ---------------------------------------------------------------------------
# VSAM Key definition
# ---------------------------------------------------------------------------

@dataclass
class VSAMKey:
    """
    KSDS datasets have a primary key — a field (or concatenation of fields)
    whose value uniquely identifies each record.  This mirrors the KEY(field)
    clause in the DEFINE CLUSTER JCL.

    ESDS and RRDS do not have user-defined keys:
      - ESDS uses the byte-offset (RBA – Relative Byte Address) as implicit key.
      - RRDS uses the slot number (RRN – Relative Record Number).
    """
    field_name: str
    offset: int = 0
    length: int = 0
    is_alternate: bool = False    # True if this is an alternate index key

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# VSAM Dataset model
# ---------------------------------------------------------------------------

@dataclass
class VSAMDataset:
    """
    The top-level representation of a VSAM dataset — the equivalent of a table.

    On the mainframe a VSAM dataset is defined with JCL like:
        //DEFKSDS  EXEC PGM=IDCAMS
        //SYSIN    DD  *
          DEFINE CLUSTER                  -
            (NAME(PROD.CUSTOMER.KSDS)     -
             INDEXED                      -
             KEYS(10 0)                   -
             RECORDSIZE(200 200)          -
             CYLINDERS(10 5))             -
          DATA                            -
            (NAME(PROD.CUSTOMER.KSDS.DATA))-
          INDEX                           -
            (NAME(PROD.CUSTOMER.KSDS.INDEX))

    This model captures the metadata needed for migration planning.
    """
    name: str                           # Fully-qualified VSAM dataset name
    vsam_type: VSAMType
    record_length: int                  # Fixed record length in bytes
    copybook: Optional[Copybook] = None
    primary_key: Optional[VSAMKey] = None
    alternate_keys: List[VSAMKey] = field(default_factory=list)
    record_count: int = 0               # estimated / actual record count
    description: str = ""

    # Derived target metadata (populated by the mapping engine)
    target_table: str = ""              # Delta Lake table name
    target_location: str = ""          # Delta table path on object storage

    @property
    def delta_table_name(self) -> str:
        """Return a SQL-safe Delta table name derived from the VSAM name."""
        if self.target_table:
            return self.target_table
        # PROD.CUSTOMER.KSDS → customer
        return self.name.split(".")[-2].lower() if "." in self.name else self.name.lower()

    @property
    def delta_location(self) -> str:
        if self.target_location:
            return self.target_location
        return f"/delta/{self.delta_table_name}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "vsam_type": self.vsam_type.value,
            "record_length": self.record_length,
            "record_count": self.record_count,
            "description": self.description,
            "target_table": self.delta_table_name,
            "target_location": self.delta_location,
            "primary_key": self.primary_key.to_dict() if self.primary_key else None,
            "alternate_keys": [k.to_dict() for k in self.alternate_keys],
            "copybook": self.copybook.to_dict() if self.copybook else None,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "VSAMDataset":
        vsam_type = VSAMType(data["vsam_type"])
        dataset = cls(
            name=data["name"],
            vsam_type=vsam_type,
            record_length=data.get("record_length", 0),
            record_count=data.get("record_count", 0),
            description=data.get("description", ""),
        )
        dataset.target_table = data.get("target_table", "")
        dataset.target_location = data.get("target_location", "")
        return dataset


# ---------------------------------------------------------------------------
# Migration run record
# ---------------------------------------------------------------------------

@dataclass
class MigrationRecord:
    """
    Represents a single migration execution — source dataset to Delta table.
    Stored as lineage metadata after each run.
    """
    source: str                   # VSAM dataset name
    target: str                   # Delta table name
    vsam_type: str
    record_count_source: int = 0
    record_count_target: int = 0
    status: str = "PENDING"       # PENDING / SUCCESS / FAILED
    validation_passed: bool = False
    error_message: str = ""
    run_timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
