"""Rule engine: normalize card text, apply rules, write card_tags."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Iterable

from edhb.tags.ontology import CompiledRule, Rule
from edhb.tags.rules import all_rules

_REMINDER = re.compile(r"\([^)]*\)")
# Modern oracle text self-references as "this creature" etc. instead of
# repeating the card name; fold both forms into `~`.
_SELF_REF = re.compile(r"\bthis (creature|permanent|artifact|enchantment|land|token)\b")


def normalize_text(oracle_text: str, name: str) -> str:
    """Lowercase, strip reminder text, replace the card's own name with `~`."""
    text = oracle_text or ""
    text = _REMINDER.sub("", text)
    # Full name first, then front-face short name ("Foo, the Bar" -> "Foo").
    if name:
        text = text.replace(name, "~")
        short = name.split(",")[0].strip()
        if short and short != name:
            text = text.replace(short, "~")
    return _SELF_REF.sub("~", text.lower())


def card_features(card: sqlite3.Row | dict[str, Any]) -> tuple[str, str, set[str], str, float]:
    """Extract (normalized_text, type_line, keywords, mana_cost, mana_value)."""
    get = card.__getitem__ if isinstance(card, sqlite3.Row) else card.get
    text = normalize_text(get("oracle_text") or "", get("name") or "")
    keywords = {k.lower() for k in json.loads(get("keywords") or "[]")}
    return (
        text,
        get("type_line") or "",
        keywords,
        get("mana_cost") or "",
        float(get("mana_value") or 0.0),
    )


def match_card(compiled: list[CompiledRule], card: sqlite3.Row | dict[str, Any]) -> list[Rule]:
    text, type_line, keywords, mana_cost, mv = card_features(card)
    return [
        c.rule for c in compiled
        if c.matches(text, type_line, keywords, mana_cost, mv)
    ]


def ensure_tags(conn: sqlite3.Connection, rules: Iterable[Rule]) -> dict[str, int]:
    """Insert tag rows; return name -> tag_id map."""
    for r in rules:
        conn.execute(
            "INSERT OR IGNORE INTO tags (name, category, role) VALUES (?,?,?)",
            (r.tag, r.category, r.role),
        )
    conn.commit()
    return {row["name"]: row["tag_id"] for row in conn.execute("SELECT tag_id, name FROM tags")}


def tag_all(conn: sqlite3.Connection, only_legal: bool = True) -> dict[str, int]:
    """Run every rule over every card. Returns {tag: match_count}."""
    rules = all_rules()
    compiled = [r.compiled() for r in rules]
    tag_ids = ensure_tags(conn, rules)

    conn.execute("DELETE FROM card_tags")
    where = "WHERE is_commander_legal = 1" if only_legal else ""
    stats: dict[str, int] = {}
    rows = []
    for card in conn.execute(f"SELECT * FROM cards {where}"):
        for rule in match_card(compiled, card):
            rows.append((card["oracle_id"], tag_ids[rule.tag], rule.id, rule.param))
            stats[rule.tag] = stats.get(rule.tag, 0) + 1
        if len(rows) >= 20000:
            conn.executemany(
                "INSERT OR IGNORE INTO card_tags (oracle_id, tag_id, rule_id, param)"
                " VALUES (?,?,?,?)", rows)
            rows = []
    if rows:
        conn.executemany(
            "INSERT OR IGNORE INTO card_tags (oracle_id, tag_id, rule_id, param)"
            " VALUES (?,?,?,?)", rows)
    conn.commit()
    return stats


def tags_for_card(conn: sqlite3.Connection, oracle_id: str) -> list[tuple[str, str, str]]:
    """[(tag_name, param, role)] for one card."""
    return [
        (row["name"], row["param"], row["role"])
        for row in conn.execute(
            "SELECT t.name, ct.param, t.role FROM card_tags ct"
            " JOIN tags t ON t.tag_id = ct.tag_id WHERE ct.oracle_id = ?",
            (oracle_id,),
        )
    ]
