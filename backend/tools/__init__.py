"""Tool package — everything the agent can call to get real data."""
from .base import Tool, ToolRegistry
from .car_details import GetCarDetails
from .insurance import GetInsuranceQuotes, GetAddonPrices
from .fields import GetRequiredFields, JOURNEY


def build_registry() -> ToolRegistry:
    """Assemble the default mock-backed registry. Swap providers for prod."""
    registry = ToolRegistry()
    registry.register(GetCarDetails())
    registry.register(GetInsuranceQuotes())
    registry.register(GetAddonPrices())
    registry.register(GetRequiredFields())
    return registry


__all__ = [
    "Tool", "ToolRegistry", "build_registry",
    "GetCarDetails", "GetInsuranceQuotes", "GetAddonPrices", "GetRequiredFields",
    "JOURNEY",
]
