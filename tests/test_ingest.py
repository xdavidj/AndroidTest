from edhb import config
from edhb.ingest import scryfall, spellbook


def test_oracle_ingest_counts(conn, oracle_cards):
    n = scryfall.ingest_oracle_cards(conn, oracle_cards)
    assert n == len(oracle_cards)


def test_color_identity_mask(conn, oracle_cards):
    scryfall.ingest_oracle_cards(conn, oracle_cards)
    row = conn.execute(
        "SELECT color_identity FROM cards WHERE name = 'Wilhelt, the Rotcleaver'"
    ).fetchone()
    assert row["color_identity"] == config.color_mask("UB")


def test_commander_eligibility(conn, oracle_cards):
    scryfall.ingest_oracle_cards(conn, oracle_cards)
    rows = {
        r["name"]: r["can_be_commander"]
        for r in conn.execute("SELECT name, can_be_commander FROM cards")
    }
    assert rows["Wilhelt, the Rotcleaver"] == 1
    assert rows["Opt"] == 0
    assert rows["Sol Ring"] == 0


def test_cheapest_price_rollup(conn, oracle_cards, printings):
    scryfall.ingest_oracle_cards(conn, oracle_cards)
    scryfall.ingest_printings(conn, printings)
    scryfall.rollup_cheapest_prices(conn)
    row = conn.execute("SELECT price_usd FROM cards WHERE name = 'Sol Ring'").fetchone()
    # Cheapest paper printing is the $0.90 foil; digital ($0.02) and
    # oversized ($0.01) printings must be ignored.
    assert row["price_usd"] == 0.90


def test_provisional_price_without_printings(conn, oracle_cards):
    scryfall.ingest_oracle_cards(conn, oracle_cards)
    row = conn.execute("SELECT price_usd FROM cards WHERE name = 'Opt'").fetchone()
    assert row["price_usd"] == 0.15


def test_spellbook_filters(conn, oracle_cards, spellbook_payload):
    scryfall.ingest_oracle_cards(conn, oracle_cards)
    n = spellbook.ingest_variants(conn, spellbook_payload)
    # NEEDS_REVIEW and non-commander-legal variants are dropped.
    assert n == 1
    combo = conn.execute("SELECT * FROM combos").fetchone()
    assert combo["combo_id"] == "gravecrawler-altar-cutthroat"
    assert combo["card_count"] == 3
    members = {
        r["oracle_id"]
        for r in conn.execute("SELECT oracle_id FROM combo_cards WHERE combo_id = ?",
                              (combo["combo_id"],))
    }
    assert members == {"oid-gravecrawler", "oid-ashnods-altar", "oid-zulaport-cutthroat"}


def test_combo_quality_ordering():
    win2 = spellbook.combo_quality(["Win the game"], 2, False, "")
    win4 = spellbook.combo_quality(["Win the game"], 4, False, "")
    mana2 = spellbook.combo_quality(["Infinite mana"], 2, False, "")
    templated = spellbook.combo_quality(["Win the game"], 2, True, "")
    assert win2 > win4
    assert win2 > mana2
    assert win2 > templated
