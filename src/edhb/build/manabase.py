"""Manabase construction: basics by pip proportion + budget fixing lands.

Basic lands are counted at $0 — every player has them, and pricing them
would just add noise to the budget math.
"""

from __future__ import annotations

import json
import re
import sqlite3

from edhb import config

BASIC_FOR_COLOR = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
_PIP = re.compile(r"\{([WUBRG])(?:/[WUBRGP])?\}")


def pip_counts(mana_costs: list[str]) -> dict[str, int]:
    counts = {c: 0 for c in config.WUBRG}
    for cost in mana_costs:
        for m in _PIP.finditer(cost or ""):
            counts[m.group(1)] += 1
    return {c: n for c, n in counts.items() if n}


def pick_fixing_lands(
    conn: sqlite3.Connection,
    identity_mask: int,
    budget: float,
    max_lands: int,
    exclude: set[str],
) -> list[sqlite3.Row]:
    """Cheap nonbasic lands that produce >=2 of the deck's colors."""
    identity_colors = set(config.mask_colors(identity_mask))
    if len(identity_colors) < 2 or identity_colors == {"C"}:
        return []
    picked: list[sqlite3.Row] = []
    spent = 0.0
    rows = conn.execute(
        """
        SELECT * FROM cards
        WHERE is_commander_legal = 1 AND type_line LIKE '%Land%'
          AND type_line NOT LIKE '%Basic%'
          AND price_usd IS NOT NULL AND produced_mana IS NOT NULL
          AND (color_identity & ~?) = 0
        ORDER BY price_usd ASC, name ASC
        """,
        (identity_mask,),
    )
    for row in rows:
        if len(picked) >= max_lands:
            break
        if row["oracle_id"] in exclude:
            continue
        produced = set(json.loads(row["produced_mana"] or "[]"))
        if len(produced & identity_colors) < 2:
            continue
        if spent + (row["price_usd"] or 0.0) > budget:
            continue
        picked.append(row)
        spent += row["price_usd"] or 0.0
    return picked


def build_manabase(
    conn: sqlite3.Connection,
    identity_mask: int,
    deck_mana_costs: list[str],
    land_budget: float,
    total_lands: int | None = None,
    exclude: set[str] | None = None,
) -> tuple[list[dict], float]:
    """Returns ([{name, oracle_id, qty, price}], nonbasic_spend)."""
    total_lands = total_lands or config.ROLE_QUOTAS["LAND"]
    pips = pip_counts(deck_mana_costs)
    identity_colors = [c for c in config.WUBRG if config.COLOR_BITS[c] & identity_mask]

    fixing = pick_fixing_lands(
        conn, identity_mask,
        budget=land_budget,
        max_lands=min(10, total_lands // 3) if len(identity_colors) >= 2 else 0,
        exclude=exclude or set(),
    )
    lands: list[dict] = [
        {"name": r["name"], "oracle_id": r["oracle_id"], "qty": 1,
         "price": r["price_usd"] or 0.0, "type_line": r["type_line"]}
        for r in fixing
    ]
    spend = sum(land["price"] for land in lands)

    basics_needed = total_lands - len(lands)
    if not identity_colors:
        lands.append({"name": "Wastes", "oracle_id": None, "qty": basics_needed,
                      "price": 0.0, "type_line": "Basic Land"})
        return lands, spend

    total_pips = sum(pips.get(c, 0) for c in identity_colors) or len(identity_colors)
    allocation: dict[str, int] = {}
    for c in identity_colors:
        share = pips.get(c, 0) / total_pips if total_pips else 1 / len(identity_colors)
        allocation[c] = max(1, round(share * basics_needed))
    # Fix rounding drift against the largest allocation.
    drift = basics_needed - sum(allocation.values())
    biggest = max(allocation, key=allocation.__getitem__)
    allocation[biggest] += drift
    for c in identity_colors:
        if allocation[c] > 0:
            lands.append({"name": BASIC_FOR_COLOR[c], "oracle_id": None,
                          "qty": allocation[c], "price": 0.0, "type_line": "Basic Land"})
    return lands, spend
