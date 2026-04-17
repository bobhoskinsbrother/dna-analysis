"""Unit tests for app/models.py — Pydantic models and enums."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import (
    Actionability,
    AnnotationRecord,
    ClinvarVariant,
    ConfidenceTier,
    EffectDirection,
    EffectSizeType,
    EvidenceType,
    Finding,
    GwasAssociation,
    SampleVariant,
    SourceRef,
    SourceType,
)


# ---------------------------------------------------------------------------
# U1: SampleVariant round-trips (dict -> model -> model_dump matches)
# ---------------------------------------------------------------------------

class TestSampleVariantRoundTrip:
    def test_dict_to_model_to_dict(self):
        data = {
            "rsid": "rs429358",
            "chromosome": "19",
            "position": 44908684,
            "result": "CT",
            "source_file": "myheritage_export.csv",
            "build_guess": "GRCh37",
            "imported_at": datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        }
        variant = SampleVariant(**data)
        dumped = variant.model_dump()

        assert dumped["rsid"] == data["rsid"]
        assert dumped["chromosome"] == data["chromosome"]
        assert dumped["position"] == data["position"]
        assert dumped["result"] == data["result"]
        assert dumped["source_file"] == data["source_file"]
        assert dumped["build_guess"] == data["build_guess"]
        assert dumped["imported_at"] == data["imported_at"]


# ---------------------------------------------------------------------------
# U2: SampleVariant defaults (build_guess="GRCh37", imported_at populated)
# ---------------------------------------------------------------------------

class TestSampleVariantDefaults:
    def test_build_guess_defaults_to_grch37(self):
        variant = SampleVariant(
            rsid="rs429358",
            chromosome="19",
            position=44908684,
            result="CT",
            source_file="export.csv",
        )
        assert variant.build_guess == "GRCh37"

    def test_imported_at_auto_populated(self):
        before = datetime.now(timezone.utc)
        variant = SampleVariant(
            rsid="rs429358",
            chromosome="19",
            position=44908684,
            result="CT",
            source_file="export.csv",
        )
        after = datetime.now(timezone.utc)

        assert variant.imported_at is not None
        assert before <= variant.imported_at <= after


# ---------------------------------------------------------------------------
# U3: Finding JSON matches the canonical contract from agents.md
# ---------------------------------------------------------------------------

class TestFindingCanonicalContract:
    def test_full_canonical_example(self):
        """Validate the full example JSON from the spec round-trips correctly."""
        canonical = {
            "finding_id": str(uuid.uuid4()),
            "rsid": "rs429358",
            "genotype": "CT",
            "source_type": "gwas",
            "evidence_type": "association",
            "trait_or_condition": "Type 2 diabetes",
            "effect_allele": "T",
            "effect_direction": "increased",
            "effect_size_type": "odds_ratio",
            "effect_size_value": "1.18",
            "clinical_significance": None,
            "review_status": None,
            "confidence_tier": "medium",
            "actionability": "none",
            "allowed_claims": [
                "association_only",
                "relative_odds_description",
                "not_diagnostic",
                "modestly_increased_relative_odds",
            ],
            "forbidden_claims": [
                "diagnosis",
                "absolute_risk_estimate",
                "treatment_recommendation",
                "you_will_develop",
                "this_confirms_you_have",
                "safe_or_unsafe_label",
            ],
            "user_visible_notes": [
                "This result is a population-level statistical association, not a diagnosis.",
                "A single SNP explains only a small part of overall risk for most traits.",
            ],
            "source_refs": [
                {"type": "gwas", "id": "GCST000123"},
                {"type": "pubmed", "id": "12345678"},
            ],
        }

        finding = Finding(**canonical)

        dumped = finding.model_dump()
        assert dumped["rsid"] == "rs429358"
        assert dumped["genotype"] == "CT"
        assert dumped["source_type"] == "gwas"
        assert dumped["evidence_type"] == "association"
        assert dumped["trait_or_condition"] == "Type 2 diabetes"
        assert dumped["effect_allele"] == "T"
        assert dumped["effect_direction"] == "increased"
        assert dumped["effect_size_type"] == "odds_ratio"
        assert dumped["effect_size_value"] == "1.18"
        assert dumped["clinical_significance"] is None
        assert dumped["review_status"] is None
        assert dumped["confidence_tier"] == "medium"
        assert dumped["actionability"] == "none"
        assert "association_only" in dumped["allowed_claims"]
        assert "diagnosis" in dumped["forbidden_claims"]
        assert len(dumped["user_visible_notes"]) == 2
        assert len(dumped["source_refs"]) == 2

    def test_finding_json_serialization(self):
        """Finding can serialize to JSON and back."""
        finding = Finding(
            finding_id=str(uuid.uuid4()),
            rsid="rs429358",
            genotype="CT",
            source_type="gwas",
            evidence_type="association",
            trait_or_condition="Type 2 diabetes",
            effect_allele="T",
            effect_direction="increased",
            effect_size_type="odds_ratio",
            effect_size_value="1.18",
            clinical_significance=None,
            review_status=None,
            confidence_tier="medium",
            actionability="none",
            allowed_claims=["association_only"],
            forbidden_claims=["diagnosis"],
            user_visible_notes=["Informational only."],
            source_refs=[{"type": "gwas", "id": "GCST000123"}],
        )
        json_str = finding.model_dump_json()
        restored = Finding.model_validate_json(json_str)
        assert restored.rsid == finding.rsid
        assert restored.allowed_claims == finding.allowed_claims


# ---------------------------------------------------------------------------
# U4: Finding requires allowed_claims and forbidden_claims
# ---------------------------------------------------------------------------

class TestFindingRequiredFields:
    def test_missing_allowed_claims_raises(self):
        with pytest.raises(ValidationError):
            Finding(
                finding_id=str(uuid.uuid4()),
                rsid="rs429358",
                genotype="CT",
                source_type="gwas",
                evidence_type="association",
                trait_or_condition="Type 2 diabetes",
                confidence_tier="medium",
                actionability="none",
                # allowed_claims deliberately omitted
                forbidden_claims=["diagnosis"],
                user_visible_notes=["Note."],
                source_refs=[],
            )

    def test_missing_forbidden_claims_raises(self):
        with pytest.raises(ValidationError):
            Finding(
                finding_id=str(uuid.uuid4()),
                rsid="rs429358",
                genotype="CT",
                source_type="gwas",
                evidence_type="association",
                trait_or_condition="Type 2 diabetes",
                confidence_tier="medium",
                actionability="none",
                allowed_claims=["association_only"],
                # forbidden_claims deliberately omitted
                user_visible_notes=["Note."],
                source_refs=[],
            )


# ---------------------------------------------------------------------------
# U5: AnnotationRecord accepts optional fields
# ---------------------------------------------------------------------------

class TestAnnotationRecordOptionalFields:
    def test_minimal_record(self):
        """Only rsid, genotype, source_type, and trait are required."""
        record = AnnotationRecord(
            rsid="rs429358",
            genotype="CT",
            source_type=SourceType.GWAS,
            trait_or_condition="Alzheimer's disease",
        )
        assert record.rsid == "rs429358"
        assert record.genotype == "CT"
        assert record.source_type == SourceType.GWAS
        assert record.trait_or_condition == "Alzheimer's disease"

    def test_optional_gwas_fields_default_none(self):
        record = AnnotationRecord(
            rsid="rs429358",
            genotype="CT",
            source_type=SourceType.GWAS,
            trait_or_condition="Alzheimer's disease",
        )
        assert record.p_value is None
        assert record.odds_ratio is None
        assert record.beta is None
        assert record.effect_allele is None
        assert record.study_accession is None
        assert record.pubmed_id is None

    def test_optional_clinvar_fields_default_none(self):
        record = AnnotationRecord(
            rsid="rs429358",
            genotype="CT",
            source_type=SourceType.CLINVAR,
            trait_or_condition="Alzheimer disease",
        )
        assert record.clinical_significance is None
        assert record.review_status is None
        assert record.review_stars is None
        assert record.variation_id is None

    def test_full_gwas_record(self):
        record = AnnotationRecord(
            rsid="rs429358",
            genotype="CT",
            source_type=SourceType.GWAS,
            trait_or_condition="Alzheimer's disease",
            effect_allele="T",
            p_value="3e-12",
            odds_ratio="1.18",
            study_accession="GCST000123",
            pubmed_id="12345678",
        )
        assert record.effect_allele == "T"
        assert record.p_value == "3e-12"
        assert record.odds_ratio == "1.18"
        assert record.study_accession == "GCST000123"

    def test_full_clinvar_record(self):
        record = AnnotationRecord(
            rsid="rs429358",
            genotype="CT",
            source_type=SourceType.CLINVAR,
            trait_or_condition="Alzheimer disease",
            clinical_significance="Pathogenic",
            review_status="reviewed by expert panel",
            review_stars=3,
            variation_id="12345",
        )
        assert record.clinical_significance == "Pathogenic"
        assert record.review_stars == 3


# ---------------------------------------------------------------------------
# U6: Enum values match spec strings
# ---------------------------------------------------------------------------

class TestEnumValues:
    def test_confidence_tier_values(self):
        assert ConfidenceTier.LOW == "low"
        assert ConfidenceTier.MEDIUM == "medium"
        assert ConfidenceTier.HIGH == "high"

    def test_actionability_values(self):
        assert Actionability.NONE == "none"
        assert Actionability.DISCUSS_WITH_CLINICIAN == "discuss_with_clinician"
        assert Actionability.MEDICATION_RELEVANCE == "medication_relevance"

    def test_evidence_type_values(self):
        assert EvidenceType.CLINICAL == "clinical"
        assert EvidenceType.ASSOCIATION == "association"
        assert EvidenceType.PGX == "pgx"

    def test_source_type_values(self):
        assert SourceType.GWAS == "gwas"
        assert SourceType.CLINVAR == "clinvar"
        assert SourceType.PGX == "pgx"

    def test_effect_direction_values(self):
        assert EffectDirection.INCREASED == "increased"
        assert EffectDirection.DECREASED == "decreased"
        assert EffectDirection.UNCLEAR == "unclear"

    def test_effect_size_type_values(self):
        assert EffectSizeType.ODDS_RATIO == "odds_ratio"
        assert EffectSizeType.BETA == "beta"
        assert EffectSizeType.CLASSIFICATION == "classification"
        assert EffectSizeType.NONE == "none"


# ---------------------------------------------------------------------------
# U7: SourceRef validates {"type": "gwas", "id": "GCST000123"}
# ---------------------------------------------------------------------------

class TestSourceRef:
    def test_valid_gwas_source_ref(self):
        ref = SourceRef(type="gwas", id="GCST000123")
        assert ref.type == "gwas"
        assert ref.id == "GCST000123"

    def test_valid_pubmed_source_ref(self):
        ref = SourceRef(type="pubmed", id="12345678")
        assert ref.type == "pubmed"
        assert ref.id == "12345678"

    def test_valid_clinvar_source_ref(self):
        ref = SourceRef(type="clinvar", id="12345")
        assert ref.type == "clinvar"
        assert ref.id == "12345"

    def test_source_ref_round_trip(self):
        ref = SourceRef(type="gwas", id="GCST000123")
        dumped = ref.model_dump()
        assert dumped == {"type": "gwas", "id": "GCST000123"}

    def test_source_ref_missing_type_raises(self):
        with pytest.raises(ValidationError):
            SourceRef(id="GCST000123")  # type: ignore[call-arg]

    def test_source_ref_missing_id_raises(self):
        with pytest.raises(ValidationError):
            SourceRef(type="gwas")  # type: ignore[call-arg]
