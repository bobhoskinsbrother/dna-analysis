"""Pure prompt builders and LLM client functions for the explain layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

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


def _is_anthropic(settings: Settings) -> bool:
    return settings.llm_model.startswith("claude")


def _call_anthropic(messages: list[dict], settings: Settings) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.llm_api_key)
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_messages = [m for m in messages if m["role"] != "system"]
    response = client.messages.create(
        model=settings.llm_model,
        max_tokens=4096,
        system=system,
        messages=user_messages,
    )
    return response.content[0].text


def _call_openai(messages: list[dict], settings: Settings) -> str:
    import openai

    kwargs: dict = {"api_key": settings.llm_api_key}
    if settings.llm_api_base:
        kwargs["base_url"] = settings.llm_api_base
    client = openai.OpenAI(**kwargs)
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
    )
    return response.choices[0].message.content


def _call_llm(messages: list[dict], settings: Settings) -> str:
    if _is_anthropic(settings):
        return _call_anthropic(messages, settings)
    return _call_openai(messages, settings)


def explain_finding(finding: Finding, settings: Settings) -> str:
    """Generate a plain-English explanation for a single finding."""
    return _call_llm(build_messages_for_explain(finding), settings)


def ask_about_finding(finding: Finding, question: str, settings: Settings) -> str:
    """Answer a user question about a specific finding."""
    return _call_llm(build_messages_for_ask(finding, question), settings)
