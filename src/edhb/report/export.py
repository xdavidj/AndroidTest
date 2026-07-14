"""Decklist output: plain text (importable) and JSON (full detail)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edhb.build.builder import DeckResult


def to_text(result: "DeckResult") -> str:
    lines = [
        f"// Commander: {result.commander.name}  (${result.commander.price:.2f})",
        f"// Total price: ${result.total_price:.2f}   Power score: {result.score['total']}/100",
        "",
        f"1 {result.commander.name}",
        "",
        "// Nonlands",
    ]
    for card in result.nonlands:
        lines.append(f"1 {card.name}")
    lines.append("")
    lines.append("// Lands")
    for land in result.lands:
        lines.append(f"{land['qty']} {land['name']}")
    return "\n".join(lines) + "\n"


def to_json(result: "DeckResult") -> str:
    payload = {
        "commander": {
            "name": result.commander.name,
            "oracle_id": result.commander.oracle_id,
            "price": result.commander.price,
        },
        "total_price": result.total_price,
        "score": {k: v for k, v in result.score.items() if k != "complete_combo_ids"},
        "complete_combos": result.score.get("complete_combo_ids", []),
        "seeded_combos": result.seeded_combos,
        "nonlands": [
            {
                "name": c.name, "oracle_id": c.oracle_id, "price": c.price,
                "mana_value": c.mana_value, "role": c.primary_role,
                "reasons": result.pick_reasons.get(c.oracle_id, []),
            }
            for c in result.nonlands
        ],
        "lands": result.lands,
    }
    return json.dumps(payload, indent=2)
