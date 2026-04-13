"""
Agentic car insurance chatbot with tool use, quality verification loops,
and salesy nudging toward purchase completion.
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)
from anthropic import Anthropic
from mock_data import (
    lookup_registration, get_quotes, get_addon_prices,
    ADDONS, INSURERS, NCB_SLABS, CAR_DATABASE,
)

client = Anthropic(max_retries=3)

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

SYSTEM_PROMPT = """You are an expert car insurance advisor chatbot for an Indian insurance aggregator platform. Your role is to help users find and purchase the best car insurance policy.

## Your Personality
- Friendly, professional, and knowledgeable about car insurance in India
- Proactively helpful — anticipate user needs and guide them through the process
- Salesy but not pushy — use soft nudges, urgency cues, and value framing to encourage purchase completion
- Use simple language, avoid jargon unless explaining it
- Be conversational — use short paragraphs, bullet points, and emojis sparingly for warmth

## The Insurance Purchase Flow
Guide users through this flow conversationally:

1. **Registration Lookup**: Ask for their car registration number (e.g., KA05NG2604). Use the `lookup_registration` tool to fetch car details.
2. **Car Details Confirmation**: Confirm car make/model/variant, registration year. Ask about:
   - Usage: Personal or Taxi
   - Previous policy type: Comprehensive or Third Party
   - Ownership change in last 12 months
   - Previous policy expired?
   - Claims made in last policy period?
   - Previous NCB (No Claim Bonus) percentage
3. **Plan Comparison**: Use `get_insurance_quotes` to fetch quotes. Present top plans with:
   - Insurer name, premium, IDV
   - Network garages, claim settlement ratio
   - Highlight best value, lowest price, highest claim settlement
   - Use comparison to help user decide
4. **Add-ons Selection**: Use `get_addon_prices` to show available add-ons. Recommend:
   - Zero Depreciation (strongly recommend for cars < 5 years old)
   - Engine Protect (recommend for flood-prone areas)
   - Return to Invoice (recommend for new cars)
   - PA Cover is mandatory — explain why
5. **Previous Policy Details**: Collect previous policy expiry date, insurer, policy number, NCB%
6. **Nominee Details**: Collect nominee name, relation, age
7. **Review & Purchase**: Summarize everything and present final price with "Buy Plan" CTA

## Sales Techniques
- **Urgency**: "Prices may increase if your policy lapses!" / "This offer is valid today"
- **Social proof**: "93% of our customers choose Zero Dep for cars under 5 years"
- **Value framing**: "For just ₹X more per day, you get complete bumper-to-bumper coverage"
- **Loss aversion**: "Without Zero Dep, you'd pay 30-40% of parts cost from your pocket during a claim"
- **Comparison**: When user hesitates, compare what they get vs what they'd miss
- **Objection handling**: Address concerns about price by showing value, about trust by showing claim settlement ratios

## Objection Handling
- "Too expensive" → Show cheaper plans, or break down per-day cost, highlight savings vs out-of-pocket costs
- "I'll do it later" → Mention policy lapse risks, NCB loss, legal issues of driving uninsured
- "I don't need add-ons" → Explain real-world scenarios where each add-on saves money
- "Which insurer is best?" → Compare claim settlement ratio, network garages, digital experience
- "What is IDV?" → Explain Insured Declared Value = current market value of car, affects claim payout
- "What is NCB?" → Explain No Claim Bonus discount, how it accumulates year over year

## Formatting
- Use markdown for structured responses
- Use tables for plan comparisons
- Use bullet points for feature lists
- Bold key numbers and recommendations
- Keep responses focused and not too long — break into steps

