"""
get_car_details tool — maps a registration number to car specs.
Mock implementation is deterministic (hash-based) so tests are reproducible.
Swap with a real RTO/VAHAN lookup API in production by implementing CarProvider.
"""
from __future__ import annotations
import asyncio
from typing import Protocol
from .base import Tool
from mock_data import lookup_registration


class CarProvider(Protocol):
    async def fetch(self, registration_number: str) -> dict | None: ...


class MockCarProvider:
    async def fetch(self, registration_number: str) -> dict | None:
        # Simulate a small API latency so async benefits are visible.
        await asyncio.sleep(0.05)
        return lookup_registration(registration_number)


class GetCarDetails(Tool):
    name = "get_car_details"
    description = (
        "Look up car details (make, model, variant, fuel_type, year, RTO state) "
        "from a vehicle registration number. Call this the moment the user "
        "provides a registration number. Never guess car details — always call "
        "this tool."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "registration_number": {
                "type": "string",
                "description": "Vehicle registration number, e.g. KA05NG2604",
            }
        },
        "required": ["registration_number"],
    }

    def __init__(self, provider: CarProvider | None = None):
        self.provider = provider or MockCarProvider()

    async def run(self, registration_number: str, _session_data: dict | None = None) -> dict:
        reg_norm = registration_number.upper().replace(" ", "").replace("-", "")

        # If session already has extracted car info for this registration, use it
        if _session_data:
            car_info = _session_data.get("car_info", {})
            session_reg = (car_info.get("registration_number") or "").upper().replace(" ", "")
            if session_reg and session_reg == reg_norm and car_info.get("make"):
                mock = await self.provider.fetch(registration_number) or {}
                return {
                    "registration_number": reg_norm,
                    "make": car_info.get("make") or mock.get("make", ""),
                    "model": car_info.get("model") or mock.get("model", ""),
                    "variant": car_info.get("variant") or mock.get("variant", ""),
                    "fuel_type": car_info.get("fuel_type") or mock.get("fuel_type", "petrol"),
                    "year": str(car_info.get("year") or mock.get("registration_year", 2020)),
                    "cc": mock.get("cc", 1200),
                    "segment": mock.get("segment", "sedan"),
                    "rto_state": mock.get("rto_state", ""),
                    "source": "document",
                }

        details = await self.provider.fetch(registration_number)
        if details is None:
            return {
                "error": "Registration number not found",
                "registration_number": registration_number,
            }
        return {
            "registration_number": details["registration_number"],
            "make": details["make"],
            "model": details["model"],
            "variant": details["variant"],
            "fuel_type": details["fuel_type"],
            "year": details["registration_year"],
            "cc": details["cc"],
            "segment": details["segment"],
            "rto_state": details["rto_state"],
        }
