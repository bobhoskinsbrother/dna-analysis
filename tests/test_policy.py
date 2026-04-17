"""Unit tests for app/policy/engine.py — policy engine scoring and claim building."""
from __future__ import annotations

import pytest

from app.models import (
    Actionability,
    AnnotationRecord,
    ConfidenceTier,
    EffectDirection,
    EvidenceType,
    Finding,
    SourceType,
)
from app.policy.engine import (
    build_allowed_claims,
    build_forbidden_claims,
    build_user_visible_notes,
    determine_actionability,
    determine_confidence_tier,
    determine_effect_direction,
    determine_effect_size,
    determine_evidence_type,
    evaluate,
    parse_p_value,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gwas_record():
    return AnnotationRecord(
        rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
        trait_or_condition="Alzheimer's disease", effect_allele="T",
        p_value="3e-12", odds_ratio="1.18",
        study_accession="GCST000123", pubmed_id="12345678",
    )


@pytest.fixture
def clinvar_record_pathogenic():
    return AnnotationRecord(
        rsid="rs429358", genotype="CT", source_type=SourceType.CLINVAR,
        trait_or_condition="Alzheimer disease",
        clinical_significance="Pathogenic",
        review_status="reviewed by expert panel", review_stars=3,
        variation_id="12345",
    )


@pytest.fixture
def clinvar_record_benign():
    return AnnotationRecord(
        rsid="rs7412", genotype="CC", source_type=SourceType.CLINVAR,
        trait_or_condition="Alzheimer disease",
        clinical_significance="Benign",
        review_status="criteria provided, multiple submitters, no conflicts",
        review_stars=2, variation_id="67890",
    )


@pytest.fixture
def clinvar_record_vus():
    return AnnotationRecord(
        rsid="rs1801133", genotype="AG", source_type=SourceType.CLINVAR,
        trait_or_condition="MTHFR deficiency",
        clinical_significance="Uncertain significance",
        review_status="criteria provided, single submitter",
        review_stars=1, variation_id="11111",
    )


# ---------------------------------------------------------------------------
# P1: GWAS -> evidence_type=association
# ---------------------------------------------------------------------------

class TestEvidenceType:
    def test_gwas_evidence_type_is_association(self, gwas_record):
        assert determine_evidence_type(gwas_record) == EvidenceType.ASSOCIATION

    # P2: ClinVar -> evidence_type=clinical
    def test_clinvar_evidence_type_is_clinical(self, clinvar_record_pathogenic):
        assert determine_evidence_type(clinvar_record_pathogenic) == EvidenceType.CLINICAL


# ---------------------------------------------------------------------------
# P3–P7: ClinVar review stars -> confidence tier (parametrized)
# ---------------------------------------------------------------------------

class TestClinvarConfidenceTier:
    @pytest.mark.parametrize(
        "stars, expected_tier",
        [
            (4, ConfidenceTier.HIGH),    # P3
            (3, ConfidenceTier.HIGH),    # P4
            (2, ConfidenceTier.MEDIUM),  # P5
            (1, ConfidenceTier.LOW),     # P6
            (0, ConfidenceTier.LOW),     # P7
        ],
        ids=["stars=4-high", "stars=3-high", "stars=2-medium", "stars=1-low", "stars=0-low"],
    )
    def test_clinvar_stars_to_confidence(self, stars, expected_tier):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.CLINVAR,
            trait_or_condition="Test condition",
            clinical_significance="Pathogenic",
            review_status="test",
            review_stars=stars,
            variation_id="99999",
        )
        assert determine_confidence_tier(record) == expected_tier


# ---------------------------------------------------------------------------
# P8–P10: GWAS p-value -> confidence tier
# ---------------------------------------------------------------------------

class TestGwasConfidenceTier:
    # P8: p <= 1e-8 -> medium
    def test_gwas_genome_wide_significance_is_medium(self):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value="3e-12",
        )
        assert determine_confidence_tier(record) == ConfidenceTier.MEDIUM

    # P9: p <= 1e-5 -> low
    def test_gwas_suggestive_is_low(self):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value="5e-7",
        )
        assert determine_confidence_tier(record) == ConfidenceTier.LOW

    # P10: p > 1e-5 -> low
    def test_gwas_weak_is_low(self):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value="0.001",
        )
        assert determine_confidence_tier(record) == ConfidenceTier.LOW


