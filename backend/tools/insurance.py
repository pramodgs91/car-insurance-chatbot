"""
get_insurance_quotes and get_addon_prices tools.
"""
from __future__ import annotations
import asyncio
from typing import Protocol
from .base import Tool
from mock_data import lookup_registration, get_quotes, get_quotes_with_car_info, get_addon_prices


class QuotesProvider(Protocol):
    async def fetch(
        self, registration_number: str, coverage_type: str, ncb_years: int
    ) -> dict: ...


class MockQuotesProvider:
    async def fetch(
        self, registration_number: str, coverage_type: str, ncb_years: int
    ) -> dict:
        await asyncio.sleep(0.15)  # simulate real-world API aggregation latency
        car = lookup_registration(registration_number)
        if car is None:
            return {"error": "Registration number not found"}
        quotes = get_quotes(car, policy_type=coverage_type, ncb_years=ncb_years)
        return {"car": car, "quotes": quotes[:8]}


class GetInsuranceQuotes(Tool):
    name = "get_insurance_quotes"
    description = (
        "Fetch insurance premium quotes from 12+ insurers for a registered car. "
        "Returns top 8 quotes sorted by premium (cheapest first), with insurer "
        "name, premium, IDV, network garages, and claim-settlement ratio. "
        "Must be called before presenting any premium numbers — NEVER make up quotes."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "registration_number": {"type": "string"},
            "coverage_type": {
                "type": "string",
                "enum": ["comprehensive", "third_party"],
                "description": "Comprehensive covers own damage + third-party. Third-party is mandatory-only cover.",
            },
            "ncb_years": {
                "type": "integer",
                "minimum": 0,
                "maximum": 5,
                "description": "Claim-free years (0 if first-time buyer or claim made last year).",
            },
        },
        "required": ["registration_number", "coverage_type"],
    }

    def __init__(self, provider: QuotesProvider | None = None):
        self.provider = provider or MockQuotesProvider()

    async def run(
        self,
        registration_number: str,
        coverage_type: str = "comprehensive",
        ncb_years: int = 0,
        _session_data: dict | None = None,
    ) -> dict:
        # If session has extracted car info, use it for accurate IDV/NCB/car matching
        if _session_data:
            car_info = _session_data.get("car_info", {})
            filled = _session_data.get("filled_fields", {})
            session_reg = (car_info.get("registration_number") or "").upper().replace(" ", "")
            reg_norm = registration_number.upper().replace(" ", "").replace("-", "")
            if session_reg and session_reg == reg_norm and car_info.get("make"):
                merged = {
                    **car_info,
                    "ncb_percent": filled.get("ncb_percent") or car_info.get("ncb_percent"),
                    "claims_made": filled.get("claim_made") or car_info.get("claims_made"),
                }
                quotes = get_quotes_with_car_info(merged, policy_type=coverage_type, ncb_years=ncb_years)
                return {"car": merged, "quotes": quotes[:8], "source": "document"}

        return await self.provider.fetch(registration_number, coverage_type, ncb_years)


class GetAddonPrices(Tool):
    name = "get_addon_prices"
    description = (
        "Fetch add-on cover prices (Zero Depreciation, Roadside Assistance, "
        "Engine Protect, Return to Invoice, NCB Protect, etc.) for the selected "
        "insurer plan. Must be called with the base premium of the selected plan."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "registration_number": {"type": "string"},
            "base_premium": {
                "type": "integer",
                "description": "Base premium of the selected plan in INR.",
            },
        },
        "required": ["registration_number", "base_premium"],
    }

    async def run(self, registration_number: str, base_premium: int) -> dict:
        await asyncio.sleep(0.05)
        car = lookup_registration(registration_number)
        if car is None:
            return {"error": "Registration number not found"}
        return {"addons": get_addon_prices(base_premium, car)}
