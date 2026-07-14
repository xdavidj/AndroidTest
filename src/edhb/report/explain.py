"""Human-readable explanation of why a built deck is what it is."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edhb.build.builder import DeckResult


def explain(result: "DeckResult", top_edges: int = 3) -> str:
    ctx = result.ctx
    lines = [
        f"# {result.commander.name} — ${result.total_price:.2f}",
        "",
        "## Power score",
    ]
    for key in ("synergy_density", "combos", "consistency", "interaction", "mana", "total"):
        lines.append(f"- {key}: {result.score[key]}")
    lines.append(f"- average mana value: {result.score['avg_mana_value']}")

    complete = result.score.get("complete_combo_ids", [])
    if complete and ctx:
        lines += ["", "## Win lines (complete combos in deck)"]
        names = {c.oracle_id: c.name for c in result.nonlands}
        names[result.commander.oracle_id] = result.commander.name
        for cid in complete:
            meta = ctx.combo_meta.get(cid)
            members = [names.get(m, m) for m in ctx.combo_cards.get(cid, [])]
            produces = ", ".join(json.loads(meta["produces"])) if meta else "?"
            lines.append(f"- [{cid}] {' + '.join(members)} => {produces}")
            if meta and meta["description"]:
                first = meta["description"].strip().splitlines()[0]
                lines.append(f"    steps: {first}")

    lines += ["", "## Card choices"]
    for card in result.nonlands:
        reasons = result.pick_reasons.get(card.oracle_id, [])
        lines.append(f"- {card.name} (${card.price:.2f}, {card.primary_role.lower()})")
        for r in reasons[:1]:
            lines.append(f"    picked: {r}")
        if ctx:
            edges = []
            for other in result.nonlands:
                if other.oracle_id == card.oracle_id:
                    continue
                w = ctx.edge(card.oracle_id, other.oracle_id)
                if w > 0:
                    edges.append((w, other.name))
            w_cmd = ctx.edge(card.oracle_id, result.commander.oracle_id)
            if w_cmd > 0:
                edges.append((w_cmd, f"{result.commander.name} (commander)"))
            edges.sort(reverse=True)
            for w, name in edges[:top_edges]:
                lines.append(f"    synergy {w:.1f} with {name}")
    return "\n".join(lines) + "\n"
