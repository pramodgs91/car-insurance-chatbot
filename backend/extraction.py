"""
Document extraction for RC cards and prior motor insurance policies.

Uses Claude Vision (sonnet — best accuracy on Indian docs) with a forced
tool call so the output is always a strict, typed JSON object.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from anthropic import AsyncAnthropic


# Vision is more reliable on Sonnet for dense Indian docs. This call only
# runs on file uploads, not per turn, so cost isn't a concern.
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "claude-sonnet-4-20250514")

_client = AsyncAnthropic(max_retries=2)


SUPPORTED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
}
SUPPORTED_DOC_TYPES = {"application/pdf"}


EXTRACTION_TOOL = {
    "name": "record_extracted_fields",
    "description": (
        "Record the fields you extracted from the uploaded document. "
        "This is an Indian RC (Registration Certificate) card OR a motor "
        "insurance policy document. Fill every field you can read with "
        "high confidence; leave fields empty if unsure — do NOT guess."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "doc_type": {
                "type": "string",
                "enum": ["rc_card", "previous_policy", "other"],
                "description": "Which kind of document this is.",
            },
            # RC / car fields
            "registration_number": {
                "type": "string",
                "description": "Vehicle registration without spaces, e.g. KA05NG2604.",
            },
            "make": {"type": "string", "description": "Manufacturer, e.g. Maruti Suzuki."},
            "model": {"type": "string", "description": "Model name, e.g. Swift."},
            "variant": {"type": "string", "description": "Variant / trim, e.g. VXI."},
            "year": {"type": "string", "description": "Registration year, 4 digits."},
            "fuel_type": {
                "type": "string",
                "enum": ["petrol", "diesel", "cng", "electric", "hybrid", "unknown"],
            },
            "owner_name": {"type": "string"},
            "chassis_number": {"type": "string"},
            "engine_number": {"type": "string"},
            "rto_code": {"type": "string", "description": "e.g. KA05."},
            # Policy fields
            "previous_insurer": {"type": "string"},
            "previous_policy_number": {"type": "string"},
            "policy_type": {
                "type": "string",
                "enum": ["comprehensive", "third_party", "own_damage", "unknown"],
            },
            "policy_start_date": {"type": "string", "description": "DD/MM/YYYY if visible."},
            "policy_expiry_date": {"type": "string", "description": "DD/MM/YYYY if visible."},
            "idv": {"type": "string", "description": "Insured Declared Value in rupees, digits only."},
            "ncb_percent": {"type": "string", "description": "NCB percentage, e.g. '25'."},
            "claims_made": {"type": "string", "enum": ["yes", "no", "unknown"]},
            "nominee_name": {"type": "string"},
            "nominee_relation": {"type": "string"},
            # Meta
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "notes": {
                "type": "string",
                "description": "Anything notable: poor scan, partial crop, unusual format.",
            },
        },
        "required": ["doc_type"],
    },
}


EXTRACTION_PROMPT = """You are extracting structured data from an Indian automobile document uploaded by a user seeking car insurance. The document is either:

1. An **RC (Registration Certificate) card** — issued by the RTO, contains the vehicle's registration number, make, model, variant, year of registration, fuel type, owner name, chassis/engine numbers.

2. A **motor insurance policy document** — from an Indian insurer (ICICI Lombard, HDFC Ergo, Bajaj Allianz, Digit, Acko, Tata AIG, etc.). Contains policy number, insurer, policy type (comprehensive / third-party / own-damage), dates, IDV, NCB, claims history, nominee details.

3. Something else — mark doc_type="other".

Read the document carefully and call the `record_extracted_fields` tool EXACTLY ONCE with everything you can see. Rules:

