from edhb.synergy.graph import SynergyContext

POOL = [
    "oid-viscera-seer", "oid-zulaport-cutthroat", "oid-blood-artist",
    "oid-ashnods-altar", "oid-gravecrawler", "oid-raise-the-alarm",
    "oid-rampant-growth", "oid-lord-of-the-undead", "oid-diregraf-captain",
]


def test_complementary_tag_edge(loaded):
    ctx = SynergyContext(loaded, POOL)
    # sac_outlet.free + death_payoff = 3.0
    assert ctx.tag_edge("oid-viscera-seer", "oid-zulaport-cutthroat") >= 3.0
    # unrelated cards have no edge
    assert ctx.tag_edge("oid-rampant-growth", "oid-blood-artist") == 0.0


def test_parametric_tribal_edge(loaded):
    ctx = SynergyContext(loaded, POOL)
    # lord(zombie) on Lord of the Undead + typal_member(zombie) on Gravecrawler
    assert ctx.tag_edge("oid-lord-of-the-undead", "oid-gravecrawler") >= 1.5


def test_combo_bonus(loaded):
    ctx = SynergyContext(loaded, POOL)
    # 3-card combo shared by Gravecrawler and Ashnod's Altar => +2.0
    assert ctx.combo_edge("oid-gravecrawler", "oid-ashnods-altar") == 2.0
    assert ctx.combo_edge("oid-gravecrawler", "oid-raise-the-alarm") == 0.0


def test_combo_dropped_when_member_outside_pool(loaded):
    ctx = SynergyContext(loaded, [p for p in POOL if p != "oid-zulaport-cutthroat"])
    # Combo requires Zulaport Cutthroat; without it in the pool, no bonus.
    assert ctx.combo_edge("oid-gravecrawler", "oid-ashnods-altar") == 0.0


def test_edge_symmetry_and_explain(loaded):
    ctx = SynergyContext(loaded, POOL)
    a, b = "oid-viscera-seer", "oid-zulaport-cutthroat"
    assert ctx.edge(a, b) == ctx.edge(b, a)
    assert ctx.explain_edge(a, b)