# ---------------------------------------------------------------------------
# P11: INVARIANT — GWAS never high (parametrized with multiple p-values)
# ---------------------------------------------------------------------------

class TestGwasNeverHigh:
    @pytest.mark.parametrize(
        "p_value",
        ["1e-100", "1e-50", "1e-20", "1e-12", "1e-8", "5e-9", "1e-5", "0.05"],
        ids=[
            "p=1e-100", "p=1e-50", "p=1e-20", "p=1e-12",
            "p=1e-8", "p=5e-9", "p=1e-5", "p=0.05",
        ],
    )
    def test_gwas_never_high_confidence(self, p_value):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value=p_value,
        )
        tier = determine_confidence_tier(record)
        assert tier != ConfidenceTier.HIGH, (
            f"GWAS must never be HIGH confidence, but got HIGH for p={p_value}"
        )


# ---------------------------------------------------------------------------
# P12–P16: Actionability rules
# ---------------------------------------------------------------------------

class TestActionability:
    # P12: GWAS -> actionability=none
    def test_gwas_actionability_is_none(self, gwas_record):
        assert determine_actionability(gwas_record) == Actionability.NONE

    # P13: ClinVar benign -> actionability=none
    def test_clinvar_benign_actionability_is_none(self, clinvar_record_benign):
        assert determine_actionability(clinvar_record_benign) == Actionability.NONE

    # P14: ClinVar VUS -> actionability=none
    def test_clinvar_vus_actionability_is_none(self, clinvar_record_vus):
        assert determine_actionability(clinvar_record_vus) == Actionability.NONE

    # P15: ClinVar pathogenic -> discuss_with_clinician
    def test_clinvar_pathogenic_actionability(self, clinvar_record_pathogenic):
        assert determine_actionability(clinvar_record_pathogenic) == Actionability.DISCUSS_WITH_CLINICIAN

    # P16: ClinVar likely_pathogenic -> discuss_with_clinician
    def test_clinvar_likely_pathogenic_actionability(self):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.CLINVAR,
            trait_or_condition="Test condition",
            clinical_significance="Likely pathogenic",
            review_status="reviewed by expert panel",
            review_stars=3, variation_id="99999",
        )
        assert determine_actionability(record) == Actionability.DISCUSS_WITH_CLINICIAN


# ---------------------------------------------------------------------------
# P17–P19: Effect direction
# ---------------------------------------------------------------------------

class TestEffectDirection:
    # P17: odds_ratio > 1 -> increased
    def test_or_greater_than_one_is_increased(self):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
            trait_or_condition="Test", odds_ratio="1.18",
        )
        assert determine_effect_direction(record) == EffectDirection.INCREASED

    # P18: odds_ratio < 1 -> decreased
    def test_or_less_than_one_is_decreased(self):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
            trait_or_condition="Test", odds_ratio="0.85",
        )
        assert determine_effect_direction(record) == EffectDirection.DECREASED

    # P19: No odds_ratio/beta -> unclear
    def test_no_effect_size_is_unclear(self):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
            trait_or_condition="Test",
        )
        assert determine_effect_direction(record) == EffectDirection.UNCLEAR


# ---------------------------------------------------------------------------
# P20–P25: Allowed and forbidden claims
# ---------------------------------------------------------------------------

class TestAllowedClaims:
    # P20: GWAS allowed_claims includes "association_only"
    def test_gwas_has_association_only(self, gwas_record):
        claims = build_allowed_claims(gwas_record)
        assert "association_only" in claims

    # P21: GWAS allowed_claims includes "not_diagnostic"
    def test_gwas_has_not_diagnostic(self, gwas_record):
        claims = build_allowed_claims(gwas_record)
        assert "not_diagnostic" in claims

    # P24: ClinVar allowed_claims includes "clinical_interpretation_summary"
    def test_clinvar_has_clinical_interpretation_summary(self, clinvar_record_pathogenic):
        claims = build_allowed_claims(clinvar_record_pathogenic)
        assert "clinical_interpretation_summary" in claims

    # P29: GWAS OR > 1 -> "modestly_increased_relative_odds" in allowed
    def test_gwas_or_gt_1_has_modestly_increased(self, gwas_record):
        # gwas_record has odds_ratio="1.18" (> 1)
        claims = build_allowed_claims(gwas_record)
        assert "modestly_increased_relative_odds" in claims

    # P30: GWAS OR < 1 -> "possibly_protective_association" in allowed
    def test_gwas_or_lt_1_has_possibly_protective(self):
        record = AnnotationRecord(
            rsid="rs7412", genotype="CC", source_type=SourceType.GWAS,
            trait_or_condition="Alzheimer's disease",
            odds_ratio="0.75", p_value="1e-10",
        )
        claims = build_allowed_claims(record)
        assert "possibly_protective_association" in claims


