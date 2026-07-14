"""Marginal card value during the build, and the deck power score."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from edhb import config
from edhb.build import roles

if TYPE_CHECKING:
    from edhb.synergy.graph import SynergyContext


@dataclass
class CardRec:
    """In-memory card record used by the builder."""
    oracle_id: str
    name: str
    price: float
    mana_value: float
    type_line: str
    mana_cost: str
    tag_roles: set[str] = field(default_factory=set)
    n_tags: int = 0

    @property
    def primary_role(self) -> str:
        return roles.primary_role(self.type_line, self.tag_roles)

    @property
    def is_land(self) -> bool:
        return "Land" in self.type_line


COMMANDER_EDGE_WEIGHT = 3.0
COMBO_COMPLETION_BONUS = 8.0
COMBO_PROGRESS_BONUS = 1.0
QUALITY_PER_TAG = 0.2
CURVE_PENALTY_PER_MV = 0.3
CURVE_FREE_MV = 4.0


def combo_bonus(candidate: str, deck_ids: set[str], ctx: "SynergyContext") -> float:
    """Reward completing (or advancing) a known combo line."""
    bonus = 0.0
    for combo_id in ctx.combos_by_card.get(candidate, ()):  # combos fully inside the pool
        cards = ctx.combo_cards[combo_id]
        have = sum(1 for c in cards if c != candidate and c in deck_ids)
        need = len(cards) - 1
        if need > 0 and have == need:
            bonus += COMBO_COMPLETION_BONUS
        elif have > 0:
            bonus += COMBO_PROGRESS_BONUS * have
    return bonus


def marginal_value(
    card: CardRec,
    synergy_to_deck: float,
    commander_edge: float,
    deck_ids: set[str],
    role_counts: dict[str, int],
    ctx: "SynergyContext",
) -> float:
    value = synergy_to_deck
    value += COMMANDER_EDGE_WEIGHT * commander_edge
    value += combo_bonus(card.oracle_id, deck_ids, ctx)
    value += roles.role_deficit_bonus(card.primary_role, role_counts)
    value += QUALITY_PER_TAG * card.n_tags
    if card.price < config.NOVELTY_PRICE_THRESHOLD:
        value += config.NOVELTY_BONUS
    value -= CURVE_PENALTY_PER_MV * max(0.0, card.mana_value - CURVE_FREE_MV)
    return value


# --- Deck power score (0-100) ----------------------------------------------


def deck_power_score(
    nonland_ids: list[str],
    commander_id: str,
    ctx: "SynergyContext",
    cards: dict[str, CardRec],
    land_count: int,
) -> dict[str, float]:
    """Component breakdown; 'total' is the headline 0-100 number."""
    ids = list(nonland_ids)
    n = len(ids)

    # Synergy density: mean pairwise edge among nonlands + commander edges.
    pair_sum, pair_count = 0.0, 0
    for i in range(n):
        for j in range(i + 1, n):
            pair_sum += ctx.edge(ids[i], ids[j])
            pair_count += 1
        pair_sum += ctx.edge(ids[i], commander_id) * 2  # commander is always available
        pair_count += 2
    density = pair_sum / pair_count if pair_count else 0.0
    synergy_pts = min(40.0, density * 55.0)

    # Combo lines fully present in deck (+commander), diminishing after 2.
    deck_set = set(ids) | {commander_id}
    complete = [
        cid for cid, members in ctx.combo_cards.items()
        if all(m in deck_set for m in members)
    ]
    qualities = sorted(
        (max(0.0, ctx.combo_meta[c]["quality"]) for c in complete if c in ctx.combo_meta),
        reverse=True,
    )
    combo_raw = sum(q if i < 2 else q * 0.4 for i, q in enumerate(qualities))
    combo_pts = min(25.0, combo_raw * 1.5)

    # Consistency: tutors + redundancy (roles with >= 3 members beyond quota roles).
    tutor_count = sum(1 for i in ids if "TUTOR" in cards[i].tag_roles)
    consistency_pts = min(10.0, tutor_count * 2.0 + (2.0 if len(complete) >= 2 else 0.0))

    # Interaction vs quota.
    interaction = sum(1 for i in ids if cards[i].primary_role in ("REMOVAL", "WIPE"))
    interaction_quota = config.ROLE_QUOTAS["REMOVAL"] + config.ROLE_QUOTAS["WIPE"]
    interaction_pts = min(10.0, 10.0 * interaction / interaction_quota)

    # Mana health: land count in band + curve.
    mvs = [cards[i].mana_value for i in ids]
    avg_mv = sum(mvs) / len(mvs) if mvs else 0.0
    land_pts = 8.0 - min(8.0, abs(land_count - config.ROLE_QUOTAS["LAND"]) * 2.0)
    curve_pts = 7.0 - min(7.0, max(0.0, avg_mv - 3.2) * 3.0)
    mana_pts = max(0.0, land_pts + curve_pts)

    total = synergy_pts + combo_pts + consistency_pts + interaction_pts + mana_pts
    return {
        "synergy_density": round(synergy_pts, 1),
        "combos": round(combo_pts, 1),
        "consistency": round(consistency_pts, 1),
        "interaction": round(interaction_pts, 1),
        "mana": round(mana_pts, 1),
        "total": round(total, 1),
        "raw_density": round(density, 3),
        "complete_combo_ids": complete,
        "avg_mana_value": round(avg_mv, 2),
    }
