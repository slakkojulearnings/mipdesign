from pathlib import Path

from typer.testing import CliRunner

from mip.cli import app

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-mainframe"


def test_cli_analyze_stats_and_validate(tmp_path: Path) -> None:
    runner = CliRunner()
    db = tmp_path / "mip.db"
    output = tmp_path / "out"

    analyzed = runner.invoke(
        app,
        ["analyze", str(SAMPLE), "--db", str(db), "--output", str(output)],
    )
    assert analyzed.exit_code == 0, analyzed.output
    assert '"files_discovered": 6' in analyzed.output

    stats = runner.invoke(app, ["stats", "--db", str(db)])
    assert stats.exit_code == 0
    assert '"PROGRAM": 2' in stats.output

    validation = runner.invoke(app, ["validate", "--db", str(db)])
    assert validation.exit_code == 0, validation.output