class TestForbiddenClaims:
    # P22: GWAS forbidden_claims includes "diagnosis"
    def test_gwas_forbids_diagnosis(self, gwas_record):
        claims = build_forbidden_claims(gwas_record)
        assert "diagnosis" in claims

    # P23: GWAS forbidden_claims includes "absolute_risk_estimate"
    def test_gwas_forbids_absolute_risk_estimate(self, gwas_record):
        claims = build_forbidden_claims(gwas_record)
        assert "absolute_risk_estimate" in claims

    # P25: Low confidence ClinVar -> forbidden "strong_clinical_assertion"
    def test_low_confidence_clinvar_forbids_strong_assertion(self, clinvar_record_vus):
        # clinvar_record_vus has review_stars=1 -> low confidence
        claims = build_forbidden_claims(clinvar_record_vus)
        assert "strong_clinical_assertion" in claims


# ---------------------------------------------------------------------------
# P26: evaluate() returns complete Finding with all fields
# ---------------------------------------------------------------------------

class TestEvaluate:
    def test_evaluate_returns_complete_finding(self, gwas_record):
        finding = evaluate(gwas_record)
        assert isinstance(finding, Finding)

        # All required fields are present and non-None
        assert finding.finding_id is not None
        assert finding.rsid == "rs429358"
        assert finding.genotype == "CT"
        assert finding.source_type is not None
        assert finding.evidence_type is not None
        assert finding.trait_or_condition == "Alzheimer's disease"
        assert finding.confidence_tier is not None
        assert finding.actionability is not None
        assert finding.allowed_claims is not None
        assert isinstance(finding.allowed_claims, list)
        assert len(finding.allowed_claims) > 0
        assert finding.forbidden_claims is not None
        assert isinstance(finding.forbidden_claims, list)
        assert len(finding.forbidden_claims) > 0
        assert finding.user_visible_notes is not None
        assert isinstance(finding.user_visible_notes, list)
        assert finding.source_refs is not None
        assert isinstance(finding.source_refs, list)

    def test_evaluate_clinvar_returns_finding(self, clinvar_record_pathogenic):
        finding = evaluate(clinvar_record_pathogenic)
        assert isinstance(finding, Finding)
        assert finding.evidence_type == "clinical"
        assert finding.confidence_tier == "high"
        assert finding.actionability == "discuss_with_clinician"


# ---------------------------------------------------------------------------
# P27: user_visible_notes non-empty for any record
# ---------------------------------------------------------------------------

class TestUserVisibleNotes:
    def test_gwas_notes_non_empty(self, gwas_record):
        notes = build_user_visible_notes(gwas_record)
        assert isinstance(notes, list)
        assert len(notes) > 0

    def test_clinvar_notes_non_empty(self, clinvar_record_pathogenic):
        notes = build_user_visible_notes(clinvar_record_pathogenic)
        assert isinstance(notes, list)
        assert len(notes) > 0

    def test_clinvar_benign_notes_non_empty(self, clinvar_record_benign):
        notes = build_user_visible_notes(clinvar_record_benign)
        assert isinstance(notes, list)
        assert len(notes) > 0

    def test_clinvar_vus_notes_non_empty(self, clinvar_record_vus):
        notes = build_user_visible_notes(clinvar_record_vus)
        assert isinstance(notes, list)
        assert len(notes) > 0


# ---------------------------------------------------------------------------
# P28: source_refs populated for GWAS with study_accession
# ---------------------------------------------------------------------------

