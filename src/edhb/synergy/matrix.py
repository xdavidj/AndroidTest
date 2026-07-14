"""Complementary tag-pair weights: the heart of self-derived synergy.

Each entry says "a card with tag A and a card with tag B work well
together, worth W". Pairs are unordered. Parametric pairs (tribal)
require the SAME param on both sides. No popularity data anywhere.
"""

from __future__ import annotations

# (tag_a, tag_b, weight)
PAIRS: list[tuple[str, str, float]] = [
    # Aristocrats
    ("sac_outlet.free", "death_payoff", 3.0),
    ("sac_outlet.paid", "death_payoff", 2.0),
    ("token.creature_producer", "sac_outlet.free", 2.0),
    ("token.creature_producer", "sac_outlet.paid", 1.5),
    ("token.creature_producer", "death_payoff", 1.5),
    ("death_payoff", "drain", 1.0),
    ("etb_trigger", "flicker", 2.5),
    ("etb_trigger", "reanimate", 2.0),
    ("token.creature_producer", "drain", 1.0),

    # Go-wide
    ("token.creature_producer", "anthem", 1.5),
    ("token.creature_producer", "overrun_finisher", 2.0),
    ("token.creature_producer", "token_doubler", 2.5),
    ("token.creature_producer", "attack_trigger", 1.5),
    ("anthem", "attack_trigger", 1.0),
    ("haste_enabler", "token.creature_producer", 1.0),

    # Spellslinger
    ("cast_trigger.spells", "cantrip", 2.5),
    ("magecraft", "cantrip", 2.5),
    ("cast_trigger.spells", "cost_reducer", 2.0),
    ("magecraft", "copy_spell", 2.0),
    ("copy_spell", "cast_trigger.spells", 1.5),
    ("spell_recursion", "cast_trigger.spells", 1.5),
    ("spell_recursion", "self_mill", 1.5),
    ("storm", "ritual", 2.5),
    ("storm", "cost_reducer", 2.5),
    ("cast_trigger.spells", "ritual", 1.0),

    # Tap/untap
    ("tap_ability", "untapper", 2.5),
    ("ramp.dork", "untapper", 1.5),

    # Big mana
    ("mana_doubler", "big_mana_payoff.x_spell", 2.5),
    ("treasure_producer", "big_mana_payoff.x_spell", 2.0),
    ("ritual", "big_mana_payoff.x_spell", 1.0),
    ("mana_doubler", "ramp.land_search", 1.0),

    # Lands-matter
    ("ramp.land_search", "landfall", 2.0),
    ("extra_land_drop", "landfall", 2.5),
    ("land_recursion", "landfall", 1.5),

    # Artifacts / enchantments
    ("treasure_producer", "artifacts_payoff", 2.0),
    ("treasure_producer", "affinity_improvise", 2.0),
    ("artifact_cast_trigger", "affinity_improvise", 1.5),
    ("ramp.rock", "artifacts_payoff", 1.5),
    ("constellation", "enchantress_draw", 2.0),

    # Counters
    ("p1p1.producer", "counters_payoff", 2.5),
    ("p1p1.producer", "proliferate", 2.5),
    ("counter_doubler", "p1p1.producer", 2.5),
    ("proliferate", "counters_payoff", 2.0),
    ("proliferate", "infect", 3.0),

    # Lifegain
    ("lifegain_producer", "lifegain_payoff", 2.5),

    # Graveyard
    ("self_mill", "reanimate", 2.5),
    ("discard_outlet", "reanimate", 2.5),
    ("self_mill", "gy_value", 2.0),
    ("discard_outlet", "gy_value", 2.0),
    ("self_mill", "threshold_payoff", 2.0),
    ("self_mill", "recursion.to_hand", 1.5),
    ("wheel", "death_payoff", 0.5),

    # Combat
    ("extra_combat", "attack_trigger", 2.0),
    ("unblockable_grant", "infect", 2.0),

    # Tribal (parametric: params must match)
    ("lord", "typal_member", 1.5),
    ("typal_payoff", "typal_member", 1.5),
]

# Tags whose pairwise contribution is capped so 10 copies of the same
# producer tag don't read as ever-deeper synergy.
EDGE_CAP = 6.0
PARAMETRIC_TAGS = {"lord", "typal_payoff", "typal_member"}


def weight_index() -> dict[frozenset[str], float]:
    idx: dict[frozenset[str], float] = {}
    for a, b, w in PAIRS:
        key = frozenset((a, b))
        idx[key] = max(idx.get(key, 0.0), w)
    return idx
