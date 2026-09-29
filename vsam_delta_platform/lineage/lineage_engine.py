"""
Phase 9 — Lineage Generation
==============================
Data lineage answers the question: "Where did this data come from?"

In a mainframe migration this is critical for:
  - Regulatory compliance (BCBS 239, GDPR, SOX) — prove data traceability
  - Impact analysis — if the VSAM source changes, which Delta tables are affected?
  - Migration audit — prove every source field landed in the target
  - Debugging — trace a bad value in Delta back to its source record

Lineage vocabulary
-------------------
  Source      : VSAM dataset (PROD.CUSTOMER.KSDS)
  Stage 1     : Schema extraction (copybook parsing)
  Stage 2     : Record decoding (fixed-width → Python dict)
  Stage 3     : Spark transformation (dict → DataFrame)
  Stage 4     : Delta write (DataFrame → Delta table)
  Target      : Delta table (customer_delta)

This engine produces:
  1. A lineage graph in mermaid diagram syntax (renderable in GitHub/Notion/VSCode)
  2. A JSON lineage document (importable by tools like Apache Atlas, OpenLineage)
  3. A field-level mapping document (source field → target column)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

from vsam_delta_platform.metadata.models import Copybook, CopybookField, FieldStatus, VSAMDataset


# ---------------------------------------------------------------------------
# Lineage node and edge models
# ---------------------------------------------------------------------------

@dataclass
class LineageNode:
    node_id: str
    label: str
    node_type: str    # SOURCE | PROCESS | TARGET | ARTIFACT
    description: str = ""
    properties: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LineageEdge:
    from_node: str
    to_node: str
    label: str = ""
    transformation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FieldLineageEntry:
    source_dataset: str
    source_field: str
    source_pic_type: str
    source_offset: int
    source_length: int
    target_table: str
    target_column: str
    target_spark_type: str
    transformation: str = "direct mapping"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LineageDocument:
    """Full lineage document for one VSAM → Delta migration."""
    dataset_name: str
    target_table: str
    vsam_type: str
    generated_at: str
    nodes: List[LineageNode] = field(default_factory=list)
    edges: List[LineageEdge] = field(default_factory=list)
    field_lineage: List[FieldLineageEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source": self.dataset_name,
            "target": self.target_table,
            "vsam_type": self.vsam_type,
            "generated_at": self.generated_at,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "field_lineage": [f.to_dict() for f in self.field_lineage],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Lineage engine
# ---------------------------------------------------------------------------

class LineageEngine:
    """
    Generates lineage metadata for a VSAM → Delta migration.
    """

    def generate(self, dataset: VSAMDataset) -> LineageDocument:
        """
        Produce the full lineage document for one dataset migration.
        """
        now = datetime.utcnow().isoformat() + "Z"
        doc = LineageDocument(
            dataset_name=dataset.name,
            target_table=dataset.delta_table_name,
            vsam_type=dataset.vsam_type.value,
            generated_at=now,
        )

        # --- Build nodes ---
        n_source = LineageNode(
            node_id="vsam_source",
            label=dataset.name,
            node_type="SOURCE",
            description=f"VSAM {dataset.vsam_type.value} dataset on mainframe",
            properties={
                "system": "IBM z/OS Mainframe",
                "record_length": str(dataset.record_length),
                "record_count": str(dataset.record_count),
                "type": dataset.vsam_type.value,
            },
        )

        n_copybook = LineageNode(
            node_id="copybook_parser",
            label=f"Copybook: {dataset.copybook.name if dataset.copybook else 'Unknown'}",
            node_type="ARTIFACT",
            description="COBOL copybook defines the record layout",
        )

        n_schema = LineageNode(
            node_id="schema_extraction",
            label="Schema Extraction",
            node_type="PROCESS",
            description="Copybook parsed into Spark StructType",
        )

        n_decoder = LineageNode(
            node_id="record_decoder",
            label="Record Decoder",
            node_type="PROCESS",
            description="Fixed-width bytes decoded to Python dicts",
        )

        n_spark = LineageNode(
            node_id="spark_transform",
            label="Spark Transformation",
            node_type="PROCESS",
            description="Dicts loaded into Spark DataFrame with typed schema",
        )

        n_delta = LineageNode(
            node_id="delta_write",
            label="Delta Lake Write",
            node_type="PROCESS",
            description=f"DataFrame written as Delta table ({dataset.vsam_type.value} → appropriate mode)",
        )

        n_target = LineageNode(
            node_id="delta_target",
            label=dataset.delta_table_name,
            node_type="TARGET",
            description=f"Delta Lake table at {dataset.delta_location}",
            properties={
                "format": "Delta Lake",
                "location": dataset.delta_location,
                "acid": "true",
                "time_travel": "true",
            },
        )

        doc.nodes = [n_source, n_copybook, n_schema, n_decoder, n_spark, n_delta, n_target]

        # --- Build edges ---
        doc.edges = [
            LineageEdge("vsam_source", "copybook_parser", "drives schema of"),
            LineageEdge("copybook_parser", "schema_extraction", "parsed by"),
            LineageEdge("vsam_source", "record_decoder", "records read by"),
            LineageEdge("schema_extraction", "spark_transform", "schema applied in"),
            LineageEdge("record_decoder", "spark_transform", "decoded rows fed into"),
            LineageEdge("spark_transform", "delta_write", "DataFrame written via"),
            LineageEdge("delta_write", "delta_target", "persisted as"),
        ]

        # --- Field-level lineage ---
        if dataset.copybook:
            active = [f for f in dataset.copybook.fields if f.status == FieldStatus.ACTIVE]
            for fld in active:
                # Determine transformation description
                if hasattr(fld.pic_type, 'value'):
                    pic = fld.pic_type.value
                else:
                    pic = str(fld.pic_type)

                if "decimal" in pic.lower():
                    transform = f"implied decimal inserted (scale={fld.decimal_places})"
                elif "comp3" in pic.lower():
                    transform = "BCD packed decimal unpacked"
                elif "signed" in pic.lower():
                    transform = "EBCDIC overpunch sign decoded"
                else:
                    transform = "direct fixed-width extraction"

                doc.field_lineage.append(FieldLineageEntry(
                    source_dataset=dataset.name,
                    source_field=fld.name,
                    source_pic_type=pic,
                    source_offset=fld.offset,
                    source_length=fld.length,
                    target_table=dataset.delta_table_name,
                    target_column=fld.name.lower(),
                    target_spark_type=fld.spark_type(),
                    transformation=transform,
                ))

        return doc

    def generate_mermaid(self, doc: LineageDocument) -> str:
        """
        Generate a Mermaid flowchart diagram of the lineage.
        Paste this into any Mermaid renderer (GitHub MD, Notion, VSCode plugin).
        """
        lines = [
            "```mermaid",
            "flowchart TD",
            f'    A["{doc.dataset_name}\\n({doc.vsam_type} on z/OS)"] --> B["Copybook Parser"]',
            f'    A --> C["Record Decoder\\n(fixed-width bytes)"]',
            f'    B --> D["Spark Schema\\n(StructType)"]',
            f'    C --> E["Spark DataFrame"]',
            f'    D --> E',
            f'    E --> F["Delta Lake Write\\n(.format delta)"]',
            f'    F --> G["{doc.target_table}\\n(Delta Table)"]',
            "",
            "    style A fill:#1a6b3a,color:#fff",
            "    style G fill:#1565C0,color:#fff",
            "    style F fill:#6A1B9A,color:#fff",
            "```",
        ]
        return "\n".join(lines)

    def generate_field_lineage_markdown(self, doc: LineageDocument) -> str:
        """Generate a markdown table showing field-level lineage."""
        lines = [
            f"## Field Lineage: {doc.dataset_name} → {doc.target_table}",
            "",
            "| Source Field | PIC Type | Offset | Len | Target Column | Spark Type | Transformation |",
            "|---|---|---|---|---|---|---|",
        ]
        for fl in doc.field_lineage:
            lines.append(
                f"| {fl.source_field} | {fl.source_pic_type} | {fl.source_offset} "
                f"| {fl.source_length} | {fl.target_column} | {fl.target_spark_type} "
                f"| {fl.transformation} |"
            )
        return "\n".join(lines)

    def generate_vsam_concept_map_mermaid(self) -> str:
        """Generate a concept mapping diagram between VSAM and Delta Lake."""
        return "\n".join([
            "```mermaid",
            "graph LR",
            '    subgraph VSAM["VSAM (Mainframe)"]',
            '        K["KSDS\\n(Key Sequenced)"]',
            '        E["ESDS\\n(Entry Sequenced)"]',
            '        R["RRDS\\n(Relative Record)"]',
            '        CB["Copybook\\n(.cpy file)"]',
            '        REC["Fixed-Width Record"]',
            '        CAT["ICF Catalog Entry"]',
            "    end",
            '    subgraph DL["Delta Lake (Cloud)"]',
            '        DKT["Delta Table\\n+ Z-ORDER by key"]',
            '        DAT["Append-Only Delta Table"]',
            '        DRT["Delta Table\\n+ row_number key"]',
            '        SCH["StructType Schema"]',
            '        ROW["Parquet Row"]',
            '        MET["Hive Metastore"]',
            "    end",
            "    K -->|maps to| DKT",
            "    E -->|maps to| DAT",
            "    R -->|maps to| DRT",
            "    CB -->|maps to| SCH",
            "    REC -->|maps to| ROW",
            "    CAT -->|maps to| MET",
            "```",
        ])
