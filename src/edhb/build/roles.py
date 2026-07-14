"""Role assignment and quota logic."""

from __future__ import annotations

from edhb import config

# When a card carries tags with several roles, the first matching role in
# this order is its primary role (what quota slot it fills).
ROLE_PRIORITY = ["WINCON", "WIPE", "REMOVAL", "RAMP", "DRAW", "TUTOR", "PROTECTION", "SYNERGY"]


def primary_role(type_line: str, tag_roles: set[str]) -> str:
    if "Land" in type_line:
        return "LAND"
    for role in ROLE_PRIORITY:
        if role in tag_roles:
            return role
    return "SYNERGY"


def role_deficit_bonus(role: str, counts: dict[str, int]) -> float:
    """Positive while a role is under quota, negative once over-quota."""
    if role in ("LAND",):
        return 0.0
    quota = config.ROLE_QUOTAS.get(role)
    if quota is None:  # SYNERGY flex has no quota
        return 0.0
    deficit = quota - counts.get(role, 0)
    if deficit > 0:
        return 2.0 * min(1.0, deficit / quota) + 1.0
    return -1.0 * min(2.0, -deficit * 0.5)


def nonland_slots() -> int:
    return config.DECK_SIZE - 1 - config.ROLE_QUOTAS["LAND"]  # minus commander, minus lands
