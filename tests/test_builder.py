"""Builder tests on a synthetic pool large enough to fill a real deck."""

import pytest

from edhb.build.builder import BuildError, build_deck, suggest_commanders
from edhb.ingest import scryfall
from edhb.tags.tagger import tag_all


def card(oid, name, text, type_line, cmc, price, colors=None, legendary=False):
    return {
        "oracle_id": oid, "name": name, "oracle_text": text,
        "mana_cost": "{%d}" % int(cmc), "cmc": float(cmc),
        "type_line": ("Legendary " if legendary else "") + type_line,
        "colors": colors or [], "color_identity": colors or [],
        "keywords": [], "layout": "normal",
        "legalities": {"commander": "legal"},
        "prices": {"usd": str(price)}, "games": ["paper"],
    }


TEMPLATES = [
    ("Ramp Rock", "{T}: Add {C}{C}.", "Artifact", 2, 12),
    ("Draw Engine", "Whenever you cast a noncreature spell, draw a card.", "Creature — Zombie", 3, 12),
    ("Spot Removal", "Destroy target creature.", "Instant", 2, 10),
    ("Board Wipe", "Destroy all creatures.", "Sorcery", 5, 3),
    ("Token Maker", "Create two 1/1 black Zombie creature tokens.", "Sorcery", 2, 8),
    ("Sac Outlet", "Sacrifice a creature: Scry 1.", "Creature — Zombie", 1, 8),
    ("Death Payoff", "Whenever another creature you control dies, each opponent loses 1 life.", "Creature — Zombie", 2, 8),
    ("Tutor Box", "Search your library for a card, put it into your hand, then shuffle.", "Sorcery", 3, 3),
    ("Protector", "Creatures you control gain hexproof until end of turn.", "Instant", 2, 4),
    ("Win Button", "At the beginning of your upkeep, you win the game.", "Enchantment", 6, 2),
]


@pytest.fixture
def synth_db(conn):
    cards = [card("oid-cmd", "Test Overlord",
                  "Whenever another creature you control dies, create a 2/2 black Zombie creature token.",
                  "Creature — Zombie Lord", 4, 0.5, colors=["B"], legendary=True)]
    i = 0
    for base_name, text, type_line, cmc, count in TEMPLATES:
        for k in range(count):
            i += 1
            cards.append(card(f"oid-s{i}", f"{base_name} {k+1}", text, type_line,
                              cmc, 0.25, colors=["B"]))
    # Expensive high-synergy cards that only fit at larger budgets.
    for k in range(5):
        i += 1
        cards.append(card(f"oid-exp-sac{k}", f"Premium Outlet {k+1}",
                          "Sacrifice a creature: Add {C}{C}.", "Artifact", 2, 5.0))
        i += 1
        cards.append(card(f"oid-exp-pay{k}", f"Premium Payoff {k+1}",
                          "Whenever another creature you control dies, each opponent loses 2 life. "
                          "Create a 1/1 black Zombie creature token.",
                          "Creature — Zombie", 3, 5.0, colors=["B"]))
    scryfall.ingest_oracle_cards(conn, cards)
    tag_all(conn)
    return conn


def assert_legal(result, budget):
    total_cards = 1 + len(result.nonlands) + sum(land["qty"] for land in result.lands)
    assert total_cards == 100
    names = [c.name for c in result.nonlands]
    assert len(names) == len(set(names)), "singleton violated"
    assert result.commander.name not in names
    assert result.total_price <= budget + 1e-6


def test_build_legal_deck(synth_db):
    result = build_deck(synth_db, "Test Overlord", budget=25.0)
    assert_legal(result, 25.0)
    assert result.score["total"] > 0


def test_budget_is_hard_constraint(synth_db):
    for budget in (20.0, 40.0):
        result = build_deck(synth_db, "Test Overlord", budget=budget)
        assert result.total_price <= budget


def test_power_scales_with_budget(synth_db):
    low = build_deck(synth_db, "Test Overlord", budget=22.0)
    high = build_deck(synth_db, "Test Overlord", budget=60.0)
    assert_legal(low, 22.0)
    assert_legal(high, 60.0)
    assert high.score["total"] >= low.score["total"]
    # The bigger budget should actually spend more.
    assert high.total_price > low.total_price


def test_deterministic_under_seed(synth_db):
    a = build_deck(synth_db, "Test Overlord", budget=25.0, seed=7)
    b = build_deck(synth_db, "Test Overlord", budget=25.0, seed=7)
    assert [c.name for c in a.nonlands] == [c.name for c in b.nonlands]


def test_unknown_commander_raises(synth_db):
    with pytest.raises(BuildError):
        build_deck(synth_db, "Definitely Not A Card", budget=25.0)


def test_over_budget_commander_raises(synth_db, conn):
    conn.execute("UPDATE cards SET price_usd = 99.0 WHERE name = 'Test Overlord'")
    with pytest.raises(BuildError):
        build_deck(synth_db, "Test Overlord", budget=25.0)


def test_suggest_commanders_runs(synth_db):
    results = suggest_commanders(synth_db, budget=30.0, top=5)
    assert results
    assert results[0]["name"] == "Test Overlord"


def test_fixture_deck_end_to_end(loaded):
    # Fixture pool is far too small for a full deck: builder must refuse
    # loudly instead of emitting an illegal list.
    with pytest.raises(BuildError):
        build_deck(loaded, "Wilhelt", budget=50.0)


def test_export_and_explain_smoke(synth_db):
    from edhb.report import explain, export

    result = build_deck(synth_db, "Test Overlord", budget=25.0)
    text = export.to_text(result)
    assert "1 Test Overlord" in text
    assert "// Lands" in text
    js = export.to_json(result)
    assert '"total_price"' in js
    report = explain.explain(result)
    assert "Power score" in report