- Registration number: strip all spaces, convert to uppercase (e.g. "KA 05 NG 2604" → "KA05NG2604").
- Dates: normalize to DD/MM/YYYY.
- IDV and premium: digits only (strip ₹, commas, "Rs.", decimals).
- NCB: just the number (e.g. "25").
- For RC cards, leave policy fields empty. For policy docs, leave chassis/engine empty if not present.
- If you cannot read a field with reasonable confidence, DO NOT GUESS — leave it empty.
- Set `confidence` based on how clearly the document was readable.
"""


def _media_type_from(filename: str, content_type: str | None) -> str | None:
    ct = (content_type or "").lower()
    if ct in SUPPORTED_IMAGE_TYPES or ct in SUPPORTED_DOC_TYPES:
        return ct
    # Fallback: sniff by extension.
    name = (filename or "").lower()
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    if name.endswith(".pdf"):
        return "application/pdf"
    return None


def _build_content_block(file_bytes: bytes, media_type: str) -> dict:
    b64 = base64.standard_b64encode(file_bytes).decode("ascii")
    if media_type in SUPPORTED_IMAGE_TYPES:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        }
    if media_type in SUPPORTED_DOC_TYPES:
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        }
    raise ValueError(f"Unsupported media type: {media_type}")


async def extract_from_upload(
    file_bytes: bytes,
    content_type: str | None,
    filename: str,
    doc_hint: str | None = None,
) -> dict[str, Any]:
    """
    Return a dict of extracted fields (empty strings for unreadable fields).
    Raises ValueError on unsupported file types, RuntimeError on model errors.
    """
    media_type = _media_type_from(filename, content_type)
    if media_type is None:
        raise ValueError(
            "Unsupported file type. Please upload a PDF or an image "
            "(JPG, PNG, WebP)."
        )

    hint_text = ""
    if doc_hint:
        hint_text = f"\nHint from user: this is a **{doc_hint}**."

    content = [
        _build_content_block(file_bytes, media_type),
        {"type": "text", "text": EXTRACTION_PROMPT + hint_text},
    ]

    try:
        response = await _client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=1024,
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "record_extracted_fields"},
            messages=[{"role": "user", "content": content}],
        )
    except Exception as exc:
        raise RuntimeError(f"Vision model call failed: {exc}") from exc

    for block in response.content:
        if block.type == "tool_use" and block.name == "record_extracted_fields":
            # Drop empty strings so downstream code can treat missing as missing.
            raw = block.input or {}
            cleaned = {k: v for k, v in raw.items() if v not in ("", None)}
            return cleaned

    raise RuntimeError("Model did not return structured extraction.")


# ── Session mapping ──────────────────────────────────────────────────────────

# Map extraction keys → session_data keys used by tools/fields.py journey.
_FIELD_TO_SESSION = {
    "registration_number": "registration_number",
    "usage_type": "usage_type",            # rarely on docs, but keep
    "previous_policy_type": "previous_policy_type",
    "policy_expired": "policy_expired",
    "claim_made": "claim_made",
    "ncb_percent": "ncb_percent",
    "previous_insurer": "previous_insurer",
    "previous_policy_number": "previous_policy_number",
    "previous_policy_expiry": "previous_policy_expiry",
    "nominee_name": "nominee_name",
    "nominee_relation": "nominee_relation",
}


def merge_into_session(session_data: dict, extracted: dict) -> dict:
    """
    Translate extracted fields into the session_data shape that
    get_required_fields expects. Returns the subset actually applied.
    """
    applied: dict[str, Any] = {}
    filled = session_data.setdefault("filled_fields", {})

    if extracted.get("registration_number"):
        filled["registration_number"] = extracted["registration_number"]
        applied["registration_number"] = extracted["registration_number"]

    if extracted.get("policy_type") and extracted["policy_type"] != "unknown":
        filled["previous_policy_type"] = extracted["policy_type"]
        applied["previous_policy_type"] = extracted["policy_type"]

    if extracted.get("previous_insurer"):
        filled["previous_insurer"] = extracted["previous_insurer"]
        applied["previous_insurer"] = extracted["previous_insurer"]

    if extracted.get("previous_policy_number"):
        filled["previous_policy_number"] = extracted["previous_policy_number"]
        applied["previous_policy_number"] = extracted["previous_policy_number"]

    if extracted.get("policy_expiry_date"):
        filled["previous_policy_expiry"] = extracted["policy_expiry_date"]
        applied["previous_policy_expiry"] = extracted["policy_expiry_date"]

    if extracted.get("ncb_percent"):
        filled["ncb_percent"] = extracted["ncb_percent"]
        applied["ncb_percent"] = extracted["ncb_percent"]

    if extracted.get("claims_made") in ("yes", "no"):
        filled["claim_made"] = extracted["claims_made"]
        applied["claim_made"] = extracted["claims_made"]

    if extracted.get("nominee_name"):
        filled["nominee_name"] = extracted["nominee_name"]
        applied["nominee_name"] = extracted["nominee_name"]

    if extracted.get("nominee_relation"):
        filled["nominee_relation"] = extracted["nominee_relation"]
        applied["nominee_relation"] = extracted["nominee_relation"]

    # Car info (from RC) goes into the same slot the get_car_details tool
    # populates — so the agent can skip the lookup call.
    car_fields = {
        k: extracted[k]
        for k in ("registration_number", "make", "model", "variant",
                  "year", "fuel_type", "owner_name", "rto_code")
        if k in extracted
    }
    if car_fields:
        existing = session_data.get("car_info") or {}
        session_data["car_info"] = {**existing, **car_fields, "source": "user_upload"}

    return applied


def format_for_agent(filename: str, extracted: dict, applied: dict) -> str:
    """Render a user-visible summary that doubles as the agent's next turn."""
    doc_type = extracted.get("doc_type", "document")
    pretty = {
        "rc_card": "RC card",
        "previous_policy": "previous policy document",
    }.get(doc_type, "document")

    lines: list[str] = []

    if doc_type == "rc_card":
        for label, key in [
            ("Registration", "registration_number"),
            ("Make", "make"),
            ("Model", "model"),
            ("Variant", "variant"),
            ("Year", "year"),
            ("Fuel", "fuel_type"),
            ("Owner", "owner_name"),
        ]:
            if extracted.get(key):
                lines.append(f"- {label}: {extracted[key]}")
    elif doc_type == "previous_policy":
        for label, key in [
            ("Registration", "registration_number"),
            ("Previous insurer", "previous_insurer"),
            ("Policy number", "previous_policy_number"),
            ("Policy type", "policy_type"),
            ("Start date", "policy_start_date"),
            ("Expiry date", "policy_expiry_date"),
            ("IDV", "idv"),
            ("NCB", "ncb_percent"),
            ("Claims made", "claims_made"),
        ]:
            if extracted.get(key):
                lines.append(f"- {label}: {extracted[key]}")
    else:
        for k, v in extracted.items():
            if k in ("doc_type", "confidence", "notes"):
                continue
            if v:
                lines.append(f"- {k}: {v}")

    body = (
        f"[I uploaded my {pretty} — \"{filename}\". "
        f"Extracted fields below are authoritative; use them directly and do NOT re-ask for these. "
        f"Skip tools like get_car_details when registration_number is already known. "
        f"Confirm briefly and proceed to the next missing field in the journey.]\n\n"
    )
    if lines:
        body += "\n".join(lines)
    else:
        body += "(No fields could be read confidently — please apologize and ask for the registration number in text.)"

    note = extracted.get("notes")
    if note:
        body += f"\n\nNote: {note}"
    return body
