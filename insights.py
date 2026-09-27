"""AI answers, insights and WhatsApp summaries via Groq."""

import json
import os

import groq
from groq import Groq

from prompts import (
    get_system_prompt,
    get_insights_prompt,
    get_whatsapp_prompt
)

DEFAULT_MODEL = "openai/gpt-oss-120b"
VALID_INSIGHT_TYPES = {"positive", "warning", "tip"}
HISTORY_MESSAGES = 6
# gpt-oss models "think" before answering; low effort keeps answers fast
REASONING_MODELS_PREFIX = "openai/gpt-oss"


class IRaayaError(Exception):
    """A problem worth showing to the user, in plain words."""


def get_model() -> str:
    return os.getenv("GROQ_MODEL") or DEFAULT_MODEL


def _chat(
    api_key: str,
    messages: list,
    temperature: float,
    max_tokens: int,
    reasoning_effort: str = "low"
) -> str:
    if not api_key:
        raise IRaayaError(
            "Groq API key is missing. Add GROQ_API_KEY to your .env file."
        )
    client = Groq(api_key=api_key)
    model = get_model()
    extra = {}
    if model.startswith(REASONING_MODELS_PREFIX):
        extra["reasoning_effort"] = reasoning_effort
        # Thinking uses tokens too, so allow room for it plus the answer.
        # Kept small: Groq's free tier allows 8,000 tokens per minute.
        max_tokens += 400 if reasoning_effort == "low" else 800
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra
        )
    except groq.AuthenticationError as e:
        raise IRaayaError("Groq rejected the API key. Please check GROQ_API_KEY.") from e
    except groq.RateLimitError as e:
        raise IRaayaError("Groq's free limit was reached. Please wait a minute and try again.") from e
    except (groq.NotFoundError, groq.PermissionDeniedError, groq.BadRequestError) as e:
        raise IRaayaError(
            f"Groq could not use the model '{get_model()}'. "
            "Check GROQ_MODEL in .env. "
            f"Details: {e}"
        ) from e
    except groq.APIConnectionError as e:
        raise IRaayaError("Could not reach Groq. Please check your internet connection.") from e
    except groq.APIStatusError as e:
        raise IRaayaError(f"Groq returned an error: {e}") from e

    text = response.choices[0].message.content or ""
    # Drop broken characters (e.g. a half-generated emoji)
    return text.replace("\ufffd", "").strip()


def list_available_models(api_key: str) -> list:
    """Model IDs this Groq account can use."""
    client = Groq(api_key=api_key)
    return sorted(m.id for m in client.models.list().data)


def ask_iraaya(
    question: str,
    data_context: str,
    language: str,
    mode: str,
    api_key: str,
    chat_history: list = None
) -> str:

    messages = [
        {
            "role": "system",
            "content": get_system_prompt(
                data_context,
                language,
                mode
            )
        }
    ]

    for msg in (chat_history or [])[-HISTORY_MESSAGES:]:
        messages.append(msg)

    messages.append({
        "role": "user",
        "content": question
    })

    # Short answers (read aloud); the prompt asks for 2 to 5 sentences
    return _chat(api_key, messages, temperature=0.3, max_tokens=500)


def _parse_insights(raw: str) -> list:
    """Pull the insights list out of the model's reply, tolerating extra text."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    parsed = json.loads(raw[start:end + 1])

    insights = []
    for item in parsed.get("insights", []):
        if not isinstance(item, dict) or not item.get("title"):
            continue
        kind = str(item.get("type", "tip")).lower().strip()
        insights.append({
            "title": str(item["title"]),
            "detail": str(item.get("detail", "")),
            "type": kind if kind in VALID_INSIGHT_TYPES else "tip",
        })
    return insights


def generate_insights(
    data_context: str,
    api_key: str,
    language: str = "English"
) -> list:

    raw = _chat(
        api_key,
        [{"role": "user", "content": get_insights_prompt(data_context, language)}],
        temperature=0.3,
        max_tokens=1000,
        reasoning_effort="medium",
    )

    try:
        return _parse_insights(raw)
    except Exception as e:
        print(f"JSON parse error: {e}")
        print(f"Raw response: {raw}")
        return []


def generate_whatsapp_summary(
    data_context: str,
    api_key: str,
    language: str = "English"
) -> str:

    text = _chat(
        api_key,
        [{"role": "user", "content": get_whatsapp_prompt(data_context, language)}],
        temperature=0.5,
        max_tokens=400,
    )
    # WhatsApp bold is *text*, not **text**
    return text.replace("**", "*")
