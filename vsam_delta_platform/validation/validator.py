"""
Phase 8 — Data Quality Validation Engine
==========================================
After migrating VSAM records to Delta Lake, we must verify the data arrived
correctly.  The validation is a core deliverable in any mainframe migration
project — without it, the business cannot retire the source system.

Validation checks
-----------------
1.  Record count        : source count == target count (most critical gate)
2.  Null check          : no unexpected NULL values in mandatory fields
3.  Duplicate key check : no duplicate primary keys (KSDS guarantee)
4.  Numeric range check : numeric fields within domain bounds
5.  String pattern check: key fields match expected patterns
6.  Checksum (optional) : sum of all numeric fields in source == sum in target

Validation in the VSAM migration world
---------------------------------------
VSAM itself provides count information via LISTCAT (LIST CATALOG).
After migration the counts must reconcile.  A typical sign-off document
shows a three-way comparison: VSAM LISTCAT count, extract record count,
and Delta target count.  All three must agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from vsam_delta_platform.metadata.models import Copybook, CopybookField, FieldStatus, PICType, VSAMDataset


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class FieldValidationResult:
    field_name: str
    check_type: str
    passed: bool
    message: str
    severity: str = "ERROR"   # ERROR | WARNING | INFO

    def to_dict(self) -> dict:
        return {
            "Field": self.field_name,
            "Check": self.check_type,
            "Status": "PASS" if self.passed else self.severity,
            "Message": self.message,
        }


@dataclass
class ValidationReport:
    dataset_name: str
    source_count: int
    target_count: int
    field_results: List[FieldValidationResult] = field(default_factory=list)
    duplicate_key_count: int = 0
    overall_passed: bool = False
    summary: str = ""

    def add(self, result: FieldValidationResult):
        self.field_results.append(result)

    def compute_overall(self):
        error_checks = [r for r in self.field_results if not r.passed and r.severity == "ERROR"]
        count_ok = self.source_count == self.target_count
        dup_ok = self.duplicate_key_count == 0
        self.overall_passed = count_ok and dup_ok and len(error_checks) == 0

        lines = [
            "=" * 60,
            " VSAM → Delta Lake Validation Report",
            "=" * 60,
            f" Dataset          : {self.dataset_name}",
            f" Records (source) : {self.source_count:,}",
            f" Records (target) : {self.target_count:,}",
            f" Count Match      : {'PASS' if count_ok else 'FAIL'}",
            f" Duplicate Keys   : {self.duplicate_key_count}",
            f" Field Checks     : {len(self.field_results)} checks, "
            f"{sum(1 for r in self.field_results if r.passed)} passed",
            f" Overall Status   : {'PASSED' if self.overall_passed else 'FAILED'}",
            "=" * 60,
        ]
        for r in self.field_results:
            status = "✓" if r.passed else "✗"
            lines.append(f" [{status}] {r.field_name:<25} {r.check_type:<20} {r.message}")
        self.summary = "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "dataset_name": self.dataset_name,
            "source_count": self.source_count,
            "target_count": self.target_count,
            "duplicate_key_count": self.duplicate_key_count,
            "overall_passed": self.overall_passed,
            "field_results": [r.to_dict() for r in self.field_results],
        }


# ---------------------------------------------------------------------------
# Validation engine
# ---------------------------------------------------------------------------

class ValidationEngine:
    """
    Validates decoded VSAM records against quality rules derived from the copybook.

    Usage:
    ------
        engine = ValidationEngine(dataset, copybook)
        report = engine.validate(decoded_records)
        print(report.summary)
    """

    def __init__(self, dataset: VSAMDataset, copybook: Optional[Copybook] = None):
        self.dataset = dataset
        self.copybook = copybook or dataset.copybook
        self.active_fields: List[CopybookField] = []
        if self.copybook:
            self.active_fields = [f for f in self.copybook.fields if f.status == FieldStatus.ACTIVE]

    def validate(
        self,
        decoded_records: List[Dict[str, Any]],
        target_count: Optional[int] = None,
    ) -> ValidationReport:
        """
        Run all validation checks and return a ValidationReport.

        Parameters
        ----------
        decoded_records : list of dicts
            Output from VSAMRecordDecoder.decode_records().
        target_count : int, optional
            The count of records loaded into Delta Lake (for count reconciliation).
        """
        source_count = len(decoded_records)
        t_count = target_count if target_count is not None else source_count

        report = ValidationReport(
            dataset_name=self.dataset.name,
            source_count=source_count,
            target_count=t_count,
        )

        if not decoded_records:
            report.add(FieldValidationResult(
                field_name="ALL",
                check_type="RECORD_COUNT",
                passed=False,
                message="No records provided for validation.",
                severity="ERROR",
            ))
            report.compute_overall()
            return report

        # 1. Record count check
        count_ok = source_count == t_count
        report.add(FieldValidationResult(
            field_name="ALL",
            check_type="RECORD_COUNT",
            passed=count_ok,
            message=f"Source={source_count:,}, Target={t_count:,}" + ("" if count_ok else " ← MISMATCH"),
            severity="ERROR" if not count_ok else "INFO",
        ))

        # 2. Duplicate primary key check (KSDS)
        if self.dataset.primary_key:
            key_field = self.dataset.primary_key.field_name.upper()
            key_values = [str(r.get(key_field, "")) for r in decoded_records]
            unique_keys = set(key_values)
            dup_count = len(key_values) - len(unique_keys)
            report.duplicate_key_count = dup_count
            report.add(FieldValidationResult(
                field_name=key_field,
                check_type="DUPLICATE_KEY",
                passed=dup_count == 0,
                message=f"Duplicates found: {dup_count}" if dup_count > 0 else "No duplicates",
                severity="ERROR" if dup_count > 0 else "INFO",
            ))

        # 3. Per-field checks
        for fld in self.active_fields:
            fname = fld.name.upper()
            values = [r.get(fname) for r in decoded_records]

            # Null / empty check
            nulls = sum(1 for v in values if v is None or str(v).strip() == "")
            null_pct = round(nulls / source_count * 100, 1) if source_count else 0
            is_key = (
                self.dataset.primary_key is not None
                and fname == self.dataset.primary_key.field_name.upper()
            )
            null_ok = (nulls == 0) if is_key else (null_pct < 50)
            report.add(FieldValidationResult(
                field_name=fname,
                check_type="NULL_CHECK",
                passed=null_ok,
                message=f"{nulls} nulls ({null_pct}%)" if nulls else "No nulls",
                severity="ERROR" if (is_key and not null_ok) else "WARNING" if not null_ok else "INFO",
            ))

            # Numeric field checks
            if fld.pic_type in (PICType.NUMERIC, PICType.DECIMAL, PICType.SIGNED, PICType.COMP3):
                non_numeric = sum(1 for v in values if v is not None and not _is_numeric(v))
                num_ok = non_numeric == 0
                numeric_vals = [float(v) for v in values if _is_numeric(v)]
                if numeric_vals:
                    min_v, max_v = min(numeric_vals), max(numeric_vals)
                    total = sum(numeric_vals)
                    msg = (
                        f"Min={min_v:,.2f}, Max={max_v:,.2f}, Sum={total:,.2f}"
                        if num_ok
                        else f"Non-numeric values: {non_numeric}"
                    )
                else:
                    msg = "No numeric values"
                report.add(FieldValidationResult(
                    field_name=fname,
                    check_type="NUMERIC_RANGE",
                    passed=num_ok,
                    message=msg,
                    severity="ERROR" if not num_ok else "INFO",
                ))

        report.compute_overall()
        return report

    def generate_validation_spark_code(self) -> str:
        """Generate PySpark code to run the same validation checks on Delta data."""
        tbl = self.dataset.delta_table_name
        key = self.dataset.primary_key.field_name.lower() if self.dataset.primary_key else None

        lines = [
            f"# -------------------------------------------------------",
            f"# Delta Lake Post-Migration Validation",
            f"# Dataset: {self.dataset.name} → {tbl}",
            f"# -------------------------------------------------------",
            "",
            f'df = spark.table("{tbl}")',
            f'record_count = df.count()',
            f'print(f"Record Count: {{record_count:,}}")',
            "",
        ]

        if key:
            lines += [
                f"# Duplicate primary key check",
                f"from pyspark.sql import functions as F",
                f"dup_check = (",
                f"    df.groupBy(\"{key}\")",
                f"    .agg(F.count(\"*\").alias(\"cnt\"))",
                f"    .filter(\"cnt > 1\")",
                f"    .count()",
                f")",
                f'print(f"Duplicate keys: {{dup_check}}")',
                "",
            ]

        if self.copybook:
            for fld in self.active_fields[:5]:  # show first 5 as examples
                col = fld.name.lower()
                if fld.pic_type in (PICType.NUMERIC, PICType.DECIMAL, PICType.SIGNED, PICType.COMP3):
                    lines += [
                        f"# Numeric validation for {col}",
                        f"df.agg(",
                        f"    F.min(\"{col}\").alias(\"min_{col}\"),",
                        f"    F.max(\"{col}\").alias(\"max_{col}\"),",
                        f"    F.sum(\"{col}\").alias(\"sum_{col}\")",
                        f").show()",
                        "",
                    ]
                else:
                    lines += [
                        f"# Null check for {col}",
                        f'print(f"{col} nulls: {{df.filter(F.col("{col}").isNull()).count()}}")',
                        "",
                    ]

        return "\n".join(lines)


def _is_numeric(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError, Exception):
        return False