## Important Rules
- Always verify car details with the user before fetching quotes
- If user seems confused, simplify and explain
- If user wants to explore, let them but gently guide back to the flow
- Track where the user is in the flow and remind them of next steps
- After showing quotes, always ask "Would you like to proceed with [recommended plan]?"
- Be transparent about what's mandatory (PA cover, third party) vs optional
"""

TOOLS = [
    {
        "name": "lookup_registration",
        "description": "Look up car details (make, model, variant, fuel type, registration year) from a vehicle registration number. Returns the car information associated with this registration. Use this when the user provides their car registration number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "registration_number": {
                    "type": "string",
                    "description": "The vehicle registration number (e.g., KA05NG2604, MH01AB1234)"
                }
            },
            "required": ["registration_number"]
        }
    },
    {
        "name": "get_insurance_quotes",
        "description": "Get insurance premium quotes from multiple insurers for a given car. Returns a list of quotes sorted by premium with insurer details, IDV, premium breakdown, and features.",
        "input_schema": {
            "type": "object",
            "properties": {
                "registration_number": {
                    "type": "string",
                    "description": "The vehicle registration number"
                },
                "policy_type": {
                    "type": "string",
                    "enum": ["comprehensive", "third_party"],
                    "description": "Type of insurance policy"
                },
                "ncb_years": {
                    "type": "integer",
                    "description": "Number of claim-free years (0-5) for NCB discount",
                    "minimum": 0,
                    "maximum": 5
                }
            },
            "required": ["registration_number", "policy_type"]
        }
    },
    {
        "name": "get_addon_prices",
        "description": "Get available add-on covers and their prices for a specific car and base premium. Returns list of add-ons with descriptions, prices, and whether they are mandatory or popular.",
        "input_schema": {
            "type": "object",
            "properties": {
                "registration_number": {
                    "type": "string",
                    "description": "The vehicle registration number"
                },
                "base_premium": {
                    "type": "integer",
                    "description": "The base premium of the selected plan (used to calculate add-on prices)"
                }
            },
            "required": ["registration_number", "base_premium"]
        }
    },
    {
        "name": "generate_summary",
        "description": "Generate a final review summary for the insurance purchase. Use this when the user has selected a plan, add-ons, and provided all required details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "registration_number": {"type": "string"},
                "selected_insurer": {"type": "string", "description": "Name of selected insurer"},
                "base_premium": {"type": "integer"},
                "selected_addons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of selected add-on IDs"
                },
                "addon_total": {"type": "integer"},
                "policy_type": {"type": "string"},
                "idv": {"type": "integer"},
                "ncb_percent": {"type": "integer"},
                "previous_policy_expiry": {"type": "string"},
                "previous_insurer": {"type": "string"},
                "nominee_name": {"type": "string"},
                "nominee_relation": {"type": "string"},
                "nominee_age": {"type": "integer"}
            },
            "required": ["registration_number", "selected_insurer", "base_premium", "policy_type"]
        }
    }
]


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return JSON result."""
    if tool_name == "lookup_registration":
        result = lookup_registration(tool_input["registration_number"])
        if result is None:
            return json.dumps({"error": "Registration number not found. Please check and try again."})
        return json.dumps(result)

    elif tool_name == "get_insurance_quotes":
        car_info = lookup_registration(tool_input["registration_number"])
        if car_info is None:
            return json.dumps({"error": "Registration number not found."})
        quotes = get_quotes(
            car_info,
            policy_type=tool_input.get("policy_type", "comprehensive"),
            ncb_years=tool_input.get("ncb_years", 0),
        )
        return json.dumps({"car": car_info, "quotes": quotes[:8]})  # Top 8

    elif tool_name == "get_addon_prices":
        car_info = lookup_registration(tool_input["registration_number"])
        if car_info is None:
            return json.dumps({"error": "Registration number not found."})
        addons = get_addon_prices(
            tool_input["base_premium"],
            car_info,
        )
        return json.dumps({"addons": addons})

    elif tool_name == "generate_summary":
        car_info = lookup_registration(tool_input["registration_number"])
        total = tool_input["base_premium"] + tool_input.get("addon_total", 0)
        gst = int(total * 0.18)
        grand_total = total + gst

        summary = {
            "car": car_info,
            "insurer": tool_input["selected_insurer"],
            "policy_type": tool_input.get("policy_type", "comprehensive"),
            "idv": tool_input.get("idv", 0),
            "ncb_percent": tool_input.get("ncb_percent", 0),
            "base_premium": tool_input["base_premium"],
            "addon_total": tool_input.get("addon_total", 0),
            "subtotal": total,
            "gst": gst,
            "grand_total": grand_total,
            "selected_addons": tool_input.get("selected_addons", []),
            "previous_policy_expiry": tool_input.get("previous_policy_expiry"),
            "previous_insurer": tool_input.get("previous_insurer"),
            "nominee_name": tool_input.get("nominee_name"),
            "nominee_relation": tool_input.get("nominee_relation"),
            "nominee_age": tool_input.get("nominee_age"),
        }
        return json.dumps(summary)

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def quality_check(response_text: str, conversation_context: list) -> str | None:
    """
    Quality verification loop: check if the agent's response is accurate,
    helpful, and moves the conversation forward. Returns correction if needed.
    """
    check_messages = [
        {
            "role": "user",
            "content": f"""You are a quality checker for a car insurance chatbot. Review this response and check:
1. Are any insurance facts or numbers incorrect?
2. Is the response helpful and moving toward purchase completion?
3. Is the tone appropriate (friendly, professional, gently salesy)?
4. Are there any confusing or misleading statements?

Response to check:
{response_text}

If the response is good, reply with exactly: APPROVED
If there are issues, briefly describe what needs fixing (one line)."""
        }
    ]

    check_response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=check_messages,
    )

    result = check_response.content[0].text.strip()
    if result == "APPROVED":
        return None
    return result


