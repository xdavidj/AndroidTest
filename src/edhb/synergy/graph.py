"""Per-pool synergy computation.

Edges are computed lazily over a candidate pool (a few thousand cards),
never globally: edge(a, b) = capped sum of complementary tag-pair
weights + a bonus when both cards share a known combo.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from edhb.synergy import matrix

COMBO_BONUS = {2: 4.0, 3: 2.0}
COMBO_BONUS_WIDE = 1.0  # 4+ cards


@dataclass
class TagSet:
    """One card's tags as (tag, param) pairs, split for fast matching."""
    plain: set[str] = field(default_factory=set)
    parametric: set[tuple[str, str]] = field(default_factory=set)


class SynergyContext:
    """Holds tag sets, weights, and combo membership for a card pool."""

    def __init__(self, conn: sqlite3.Connection, oracle_ids: list[str]):
        self.weights = matrix.weight_index()
        self.tagsets: dict[str, TagSet] = {oid: TagSet() for oid in oracle_ids}
        self._load_tags(conn, oracle_ids)
        self.combos_by_card: dict[str, set[str]] = {}
        self.combo_cards: dict[str, list[str]] = {}
        self.combo_meta: dict[str, sqlite3.Row] = {}
        self._load_combos(conn, set(oracle_ids))

    def _load_tags(self, conn: sqlite3.Connection, oracle_ids: list[str]) -> None:
        rows = conn.execute(
            "SELECT ct.oracle_id, t.name, ct.param FROM card_tags ct"
            " JOIN tags t ON t.tag_id = ct.tag_id"
        )
        wanted = self.tagsets
        for oid, name, param in rows:
            ts = wanted.get(oid)
            if ts is None:
                continue
            if name in matrix.PARAMETRIC_TAGS and param:
                ts.parametric.add((name, param))
            else:
                ts.plain.add(name)

    def _load_combos(self, conn: sqlite3.Connection, pool: set[str]) -> None:
        """Keep combos whose every card is inside the pool."""
        by_combo: dict[str, list[str]] = {}
        for combo_id, oid in conn.execute("SELECT combo_id, oracle_id FROM combo_cards"):
            by_combo.setdefault(combo_id, []).append(oid)
        for combo_id, cards in by_combo.items():
            if all(c in pool for c in cards):
                self.combo_cards[combo_id] = cards
                for c in cards:
                    self.combos_by_card.setdefault(c, set()).add(combo_id)
        if self.combo_cards:
            marks = ",".join("?" * len(self.combo_cards))
            for row in conn.execute(
                f"SELECT * FROM combos WHERE combo_id IN ({marks})",
                list(self.combo_cards),
            ):
                self.combo_meta[row["combo_id"]] = row

    # -- scoring -----------------------------------------------------------

    def tag_edge(self, a: str, b: str) -> float:
        ta, tb = self.tagsets.get(a), self.tagsets.get(b)
        if ta is None or tb is None:
            return 0.0
        total = 0.0
        for tag_a in ta.plain:
            for tag_b in tb.plain:
                if tag_a != tag_b:
                    total += self.weights.get(frozenset((tag_a, tag_b)), 0.0)
        for name_a, param_a in ta.parametric:
            for name_b, param_b in tb.parametric:
                if name_a != name_b and param_a == param_b:
                    total += self.weights.get(frozenset((name_a, name_b)), 0.0)
        return min(matrix.EDGE_CAP, total)

    def combo_edge(self, a: str, b: str) -> float:
        shared = self.combos_by_card.get(a, set()) & self.combos_by_card.get(b, set())
        best = 0.0
        for combo_id in shared:
            size = len(self.combo_cards[combo_id])
            best = max(best, COMBO_BONUS.get(size, COMBO_BONUS_WIDE))
        return best

    def edge(self, a: str, b: str) -> float:
        return self.tag_edge(a, b) + self.combo_edge(a, b)

    def explain_edge(self, a: str, b: str) -> list[str]:
        """Human-readable reasons two cards synergize."""
        reasons = []
        ta, tb = self.tagsets.get(a), self.tagsets.get(b)
        if ta and tb:
            for tag_a in ta.plain:
                for tag_b in tb.plain:
                    w = self.weights.get(frozenset((tag_a, tag_b)), 0.0)
                    if tag_a != tag_b and w > 0:
                        reasons.append(f"{tag_a} + {tag_b} ({w:+.1f})")
            for name_a, param_a in ta.parametric:
                for name_b, param_b in tb.parametric:
                    if name_a != name_b and param_a == param_b:
                        w = self.weights.get(frozenset((name_a, name_b)), 0.0)
                        if w > 0:
                            reasons.append(f"{name_a}({param_a}) + {name_b}({param_b}) ({w:+.1f})")
        shared = self.combos_by_card.get(a, set()) & self.combos_by_card.get(b, set())
        for combo_id in shared:
            meta = self.combo_meta.get(combo_id)
            produces = meta["produces"] if meta else "?"
            reasons.append(f"combo {combo_id}: {produces}")
        return reasons
