import pytest

from edhb.tags.tagger import tags_for_card


def tag_names(conn, oracle_id):
    return {(t, p) for t, p, _ in tags_for_card(conn, oracle_id)}


@pytest.mark.parametrize("oracle_id,expected", [
    ("oid-rampant-growth", ("ramp.land_search", "")),
    ("oid-sol-ring", ("ramp.rock", "")),
    ("oid-llanowar-elves", ("ramp.dork", "")),
    ("oid-viscera-seer", ("sac_outlet.free", "")),
    ("oid-ashnods-altar", ("sac_outlet.free", "")),
    ("oid-zulaport-cutthroat", ("death_payoff", "")),
    ("oid-zulaport-cutthroat", ("drain", "")),
    ("oid-blood-artist", ("death_payoff", "")),
    ("oid-raise-the-alarm", ("token.creature_producer", "")),
    ("oid-guttersnipe", ("cast_trigger.spells", "")),
    ("oid-opt", ("cantrip", "")),
    ("oid-swords", ("removal.exile", "")),
    ("oid-blasphemous-act", ("board_wipe", "")),
    ("oid-counterspell", ("counterspell", "")),
    ("oid-lord-of-the-undead", ("lord", "zombie")),
    ("oid-lord-of-the-undead", ("recursion.to_hand", "")),
    ("oid-diregraf-captain", ("lord", "zombie")),
    ("oid-diregraf-captain", ("typal_payoff", "zombie")),
    ("oid-diregraf-captain", ("typal_member", "zombie")),
    ("oid-gravecrawler", ("spell_recursion", "")),
    ("oid-gravecrawler", ("typal_member", "zombie")),
    ("oid-wilhelt", ("typal_payoff", "zombie")),
    ("oid-wilhelt", ("token.creature_producer", "")),
])
def test_canonical_tags(loaded, oracle_id, expected):
    assert expected in tag_names(loaded, oracle_id)


@pytest.mark.parametrize("oracle_id,absent_tag", [
    ("oid-rampant-growth", "sac_outlet.free"),
    ("oid-opt", "draw.engine"),
    ("oid-blasphemous-act", "cost_reducer"),  # self-reduction is not a reducer engine
    ("oid-swords", "removal.creature"),
])
def test_precision_negatives(loaded, oracle_id, absent_tag):
    assert absent_tag not in {t for t, _, _ in tags_for_card(loaded, oracle_id)}


def test_untagged_card_gets_nothing(loaded):
    # Digital-only test card is not commander legal, so tagger skips it.
    assert tags_for_card(loaded, "oid-digital-only") == []
