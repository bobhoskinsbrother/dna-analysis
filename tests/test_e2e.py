"""End-to-end pipeline tests — load, annotate, match, evaluate."""
from __future__ import annotations

import json
import uuid

import duckdb
import pytest

from app.db import init_schema
from app.ingest.loader import load_file
from app.annotate.importer import import_gwas_catalog, import_clinvar
from app.annotate.matcher import match_all
from app.policy.engine import evaluate
from app.models import Finding, SourceType, ConfidenceTier


# ---------------------------------------------------------------------------
# Canonical Finding contract — required top-level keys
# ---------------------------------------------------------------------------

CANONICAL_KEYS = {
    "finding_id",
    "rsid",
    "genotype",
    "source_type",
    "evidence_type",
    "trait_or_condition",
    "effect_allele",
    "effect_direction",
    "effect_size_type",
    "effect_size_value",
    "clinical_significance",
    "review_status",
    "confidence_tier",
    "actionability",
    "allowed_claims",
    "forbidden_claims",
    "user_visible_notes",
    "source_refs",
}


# ---------------------------------------------------------------------------
# Pipeline fixture — runs load -> import -> match -> evaluate
# ---------------------------------------------------------------------------

@pytest.fixture
def full_pipeline(tmp_path, sample_csv, sample_gwas_tsv, sample_clinvar_txt):
    """Run the complete pipeline and return (connection, findings)."""
    con = duckdb.connect(":memory:")
    init_schema(con)
    load_file(con, sample_csv)
    import_gwas_catalog(con, sample_gwas_tsv)
    import_clinvar(con, sample_clinvar_txt)
    records = match_all(con)
    findings = [evaluate(r) for r in records]
    yield con, findings
    con.close()


# ---------------------------------------------------------------------------
# E1: Full pipeline produces findings
# ---------------------------------------------------------------------------

class TestE1FullPipelineProducesFindings:
    def test_findings_not_empty(self, full_pipeline):
        _con, findings = full_pipeline
        assert len(findings) > 0, "Pipeline should produce at least one finding"

    def test_each_finding_is_valid(self, full_pipeline):
        _con, findings = full_pipeline
        for f in findings:
            assert isinstance(f, Finding), f"Expected Finding, got {type(f)}"


# ---------------------------------------------------------------------------
# E2: rs429358 produces expected Finding
# ---------------------------------------------------------------------------

class TestE2Rs429358Finding:
    @staticmethod
    def _find_rs429358(findings: list[Finding]) -> list[Finding]:
        return [f for f in findings if f.rsid == "rs429358"]

    def test_rs429358_present(self, full_pipeline):
        _con, findings = full_pipeline
        matches = self._find_rs429358(findings)
        assert len(matches) >= 1, "rs429358 should produce at least one finding"

    def test_rs429358_genotype(self, full_pipeline):
        _con, findings = full_pipeline
        for f in self._find_rs429358(findings):
            assert f.genotype == "CT"

    def test_rs429358_has_source_types(self, full_pipeline):
        _con, findings = full_pipeline
        source_types = {f.source_type for f in self._find_rs429358(findings)}
        # rs429358 appears in both GWAS and ClinVar fixtures
        assert SourceType.GWAS in source_types or SourceType.CLINVAR in source_types

    def test_rs429358_confidence_tier_valid(self, full_pipeline):
        _con, findings = full_pipeline
        valid_tiers = {ConfidenceTier.LOW, ConfidenceTier.MEDIUM, ConfidenceTier.HIGH}
        for f in self._find_rs429358(findings):
            assert f.confidence_tier in valid_tiers


# ---------------------------------------------------------------------------
# E3: No-call rows are not loaded into sample_variants
# ---------------------------------------------------------------------------

