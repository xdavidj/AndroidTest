import json
from pathlib import Path

import pytest

from edhb import db
from edhb.ingest import scryfall, spellbook

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


@pytest.fixture
def oracle_cards():
    return json.loads((FIXTURES / "oracle_sample.json").read_text())


@pytest.fixture
def printings():
    return json.loads((FIXTURES / "default_sample.json").read_text())


@pytest.fixture
def spellbook_payload():
    return json.loads((FIXTURES / "spellbook_sample.json").read_text())


@pytest.fixture
def loaded(conn, oracle_cards, printings, spellbook_payload):
    """DB with fixtures ingested and tagged."""
    from edhb.tags.tagger import tag_all

    scryfall.ingest_oracle_cards(conn, oracle_cards)
    scryfall.ingest_printings(conn, printings)
    scryfall.rollup_cheapest_prices(conn)
    spellbook.ingest_variants(conn, spellbook_payload)
    tag_all(conn)
    return conn
