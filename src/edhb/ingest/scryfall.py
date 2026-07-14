"""Scryfall bulk-data ingest.

Two bulk files are used:
- oracle_cards (~150 MB): one object per oracle_id -> the `cards` table.
- default_cards (~2 GB): one object per printing -> the `printings` table,
  used ONLY to roll up the cheapest paper price per oracle_id.

NOTE: Scryfall card objects include an `edhrec_rank` field. It is
deliberately NOT ingested anywhere in this project — popularity data is
off-limits by design (synergy must be self-derived). Do not add it.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator

import httpx
import ijson

from edhb import config, db

BATCH = 5000

# Printings that can never be played in paper Commander.
_EXCLUDED_LAYOUTS = {"art_series", "token", "double_faced_token", "emblem", "planar", "scheme", "vanguard"}


# --- Download -------------------------------------------------------------


def fetch_bulk_catalog() -> list[dict[str, Any]]:
    resp = httpx.get(config.SCRYFALL_BULK_CATALOG, headers=config.HTTP_HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()["data"]


def download_bulk_file(entry: dict[str, Any], dest_dir: Path | None = None) -> Path:
    """Stream a bulk file to disk. Returns the local path."""
    dest_dir = dest_dir or config.DOWNLOAD_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{entry['type']}.json"
    with httpx.stream(
        "GET", entry["download_uri"], headers=config.HTTP_HEADERS, timeout=None, follow_redirects=True
    ) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(1 << 20):
                f.write(chunk)
    return dest


def bulk_file_is_fresh(conn: sqlite3.Connection, entry: dict[str, Any]) -> bool:
    return db.get_meta(conn, f"scryfall.{entry['type']}.updated_at") == entry["updated_at"]


def mark_bulk_file(conn: sqlite3.Connection, entry: dict[str, Any]) -> None:
    db.set_meta(conn, f"scryfall.{entry['type']}.updated_at", entry["updated_at"])


# --- Parse ----------------------------------------------------------------


def _face_text(card: dict[str, Any], field: str) -> str:
    """Union a field across faces for MDFC/split/adventure cards."""
    faces = card.get("card_faces") or []
    if faces:
        return "\n//\n".join(f.get(field) or "" for f in faces)
    return card.get(field) or ""


def can_be_commander(card: dict[str, Any]) -> bool:
    type_line = card.get("type_line") or ""
    faces = card.get("card_faces") or []
    front_type = faces[0].get("type_line", "") if faces else type_line
    text = _face_text(card, "oracle_text")
    if "Legendary" in front_type and "Creature" in front_type:
        return True
    return "can be your commander" in text.lower()


def parse_oracle_card(card: dict[str, Any]) -> tuple | None:
    """Scryfall oracle card object -> `cards` row tuple, or None to skip."""
    if card.get("layout") in _EXCLUDED_LAYOUTS:
        return None
    oracle_id = card.get("oracle_id")
    if not oracle_id:
        return None
    legal = card.get("legalities", {}).get("commander") == "legal"
    prices = card.get("prices") or {}
    provisional = _min_price(prices)
    return (
        oracle_id,
        card["name"],
        card.get("mana_cost") or _face_text(card, "mana_cost"),
        card.get("cmc", 0.0),
        card.get("type_line") or "",
        _face_text(card, "oracle_text"),
        config.color_mask(card.get("color_identity", [])),
        config.color_mask(card.get("colors", []) or []),
        json.dumps(card.get("keywords", [])),
        json.dumps(card.get("produced_mana")) if card.get("produced_mana") else None,
        card.get("layout"),
        json.dumps(card.get("card_faces")) if card.get("card_faces") else None,
        int(legal),
        int(can_be_commander(card)),
        provisional,  # replaced by cheapest-printing rollup when default_cards is ingested
    )


def _min_price(prices: dict[str, Any]) -> float | None:
    vals = [float(prices[k]) for k in ("usd", "usd_foil", "usd_etched") if prices.get(k)]
    return min(vals) if vals else None


def iter_bulk_cards(path: Path) -> Iterator[dict[str, Any]]:
    """Stream card objects from a bulk JSON array file without loading it all."""
    with open(path, "rb") as f:
        yield from ijson.items(f, "item")


# --- Ingest ---------------------------------------------------------------


def ingest_oracle_cards(conn: sqlite3.Connection, cards: Iterable[dict[str, Any]]) -> int:
    """Insert/replace oracle-level cards. Returns row count."""
    rows, n = [], 0
    sql = (
        "INSERT OR REPLACE INTO cards (oracle_id, name, mana_cost, mana_value, type_line,"
        " oracle_text, color_identity, colors, keywords, produced_mana, layout, faces,"
        " is_commander_legal, can_be_commander, price_usd)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )
    for card in cards:
        row = parse_oracle_card(card)
        if row is None:
            continue
        rows.append(row)
        if len(rows) >= BATCH:
            conn.executemany(sql, rows)
            n += len(rows)
            rows = []
    if rows:
        conn.executemany(sql, rows)
        n += len(rows)
    conn.commit()
    return n


def ingest_printings(conn: sqlite3.Connection, cards: Iterable[dict[str, Any]]) -> int:
    """Insert printings (from default_cards) for price rollup. Paper only."""
    rows, n = [], 0
    sql = (
        "INSERT OR REPLACE INTO printings"
        " (scryfall_id, oracle_id, set_code, usd, usd_foil, usd_etched, digital, promo)"
        " VALUES (?,?,?,?,?,?,?,?)"
    )
    for card in cards:
        if card.get("layout") in _EXCLUDED_LAYOUTS or card.get("oversized"):
            continue
        if card.get("digital") or "paper" not in (card.get("games") or []):
            continue
        oracle_id = card.get("oracle_id")
        if not oracle_id:
            continue
        p = card.get("prices") or {}
        rows.append((
            card["id"], oracle_id, card.get("set"),
            float(p["usd"]) if p.get("usd") else None,
            float(p["usd_foil"]) if p.get("usd_foil") else None,
            float(p["usd_etched"]) if p.get("usd_etched") else None,
            int(bool(card.get("digital"))), int(bool(card.get("promo"))),
        ))
        if len(rows) >= BATCH:
            conn.executemany(sql, rows)
            n += len(rows)
            rows = []
    if rows:
        conn.executemany(sql, rows)
        n += len(rows)
    conn.commit()
    return n


def rollup_cheapest_prices(conn: sqlite3.Connection) -> int:
    """Set cards.price_usd to the cheapest price across all paper printings."""
    cur = conn.execute(
        """
        UPDATE cards SET price_usd = (
          SELECT MIN(m) FROM (
            SELECT MIN(usd) AS m FROM printings p WHERE p.oracle_id = cards.oracle_id
            UNION ALL
            SELECT MIN(usd_foil) FROM printings p WHERE p.oracle_id = cards.oracle_id
            UNION ALL
            SELECT MIN(usd_etched) FROM printings p WHERE p.oracle_id = cards.oracle_id
          )
        )
        WHERE EXISTS (SELECT 1 FROM printings p WHERE p.oracle_id = cards.oracle_id)
        """
    )
    conn.commit()
    return cur.rowcount


# --- Orchestration --------------------------------------------------------


def refresh(conn: sqlite3.Connection, include_prices: bool = True, force: bool = False) -> dict[str, int]:
    """Download and ingest fresh bulk data. Network required."""
    stats: dict[str, int] = {}
    catalog = {e["type"]: e for e in fetch_bulk_catalog()}

    oracle = catalog["oracle_cards"]
    if force or not bulk_file_is_fresh(conn, oracle):
        path = download_bulk_file(oracle)
        stats["oracle_cards"] = ingest_oracle_cards(conn, iter_bulk_cards(path))
        mark_bulk_file(conn, oracle)
        path.unlink(missing_ok=True)

    if include_prices:
        default = catalog["default_cards"]
        if force or not bulk_file_is_fresh(conn, default):
            path = download_bulk_file(default)
            stats["printings"] = ingest_printings(conn, iter_bulk_cards(path))
            stats["prices_updated"] = rollup_cheapest_prices(conn)
            mark_bulk_file(conn, default)
            path.unlink(missing_ok=True)

    return stats