class TestE3NoCallsExcluded:
    def test_no_call_dash_dash_not_in_db(self, full_pipeline):
        con, _findings = full_pipeline
        rows = con.execute(
            "SELECT rsid FROM sample_variants WHERE rsid = 'rs12345'"
        ).fetchall()
        assert len(rows) == 0, "rs12345 (--) should not be in sample_variants"

    def test_no_call_zero_zero_not_in_db(self, full_pipeline):
        con, _findings = full_pipeline
        rows = con.execute(
            "SELECT rsid FROM sample_variants WHERE rsid = 'rs99999'"
        ).fetchall()
        assert len(rows) == 0, "rs99999 (00) should not be in sample_variants"

    def test_no_call_empty_not_in_db(self, full_pipeline):
        con, _findings = full_pipeline
        rows = con.execute(
            "SELECT rsid FROM sample_variants WHERE rsid = 'rs77777'"
        ).fetchall()
        assert len(rows) == 0, "rs77777 (empty) should not be in sample_variants"


# ---------------------------------------------------------------------------
# E4: Unmatched variant produces no finding
# ---------------------------------------------------------------------------

class TestE4UnmatchedVariant:
    def test_rs1234567_in_sample_variants(self, full_pipeline):
        """rs1234567 is loaded (valid genotype GG) but has no annotation match."""
        con, _findings = full_pipeline
        rows = con.execute(
            "SELECT rsid FROM sample_variants WHERE rsid = 'rs1234567'"
        ).fetchall()
        assert len(rows) == 1, "rs1234567 should be in sample_variants"

    def test_rs1234567_not_in_findings(self, full_pipeline):
        """rs1234567 has no annotation, so it should produce no finding."""
        _con, findings = full_pipeline
        matched = [f for f in findings if f.rsid == "rs1234567"]
        assert len(matched) == 0, "rs1234567 should not produce a finding"


# ---------------------------------------------------------------------------
# E5: Every Finding serializes to JSON matching canonical contract
# ---------------------------------------------------------------------------

class TestE5FindingCanonicalContract:
    def test_all_findings_have_canonical_keys(self, full_pipeline):
        _con, findings = full_pipeline
        for f in findings:
            json_str = f.model_dump_json()
            data = json.loads(json_str)
            missing = CANONICAL_KEYS - set(data.keys())
            assert not missing, (
                f"Finding for {f.rsid} missing canonical keys: {missing}"
            )

    def test_all_findings_json_round_trip(self, full_pipeline):
        _con, findings = full_pipeline
        for f in findings:
            json_str = f.model_dump_json()
            restored = Finding.model_validate_json(json_str)
            assert restored.rsid == f.rsid
            assert restored.genotype == f.genotype
            assert restored.source_type == f.source_type
            assert restored.confidence_tier == f.confidence_tier

    def test_source_refs_are_list_of_dicts(self, full_pipeline):
        _con, findings = full_pipeline
        for f in findings:
            assert isinstance(f.source_refs, list)
            for ref in f.source_refs:
                dumped = ref.model_dump() if hasattr(ref, "model_dump") else ref
                assert "type" in dumped
                assert "id" in dumped


# ---------------------------------------------------------------------------
# E6: ClinVar pathogenic finding has actionability=discuss_with_clinician
# ---------------------------------------------------------------------------

class TestE6ClinvarPathogenicActionability:
    def test_rs334_pathogenic_actionability(self, full_pipeline):
        """rs334 (HBB, sickle cell) is Pathogenic in ClinVar with practice guideline."""
        _con, findings = full_pipeline
        rs334_findings = [
            f for f in findings
            if f.rsid == "rs334" and f.source_type == SourceType.CLINVAR
        ]
        assert len(rs334_findings) >= 1, "rs334 should have a ClinVar finding"
        for f in rs334_findings:
            assert f.actionability == "discuss_with_clinician", (
                f"Pathogenic ClinVar finding should have "
                f"actionability=discuss_with_clinician, got {f.actionability}"
            )

    def test_rs334_confidence_tier_high(self, full_pipeline):
        """rs334 has practice guideline (4 stars) -> high confidence."""
        _con, findings = full_pipeline
        rs334_findings = [
            f for f in findings
            if f.rsid == "rs334" and f.source_type == SourceType.CLINVAR
        ]
        for f in rs334_findings:
            assert f.confidence_tier == ConfidenceTier.HIGH, (
                f"Practice guideline ClinVar should be high confidence, "
                f"got {f.confidence_tier}"
            )


