"""Pydantic v2 canonical models and enums for the DNA analysis pipeline."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EvidenceType(StrEnum):
    CLINICAL = "clinical"
    ASSOCIATION = "association"
    PGX = "pgx"


class ConfidenceTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Actionability(StrEnum):
    NONE = "none"
    DISCUSS_WITH_CLINICIAN = "discuss_with_clinician"
    MEDICATION_RELEVANCE = "medication_relevance"


class SourceType(StrEnum):
    GWAS = "gwas"
    CLINVAR = "clinvar"
    PGX = "pgx"


class EffectDirection(StrEnum):
    INCREASED = "increased"
    DECREASED = "decreased"
    UNCLEAR = "unclear"


class EffectSizeType(StrEnum):
    ODDS_RATIO = "odds_ratio"
    BETA = "beta"
    CLASSIFICATION = "classification"
    NONE = "none"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SampleVariant(BaseModel):
    """A single genotype row from the user's raw DNA file."""

    rsid: str
    chromosome: str
    position: int
    result: str
    source_file: str = ""
    build_guess: str = "GRCh37"
    imported_at: datetime = Field(default_factory=_utcnow)


class GwasAssociation(BaseModel):
    """A GWAS Catalog association record."""

    id: str
    rsid: str
    trait: str
    p_value: Optional[str] = None
    odds_ratio: Optional[str] = None
    beta: Optional[str] = None
    effect_allele: Optional[str] = None
    risk_frequency: Optional[str] = None
    study_accession: Optional[str] = None
    pubmed_id: Optional[str] = None
    mapped_gene: Optional[str] = None


class ClinvarVariant(BaseModel):
    """A ClinVar variant record."""

    variation_id: str
    rsid: str
    gene_symbol: Optional[str] = None
    condition_name: Optional[str] = None
    clinical_significance: Optional[str] = None
    review_status: Optional[str] = None
    review_stars: int = 0
    variation_type: Optional[str] = None


class AnnotationRecord(BaseModel):
    """Intermediate record produced by the matcher before policy scoring."""

    rsid: str
    genotype: str
    source_type: SourceType
    trait_or_condition: str
    effect_allele: Optional[str] = None
    p_value: Optional[str] = None
    odds_ratio: Optional[str] = None
    beta: Optional[str] = None
    clinical_significance: Optional[str] = None
    review_status: Optional[str] = None
    review_stars: Optional[int] = None
    mapped_gene: Optional[str] = None
    study_accession: Optional[str] = None
    pubmed_id: Optional[str] = None
    variation_id: Optional[str] = None


class SourceRef(BaseModel):
    """A reference to an external source (e.g. GWAS study, PubMed article)."""

    type: str
    id: str


class Finding(BaseModel):
    """The canonical Finding object -- contract between policy engine and LLM."""

    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rsid: str
    genotype: str
    source_type: SourceType
    evidence_type: EvidenceType
    trait_or_condition: str
    effect_allele: Optional[str] = None
    effect_direction: EffectDirection = EffectDirection.UNCLEAR
    effect_size_type: EffectSizeType = EffectSizeType.NONE
    effect_size_value: Optional[str] = None
    clinical_significance: Optional[str] = None
    review_status: Optional[str] = None
    confidence_tier: ConfidenceTier
    actionability: Actionability
    allowed_claims: list[str]
    forbidden_claims: list[str]
    user_visible_notes: list[str]
    source_refs: list[SourceRef]
    created_at: datetime = Field(default_factory=_utcnow)