def chat(user_message: str, conversation_history: list, session_data: dict) -> tuple[str, list, dict]:
    """
    Process a user message through the agentic flow.
    Returns (response_text, updated_history, updated_session_data).
    """
    conversation_history.append({
        "role": "user",
        "content": user_message,
    })

    max_iterations = 5  # Safety limit for agentic loop
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history,
        )

        # Process tool use
        if response.stop_reason == "tool_use":
            # Add assistant's response (may contain text + tool_use blocks)
            conversation_history.append({
                "role": "assistant",
                "content": response.content,
            })

            # Execute all tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)

                    # Store useful data in session
                    if block.name == "lookup_registration":
                        parsed = json.loads(result)
                        if "error" not in parsed:
                            session_data["car_info"] = parsed

                    elif block.name == "get_insurance_quotes":
                        parsed = json.loads(result)
                        if "error" not in parsed:
                            session_data["quotes"] = parsed["quotes"]

                    elif block.name == "get_addon_prices":
                        parsed = json.loads(result)
                        if "error" not in parsed:
                            session_data["addons"] = parsed["addons"]

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            conversation_history.append({
                "role": "user",
                "content": tool_results,
            })
            # Continue the loop to let the model respond after tool results
            continue

        else:
            # End turn — extract text response
            response_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    response_text += block.text

            # Quality verification loop (skip for very short responses)
            if len(response_text) > 100:
                correction = quality_check(response_text, conversation_history)
                if correction:
                    # Ask the model to revise
                    conversation_history.append({
                        "role": "assistant",
                        "content": response_text,
                    })
                    conversation_history.append({
                        "role": "user",
                        "content": [{"type": "text", "text": f"[SYSTEM QUALITY CHECK — not from user] Please revise your last response. Issue found: {correction}. Provide the corrected response only — do not mention this check to the user."}],
                    })
                    # One more iteration to get corrected response
                    revision = client.messages.create(
                        model=MODEL,
                        max_tokens=2048,
                        system=SYSTEM_PROMPT,
                        tools=TOOLS,
                        messages=conversation_history,
                    )
                    revised_text = ""
                    for block in revision.content:
                        if hasattr(block, "text"):
                            revised_text += block.text
                    if revised_text:
                        # Replace the last two messages with the clean version
                        conversation_history.pop()  # Remove quality check
                        conversation_history.pop()  # Remove original response
                        response_text = revised_text

            conversation_history.append({
                "role": "assistant",
                "content": response_text,
            })
            return response_text, conversation_history, session_data

    # Fallback if we hit max iterations
    fallback = "I'm processing your request. Could you please repeat what you need?"
    conversation_history.append({"role": "assistant", "content": fallback})
    return fallback, conversation_history, session_data
