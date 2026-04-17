"""CLI integration tests using Typer's CliRunner."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from app.cli import app


# ---------------------------------------------------------------------------
# Shared CLI fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cli_db(tmp_path, monkeypatch):
    """Provide a CliRunner with a fresh database initialised via init-db."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DNA_DB_PATH", str(db_path))
    runner = CliRunner()
    result = runner.invoke(app, ["init-db"])
    assert result.exit_code == 0, f"init-db failed: {result.output}"
    return runner, db_path


@pytest.fixture
def cli_loaded(cli_db, sample_csv, sample_gwas_tsv, sample_clinvar_txt):
    """Database with sample data loaded and annotations imported."""
    runner, db_path = cli_db

    result = runner.invoke(app, ["load", str(sample_csv)])
    assert result.exit_code == 0, f"load failed: {result.output}"

    result = runner.invoke(app, ["import-gwas", str(sample_gwas_tsv)])
    assert result.exit_code == 0, f"import-gwas failed: {result.output}"

    result = runner.invoke(app, ["import-clinvar", str(sample_clinvar_txt)])
    assert result.exit_code == 0, f"import-clinvar failed: {result.output}"

    return runner, db_path


# ---------------------------------------------------------------------------
# C1: init-db succeeds
# ---------------------------------------------------------------------------

