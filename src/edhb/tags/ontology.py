"""Tag and rule datatypes.

A Tag is a machine-detectable card feature (e.g. `sac_outlet.free`,
`death_payoff`). Every tag carries a deck-building ROLE used for quotas.
A Rule is a declarative recipe for detecting a tag from card data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROLES = {"LAND", "RAMP", "DRAW", "REMOVAL", "WIPE", "TUTOR", "PROTECTION", "WINCON", "SYNERGY"}


@dataclass(frozen=True)
class Rule:
    """All specified predicates must pass; `any_regex` passes if ANY matches.

    Regexes run against normalized oracle text: lowercased, card name
    replaced by `~`, reminder text stripped, MDFC faces unioned.
    """

    id: str                      # unique rule id (usually == tag)
    tag: str                     # tag name; parametric rules use e.g. "lord" + param
    category: str                # taxonomy bucket, for reporting
    role: str                    # LAND/RAMP/DRAW/.../SYNERGY
    any_regex: tuple[str, ...] = ()
    all_regex: tuple[str, ...] = ()
    negate_regex: tuple[str, ...] = ()
    keyword_any: tuple[str, ...] = ()   # matches Scryfall `keywords`
    type_all: tuple[str, ...] = ()      # substrings that must ALL be in type_line
    type_any: tuple[str, ...] = ()      # at least one must be in type_line
    type_none: tuple[str, ...] = ()     # none may be in type_line
    mana_cost_contains: str = ""
    max_mana_value: float | None = None
    param: str = ""                     # parametric tag instance (e.g. tribe name)

    def compiled(self) -> "CompiledRule":
        return CompiledRule(
            rule=self,
            any_re=[re.compile(p) for p in self.any_regex],
            all_re=[re.compile(p) for p in self.all_regex],
            neg_re=[re.compile(p) for p in self.negate_regex],
        )


@dataclass
class CompiledRule:
    rule: Rule
    any_re: list[re.Pattern] = field(default_factory=list)
    all_re: list[re.Pattern] = field(default_factory=list)
    neg_re: list[re.Pattern] = field(default_factory=list)

    def matches(self, text: str, type_line: str, keywords: set[str],
                mana_cost: str, mana_value: float) -> bool:
        r = self.rule
        tl = type_line.lower()
        if r.type_all and not all(t.lower() in tl for t in r.type_all):
            return False
        if r.type_any and not any(t.lower() in tl for t in r.type_any):
            return False
        if r.type_none and any(t.lower() in tl for t in r.type_none):
            return False
        if r.keyword_any and not (keywords & {k.lower() for k in r.keyword_any}):
            return False
        if r.mana_cost_contains and r.mana_cost_contains not in (mana_cost or ""):
            return False
        if r.max_mana_value is not None and mana_value > r.max_mana_value:
            return False
        if self.all_re and not all(p.search(text) for p in self.all_re):
            return False
        if self.any_re and not any(p.search(text) for p in self.any_re):
            return False
        if any(p.search(text) for p in self.neg_re):
            return False
        # A rule with no positive predicate at all never matches.
        if not (self.any_re or self.all_re or r.keyword_any or r.type_all
                or r.type_any or r.mana_cost_contains):
            return False
        return True
