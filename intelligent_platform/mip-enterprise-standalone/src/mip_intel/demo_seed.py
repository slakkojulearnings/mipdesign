from __future__ import annotations

from pathlib import Path

from .graph_service import GraphService
from .models import Asset, Evidence, Relationship, SourceMember, stable_id
from .repositories import SQLiteGraphRepository


def seed_demo(db_path: str | Path) -> str:
    repo = SQLiteGraphRepository(db_path)
    run_id = repo.create_run("demo://card-processing", run_id="demo-run")

    def member(path: str, artifact_type: str) -> str:
        folder, name = path.rsplit("/", 1)
        item = SourceMember(
            run_id=run_id,
            relative_path=path,
            folder_path=folder,
            member_name=name,
            sha256=stable_id("sha", path),
            size_bytes=256,
            encoding="utf-8",
            is_binary=False,
            text_status="TEXT",
            artifact_type=artifact_type,
            classification_basis="content-signature",
            confidence=1.0,
            validation_status="confirmed",
        )
        return repo.upsert_member(item)

    members = {
        "DAILYCRD": member("JCL/DAILYCRD", "JCL"),
        "CRDPOST": member("COBOL/CRDPOST", "COBOL"),
        "CRDVAL": member("COBOL/CRDVAL", "COBOL"),
        "BALUPD": member("COBOL/BALUPD", "COBOL"),
        "CARDREC": member("COPYLIB/CARDREC", "COPYBOOK"),
    }

    def asset(
        asset_type: str,
        name: str,
        member_name: str | None = None,
        validation_status: str = "confirmed",
        confidence: float = 1.0,
    ) -> str:
        item = Asset(
            run_id=run_id,
            asset_type=asset_type,
            technical_name=name,
            member_id=members.get(member_name or name),
            folder_path=(member_name or name),
            confidence=confidence,
            validation_status=validation_status,
            discovery_method="demo-seed",
        )
        return repo.upsert_asset(
            item,
            [
                Evidence(
                    source_path=f"demo/{name}",
                    line_start=1,
                    evidence_text=f"demo evidence for {name}",
                    extractor="demo-seed",
                )
            ],
        )

    ids = {
        "DAILYCRD": asset("JOB", "DAILYCRD"),
        "CRDPOST": asset("PROGRAM", "CRDPOST"),
        "CRDVAL": asset("PROGRAM", "CRDVAL"),
        "BALUPD": asset("PROGRAM", "BALUPD"),
        "CARDREC": asset("COPYBOOK", "CARDREC"),
        "CARD_MASTER": asset("TABLE", "CARD_MASTER", "BALUPD"),
        "WS-RATE-PGM": asset(
            "UNRESOLVED",
            "DYNAMIC:WS-RATE-PGM",
            "CRDPOST",
            validation_status="needs_review",
            confidence=0.35,
        ),
    }

    rels = [
        ("EXECUTES", "DAILYCRD", "CRDPOST", "confirmed", 1.0),
        ("CALLS", "CRDPOST", "CRDVAL", "confirmed", 1.0),
        ("CALLS", "CRDPOST", "BALUPD", "confirmed", 1.0),
        ("USES_COPYBOOK", "CRDPOST", "CARDREC", "confirmed", 0.98),
        ("USES_COPYBOOK", "CRDVAL", "CARDREC", "confirmed", 0.98),
        ("WRITES_TABLE", "BALUPD", "CARD_MASTER", "confirmed", 0.95),
        ("DYNAMIC_CALL", "CRDPOST", "WS-RATE-PGM", "needs_review", 0.35),
    ]
    for rel_type, source, target, status, confidence in rels:
        rel = Relationship(
            run_id=run_id,
            relationship_type=rel_type,
            source_asset_id=ids[source],
            target_asset_id=ids[target],
            confidence=confidence,
            validation_status=status,
            discovery_method="demo-seed" if status == "confirmed" else "static-inference",
        )
        repo.insert_relationship(
            rel,
            [
                Evidence(
                    source_path=f"demo/{source}",
                    line_start=10,
                    evidence_text=f"{source} {rel_type} {target}",
                    extractor="demo-seed",
                    confidence=confidence,
                    validation_status=status,
                    discovery_method=rel.discovery_method,
                )
            ],
        )

    GraphService(repo).recompute_summaries(run_id)
    repo.complete_run(run_id)
    return run_id
