"""Tests for app/explain/contract.py and app/explain/prompt.py — LLM prompt rules.

RED phase: these modules do not exist yet, so all tests will fail with
ImportError.  That is expected and correct.
"""
from __future__ import annotations

import pytest

from app.models import (
    AnnotationRecord,
    ConfidenceTier,
    Finding,
    SourceRef,
    SourceType,
    EvidenceType,
    EffectDirection,
    EffectSizeType,
    Actionability,
)
from app.policy.engine import evaluate

from app.explain.contract import (
    ALLOWED_CLAIM_TYPES,
    ANSWER_STRUCTURE_STEPS,
    FORBIDDEN_CLAIM_TYPES,
    FORBIDDEN_PHRASES,
    PREFERRED_LANGUAGE,
    SYSTEM_PROMPT,
)
from app.explain.prompt import (
    build_finding_context,
    build_messages_for_ask,
    build_messages_for_explain,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gwas_finding():
    record = AnnotationRecord(
        rsid="rs429358",
        genotype="CT",
        source_type=SourceType.GWAS,
        trait_or_condition="Alzheimer's disease",
        effect_allele="T",
        p_value="3e-12",
        odds_ratio="1.18",
        study_accession="GCST000001",
        pubmed_id="19734902",
    )
    return evaluate(record)


@pytest.fixture
def clinvar_finding_high():
    record = AnnotationRecord(
        rsid="rs334",
        genotype="AA",
        source_type=SourceType.CLINVAR,
        trait_or_condition="Sickle cell anemia",
        clinical_significance="Pathogenic",
        review_status="practice guideline",
        review_stars=4,
        variation_id="11111",
    )
    return evaluate(record)


@pytest.fixture
def clinvar_finding_low():
    record = AnnotationRecord(
        rsid="rs1801133",
        genotype="AG",
        source_type=SourceType.CLINVAR,
        trait_or_condition="MTHFR deficiency",
        clinical_significance="Uncertain significance",
        review_status="criteria provided, single submitter",
        review_stars=1,
        variation_id="22222",
    )
    return evaluate(record)


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------


class TestContractConstants:
    """Verify the contract module exports correct constant sets."""

    def test_forbidden_phrases_complete(self):
        expected = {
            "confirms",
            "proves",
            "means you have",
            "safe",
            "unsafe",
            "normal",
            "abnormal",
            "will develop",
            "will not develop",
            "guaranteed",
            "definitive",
        }
        assert expected == FORBIDDEN_PHRASES

    def test_forbidden_phrases_is_frozenset(self):
        assert isinstance(FORBIDDEN_PHRASES, frozenset)

    def test_allowed_claim_types_complete(self):
        expected = {
            "association_only",
            "relative_odds_description",
            "not_diagnostic",
            "modestly_increased_relative_odds",
            "possibly_protective_association",
            "clinical_interpretation_summary",
            "review_status_description",
            "medication_response_summary",
        }
        assert expected == ALLOWED_CLAIM_TYPES

    def test_allowed_claim_types_is_frozenset(self):
        assert isinstance(ALLOWED_CLAIM_TYPES, frozenset)

    def test_forbidden_claim_types_complete(self):
        expected = {
            "diagnosis",
            "absolute_risk_estimate",
            "treatment_recommendation",
            "you_will_develop",
            "this_confirms_you_have",
            "safe_or_unsafe_label",
            "strong_clinical_assertion",
        }
        assert expected == FORBIDDEN_CLAIM_TYPES

    def test_forbidden_claim_types_is_frozenset(self):
        assert isinstance(FORBIDDEN_CLAIM_TYPES, frozenset)

    def test_allowed_and_forbidden_claims_disjoint(self):
        overlap = ALLOWED_CLAIM_TYPES & FORBIDDEN_CLAIM_TYPES
        assert overlap == set(), (
            f"allowed and forbidden claim types must not overlap, but share: {overlap}"
        )


# ---------------------------------------------------------------------------
# Cross-module: policy engine claims are subsets of contract
# ---------------------------------------------------------------------------


class TestPolicyEngineClaimsSubsetOfContract:
    """Ensure every claim string the policy engine emits is declared in the contract."""

    def test_gwas_allowed_claims_in_contract(self, gwas_finding):
        for claim in gwas_finding.allowed_claims:
            assert claim in ALLOWED_CLAIM_TYPES, (
                f"GWAS allowed claim '{claim}' is not in ALLOWED_CLAIM_TYPES"
            )

    def test_clinvar_allowed_claims_in_contract(self, clinvar_finding_high):
        for claim in clinvar_finding_high.allowed_claims:
            assert claim in ALLOWED_CLAIM_TYPES, (
                f"ClinVar allowed claim '{claim}' is not in ALLOWED_CLAIM_TYPES"
            )

    def test_gwas_forbidden_claims_in_contract(self, gwas_finding):
        for claim in gwas_finding.forbidden_claims:
            assert claim in FORBIDDEN_CLAIM_TYPES, (
                f"GWAS forbidden claim '{claim}' is not in FORBIDDEN_CLAIM_TYPES"
            )

    def test_clinvar_forbidden_claims_in_contract(self, clinvar_finding_high):
        for claim in clinvar_finding_high.forbidden_claims:
            assert claim in FORBIDDEN_CLAIM_TYPES, (
                f"ClinVar forbidden claim '{claim}' is not in FORBIDDEN_CLAIM_TYPES"
            )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """Verify the system prompt embeds every hard rule, preferred phrase, and answer step."""

    @pytest.mark.parametrize(
        "marker",
        [
            "Only discuss findings that are present",
            "Do not invent rsIDs",
            "Never present a GWAS association as a diagnosis",
            "Never provide an absolute risk estimate",
            "Distinguish clearly between the three evidence types",
            'confidence_tier is "low"',
            "review_status is present and reflects a weak review",
            'actionability is "none"',
            'actionability is "discuss_with_clinician"',
            'actionability is "medication_relevance"',
            "Never use the words",
            "Always include at least one caveat",
            "beyond the allowed_claims",
        ],
        ids=[
            "rule-1-only-present-findings",
            "rule-2-no-invented-rsids",
            "rule-3-no-gwas-as-diagnosis",
            "rule-4-no-absolute-risk",
            "rule-5-distinguish-evidence-types",
            "rule-6-low-confidence-hedge",
            "rule-7-weak-review-hedge",
            "rule-8-actionability-none",
            "rule-9-actionability-discuss",
            "rule-10-actionability-medication",
            "rule-11-forbidden-words",
            "rule-12-always-caveat",
            "rule-13-no-beyond-allowed",
        ],
    )
    def test_system_prompt_contains_hard_rules(self, marker):
        assert marker in SYSTEM_PROMPT, (
            f"SYSTEM_PROMPT is missing hard rule marker: {marker!r}"
        )

    @pytest.mark.parametrize(
        "phrase",
        [
            "associated with",
            "linked to in population studies",
            "may modestly increase relative odds",
            "may be protective in some studies",
            "not diagnostic on its own",
            "one small contributor to overall risk",
            "the evidence here is limited",
            "worth discussing with a clinician if relevant to your personal history",
        ],
        ids=[
            "pref-associated-with",
            "pref-linked-to-in-population",
            "pref-modestly-increase",
            "pref-protective",
            "pref-not-diagnostic",
            "pref-one-small-contributor",
            "pref-evidence-limited",
            "pref-worth-discussing",
        ],
    )
    def test_system_prompt_contains_preferred_language(self, phrase):
        assert phrase in SYSTEM_PROMPT, (
            f"SYSTEM_PROMPT is missing preferred language phrase: {phrase!r}"
        )

    @pytest.mark.parametrize(
        "step",
        [
            "What was found",
            "What it may mean",
            "How strong the evidence is",
            "What this does not mean",
            "Reasonable next step",
        ],
        ids=[
            "step-1-what-found",
            "step-2-what-may-mean",
            "step-3-evidence-strength",
            "step-4-what-not-mean",
            "step-5-next-step",
        ],
    )
    def test_system_prompt_contains_answer_structure(self, step):
        assert step in SYSTEM_PROMPT, (
            f"SYSTEM_PROMPT is missing answer structure step: {step!r}"
        )

    def test_system_prompt_is_nonempty_string(self):
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 0


# ---------------------------------------------------------------------------
# build_finding_context
# ---------------------------------------------------------------------------


class TestBuildFindingContext:
    """Verify the finding context string includes all required sections."""

    def test_context_contains_rsid(self, gwas_finding):
        context = build_finding_context(gwas_finding)
        assert gwas_finding.rsid in context

    def test_context_contains_allowed_claims_section(self, gwas_finding):
        context = build_finding_context(gwas_finding)
        assert "ALLOWED CLAIMS" in context
        for claim in gwas_finding.allowed_claims:
            assert claim in context, (
                f"allowed claim '{claim}' missing from context"
            )

    def test_context_contains_forbidden_claims_section(self, gwas_finding):
        context = build_finding_context(gwas_finding)
        assert "FORBIDDEN CLAIMS" in context
        for claim in gwas_finding.forbidden_claims:
            assert claim in context, (
                f"forbidden claim '{claim}' missing from context"
            )

    def test_context_contains_caveats_section(self, gwas_finding):
        context = build_finding_context(gwas_finding)
        assert "REQUIRED CAVEATS" in context
        for note in gwas_finding.user_visible_notes:
            assert note in context, (
                f"user visible note missing from context: {note!r}"
            )


# ---------------------------------------------------------------------------
# build_messages_for_explain / build_messages_for_ask
# ---------------------------------------------------------------------------


class TestBuildMessages:
    """Verify message list structure for explain and ask flows."""

    def test_explain_messages_has_two_items(self, gwas_finding):
        messages = build_messages_for_explain(gwas_finding)
        assert isinstance(messages, list)
        assert len(messages) == 2

    def test_explain_system_role(self, gwas_finding):
        messages = build_messages_for_explain(gwas_finding)
        assert messages[0]["role"] == "system"

    def test_explain_system_content_is_system_prompt(self, gwas_finding):
        messages = build_messages_for_explain(gwas_finding)
        assert messages[0]["content"] == SYSTEM_PROMPT

    def test_explain_user_role(self, gwas_finding):
        messages = build_messages_for_explain(gwas_finding)
        assert messages[1]["role"] == "user"

    def test_explain_user_contains_rsid(self, gwas_finding):
        messages = build_messages_for_explain(gwas_finding)
        assert gwas_finding.rsid in messages[1]["content"]

    def test_ask_messages_contain_question(self, gwas_finding):
        question = "What does this variant mean for my health?"
        messages = build_messages_for_ask(gwas_finding, question)
        user_messages = [m for m in messages if m["role"] == "user"]
        assert any(question in m["content"] for m in user_messages), (
            "question text not found in any user message"
        )

    def test_ask_system_is_same_prompt(self, gwas_finding):
        question = "Is this a risk factor?"
        messages = build_messages_for_ask(gwas_finding, question)
        assert messages[0]["content"] == SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Cross-module invariants: contract vs policy engine
# ---------------------------------------------------------------------------


class TestContractVsPolicy:
    """Cross-module invariants linking the contract to the policy engine."""

    def test_every_forbidden_phrase_in_system_prompt(self):
        for phrase in FORBIDDEN_PHRASES:
            assert phrase in SYSTEM_PROMPT, (
                f"forbidden phrase '{phrase}' is missing from SYSTEM_PROMPT"
            )

    def test_gwas_never_high_confidence(self):
        record = AnnotationRecord(
            rsid="rs429358",
            genotype="CT",
            source_type=SourceType.GWAS,
            trait_or_condition="Alzheimer's disease",
            p_value="1e-100",
            odds_ratio="1.18",
        )
        finding = evaluate(record)
        assert finding.confidence_tier != ConfidenceTier.HIGH, (
            "GWAS finding must never have HIGH confidence tier"
        )


# ---------------------------------------------------------------------------
# Fixture: minimal / degenerate Finding
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_finding():
    """Finding with all optional fields None and empty collections."""
    return Finding(
        rsid="rs000001",
        genotype="AA",
        source_type=SourceType.GWAS,
        evidence_type=EvidenceType.ASSOCIATION,
        trait_or_condition="Test trait",
        confidence_tier=ConfidenceTier.LOW,
        actionability=Actionability.NONE,
        allowed_claims=[],
        forbidden_claims=[],
        user_visible_notes=[],
        source_refs=[],
    )


# ---------------------------------------------------------------------------
# Boundary value analysis: build_finding_context
# ---------------------------------------------------------------------------


class TestBuildFindingContextBVA:
    """Boundary value tests for build_finding_context with edge-case Findings."""

    def test_context_with_empty_allowed_claims(self, minimal_finding):
        """Empty allowed_claims list should not crash; section header still present."""
        context = build_finding_context(minimal_finding)
        assert "ALLOWED CLAIMS" in context

    def test_context_with_empty_forbidden_claims(self, minimal_finding):
        """Empty forbidden_claims list should not crash; section header still present."""
        context = build_finding_context(minimal_finding)
        assert "FORBIDDEN CLAIMS" in context

    def test_context_with_empty_user_visible_notes(self, minimal_finding):
        """Empty user_visible_notes should not crash; caveats section still present."""
        context = build_finding_context(minimal_finding)
        assert "REQUIRED CAVEATS" in context

    def test_context_with_empty_source_refs(self, minimal_finding):
        """Empty source_refs should not crash and should still produce valid context."""
        context = build_finding_context(minimal_finding)
        assert isinstance(context, str)
        assert len(context) > 0

    def test_context_with_all_none_optional_fields(self, minimal_finding):
        """All optional fields are None — no crash, rsid still present in context."""
        assert minimal_finding.effect_allele is None
        assert minimal_finding.clinical_significance is None
        assert minimal_finding.review_status is None
        assert minimal_finding.effect_size_value is None
        context = build_finding_context(minimal_finding)
        assert minimal_finding.rsid in context

    def test_context_with_single_claim(self, minimal_finding):
        """A Finding with exactly one allowed claim should include that claim."""
        minimal_finding.allowed_claims = ["not_diagnostic"]
        context = build_finding_context(minimal_finding)
        assert "not_diagnostic" in context


# ---------------------------------------------------------------------------
# Boundary value analysis: build_messages_for_explain / build_messages_for_ask
# ---------------------------------------------------------------------------


class TestBuildMessagesBVA:
    """Boundary value tests for message builder functions."""

    def test_explain_messages_with_minimal_finding(self, minimal_finding):
        """Minimal finding should still produce a valid 2-message list."""
        messages = build_messages_for_explain(minimal_finding)
        assert isinstance(messages, list)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert minimal_finding.rsid in messages[1]["content"]

    def test_ask_with_empty_question(self, gwas_finding):
        """An empty question string is still valid — no crash expected."""
        messages = build_messages_for_ask(gwas_finding, "")
        assert isinstance(messages, list)
        assert len(messages) >= 2

    def test_ask_with_long_question(self, gwas_finding):
        """A very long question (2000 chars) should appear in the user message."""
        long_question = "x" * 2000
        messages = build_messages_for_ask(gwas_finding, long_question)
        user_messages = [m for m in messages if m["role"] == "user"]
        assert any(long_question in m["content"] for m in user_messages), (
            "long question text not found in any user message"
        )

    def test_ask_with_special_characters(self, gwas_finding):
        """Special characters (quotes, angle brackets) should appear verbatim."""
        question = 'What about "quotes" and <html>?'
        messages = build_messages_for_ask(gwas_finding, question)
        user_messages = [m for m in messages if m["role"] == "user"]
        assert any(question in m["content"] for m in user_messages), (
            "special-character question not found in any user message"
        )


# ---------------------------------------------------------------------------
# Wrong-type coverage: build_finding_context / build_messages
# ---------------------------------------------------------------------------


class TestBuildFindingContextWrongType:
    """Verify that prompt builders reject wrong-typed inputs."""

    def test_build_finding_context_rejects_string(self):
        """Passing a plain string should raise TypeError or AttributeError."""
        with pytest.raises((TypeError, AttributeError)):
            build_finding_context("not a finding")

    def test_build_finding_context_rejects_none(self):
        """Passing None should raise TypeError or AttributeError."""
        with pytest.raises((TypeError, AttributeError)):
            build_finding_context(None)

    def test_build_finding_context_rejects_dict(self):
        """Passing a dict should raise TypeError or AttributeError."""
        with pytest.raises((TypeError, AttributeError)):
            build_finding_context({"rsid": "rs1"})

    def test_build_messages_for_explain_rejects_string(self):
        """Passing a string to build_messages_for_explain should raise."""
        with pytest.raises((TypeError, AttributeError)):
            build_messages_for_explain("not a finding")

    def test_build_messages_for_ask_rejects_none_finding(self):
        """Passing None as the finding to build_messages_for_ask should raise."""
        with pytest.raises((TypeError, AttributeError)):
            build_messages_for_ask(None, "question")
