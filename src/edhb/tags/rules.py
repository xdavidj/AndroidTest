"""The tag rule set — the project's core IP.

~70 initial high-value rules across the synergy taxonomy, plus a
parametric tribal template instantiated over common creature types.
Precision over recall: each rule should have known-card assertions in
tests/test_tagger.py before it ships.
"""

from __future__ import annotations

from edhb.tags.ontology import Rule

TRIBES = [
    "zombie", "goblin", "elf", "vampire", "dragon", "human", "wizard", "soldier",
    "merfolk", "spirit", "sliver", "cat", "angel", "demon", "dinosaur", "pirate",
    "rat", "squirrel", "elemental", "knight", "rogue", "cleric", "warrior",
    "faerie", "bird", "snake", "insect", "spider", "treefolk", "dwarf",
]

RULES: list[Rule] = [
    # ---------------- Mana ----------------
    Rule("ramp.land_search", "ramp.land_search", "mana", "RAMP",
         all_regex=(r"search your library for .{0,80}land card", r"onto the battlefield"),
         type_none=("Land",)),
    Rule("ramp.rock", "ramp.rock", "mana", "RAMP",
         any_regex=(r"\{t\}: add \{", r"\{t\}: add (one|two|three) mana"),
         type_all=("Artifact",), type_none=("Creature", "Land")),
    Rule("ramp.dork", "ramp.dork", "mana", "RAMP",
         any_regex=(r"\{t\}: add \{", r"\{t\}: add (one|two|three) mana"),
         type_all=("Creature",), type_none=("Land",)),
    Rule("ritual", "ritual", "mana", "RAMP",
         any_regex=(r"add \{[wubrgc]\}\{[wubrgc]\}",),
         type_any=("Instant", "Sorcery")),
    Rule("cost_reducer", "cost_reducer", "mana", "SYNERGY",
         any_regex=(r"spells (you cast )?cost \{\d\} less to cast",
                    r"spells you cast cost \{\d\} less")),
    Rule("mana_doubler", "mana_doubler", "mana", "SYNERGY",
         any_regex=(r"produces (twice|three times) that (much|many)",
                    r"whenever you tap a land for mana, add")),
    Rule("treasure_producer", "treasure_producer", "mana", "SYNERGY",
         any_regex=(r"create (a|one|two|three|x|that many) treasure tokens?",
                    r"create .{0,30}treasure tokens?")),
    Rule("big_mana_payoff.x_spell", "big_mana_payoff.x_spell", "mana", "SYNERGY",
         mana_cost_contains="{X}",
         any_regex=(r"\bx\b",)),
    Rule("extra_land_drop", "extra_land_drop", "mana", "RAMP",
         any_regex=(r"you may play (an additional land|two additional lands)",)),

    # ---------------- Card advantage ----------------
    Rule("draw.engine", "draw.engine", "card_advantage", "DRAW",
         any_regex=(r"whenever [^\n.]{0,90}, (you may )?draw a card",)),
    Rule("draw.burst", "draw.burst", "card_advantage", "DRAW",
         any_regex=(r"draws? (two|three|four|five|x) cards",)),
    Rule("cantrip", "cantrip", "card_advantage", "SYNERGY",
         any_regex=(r"draw a card",), type_any=("Instant", "Sorcery"),
         max_mana_value=2.0),
    Rule("wheel", "wheel", "card_advantage", "DRAW",
         any_regex=(r"each player discards (their|his or her) hand,? (and|then) draws seven",
                    r"each player shuffles (their|his or her) hand")),
    Rule("impulse_draw", "impulse_draw", "card_advantage", "DRAW",
         all_regex=(r"exile the top .{0,30}of your library", r"may (play|cast)")),
    Rule("tutor.generic", "tutor.generic", "card_advantage", "TUTOR",
         any_regex=(r"search your library for a card",)),
    Rule("tutor.narrow", "tutor.narrow", "card_advantage", "TUTOR",
         any_regex=(r"search your library for (a|an|up to one) "
                    r"(creature|artifact|enchantment|instant|sorcery|equipment|aura|legendary)",)),
    Rule("reanimate", "reanimate", "card_advantage", "SYNERGY",
         any_regex=(r"return .{0,60}creature card from (your|a) graveyard to the battlefield",
                    r"put .{0,60}creature card from (your|a) graveyard onto the battlefield")),
    Rule("recursion.to_hand", "recursion.to_hand", "card_advantage", "SYNERGY",
         any_regex=(r"return .{0,60}card from your graveyard to your hand",)),
    Rule("self_mill", "self_mill", "card_advantage", "SYNERGY",
         any_regex=(r"you mill", r"mill (two|three|four|five|six|x|\d+) cards")),

    # ---------------- Interaction ----------------
    Rule("removal.creature", "removal.creature", "interaction", "REMOVAL",
         any_regex=(r"destroy target (creature|attacking creature|blocking creature)",)),
    Rule("removal.exile", "removal.exile", "interaction", "REMOVAL",
         any_regex=(r"exile target (creature|permanent|nonland permanent)",)),
    Rule("removal.permanent", "removal.permanent", "interaction", "REMOVAL",
         any_regex=(r"destroy target (permanent|nonland permanent|artifact|enchantment)",)),
    Rule("board_wipe", "board_wipe", "interaction", "WIPE",
         any_regex=(r"destroy all", r"exile all creatures",
                    r"deals? \d+ damage to each creature")),
    Rule("counterspell", "counterspell", "interaction", "REMOVAL",
         any_regex=(r"counter target (spell|noncreature spell|creature spell|activated ability)",)),
    Rule("gy_hate", "gy_hate", "interaction", "REMOVAL",
         any_regex=(r"exile (all cards from )?(each|all) (player's |opponent's )?graveyards?",)),
    Rule("stax.tax", "stax.tax", "interaction", "SYNERGY",
         any_regex=(r"spells? cost \{\d\} more to cast",)),
    Rule("sac_each", "sac_each", "interaction", "REMOVAL",
         any_regex=(r"each (player|opponent) sacrifices",)),

    # ---------------- Aristocrats ----------------
    Rule("sac_outlet.free", "sac_outlet.free", "aristocrats", "SYNERGY",
         any_regex=(r"(^|\n|, )sacrifice (a|another) creature:",)),
    Rule("sac_outlet.paid", "sac_outlet.paid", "aristocrats", "SYNERGY",
         any_regex=(r"\{[^}]{1,6}\}, sacrifice (a|another) creature",
                    r"\{t\}, sacrifice (a|another) creature")),
    Rule("death_payoff", "death_payoff", "aristocrats", "SYNERGY",
         any_regex=(r"whenever (a|another|another nontoken|~ or another) creature"
                    r"( you control)? dies",)),
    Rule("drain", "drain", "aristocrats", "SYNERGY",
         any_regex=(r"each opponent loses (\d+|x) life",)),
    Rule("token.creature_producer", "token.creature_producer", "aristocrats", "SYNERGY",
         any_regex=(r"create (a|an|one|two|three|four|x|\d+|that many) "
                    r"[^\n.]{0,60}creature tokens?",)),
    Rule("flicker", "flicker", "aristocrats", "SYNERGY",
         all_regex=(r"exile [^\n.]{0,60}(creature|permanent)",
                    r"return (it|that card|them|those cards) to the battlefield")),
    Rule("etb_trigger", "etb_trigger", "aristocrats", "SYNERGY",
         any_regex=(r"when(ever)? (~|this creature|this permanent) enters",),
         type_any=("Creature", "Artifact", "Enchantment")),

    # ---------------- Spellslinger ----------------
    Rule("cast_trigger.spells", "cast_trigger.spells", "spellslinger", "SYNERGY",
         any_regex=(r"whenever you cast (an instant|a sorcery|an instant or sorcery"
                    r"|a noncreature) spell",)),
    Rule("magecraft", "magecraft", "spellslinger", "SYNERGY",
         any_regex=(r"whenever you cast or copy",)),
    Rule("copy_spell", "copy_spell", "spellslinger", "SYNERGY",
         any_regex=(r"copy target (instant|sorcery|spell)",)),
    Rule("spell_recursion", "spell_recursion", "spellslinger", "SYNERGY",
         any_regex=(r"cast [^\n.]{0,60}from your graveyard",),
         keyword_any=()),
    Rule("kw.flashback", "spell_recursion", "spellslinger", "SYNERGY",
         keyword_any=("Flashback", "Jump-start", "Retrace", "Disturb")),
    Rule("storm", "storm", "spellslinger", "SYNERGY",
         keyword_any=("Storm",)),

    # ---------------- Counters ----------------
    Rule("p1p1.producer", "p1p1.producer", "counters", "SYNERGY",
         any_regex=(r"put (a|one|two|three|four|x|\d+) \+1/\+1 counters? on",)),
    Rule("proliferate", "proliferate", "counters", "SYNERGY",
         any_regex=(r"proliferate",)),
    Rule("counters_payoff", "counters_payoff", "counters", "SYNERGY",
         any_regex=(r"for each \+1/\+1 counter", r"each creature you control with a \+1/\+1 counter")),
    Rule("counter_doubler", "counter_doubler", "counters", "SYNERGY",
         any_regex=(r"(twice that many|double the number of) [^\n.]{0,30}counters",)),

    # ---------------- Go-wide ----------------
    Rule("token_doubler", "token_doubler", "go_wide", "SYNERGY",
         any_regex=(r"creates? twice that many( of those)? tokens",)),
    Rule("anthem", "anthem", "go_wide", "SYNERGY",
         any_regex=(r"creatures you control get \+",)),
    Rule("overrun_finisher", "overrun_finisher", "go_wide", "WINCON",
         all_regex=(r"creatures you control get \+", r"trample")),
    Rule("attack_trigger", "attack_trigger", "go_wide", "SYNERGY",
         any_regex=(r"whenever (a|another) creature( you control)? attacks",
                    r"whenever you attack")),

    # ---------------- Tap/untap ----------------
    Rule("tap_ability", "tap_ability", "tap_untap", "SYNERGY",
         any_regex=(r"\{t\}[^:\n]{0,40}:",), type_none=("Land",)),
    Rule("untapper", "untapper", "tap_untap", "SYNERGY",
         any_regex=(r"untap (target|another target|all|up to (two|three|x) target|each)",)),
    Rule("extra_combat", "extra_combat", "tap_untap", "WINCON",
         any_regex=(r"additional combat phase",)),

    # ---------------- Lands-matter ----------------
    Rule("landfall", "landfall", "lands", "SYNERGY",
         any_regex=(r"whenever a land (you control )?enters",)),
    Rule("land_recursion", "land_recursion", "lands", "SYNERGY",
         any_regex=(r"return .{0,40}land card from your graveyard",)),

    # ---------------- Artifacts / enchantments ----------------
    Rule("artifact_cast_trigger", "artifact_cast_trigger", "artifacts", "SYNERGY",
         any_regex=(r"whenever you cast an artifact spell",)),
    Rule("affinity_improvise", "affinity_improvise", "artifacts", "SYNERGY",
         keyword_any=("Affinity", "Improvise")),
    Rule("artifacts_payoff", "artifacts_payoff", "artifacts", "SYNERGY",
         any_regex=(r"for each artifact you control",
                    r"whenever an artifact (you control )?enters")),
    Rule("constellation", "constellation", "enchantments", "SYNERGY",
         any_regex=(r"whenever (an enchantment|~ or another enchantment) "
                    r"(you control )?enters",)),
    Rule("enchantress_draw", "enchantress_draw", "enchantments", "DRAW",
         all_regex=(r"whenever you cast an enchantment spell", r"draw")),

    # ---------------- Graveyard ----------------
    Rule("discard_outlet", "discard_outlet", "graveyard", "SYNERGY",
         any_regex=(r"discard a card:", r"\{t\}[^:\n]{0,30}, discard a card",
                    r"discard (a|two) cards?[,:] ")),
    Rule("kw.gy_cast", "gy_value", "graveyard", "SYNERGY",
         keyword_any=("Delve", "Escape", "Embalm", "Eternalize", "Unearth", "Encore")),
    Rule("threshold_payoff", "threshold_payoff", "graveyard", "SYNERGY",
         any_regex=(r"threshold", r"delirium",
                    r"if [^\n.]{0,40}cards? (are )?in your graveyard")),

    # ---------------- Lifegain ----------------
    Rule("lifegain_producer", "lifegain_producer", "lifegain", "SYNERGY",
         any_regex=(r"you gain (\d+|x) life",)),
    Rule("lifegain_payoff", "lifegain_payoff", "lifegain", "SYNERGY",
         any_regex=(r"whenever you gain life",)),

    # ---------------- Wincons ----------------
    Rule("alt_wincon", "alt_wincon", "wincons", "WINCON",
         any_regex=(r"you win the game",)),
    Rule("opp_lose_wincon", "opp_lose_wincon", "wincons", "WINCON",
         any_regex=(r"each opponent loses the game",)),
    Rule("burn_finisher", "burn_finisher", "wincons", "WINCON",
         any_regex=(r"deals? x damage to (each opponent|any target|each player)",)),
    Rule("unblockable_grant", "unblockable_grant", "wincons", "SYNERGY",
         any_regex=(r"can't be blocked",)),
    Rule("kw.infect", "infect", "wincons", "WINCON",
         keyword_any=("Infect", "Toxic")),

    # ---------------- Protection / consistency ----------------
    Rule("protect.grant", "protect.grant", "protection", "PROTECTION",
         any_regex=(r"(gains?|have|has) (hexproof|indestructible|shroud)",
                    r"protection from",)),
    Rule("phase_protection", "protect.grant", "protection", "PROTECTION",
         any_regex=(r"phases? out",)),
    Rule("haste_enabler", "haste_enabler", "protection", "SYNERGY",
         any_regex=(r"(creatures you control|it) (have|has|gains?) haste",)),
]


def tribal_rules() -> list[Rule]:
    """Parametric tribal template instantiated per tribe."""
    out: list[Rule] = []
    for t in TRIBES:
        cap = t.capitalize()
        out.append(Rule(
            f"lord.{t}", "lord", "tribal", "SYNERGY", param=t,
            any_regex=(rf"(other )?{t}s? (creatures )?you control get \+",
                       rf"{t} creatures (you control )?get \+"),
        ))
        out.append(Rule(
            f"typal_payoff.{t}", "typal_payoff", "tribal", "SYNERGY", param=t,
            any_regex=(rf"whenever (a|another|~ or another) {t} (you control )?enters",
                       rf"for each {t} you control",
                       rf"whenever (a|another|~ or another) {t} (you control )?(dies|attacks)"),
        ))
        out.append(Rule(
            f"typal_member.{t}", "typal_member", "tribal", "SYNERGY", param=t,
            type_all=(cap,),
        ))
    return out


def all_rules() -> list[Rule]:
    rules = RULES + tribal_rules()
    # Changelings are members of every tribe.
    for t in TRIBES:
        rules.append(Rule(f"changeling.{t}", "typal_member", "tribal", "SYNERGY",
                          param=t, keyword_any=("Changeling",)))
    return rules
