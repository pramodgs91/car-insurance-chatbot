"""
Document extraction for RC cards and prior motor insurance policies.

Uses the active model family via the provider router and returns structured
fields that can be merged into the chat session.
"""
from __future__ import annotations

from typing import Any


SUPPORTED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
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

1. An RC (Registration Certificate) card from the RTO.
2. A motor insurance policy document from an Indian insurer.
3. Something else.

Read the document carefully and return the requested fields. Rules:

- Registration number: strip spaces and convert to uppercase.
- Dates: normalize to DD/MM/YYYY.
- IDV and premium: digits only.
- NCB: only the number.
- Leave unreadable fields empty.
- Do not guess.
- Set confidence based on readability.
"""


def _media_type_from(filename: str, content_type: str | None) -> str | None:
    ct = (content_type or "").lower()
    if ct in SUPPORTED_IMAGE_TYPES or ct in SUPPORTED_DOC_TYPES:
        return ct
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


async def extract_from_upload(
    file_bytes: bytes,
    content_type: str | None,
    filename: str,
    model_router,
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
        hint_text = f"\nHint from user: this is a {doc_hint}."

    try:
        raw = await model_router.extract_document(
            file_bytes=file_bytes,
            media_type=media_type,
            prompt=EXTRACTION_PROMPT + hint_text,
            tool_schema=EXTRACTION_TOOL,
        )
    except Exception as exc:
        raise RuntimeError(f"Vision model call failed: {exc}") from exc

    cleaned = {key: value for key, value in (raw or {}).items() if value not in ("", None)}
    if "registration_number" in cleaned and isinstance(cleaned["registration_number"], str):
        cleaned["registration_number"] = cleaned["registration_number"].replace(" ", "").upper()
    return cleaned


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

    car_fields = {
        key: extracted[key]
        for key in ("registration_number", "make", "model", "variant", "year", "fuel_type", "owner_name", "rto_code")
        if key in extracted
    }
    if extracted.get("idv"):
        filled["previous_idv"] = extracted["idv"]
        applied["previous_idv"] = extracted["idv"]
        car_fields["previous_idv"] = extracted["idv"]

    if car_fields:
        session_data["car_info"] = {**session_data.get("car_info", {}), **car_fields}
        applied.update(car_fields)

    return applied


def format_for_agent(filename: str, extracted: dict, applied: dict) -> str:
    doc_type = extracted.get("doc_type", "document")
    return (
        f"[I uploaded {filename} ({doc_type}). "
        f"Extracted fields: {applied}. "
        "Please acknowledge the upload, trust these extracted fields, and continue the journey.]"
    )
