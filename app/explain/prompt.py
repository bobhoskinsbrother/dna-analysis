"""Pure prompt builders and LLM client functions for the explain layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import openai

from app.explain.contract import SYSTEM_PROMPT

if TYPE_CHECKING:
    from app.config import Settings
    from app.models import Finding


def build_finding_context(finding: Finding) -> str:
    """Serialize a Finding into a structured text block for the LLM prompt."""
    parts: list[str] = []

    parts.append("FINDING DATA:")
    parts.append(finding.model_dump_json(indent=2))

    parts.append("")
    parts.append("ALLOWED CLAIMS FOR THIS FINDING:")
    for claim in finding.allowed_claims:
        parts.append(f"- {claim}")

    parts.append("")
    parts.append("FORBIDDEN CLAIMS FOR THIS FINDING:")
    for claim in finding.forbidden_claims:
        parts.append(f"- {claim}")

    parts.append("")
    parts.append("REQUIRED CAVEATS:")
    for note in finding.user_visible_notes:
        parts.append(f"- {note}")

    return "\n".join(parts)


def build_messages_for_explain(finding: Finding) -> list[dict]:
    """Return OpenAI-format messages for a plain-English explanation."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_finding_context(finding)
            + "\n\nPlease explain this finding in plain English.",
        },
    ]


def build_messages_for_ask(finding: Finding, question: str) -> list[dict]:
    """Return OpenAI-format messages for a user question about a finding."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_finding_context(finding)
            + f"\n\nUser question: {question}",
        },
    ]


def get_llm_client(settings: Settings) -> openai.OpenAI:
    """Create an OpenAI client from application settings."""
    kwargs: dict = {"api_key": settings.llm_api_key}
    if settings.llm_api_base:
        kwargs["base_url"] = settings.llm_api_base
    return openai.OpenAI(**kwargs)


def explain_finding(finding: Finding, settings: Settings) -> str:
    """Generate a plain-English explanation for a single finding."""
    client = get_llm_client(settings)
    messages = build_messages_for_explain(finding)
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
    )
    return response.choices[0].message.content


def ask_about_finding(finding: Finding, question: str, settings: Settings) -> str:
    """Answer a user question about a specific finding."""
    client = get_llm_client(settings)
    messages = build_messages_for_ask(finding, question)
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
    )
    return response.choices[0].message.content