class TestSourceRefs:
    def test_gwas_with_study_accession_has_source_refs(self, gwas_record):
        finding = evaluate(gwas_record)
        assert len(finding.source_refs) > 0
        ref_types = [ref["type"] if isinstance(ref, dict) else ref.type for ref in finding.source_refs]
        assert "gwas" in ref_types

    def test_gwas_with_pubmed_has_pubmed_ref(self, gwas_record):
        finding = evaluate(gwas_record)
        ref_types = [ref["type"] if isinstance(ref, dict) else ref.type for ref in finding.source_refs]
        assert "pubmed" in ref_types


# ---------------------------------------------------------------------------
# P31: p_value parsing handles various formats
# ---------------------------------------------------------------------------

class TestPValueParsing:
    @pytest.mark.parametrize(
        "p_value_str, expected_tier",
        [
            ("3e-9", ConfidenceTier.MEDIUM),     # standard scientific notation
            ("1E-12", ConfidenceTier.MEDIUM),     # uppercase E
            ("2 x 10-8", ConfidenceTier.MEDIUM),  # GWAS catalog format
            ("5e-6", ConfidenceTier.LOW),          # between 1e-8 and 1e-5
            ("0.001", ConfidenceTier.LOW),         # plain decimal
        ],
        ids=["3e-9", "1E-12", "2x10-8", "5e-6", "0.001"],
    )
    def test_p_value_parsing_formats(self, p_value_str, expected_tier):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value=p_value_str,
        )
        tier = determine_confidence_tier(record)
        assert tier == expected_tier, (
            f"p_value='{p_value_str}' should give {expected_tier}, got {tier}"
        )


# ---------------------------------------------------------------------------
# P29/P30 (additional parametrized): effect_size for GWAS
# ---------------------------------------------------------------------------

class TestEffectSize:
    def test_gwas_with_odds_ratio(self, gwas_record):
        size_type, size_value = determine_effect_size(gwas_record)
        assert size_type == "odds_ratio"
        assert size_value == "1.18"

    def test_gwas_without_effect_size(self):
        record = AnnotationRecord(
            rsid="rs429358", genotype="CT", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value="3e-12",
        )
        size_type, size_value = determine_effect_size(record)
        assert size_type == "none"

    def test_clinvar_classification_effect_size(self, clinvar_record_pathogenic):
        size_type, size_value = determine_effect_size(clinvar_record_pathogenic)
        assert size_type == "classification"
        assert size_value == "Pathogenic"


# ---------------------------------------------------------------------------
# BVA: Policy engine boundary values
# ---------------------------------------------------------------------------

