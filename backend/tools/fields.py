"""
get_required_fields — tells the agent exactly what data is needed at each
journey stage, in priority order. Drives progressive input collection.
"""
from __future__ import annotations
from .base import Tool


# Journey definition — single source of truth for what's collected when.
JOURNEY = {
    "registration_lookup": {
        "label": "Step 1 · Your car",
        "fields": [
            {
                "key": "registration_number",
                "label": "Registration number",
                "input_type": "text",
                "placeholder": "e.g. KA05NG2604",
                "priority": 1,
            }
        ],
        "next_stage": "car_confirmation",
    },
    "car_confirmation": {
        "label": "Step 2 · Confirm your car",
        "fields": [
            {
                "key": "usage_type",
                "label": "How do you use the car?",
                "input_type": "choice",
                "options": [{"value": "personal", "label": "Personal"},
                            {"value": "taxi", "label": "Taxi / Commercial"}],
                "priority": 1,
            }
        ],
        "next_stage": "policy_history",
    },
    "policy_history": {
        "label": "Step 3 · Policy history",
        "fields": [
            {
                "key": "previous_policy_type",
                "label": "Previous policy type",
                "input_type": "choice",
                "options": [{"value": "comprehensive", "label": "Comprehensive"},
                            {"value": "third_party", "label": "Third Party"},
                            {"value": "none", "label": "No previous policy"}],
                "priority": 1,
            },
            {
                "key": "policy_expired",
                "label": "Has previous policy expired?",
                "input_type": "choice",
                "options": [{"value": "no", "label": "No"},
                            {"value": "yes", "label": "Yes"}],
                "priority": 2,
            },
            {
                "key": "claim_made",
                "label": "Any claims made in last policy period?",
                "input_type": "choice",
                "options": [{"value": "no", "label": "No"},
                            {"value": "yes", "label": "Yes"}],
                "priority": 3,
            },
            {
                "key": "ncb_percent",
                "label": "Previous NCB %",
                "input_type": "choice",
                "options": [{"value": "0", "label": "0%"}, {"value": "20", "label": "20%"},
                            {"value": "25", "label": "25%"}, {"value": "35", "label": "35%"},
                            {"value": "45", "label": "45%"}, {"value": "50", "label": "50%"}],
                "priority": 4,
            },
            {
                "key": "ownership_changed",
                "label": "Did ownership change in the last 12 months?",
                "input_type": "choice",
                "options": [{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}],
                "priority": 5,
            },
        ],
        "next_stage": "plan_selection",
    },
    "plan_selection": {
        "label": "Step 4 · Compare plans",
        "fields": [
            {
                "key": "selected_insurer_id",
                "label": "Which insurer would you like?",
                "input_type": "dynamic_choice",  # driven by quotes result
                "priority": 1,
            }
        ],
        "next_stage": "addons",
    },
    "addons": {
        "label": "Step 5 · Add-ons",
        "fields": [
            {
                "key": "selected_addons",
                "label": "Choose add-on covers",
                "input_type": "multi_choice",
                "priority": 1,
            }
        ],
        "next_stage": "previous_policy_details",
    },
    "previous_policy_details": {
        "label": "Step 6 · Previous policy details",
        "fields": [
            {"key": "previous_insurer", "label": "Previous insurer name", "input_type": "text", "priority": 1},
            {"key": "previous_policy_number", "label": "Previous policy number", "input_type": "text", "priority": 2},
            {"key": "previous_policy_expiry", "label": "Previous policy expiry date (DD/MM/YYYY)", "input_type": "text", "priority": 3},
        ],
        "next_stage": "nominee_details",
    },
    "nominee_details": {
        "label": "Step 7 · Nominee",
        "fields": [
            {"key": "nominee_relation", "label": "Nominee relation",
             "input_type": "choice",
             "options": [{"value": "spouse", "label": "Spouse"}, {"value": "parent", "label": "Parent"},
                         {"value": "child", "label": "Child"}, {"value": "sibling", "label": "Sibling"},
                         {"value": "other", "label": "Other"}], "priority": 1},
            {"key": "nominee_name", "label": "Nominee name", "input_type": "text", "priority": 2},
            {"key": "nominee_age", "label": "Nominee age", "input_type": "text", "priority": 3},
        ],
        "next_stage": "review",
    },
    "review": {
        "label": "Step 8 · Review & buy",
        "fields": [],
        "next_stage": "complete",
    },
}


class GetRequiredFields(Tool):
    name = "get_required_fields"
    description = (
        "Get the required input fields for the current journey stage, in priority order. "
        "Use this to drive progressive input collection — ask ONE question at a time, "
        "highest priority first. Skip fields that are already collected."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "journey_stage": {
                "type": "string",
                "enum": list(JOURNEY.keys()),
                "description": "The current journey stage.",
            },
            "already_collected": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Field keys already collected (will be filtered out).",
            },
        },
        "required": ["journey_stage"],
    }

    async def run(self, journey_stage: str, already_collected: list | None = None) -> dict:
        stage = JOURNEY.get(journey_stage)
        if stage is None:
            return {"error": f"Unknown stage: {journey_stage}"}
        already_collected = already_collected or []
        remaining = [f for f in stage["fields"] if f["key"] not in already_collected]
        return {
            "stage": journey_stage,
            "stage_label": stage["label"],
            "remaining_fields": remaining,
            "next_field": remaining[0] if remaining else None,
            "next_stage": stage["next_stage"] if not remaining else None,
        }