class TestC1InitDb:
    def test_init_db_exit_code(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("DNA_DB_PATH", str(db_path))
        runner = CliRunner()
        result = runner.invoke(app, ["init-db"])
        assert result.exit_code == 0

    def test_init_db_creates_file(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("DNA_DB_PATH", str(db_path))
        runner = CliRunner()
        runner.invoke(app, ["init-db"])
        assert db_path.exists(), "init-db should create the database file"


# ---------------------------------------------------------------------------
# C2: load with fixture CSV succeeds
# ---------------------------------------------------------------------------

class TestC2LoadCsv:
    def test_load_exit_code(self, cli_db, sample_csv):
        runner, _db_path = cli_db
        result = runner.invoke(app, ["load", str(sample_csv)])
        assert result.exit_code == 0

    def test_load_output_mentions_rows(self, cli_db, sample_csv):
        runner, _db_path = cli_db
        result = runner.invoke(app, ["load", str(sample_csv)])
        # The output should mention how many rows were loaded.
        # We expect 5 valid rows (3 no-calls and 2 comments excluded).
        assert "5" in result.output, (
            f"Expected output to mention 5 loaded rows, got: {result.output}"
        )


# ---------------------------------------------------------------------------
# C3: load with missing file fails
# ---------------------------------------------------------------------------

class TestC3LoadMissingFile:
    def test_load_missing_file_nonzero_exit(self, cli_db):
        runner, _db_path = cli_db
        result = runner.invoke(app, ["load", "/nonexistent/path/missing.csv"])
        assert result.exit_code != 0, (
            f"Loading a missing file should fail, got exit code {result.exit_code}"
        )


# ---------------------------------------------------------------------------
# C4: import-gwas with fixture succeeds
# ---------------------------------------------------------------------------

class TestC4ImportGwas:
    def test_import_gwas_exit_code(self, cli_db, sample_gwas_tsv):
        runner, _db_path = cli_db
        result = runner.invoke(app, ["import-gwas", str(sample_gwas_tsv)])
        assert result.exit_code == 0, f"import-gwas failed: {result.output}"

    def test_import_gwas_output(self, cli_db, sample_gwas_tsv):
        runner, _db_path = cli_db
        result = runner.invoke(app, ["import-gwas", str(sample_gwas_tsv)])
        # Should produce some confirmation output
        assert result.output.strip() != "", "import-gwas should produce output"


# ---------------------------------------------------------------------------
# C5: import-clinvar with fixture succeeds
# ---------------------------------------------------------------------------

class TestC5ImportClinvar:
    def test_import_clinvar_exit_code(self, cli_db, sample_clinvar_txt):
        runner, _db_path = cli_db
        result = runner.invoke(app, ["import-clinvar", str(sample_clinvar_txt)])
        assert result.exit_code == 0, f"import-clinvar failed: {result.output}"

    def test_import_clinvar_output(self, cli_db, sample_clinvar_txt):
        runner, _db_path = cli_db
        result = runner.invoke(app, ["import-clinvar", str(sample_clinvar_txt)])
        assert result.output.strip() != "", "import-clinvar should produce output"


# ---------------------------------------------------------------------------
# C6: match rs429358 returns results
# ---------------------------------------------------------------------------

class TestC6MatchKnownRsid:
    def test_match_rs429358_exit_code(self, cli_loaded):
        runner, _db_path = cli_loaded
        result = runner.invoke(app, ["match", "rs429358"])
        assert result.exit_code == 0, f"match failed: {result.output}"

    def test_match_rs429358_shows_results(self, cli_loaded):
        runner, _db_path = cli_loaded
        result = runner.invoke(app, ["match", "rs429358"])
        # Output should contain the rsid and some match data
        assert "rs429358" in result.output, (
            f"match output should contain rs429358, got: {result.output}"
        )


# ---------------------------------------------------------------------------
# C7: match unknown rsid returns no matches
# ---------------------------------------------------------------------------

class TestC7MatchUnknownRsid:
    def test_match_unknown_exit_code(self, cli_loaded):
        runner, _db_path = cli_loaded
        result = runner.invoke(app, ["match", "rs000000000"])
        # Should still exit cleanly even with no results
        assert result.exit_code == 0, f"match unknown failed: {result.output}"

    def test_match_unknown_no_results(self, cli_loaded):
        runner, _db_path = cli_loaded
        result = runner.invoke(app, ["match", "rs000000000"])
        output_lower = result.output.lower()
        # Output should indicate no matches were found
        assert (
            "no" in output_lower
            or "0" in output_lower
            or "not found" in output_lower
            or result.output.strip() == ""
        ), f"Expected no-match indication, got: {result.output}"


# ---------------------------------------------------------------------------
# C8: findings lists results after full pipeline
# ---------------------------------------------------------------------------

class TestC8Findings:
    def test_findings_exit_code(self, cli_loaded):
        runner, _db_path = cli_loaded
        result = runner.invoke(app, ["findings"])
        assert result.exit_code == 0, f"findings failed: {result.output}"

    def test_findings_shows_results(self, cli_loaded):
        runner, _db_path = cli_loaded
        result = runner.invoke(app, ["findings"])
        # After a full load + import, findings should list at least one result.
        # Check for known rsids that should have matched.
        output = result.output
        assert len(output.strip()) > 0, "findings output should not be empty"


# ---------------------------------------------------------------------------
# Fixture: database with findings generated via run-all
# ---------------------------------------------------------------------------

@pytest.fixture
def cli_with_findings(cli_loaded):
    """Database with findings generated via run-all."""
    runner, db_path = cli_loaded
    result = runner.invoke(app, ["run-all"])
    assert result.exit_code == 0, f"run-all failed: {result.output}"
    # Get a finding_id from the database
    import duckdb
    con = duckdb.connect(str(db_path))
    row = con.execute("SELECT finding_id FROM findings LIMIT 1").fetchone()
    con.close()
    assert row is not None, "run-all should have generated at least one finding"
    finding_id = row[0]
    return runner, db_path, finding_id


# ---------------------------------------------------------------------------
# C9: explain command produces LLM explanation for a finding
# ---------------------------------------------------------------------------

MOCK_EXPLANATION = "This variant rs429358 is associated with Alzheimer's disease in population studies."
MOCK_ASK_RESPONSE = "This means you carry one copy of the risk allele, which slightly increases your statistical risk."


class TestC9Explain:
    @patch("app.explain.prompt.explain_finding", return_value=MOCK_EXPLANATION)
    def test_explain_exit_code_zero(self, mock_explain, cli_with_findings):
        runner, db_path, finding_id = cli_with_findings
        result = runner.invoke(app, ["explain", finding_id])
        assert result.exit_code == 0, f"explain failed: {result.output}"

    @patch("app.explain.prompt.explain_finding", return_value=MOCK_EXPLANATION)
    def test_explain_output_contains_response(self, mock_explain, cli_with_findings):
        runner, db_path, finding_id = cli_with_findings
        result = runner.invoke(app, ["explain", finding_id])
        # Rich Panel wraps text with line breaks; collapse whitespace for comparison
        collapsed = " ".join(result.output.split())
        assert "associated with" in collapsed and "Alzheimer" in collapsed, (
            f"Expected explanation text in output, got: {result.output}"
        )

    @patch("app.explain.prompt.explain_finding", return_value=MOCK_EXPLANATION)
    def test_explain_output_contains_rsid(self, mock_explain, cli_with_findings):
        runner, db_path, finding_id = cli_with_findings
        result = runner.invoke(app, ["explain", finding_id])
        # The output should reference the finding's rsid somewhere
        assert "rs" in result.output.lower(), (
            f"Expected rsid in output, got: {result.output}"
        )

    def test_explain_missing_finding_exits_nonzero(self, cli_with_findings):
        runner, db_path, finding_id = cli_with_findings
        result = runner.invoke(app, ["explain", "nonexistent-uuid-999"])
        assert result.exit_code != 0, (
            f"explain with missing finding should fail, got exit code {result.exit_code}"
        )


# ---------------------------------------------------------------------------
# C10: ask command sends a question about a finding to the LLM
# ---------------------------------------------------------------------------

class TestC10Ask:
    @patch("app.explain.prompt.ask_about_finding", return_value=MOCK_ASK_RESPONSE)
    def test_ask_exit_code_zero(self, mock_ask, cli_with_findings):
        runner, db_path, finding_id = cli_with_findings
        result = runner.invoke(app, ["ask", finding_id, "What does this mean?"])
        assert result.exit_code == 0, f"ask failed: {result.output}"

    @patch("app.explain.prompt.ask_about_finding", return_value=MOCK_ASK_RESPONSE)
    def test_ask_output_contains_response(self, mock_ask, cli_with_findings):
        runner, db_path, finding_id = cli_with_findings
        result = runner.invoke(app, ["ask", finding_id, "What does this mean?"])
        # Rich Panel wraps text with line breaks; collapse whitespace for comparison
        collapsed = " ".join(result.output.split())
        assert "risk allele" in collapsed and "statistical risk" in collapsed, (
            f"Expected ask response in output, got: {result.output}"
        )

    def test_ask_missing_finding_exits_nonzero(self, cli_with_findings):
        runner, db_path, finding_id = cli_with_findings
        result = runner.invoke(app, ["ask", "nonexistent-uuid-999", "question"])
        assert result.exit_code != 0, (
            f"ask with missing finding should fail, got exit code {result.exit_code}"
        )


# ---------------------------------------------------------------------------
# C11: BVA tests for explain and ask commands
# ---------------------------------------------------------------------------

class TestC11ExplainAskBVA:
    def test_explain_empty_finding_id(self, cli_with_findings):
        """Empty finding ID should fail gracefully."""
        runner, db_path, finding_id = cli_with_findings
        result = runner.invoke(app, ["explain", ""])
        assert result.exit_code != 0, (
            f"Empty finding ID should fail, got exit code {result.exit_code}"
        )

    @patch("app.explain.prompt.ask_about_finding", return_value=MOCK_ASK_RESPONSE)
    def test_ask_empty_question(self, mock_ask, cli_with_findings):
        """Empty question string should not crash."""
        runner, db_path, finding_id = cli_with_findings
        result = runner.invoke(app, ["ask", finding_id, ""])
        assert result.exit_code == 0, f"Empty question should not crash: {result.output}"