# ---------------------------------------------------------------------------
# E7: INVARIANT — GWAS findings never have high confidence tier
# ---------------------------------------------------------------------------

class TestE7GwasNeverHighConfidence:
    def test_no_gwas_finding_is_high_confidence(self, full_pipeline):
        """Design invariant: GWAS associations are never assigned high confidence."""
        _con, findings = full_pipeline
        gwas_findings = [f for f in findings if f.source_type == SourceType.GWAS]
        assert len(gwas_findings) > 0, "Should have at least one GWAS finding"
        for f in gwas_findings:
            assert f.confidence_tier != ConfidenceTier.HIGH, (
                f"GWAS finding for {f.rsid} must not have high confidence tier, "
                f"got {f.confidence_tier}"
            )


# ---------------------------------------------------------------------------
# E8: Pipeline-produced Finding generates valid LLM prompt messages
# ---------------------------------------------------------------------------

class TestE8FindingProducesValidPrompt:
    """Tests that a real pipeline-produced Finding generates correct prompt messages."""

    def test_pipeline_finding_produces_explain_messages(self, full_pipeline):
        from app.explain.contract import SYSTEM_PROMPT
        from app.explain.prompt import build_messages_for_explain

        _con, findings = full_pipeline
        finding = findings[0]
        messages = build_messages_for_explain(finding)
        assert isinstance(messages, list)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert finding.rsid in messages[1]["content"]

    def test_pipeline_finding_context_contains_all_fields(self, full_pipeline):
        from app.explain.prompt import build_finding_context

        _con, findings = full_pipeline
        finding = findings[0]
        context = build_finding_context(finding)
        assert finding.rsid in context
        assert finding.genotype in context
        assert finding.trait_or_condition in context
        assert finding.evidence_type.value in context

    def test_pipeline_finding_context_has_claims_sections(self, full_pipeline):
        from app.explain.prompt import build_finding_context

        _con, findings = full_pipeline
        finding = findings[0]
        context = build_finding_context(finding)
        assert "ALLOWED CLAIMS" in context
        assert "FORBIDDEN CLAIMS" in context
        assert "REQUIRED CAVEATS" in context


# ---------------------------------------------------------------------------
# E9: Every finding's forbidden/allowed claims and notes appear in its context
# ---------------------------------------------------------------------------

class TestE9ForbiddenClaimsInContext:
    """Tests that every pipeline-produced finding's claims and notes appear in its context."""

    def test_all_findings_forbidden_claims_in_context(self, full_pipeline):
        from app.explain.prompt import build_finding_context

        _con, findings = full_pipeline
        for f in findings:
            context = build_finding_context(f)
            for claim in f.forbidden_claims:
                assert claim in context, (
                    f"Forbidden claim '{claim}' missing from context for {f.rsid}"
                )

    def test_all_findings_allowed_claims_in_context(self, full_pipeline):
        from app.explain.prompt import build_finding_context

        _con, findings = full_pipeline
        for f in findings:
            context = build_finding_context(f)
            for claim in f.allowed_claims:
                assert claim in context, (
                    f"Allowed claim '{claim}' missing from context for {f.rsid}"
                )

    def test_all_findings_user_notes_in_context(self, full_pipeline):
        from app.explain.prompt import build_finding_context

        _con, findings = full_pipeline
        for f in findings:
            context = build_finding_context(f)
            for note in f.user_visible_notes:
                assert note in context, (
                    f"User note '{note}' missing from context for {f.rsid}"
                )
