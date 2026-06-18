from pathlib import Path

from mip.discovery.classifier import classify
from mip.models import ArtifactType


def test_classifies_extensionless_cobol() -> None:
    result = classify(
        Path("cbl/CUST001"),
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. CUST001.",
        False,
    )
    assert result.artifact_type == ArtifactType.COBOL
    assert result.confidence >= 0.95


def test_classifies_extensionless_jcl() -> None:
    result = classify(Path("jcl/DAILY"), "//DAILY JOB (A),'X'\n//S1 EXEC PGM=ABC", False)
    assert result.artifact_type == ArtifactType.JCL


def test_classifies_extensionless_copybook() -> None:
    result = classify(Path("cpy/REC"), "       01 REC.\n          05 ID PIC X(10).", False)
    assert result.artifact_type == ArtifactType.COPYBOOK
