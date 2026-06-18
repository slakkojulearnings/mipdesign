from pathlib import Path

from mip.config import Settings
from mip.discovery.scanner import RepositoryScanner
from mip.models import AssetType, RelationshipType
from mip.parsers.cobol import CobolParser
from mip.parsers.copybook import CopybookParser
from mip.parsers.jcl import JclParser

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-mainframe"


def _source(relative: str):
    files = RepositoryScanner(Settings()).scan(SAMPLE)
    return next(item for item in files if item.relative_path == relative)


def test_cobol_parser_extracts_program_calls_copy_sql_and_files() -> None:
    result = CobolParser().parse(_source("cbl/CUST001"))
    assert any(
        a.asset_type == AssetType.PROGRAM and a.technical_name == "CUST001" for a in result.assets
    )
    rels = {(r.relationship_type, r.target_name) for r in result.relationships}
    assert (RelationshipType.CALLS, "CUSTVAL") in rels
    assert (RelationshipType.USES_COPYBOOK, "CUSTREC") in rels
    assert (RelationshipType.READS_TABLE, "CUSTOMER_MASTER") in rels
    assert (RelationshipType.READS_FILE, "CUSTOMER-IN") in rels
    assert (RelationshipType.WRITES_FILE, "CUSTOMER-OUT") in rels


def test_jcl_parser_extracts_job_step_program_and_datasets() -> None:
    result = JclParser().parse(_source("jcl/DAILYJOB"))
    assert any(
        a.asset_type == AssetType.JOB and a.technical_name == "DAILYJOB" for a in result.assets
    )
    rels = {(r.relationship_type, r.target_name) for r in result.relationships}
    assert (RelationshipType.EXECUTES, "CUST001") in rels
    assert (RelationshipType.READS_DATASET, "APP.CUSTOMER.INPUT") in rels
    assert (RelationshipType.WRITES_DATASET, "APP.CUSTOMER.OUTPUT") in rels


def test_copybook_parser_estimates_fields_and_record_length() -> None:
    result = CopybookParser().parse(_source("cpy/CUSTREC"))
    copybook = next(a for a in result.assets if a.asset_type == AssetType.COPYBOOK)
    assert copybook.technical_name == "CUSTREC"
    assert copybook.attributes["field_count"] >= 5
    assert copybook.attributes["estimated_record_length"] > 40
    assert any(r.relationship_type == RelationshipType.REDEFINES for r in result.relationships)
