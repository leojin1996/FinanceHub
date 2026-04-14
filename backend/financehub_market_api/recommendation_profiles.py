from __future__ import annotations

from financehub_market_api.models import AllocationDisplay, RiskProfile
from financehub_market_api.recommendation.rules.profile_catalog import (
    AGGRESSIVE_ALLOCATIONS as DOMAIN_AGGRESSIVE_ALLOCATIONS,
    BASE_ALLOCATIONS as DOMAIN_BASE_ALLOCATIONS,
)

BASE_ALLOCATIONS: dict[RiskProfile, AllocationDisplay] = {
    profile: AllocationDisplay(
        fund=allocation.fund,
        wealthManagement=allocation.wealth_management,
        stock=allocation.stock,
    )
    for profile, allocation in DOMAIN_BASE_ALLOCATIONS.items()
}

AGGRESSIVE_ALLOCATIONS: dict[RiskProfile, AllocationDisplay] = {
    profile: AllocationDisplay(
        fund=allocation.fund,
        wealthManagement=allocation.wealth_management,
        stock=allocation.stock,
    )
    for profile, allocation in DOMAIN_AGGRESSIVE_ALLOCATIONS.items()
}
