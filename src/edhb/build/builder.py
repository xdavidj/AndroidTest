"""Deck construction: pool filter -> combo seeding -> greedy fill ->
spend-up swaps -> manabase. Budget is a hard constraint throughout;
power should rise monotonically with budget via the spend-up pass.
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass, field

from edhb import config
from edhb.build import manabase, roles
from edhb.build.score import CardRec, deck_power_score, marginal_value
from edhb.synergy.graph import SynergyContext


@dataclass
class DeckResult:
    commander: CardRec
    nonlands: list[CardRec]
    lands: list[dict]
    total_price: float
    score: dict
    pick_reasons: dict[str, list[str]] = field(default_factory=dict)
    seeded_combos: list[str] = field(default_factory=list)
    ctx: SynergyContext | None = None


class BuildError(Exception):
    pass


# Prices are floats of dollars; accumulated arithmetic drifts by ~1e-15 per
# op, which is enough to fail an exact budget-boundary comparison. All
# budget comparisons tolerate this.
EPS = 1e-6


def _card_rec(row: sqlite3.Row, tag_info: list[tuple[str, str, str]]) -> CardRec:
    return CardRec(
        oracle_id=row["oracle_id"],
        name=row["name"],
        price=row["price_usd"] or 0.0,
        mana_value=row["mana_value"] or 0.0,
        type_line=row["type_line"] or "",
        mana_cost=row["mana_cost"] or "",
        tag_roles={role for _, _, role in tag_info},
        n_tags=len(tag_info),
    )


def find_commander(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM cards WHERE lower(name) = lower(?) AND can_be_commander = 1",
        (name,),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM cards WHERE lower(name) LIKE lower(?) AND can_be_commander = 1"
            " ORDER BY length(name) LIMIT 1",
            (f"%{name}%",),
        ).fetchone()
    if row is None:
        raise BuildError(f"No commander-eligible card matching {name!r}")
    return row


def load_pool(
    conn: sqlite3.Connection, identity_mask: int, budget: float, exclude_oracle: str
) -> dict[str, CardRec]:
    """Tagged, in-identity, priced, affordable nonland cards."""
    max_price = budget * config.MAX_SINGLE_CARD_FRACTION
    pool: dict[str, CardRec] = {}
    tag_map: dict[str, list[tuple[str, str, str]]] = {}
    for row in conn.execute(
        "SELECT ct.oracle_id, t.name, ct.param, t.role FROM card_tags ct"
        " JOIN tags t ON t.tag_id = ct.tag_id"
    ):
        tag_map.setdefault(row["oracle_id"], []).append(
            (row["name"], row["param"], row["role"]))
    for row in conn.execute(
        """
        SELECT * FROM cards
        WHERE is_commander_legal = 1 AND price_usd IS NOT NULL AND price_usd <= ?
          AND (color_identity & ~?) = 0 AND oracle_id != ?
          AND type_line NOT LIKE '%Land%'
        """,
        (max_price, identity_mask, exclude_oracle),
    ):
        info = tag_map.get(row["oracle_id"])
        if not info:
            continue  # untagged cards contribute nothing the scorer can see
        pool[row["oracle_id"]] = _card_rec(row, info)
    return pool


def seed_combos(
    ctx: SynergyContext,
    pool: dict[str, CardRec],
    commander_id: str,
    combo_budget: float,
    max_combos: int = 3,
) -> tuple[list[str], list[str]]:
    """Pick the best cheap combo packages. Returns (card_ids, combo_ids)."""
    ranked = sorted(
        ctx.combo_cards,
        key=lambda cid: (
            -(1 if any(
                m == commander_id for m in ctx.combo_cards[cid]) else 0),
            -(ctx.combo_meta[cid]["quality"] if cid in ctx.combo_meta else 0.0),
        ),
    )
    chosen_cards: list[str] = []
    chosen_combos: list[str] = []
    spent = 0.0
    for cid in ranked:
        if len(chosen_combos) >= max_combos:
            break
        members = [m for m in ctx.combo_cards[cid] if m != commander_id]
        new = [m for m in members if m not in chosen_cards]
        cost = sum(pool[m].price for m in new if m in pool)
        if any(m not in pool for m in new):
            continue
        if spent + cost > combo_budget:
            continue
        chosen_cards.extend(new)
        chosen_combos.append(cid)
        spent += cost
    return chosen_cards, chosen_combos


# Fixed sub-budget rungs shared by every build. Because the rung set at a
# lower budget is a subset of the rung set at any higher budget, the best
# score is monotone in budget by construction.
BUDGET_GRID = (10, 15, 25, 35, 50, 70, 100, 140, 200, 300, 500, 750, 1000)


def build_deck(
    conn: sqlite3.Connection,
    commander_name: str,
    budget: float,
    seed: int | None = None,
    ladder: bool = True,
) -> DeckResult:
    """Build at the cap and at every grid rung below it; keep the best deck.

    Greedy construction is myopic: a larger budget can occasionally land on
    a slightly worse deck than a tighter one would. Trying the fixed
    sub-budget rungs and keeping the winner guarantees more budget never
    yields a worse deck.
    """
    rungs = [budget]
    if ladder:
        rungs += [float(g) for g in BUDGET_GRID if g < budget]
    best: DeckResult | None = None
    last_error: BuildError | None = None
    for rung in sorted(rungs, reverse=True):
        try:
            result = _build_once(conn, commander_name, rung, seed=seed)
        except BuildError as e:
            last_error = e
            continue
        if best is None or (result.score["total"], -result.total_price) > (
                best.score["total"], -best.total_price):
            best = result
    if best is None:
        raise last_error or BuildError("no build succeeded")
    return best


def _build_once(
    conn: sqlite3.Connection,
    commander_name: str,
    budget: float,
    seed: int | None = None,
) -> DeckResult:
    cmd_row = find_commander(conn, commander_name)
    commander_id = cmd_row["oracle_id"]
    identity = cmd_row["color_identity"]
    cmd_price = cmd_row["price_usd"] or 0.0
    if cmd_price > budget:
        raise BuildError(
            f"Commander {cmd_row['name']} (${cmd_price:.2f}) exceeds budget ${budget:.2f}")

    pool = load_pool(conn, identity, budget, commander_id)
    if len(pool) < roles.nonland_slots():
        raise BuildError(
            f"Pool too small ({len(pool)} cards) — did you run `edhb ingest` and `edhb tag`?")

    from edhb.tags.tagger import tags_for_card
    cmd_rec = _card_rec(cmd_row, tags_for_card(conn, commander_id))
    ctx = SynergyContext(conn, [*pool, commander_id])

    n_colors = bin(identity).count("1")
    land_reserve = budget * config.LAND_BUDGET_FRACTION if n_colors >= 2 else 0.0
    nonland_budget = budget - cmd_price - land_reserve

    jitter = random.Random(seed)
    noise = {oid: jitter.random() * 0.01 for oid in pool} if seed is not None else {}

    deck: dict[str, CardRec] = {}
    role_counts: dict[str, int] = {}
    spent = 0.0
    pick_reasons: dict[str, list[str]] = {}

    # Precompute commander edges; maintain incremental deck-synergy sums.
    cmd_edge = {oid: ctx.edge(oid, commander_id) for oid in pool}
    syn_sum = {oid: 0.0 for oid in pool}

    def add(oid: str, reason: str) -> None:
        nonlocal spent
        card = pool[oid]
        deck[oid] = card
        spent += card.price
        role_counts[card.primary_role] = role_counts.get(card.primary_role, 0) + 1
        for other in pool:
            if other not in deck:
                syn_sum[other] += ctx.edge(other, oid)
        pick_reasons.setdefault(oid, []).append(reason)

    # 1. Combo seeding.
    seeded_cards, seeded_combos = seed_combos(
        ctx, pool, commander_id, combo_budget=budget * config.COMBO_BUDGET_FRACTION)
    for oid in seeded_cards:
        if spent + pool[oid].price <= nonland_budget + EPS and len(deck) < roles.nonland_slots():
            add(oid, f"combo package ({', '.join(seeded_combos)})")

    # 2. Greedy fill. Each pick must leave enough budget to fill every
    # remaining slot with the actually-cheapest remaining cards (a sum,
    # not slots x min price), so the deck always reaches exactly `slots`
    # nonlands (or fails loudly).
    slots = roles.nonland_slots()
    by_price = sorted(pool.values(), key=lambda c: (c.price, c.oracle_id))
    while len(deck) < slots:
        budget_left = nonland_budget - spent
        remaining_after = slots - len(deck) - 1
        # Cheapest remaining_after+1 unpicked cards; prefix sums give the
        # exact reserve needed whether or not the candidate is among them.
        cheap_ids: dict[str, int] = {}
        cheap_prefix = [0.0]
        for c in by_price:
            if len(cheap_ids) > remaining_after:
                break
            if c.oracle_id in deck:
                continue
            cheap_ids[c.oracle_id] = len(cheap_ids)
            cheap_prefix.append(cheap_prefix[-1] + c.price)
        best_oid, best_val = None, float("-inf")
        for oid, card in pool.items():
            if oid in deck:
                continue
            if oid in cheap_ids and cheap_ids[oid] < remaining_after:
                # Candidate is inside the reserve set: replace it with the
                # next cheapest card when computing the remainder cost.
                reserve = cheap_prefix[min(remaining_after + 1, len(cheap_prefix) - 1)] \
                    - card.price
            else:
                reserve = cheap_prefix[min(remaining_after, len(cheap_prefix) - 1)]
            if card.price + reserve > budget_left + EPS:
                continue
            val = marginal_value(card, syn_sum[oid], cmd_edge[oid],
                                 set(deck), role_counts, ctx) + noise.get(oid, 0.0)
            if val > best_val or (val == best_val and best_oid and oid < best_oid):
                best_oid, best_val = oid, val
        if best_oid is None:
            raise BuildError(
                f"Cannot fill the deck at budget ${budget:.2f}: "
                f"{slots - len(deck)} slots left with ${budget_left:.2f} remaining.")
        add(best_oid, f"marginal value {best_val:.2f}")

    # 3. Spend-up pass: convert unused budget into power.
    # syn_sum freezes when a card enters the deck, so deck-side synergy is
    # recomputed fresh here rather than read from the incremental sums.
    def deck_synergy(oid: str) -> float:
        return sum(ctx.edge(oid, d) for d in deck if d != oid)

    unused = nonland_budget - spent
    if unused > 0.10 * budget and len(deck) == slots:
        for _ in range(2):
            ranked_deck = sorted(
                deck.values(),
                key=lambda c: marginal_value(
                    c, deck_synergy(c.oracle_id), cmd_edge.get(c.oracle_id, 0.0),
                    set(deck) - {c.oracle_id}, role_counts, ctx),
            )
            improved = False
            for weak in ranked_deck[:15]:
                if weak.oracle_id not in deck:
                    continue  # already swapped out this pass
                headroom = (nonland_budget - spent) + weak.price
                weak_val = marginal_value(
                    weak, deck_synergy(weak.oracle_id), cmd_edge[weak.oracle_id],
                    set(deck) - {weak.oracle_id}, role_counts, ctx)
                cand_best, cand_val = None, weak_val + 0.5
                for oid, card in pool.items():
                    if oid in deck or card.price > headroom + EPS:
                        continue
                    val = marginal_value(card, syn_sum[oid], cmd_edge[oid],
                                         set(deck) - {weak.oracle_id}, role_counts, ctx)
                    if val > cand_val:
                        cand_best, cand_val = oid, val
                if cand_best:
                    # Remove weak, add candidate; fix incremental sums.
                    del deck[weak.oracle_id]
                    spent -= weak.price
                    role_counts[weak.primary_role] -= 1
                    for other in pool:
                        if other not in deck:
                            syn_sum[other] -= ctx.edge(other, weak.oracle_id)
                    syn_sum[weak.oracle_id] = deck_synergy(weak.oracle_id)
                    add(cand_best, f"spend-up swap for {weak.name}")
                    improved = True
            if not improved:
                break

    # 4. Manabase from whatever budget remains.
    land_budget = budget - cmd_price - spent
    lands, land_spend = manabase.build_manabase(
        conn, identity,
        deck_mana_costs=[c.mana_cost for c in deck.values()] + [cmd_rec.mana_cost],
        land_budget=land_budget,
        exclude=set(deck),
    )

    nonlands = sorted(deck.values(), key=lambda c: (c.mana_value, c.name))
    total_price = cmd_price + spent + land_spend
    score = deck_power_score(
        [c.oracle_id for c in nonlands], commander_id, ctx,
        {**{c.oracle_id: c for c in nonlands}, commander_id: cmd_rec},
        land_count=sum(land["qty"] for land in lands),
    )
    return DeckResult(
        commander=cmd_rec, nonlands=nonlands, lands=lands,
        total_price=round(total_price, 2), score=score,
        pick_reasons=pick_reasons, seeded_combos=seeded_combos, ctx=ctx,
    )


# --- Commander suggestion ---------------------------------------------------


def suggest_commanders(
    conn: sqlite3.Connection,
    budget: float,
    colors: str | None = None,
    top: int = 20,
) -> list[dict]:
    """Rank eligible commanders by achievable in-budget synergy mass.

    Novelty-by-cheapness: sub-$2 commanders get a bonus; expensive
    commanders (usually popular ones) are filtered by the budget itself.
    """
    from edhb.synergy import matrix
    from edhb.tags.tagger import tags_for_card

    weights = matrix.weight_index()
    cheap_cutoff = max(1.0, budget * 0.02)

    # counts[tag][identity_mask] = number of cheap cards with that tag usable
    # under that identity.
    counts: dict[str, dict[int, int]] = {}
    rows = conn.execute(
        """
        SELECT t.name AS tag, c.color_identity AS ci FROM card_tags ct
        JOIN tags t ON t.tag_id = ct.tag_id
        JOIN cards c ON c.oracle_id = ct.oracle_id
        WHERE c.price_usd IS NOT NULL AND c.price_usd <= ? AND c.is_commander_legal = 1
        """,
        (cheap_cutoff,),
    )
    for tag, ci in rows:
        per_tag = counts.setdefault(tag, {})
        for mask in range(32):
            if ci & ~mask == 0:
                per_tag[mask] = per_tag.get(mask, 0) + 1

    color_filter = config.color_mask(colors) if colors else None
    results = []
    import math
    for row in conn.execute(
        "SELECT * FROM cards WHERE can_be_commander = 1 AND is_commander_legal = 1"
        " AND price_usd IS NOT NULL AND price_usd <= ?",
        (budget * config.MAX_SINGLE_CARD_FRACTION,),
    ):
        ci = row["color_identity"]
        if color_filter is not None and ci != color_filter:
            continue
        my_tags = {t for t, _, _ in tags_for_card(conn, row["oracle_id"])}
        mass = 0.0
        for tag in my_tags:
            for key, w in weights.items():
                if tag in key:
                    other = next(iter(key - {tag}), tag)
                    n = counts.get(other, {}).get(ci, 0)
                    mass += w * math.log1p(n)
        if mass <= 0:
            continue
        combo_count = conn.execute(
            "SELECT COUNT(DISTINCT cc.combo_id) FROM combo_cards cc WHERE cc.oracle_id = ?",
            (row["oracle_id"],),
        ).fetchone()[0]
        novelty = 1.0 if (row["price_usd"] or 0) < 2.0 else 0.0
        # log on combo count: raw counts reach the thousands for famous
        # combo commanders and would otherwise drown the synergy signal.
        score = 3.0 * mass + 25.0 * math.log1p(combo_count) + 10.0 * novelty
        results.append({
            "name": row["name"],
            "price": row["price_usd"],
            "identity": config.mask_colors(ci),
            "synergy_mass": round(mass, 1),
            "combos": combo_count,
            "score": round(score, 1),
            "tags": sorted(my_tags),
        })
    results.sort(key=lambda r: (-r["score"], r["name"]))
    return results[:top]
