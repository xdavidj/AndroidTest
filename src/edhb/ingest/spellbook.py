"""Commander Spellbook combo ingest.

Source: the daily bulk export (variants.json). Each "variant" is one
concrete combo: the cards it uses, what it produces ("Win the game",
"Infinite mana", ...), its color identity, and human-readable steps.

The export's `popularity` field is EDHREC-derived and deliberately
ignored — popularity data is off-limits by design.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

import httpx

from edhb import config

# How much a combo's output is worth when ranking lines for seeding.
# Matched by case-insensitive substring against produced feature names.
FEATURE_VALUES = [
    ("win the game", 10.0),
    ("lose the game", 9.0),  # "each opponent loses the game"
    ("infinite turns", 9.0),
    ("infinite damage", 9.0),
    ("infinite mill", 8.0),
    ("infinite tokens", 8.0),
    ("infinite draw", 7.0),
    ("infinite mana", 6.0),
    ("infinite", 5.0),
    ("near-infinite", 4.0),
]
DEFAULT_FEATURE_VALUE = 2.0


def feature_value(feature_names: list[str]) -> float:
    best = 0.0
    for name in feature_names:
        low = name.lower()
        val = next((v for pat, v in FEATURE_VALUES if pat in low), DEFAULT_FEATURE_VALUE)
        best = max(best, val)
    return best


def combo_quality(
    feature_names: list[str], card_count: int, has_templates: bool, other_prereqs: str
) -> float:
    """Higher = better seed. Penalize wide combos, template slots, setup text."""
    q = feature_value(feature_names)
    q -= 0.7 * max(0, card_count - 2)
    if has_templates:
        q -= 1.0
    q -= min(2.0, len(other_prereqs or "") / 200.0)
    return q


def download_variants() -> Any:
    resp = httpx.get(
        config.SPELLBOOK_VARIANTS_JSON, headers=config.HTTP_HEADERS, timeout=300, follow_redirects=True
    )
    resp.raise_for_status()
    return resp.json()


def _extract_variants(payload: Any) -> list[dict[str, Any]]:
    """The bulk export may be a bare list or wrapped in {"variants": [...]}."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("variants", "results", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError("Unrecognized Commander Spellbook export shape")


def _produced_names(variant: dict[str, Any]) -> list[str]:
    names = []
    for prod in variant.get("produces") or []:
        feat = prod.get("feature") if isinstance(prod, dict) else None
        if isinstance(feat, dict) and feat.get("name"):
            names.append(feat["name"])
        elif isinstance(prod, dict) and prod.get("name"):
            names.append(prod["name"])
        elif isinstance(prod, str):
            names.append(prod)
    return names


def _commander_legal(variant: dict[str, Any]) -> bool:
    legalities = variant.get("legalities")
    if isinstance(legalities, dict) and "commander" in legalities:
        val = legalities["commander"]
        return val is True or val == "legal"
    return bool(variant.get("legal", True))


def _card_oracle_id(use: dict[str, Any]) -> str | None:
    card = use.get("card") or {}
    return card.get("oracleId") or card.get("oracle_id")


def ingest_variants(conn: sqlite3.Connection, payload: Any) -> int:
    """Load OK, commander-legal variants into combos/combo_cards. Returns count."""
    variants = _extract_variants(payload)
    conn.execute("DELETE FROM combos")
    conn.execute("DELETE FROM combo_cards")
    n = 0
    for v in variants:
        if v.get("status", "OK") != "OK":
            continue
        if not _commander_legal(v):
            continue
        uses = v.get("uses") or []
        oracle_ids = [_card_oracle_id(u) for u in uses]
        if not oracle_ids or any(oid is None for oid in oracle_ids):
            continue
        produces = _produced_names(v)
        templates = v.get("requires") or []
        card_count = len(uses)
        other_prereqs = v.get("otherPrerequisites") or ""
        quality = combo_quality(produces, card_count, bool(templates), other_prereqs)
        conn.execute(
            "INSERT OR REPLACE INTO combos (combo_id, identity, produces, description,"
            " mana_needed, other_prereqs, card_count, has_templates, quality)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(v["id"]),
                config.color_mask((v.get("identity") or "").replace(",", "")),
                json.dumps(produces),
                v.get("description"),
                v.get("manaNeeded"),
                other_prereqs,
                card_count,
                int(bool(templates)),
                quality,
            ),
        )
        for use in uses:
            conn.execute(
                "INSERT OR REPLACE INTO combo_cards (combo_id, oracle_id, must_be_commander, zones)"
                " VALUES (?,?,?,?)",
                (
                    str(v["id"]),
                    _card_oracle_id(use),
                    int(bool(use.get("mustBeCommander"))),
                    json.dumps(use.get("zoneLocations")) if use.get("zoneLocations") else None,
                ),
            )
        n += 1
    conn.commit()
    return n


def refresh(conn: sqlite3.Connection) -> int:
    """Download and ingest the current combo database. Network required."""
    return ingest_variants(conn, download_variants())


def find_my_combos(decklist: Iterable[str], commanders: Iterable[str] = ()) -> dict[str, Any]:
    """Validate a decklist against Spellbook's own combo finder (verification aid)."""
    body = {
        "main": [{"card": name, "quantity": 1} for name in decklist],
        "commanders": [{"card": name, "quantity": 1} for name in commanders],
    }
    resp = httpx.post(
        f"{config.SPELLBOOK_BACKEND}/find-my-combos",
        headers={**config.HTTP_HEADERS, "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()
