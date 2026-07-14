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
    efficiency: float = 0.0

    @property
    def primary_role(self) -> str:
        return roles.primary_role(self.type_line, self.tag_roles)

    @property
    def is_land(self) -> bool:
        return "Land" in self.type_line


import re as _re

_ADD_MANA = _re.compile(r"add ((?:\{[wubrgc0-9]\})+)")
_SYMBOL = _re.compile(r"\{[wubrgc0-9]\}")


def efficiency_prior(tag_roles: set[str], mana_value: float, type_line: str,
                     oracle_text: str) -> float:
    """Intrinsic rate-of-exchange quality, computed from the card itself.

    Commander fundamentals: cheap mana acceleration and cheap interaction
    win games. Tag-pair synergy can't see that Sol Ring ({1} for {C}{C})
    is better than a 3-mana rock, so rate the exchange directly.
    Self-derived - no popularity data.
    """
    score = 0.0
    text = (oracle_text or "").lower()
    if "RAMP" in tag_roles:
        one_shot = "Instant" in type_line or "Sorcery" in type_line
        if one_shot:
            # Rituals are tempo, not acceleration: they add mana once,
            # not every turn. Modest flat credit.
            score += 1.0
        else:
            score += (3.5 - max(1.0, mana_value)) * 4.0
            m = _ADD_MANA.search(text)
            if m:  # extra credit per mana produced beyond the first, each turn
                produced = len(_SYMBOL.findall(m.group(1)))
                score += 6.0 * max(0, produced - 1)
            if "spend this mana only" in text:
                score -= 4.0  # restricted mana is a real downgrade
    if "REMOVAL" in tag_roles:
        score += (3.5 - mana_value) * 2.0
        if "Instant" in type_line:
            score += 1.5
    if "WIPE" in tag_roles:
        score += (5.5 - mana_value) * 1.0
    if "TUTOR" in tag_roles:
        score += (4.5 - mana_value) * 1.5
    if "DRAW" in tag_roles:
        score += (4.5 - mana_value) * 1.0
    return max(-3.0, min(20.0, score))


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


SYNERGY_DAMP = 14.0


def marginal_value(
    card: CardRec,
    synergy_to_deck: float,
    commander_edge: float,
    deck_ids: set[str],
    role_counts: dict[str, int],
    ctx: "SynergyContext",
) -> float:
    import math
    # Sub-linear in accumulated synergy ABOVE the knee: the 10th card
    # feeding the same trigger is worth less than the 1st, so raw pile-on
    # can't drown out rate quality at the pick margin. Below the knee the
    # response stays linear (a bare sqrt would inflate tiny synergies).
    syn = max(0.0, synergy_to_deck)
    value = min(syn, math.sqrt(syn * SYNERGY_DAMP))
    value += COMMANDER_EDGE_WEIGHT * commander_edge
    value += combo_bonus(card.oracle_id, deck_ids, ctx)
    value += roles.role_deficit_bonus(card.primary_role, role_counts)
    value += QUALITY_PER_TAG * card.n_tags
    value += card.efficiency
    if card.price < config.NOVELTY_PRICE_THRESHOLD:
        value += config.NOVELTY_BONUS
    value -= CURVE_PENALTY_PER_MV * max(0.0, card.mana_value - CURVE_FREE_MV)
    return value


# --- Deck power score (0-100) ----------------------------------------------


def _saturating(x: float, scale: float, ceiling: float) -> float:
    """Diminishing-returns curve: approaches `ceiling`, never hits a wall.

    Hard caps made every dense budget deck score identically, so extra
    budget looked worthless to the evaluator.
    """
    import math
    return ceiling * (1.0 - math.exp(-x / scale))


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
    synergy_pts = _saturating(density, scale=0.55, ceiling=35.0)

    # Combo lines fully present in deck (+commander). Geometric weighting:
    # the best few lines carry the value; the 400th redundant variant is
    # nearly worthless.
    deck_set = set(ids) | {commander_id}
    complete = [
        cid for cid, members in ctx.combo_cards.items()
        if all(m in deck_set for m in members)
    ]
    qualities = sorted(
        (max(0.0, ctx.combo_meta[c]["quality"]) for c in complete if c in ctx.combo_meta),
        reverse=True,
    )
    combo_raw = sum(q * (0.6 ** i) for i, q in enumerate(qualities[:24]))
    combo_pts = _saturating(combo_raw, scale=14.0, ceiling=25.0)

    # Consistency: tutors find the combo instead of hoping to draw it.
    tutor_count = sum(1 for i in ids if "TUTOR" in cards[i].tag_roles)
    consistency_raw = tutor_count * 2.0 + (2.0 if len(complete) >= 2 else 0.0)
    consistency_pts = _saturating(consistency_raw, scale=8.0, ceiling=15.0)

    # Interaction vs quota.
    interaction = sum(1 for i in ids if cards[i].primary_role in ("REMOVAL", "WIPE"))
    interaction_quota = config.ROLE_QUOTAS["REMOVAL"] + config.ROLE_QUOTAS["WIPE"]
    interaction_pts = _saturating(
        15.0 * interaction / interaction_quota, scale=10.0, ceiling=15.0)

    # Mana health: land count in band + curve + actual ramp count.
    # ~10 ramp / 38 mana sources is the Commander skeleton; a deck with no
    # acceleration cannot deploy its plan on schedule.
    mvs = [cards[i].mana_value for i in ids]
    avg_mv = sum(mvs) / len(mvs) if mvs else 0.0
    land_pts = 3.0 - min(3.0, abs(land_count - config.ROLE_QUOTAS["LAND"]) * 1.0)
    curve_pts = 3.0 - min(3.0, max(0.0, avg_mv - 3.2) * 1.5)
    ramp_count = sum(1 for i in ids if "RAMP" in cards[i].tag_roles)
    ramp_pts = 4.0 * min(1.0, ramp_count / config.ROLE_QUOTAS["RAMP"])
    mana_pts = max(0.0, land_pts + curve_pts + ramp_pts)

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
