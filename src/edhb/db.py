"""SQLite connection factory and schema.

Oracle-level cards are the working unit; printings exist only to compute
the cheapest paper price per oracle_id. There is deliberately NO global
synergy-edge table: edges are computed per build over the filtered
candidate pool (see synergy/graph.py).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from edhb import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS cards (
  oracle_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  mana_cost TEXT,
  mana_value REAL,
  type_line TEXT,
  oracle_text TEXT,
  color_identity INTEGER NOT NULL DEFAULT 0,
  colors INTEGER NOT NULL DEFAULT 0,
  keywords TEXT NOT NULL DEFAULT '[]',
  produced_mana TEXT,
  layout TEXT,
  faces TEXT,
  is_commander_legal INTEGER NOT NULL DEFAULT 0,
  can_be_commander INTEGER NOT NULL DEFAULT 0,
  price_usd REAL
);

CREATE TABLE IF NOT EXISTS printings (
  scryfall_id TEXT PRIMARY KEY,
  oracle_id TEXT NOT NULL REFERENCES cards(oracle_id),
  set_code TEXT,
  usd REAL,
  usd_foil REAL,
  usd_etched REAL,
  digital INTEGER NOT NULL DEFAULT 0,
  promo INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tags (
  tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL,
  role TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS card_tags (
  oracle_id TEXT NOT NULL,
  tag_id INTEGER NOT NULL,
  rule_id TEXT NOT NULL,
  param TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (oracle_id, tag_id, param)
);

CREATE TABLE IF NOT EXISTS combos (
  combo_id TEXT PRIMARY KEY,
  identity INTEGER NOT NULL DEFAULT 0,
  produces TEXT NOT NULL DEFAULT '[]',
  description TEXT,
  mana_needed TEXT,
  other_prereqs TEXT,
  card_count INTEGER NOT NULL,
  has_templates INTEGER NOT NULL DEFAULT 0,
  quality REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS combo_cards (
  combo_id TEXT NOT NULL,
  oracle_id TEXT NOT NULL,
  must_be_commander INTEGER NOT NULL DEFAULT 0,
  zones TEXT,
  PRIMARY KEY (combo_id, oracle_id)
);

CREATE INDEX IF NOT EXISTS idx_ct_tag ON card_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_cc_card ON combo_cards(oracle_id);
CREATE INDEX IF NOT EXISTS idx_cards_price ON cards(price_usd);
CREATE INDEX IF NOT EXISTS idx_printings_oracle ON printings(oracle_id);
CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
"""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None
