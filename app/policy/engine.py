"""Pure-logic policy engine. No database access.

Takes an AnnotationRecord and produces a Finding with confidence tier,
actionability, allowed/forbidden claims, user-visible notes, and source refs.
"""
from __future__ import annotations

import re

from app.models import (
    Actionability,
    AnnotationRecord,
    ConfidenceTier,
    EffectDirection,
    EffectSizeType,
    EvidenceType,
    Finding,
    SourceRef,
    SourceType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_p_value(raw: str | None) -> float | None:
    """Parse a p-value string into a float.

    Handles:
      - Standard scientific notation: "3e-9", "1E-12"
      - GWAS Catalog format: "2 x 10-8" meaning 2 × 10^-8
      - Plain decimals: "0.001"
      - None or empty → None
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    # GWAS Catalog format: "2 x 10-8" → 2e-8
    match = re.match(r"^([\d.]+)\s*[xX×]\s*10[-−](\d+)$", raw)
    if match:
        coefficient = float(match.group(1))
        exponent = int(match.group(2))
        return coefficient * (10 ** -exponent)

    try:
        return float(raw)
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    """Safely parse a string to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _is_pathogenic(clinical_significance: str | None) -> bool:
    """Check if ClinVar clinical significance indicates pathogenic."""
    if clinical_significance is None:
        return False
    lower = clinical_significance.lower()
    return "pathogenic" in lower and "benign" not in lower


# ---------------------------------------------------------------------------
# Core policy functions
# ---------------------------------------------------------------------------


def determine_evidence_type(record: AnnotationRecord) -> EvidenceType:
    """Map source_type to evidence_type."""
    if record.source_type == SourceType.GWAS:
        return EvidenceType.ASSOCIATION
    if record.source_type == SourceType.CLINVAR:
        return EvidenceType.CLINICAL
    return EvidenceType.PGX


def determine_confidence_tier(record: AnnotationRecord) -> ConfidenceTier:
    """Assign a confidence tier based on source-specific criteria.

    ClinVar: review_stars 4,3 → high; 2 → medium; 1,0 → low
    GWAS: p_value <= 1e-8 → medium; else → low. NEVER high for GWAS.
    """
    if record.source_type == SourceType.CLINVAR:
        stars = record.review_stars
        if stars is not None and stars >= 3:
            return ConfidenceTier.HIGH
        if stars == 2:
            return ConfidenceTier.MEDIUM
        return ConfidenceTier.LOW

    if record.source_type == SourceType.GWAS:
        p = parse_p_value(record.p_value)
        # Standard genome-wide significance threshold is 5e-8.
        if p is not None and p < 5e-8:
            return ConfidenceTier.MEDIUM
        return ConfidenceTier.LOW

    # PGx default
    return ConfidenceTier.LOW


def determine_actionability(record: AnnotationRecord) -> Actionability:
    """Assign actionability based on source type and clinical significance."""
    if record.source_type == SourceType.GWAS:
        return Actionability.NONE

    if record.source_type == SourceType.PGX:
        return Actionability.MEDICATION_RELEVANCE

    # ClinVar
    if _is_pathogenic(record.clinical_significance):
        return Actionability.DISCUSS_WITH_CLINICIAN

    return Actionability.NONE


def determine_effect_direction(record: AnnotationRecord) -> EffectDirection:
    """Determine whether the variant increases or decreases risk."""
    or_val = _parse_float(record.odds_ratio)
    if or_val is not None:
        if or_val > 1:
            return EffectDirection.INCREASED
        if or_val < 1:
            return EffectDirection.DECREASED
        return EffectDirection.UNCLEAR

    beta_val = _parse_float(record.beta)
    if beta_val is not None:
        if beta_val > 0:
            return EffectDirection.INCREASED
        if beta_val < 0:
            return EffectDirection.DECREASED
        return EffectDirection.UNCLEAR

    return EffectDirection.UNCLEAR


def determine_effect_size(record: AnnotationRecord) -> tuple[EffectSizeType, str | None]:
    """Determine effect size type and value.

    Returns a tuple of (EffectSizeType, value_string_or_none).
    EffectSizeType is a StrEnum so it compares equal to plain strings.
    """
    if record.odds_ratio is not None:
        return (EffectSizeType.ODDS_RATIO, record.odds_ratio)

    if record.beta is not None:
        return (EffectSizeType.BETA, record.beta)

    if record.source_type == SourceType.CLINVAR and record.clinical_significance:
        return (EffectSizeType.CLASSIFICATION, record.clinical_significance)

    return (EffectSizeType.NONE, None)


def build_allowed_claims(record: AnnotationRecord) -> list[str]:
    """Build the list of claim types the LLM may make for this finding."""
    evidence_type = determine_evidence_type(record)

    if evidence_type == EvidenceType.ASSOCIATION:
        claims = ["association_only", "not_diagnostic", "relative_odds_description"]
        or_val = _parse_float(record.odds_ratio)
        if or_val is not None:
            if or_val > 1:
                claims.append("modestly_increased_relative_odds")
            elif or_val < 1:
                claims.append("possibly_protective_association")
        return claims

    if evidence_type == EvidenceType.CLINICAL:
        return [
            "clinical_interpretation_summary",
            "review_status_description",
            "not_diagnostic",
        ]

    # PGx
    return ["medication_response_summary", "not_diagnostic"]


def build_forbidden_claims(record: AnnotationRecord) -> list[str]:
    """Build the list of claim types the LLM must never make."""
    evidence_type = determine_evidence_type(record)
    confidence = determine_confidence_tier(record)

    forbidden = [
        "diagnosis",
        "absolute_risk_estimate",
        "treatment_recommendation",
        "you_will_develop",
        "this_confirms_you_have",
        "safe_or_unsafe_label",
    ]

    if evidence_type == EvidenceType.CLINICAL and confidence == ConfidenceTier.LOW:
        forbidden.append("strong_clinical_assertion")

    return forbidden


def build_user_visible_notes(record: AnnotationRecord) -> list[str]:
    """Build caveats that must always accompany the result."""
    evidence_type = determine_evidence_type(record)
    confidence = determine_confidence_tier(record)
    notes: list[str] = []

    if evidence_type == EvidenceType.ASSOCIATION:
        notes.append(
            "This result is a population-level statistical association, "
            "not a diagnosis."
        )
        notes.append(
            "A single SNP explains only a small part of overall risk "
            "for most traits."
        )
    elif evidence_type == EvidenceType.CLINICAL:
        if confidence == ConfidenceTier.LOW:
            notes.append(
                "This ClinVar record has limited review status. "
                "Interpret with caution."
            )
        notes.append(
            "ClinVar classifications reflect expert review of published "
            "evidence and may change over time."
        )
    else:
        # PGx
        notes.append(
            "Pharmacogenomic associations may affect drug response. "
            "Discuss with a clinician or pharmacist."
        )

    return notes


def build_source_refs(record: AnnotationRecord) -> list[SourceRef]:
    """Build source reference list."""
    refs: list[SourceRef] = []

    if record.source_type == SourceType.GWAS:
        if record.study_accession:
            refs.append(SourceRef(type="gwas", id=record.study_accession))
        if record.pubmed_id:
            refs.append(SourceRef(type="pubmed", id=record.pubmed_id))
    elif record.source_type == SourceType.CLINVAR:
        if record.variation_id:
            refs.append(SourceRef(type="clinvar", id=record.variation_id))

    return refs


def evaluate(record: AnnotationRecord) -> Finding:
    """Main entry point. Evaluate an AnnotationRecord and produce a Finding."""
    evidence_type = determine_evidence_type(record)
    confidence = determine_confidence_tier(record)
    actionability = determine_actionability(record)
    effect_direction = determine_effect_direction(record)
    effect_size_type, effect_size_value = determine_effect_size(record)
    allowed_claims = build_allowed_claims(record)
    forbidden_claims = build_forbidden_claims(record)
    user_visible_notes = build_user_visible_notes(record)
    source_refs = build_source_refs(record)

    return Finding(
        rsid=record.rsid,
        genotype=record.genotype,
        source_type=record.source_type,
        evidence_type=evidence_type,
        trait_or_condition=record.trait_or_condition,
        effect_allele=record.effect_allele,
        effect_direction=effect_direction,
        effect_size_type=effect_size_type,
        effect_size_value=effect_size_value,
        clinical_significance=record.clinical_significance,
        review_status=record.review_status,
        confidence_tier=confidence,
        actionability=actionability,
        allowed_claims=allowed_claims,
        forbidden_claims=forbidden_claims,
        user_visible_notes=user_visible_notes,
        source_refs=source_refs,
    )