class TestPolicyBoundaryValues:
    """Boundary value analysis for policy engine functions."""

    def test_or_exactly_one_is_unclear(self):
        """OR = 1.0 exactly should produce UNCLEAR direction (not increased or decreased)."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", odds_ratio="1.0",
        )
        result = determine_effect_direction(record)
        assert result == EffectDirection.UNCLEAR

    def test_or_just_above_one_is_increased(self):
        """OR = 1.001 should produce INCREASED."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", odds_ratio="1.001",
        )
        result = determine_effect_direction(record)
        assert result == EffectDirection.INCREASED

    def test_or_just_below_one_is_decreased(self):
        """OR = 0.999 should produce DECREASED."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", odds_ratio="0.999",
        )
        result = determine_effect_direction(record)
        assert result == EffectDirection.DECREASED

    def test_pvalue_at_genome_wide_boundary(self):
        """p = 5e-8 exactly -- ON point for genome-wide significance threshold."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value="5e-8",
        )
        result = determine_confidence_tier(record)
        # Code uses p < 5e-8, so exactly 5e-8 should be LOW
        assert result == ConfidenceTier.LOW

    def test_pvalue_just_below_genome_wide(self):
        """p = 4.9e-8 -- IN point, should be MEDIUM."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value="4.9e-8",
        )
        result = determine_confidence_tier(record)
        assert result == ConfidenceTier.MEDIUM

    def test_pvalue_just_above_genome_wide(self):
        """p = 5.1e-8 -- OFF point, should be LOW."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value="5.1e-8",
        )
        result = determine_confidence_tier(record)
        assert result == ConfidenceTier.LOW

    def test_review_stars_boundary_two_three(self):
        """Stars=2 is MEDIUM, stars=3 is HIGH -- verify boundary."""
        record_2 = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.CLINVAR,
            trait_or_condition="Test", review_stars=2,
        )
        record_3 = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.CLINVAR,
            trait_or_condition="Test", review_stars=3,
        )
        assert determine_confidence_tier(record_2) == ConfidenceTier.MEDIUM
        assert determine_confidence_tier(record_3) == ConfidenceTier.HIGH

    def test_pvalue_none_gives_low(self):
        """None p_value should result in LOW confidence."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value=None,
        )
        result = determine_confidence_tier(record)
        assert result == ConfidenceTier.LOW

    def test_pvalue_empty_string_gives_low(self):
        """Empty string p_value should result in LOW confidence."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", p_value="",
        )
        result = determine_confidence_tier(record)
        assert result == ConfidenceTier.LOW

    def test_or_zero_gives_unclear_or_decreased(self):
        """OR = 0 should be DECREASED (< 1)."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", odds_ratio="0",
        )
        result = determine_effect_direction(record)
        assert result == EffectDirection.DECREASED

    def test_pathogenic_case_insensitive(self):
        """'pathogenic' lowercase should trigger discuss_with_clinician."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.CLINVAR,
            trait_or_condition="Test", clinical_significance="pathogenic",
        )
        result = determine_actionability(record)
        assert result == Actionability.DISCUSS_WITH_CLINICIAN

    def test_pathogenic_with_trailing_space(self):
        """'Pathogenic ' with trailing space should still trigger."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.CLINVAR,
            trait_or_condition="Test", clinical_significance="Pathogenic ",
        )
        result = determine_actionability(record)
        assert result == Actionability.DISCUSS_WITH_CLINICIAN

    def test_high_confidence_clinvar_no_strong_clinical_assertion_forbidden(self):
        """High confidence ClinVar should NOT have strong_clinical_assertion in forbidden claims."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.CLINVAR,
            trait_or_condition="Test", clinical_significance="Pathogenic",
            review_stars=4,
        )
        forbidden = build_forbidden_claims(record)
        assert "strong_clinical_assertion" not in forbidden

    def test_or_above_one_adds_modestly_increased(self):
        """OR > 1 should add modestly_increased_relative_odds to allowed claims."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", odds_ratio="1.5",
        )
        allowed = build_allowed_claims(record)
        assert "modestly_increased_relative_odds" in allowed

    def test_or_below_one_adds_possibly_protective(self):
        """OR < 1 should add possibly_protective_association to allowed claims."""
        record = AnnotationRecord(
            rsid="rs1", genotype="AA", source_type=SourceType.GWAS,
            trait_or_condition="Test", odds_ratio="0.7",
        )
        allowed = build_allowed_claims(record)
        assert "possibly_protective_association" in allowed


# ---------------------------------------------------------------------------
# BVA: parse_p_value boundary values
# ---------------------------------------------------------------------------

class TestParsePValueBVA:
    """Boundary value tests for p-value parsing."""

    def test_parse_none(self):
        assert parse_p_value(None) is None

    def test_parse_empty_string(self):
        assert parse_p_value("") is None

    def test_parse_whitespace(self):
        assert parse_p_value("   ") is None

    def test_parse_standard_scientific(self):
        result = parse_p_value("3e-9")
        assert result is not None
        assert abs(result - 3e-9) < 1e-15

    def test_parse_gwas_format(self):
        """GWAS catalog 'N x 10-M' format."""
        result = parse_p_value("2 x 10-8")
        assert result is not None
        assert abs(result - 2e-8) < 1e-15

    def test_parse_plain_decimal(self):
        result = parse_p_value("0.001")
        assert result is not None
        assert abs(result - 0.001) < 1e-10

    def test_parse_invalid_string(self):
        """Non-numeric string should return None."""
        assert parse_p_value("not_a_number") is None

    def test_parse_negative_coefficient(self):
        """Negative p-value makes no sense, but parse_p_value should handle gracefully."""
        result = parse_p_value("-3e-9")
        # Implementation-dependent: may return negative float or None
        # The key is it shouldn't crash
        assert result is None or isinstance(result, float)
