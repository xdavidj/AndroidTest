"""edhb command-line interface."""

from __future__ import annotations

import sys

import click

from edhb import db


@click.group()
def main() -> None:
    """Budget EDH synergy deck builder."""


@main.command()
@click.option("--force", is_flag=True, help="Re-download even if bulk data is fresh.")
@click.option("--no-prices", is_flag=True, help="Skip the 2GB default_cards price file.")
@click.option("--skip-spellbook", is_flag=True, help="Skip the combo database.")
def ingest(force: bool, no_prices: bool, skip_spellbook: bool) -> None:
    """Download and ingest Scryfall bulk data and Commander Spellbook combos."""
    from edhb.ingest import scryfall, spellbook

    conn = db.connect()
    click.echo("Fetching Scryfall bulk data (this can take a while)...")
    stats = scryfall.refresh(conn, include_prices=not no_prices, force=force)
    for key, val in stats.items():
        click.echo(f"  {key}: {val:,}")
    if not skip_spellbook:
        click.echo("Fetching Commander Spellbook combos...")
        n = spellbook.refresh(conn)
        click.echo(f"  combos: {n:,}")
    click.echo("Done. Next: edhb tag")


@main.command()
@click.option("--stats", "show_stats", is_flag=True, help="Print per-tag match counts.")
def tag(show_stats: bool) -> None:
    """Run the synergy tagger over all commander-legal cards."""
    from edhb.tags.tagger import tag_all

    conn = db.connect()
    stats = tag_all(conn)
    total = sum(stats.values())
    click.echo(f"Applied {total:,} tags across {len(stats)} tag types.")
    if show_stats:
        for name, count in sorted(stats.items(), key=lambda kv: -kv[1]):
            click.echo(f"  {name}: {count:,}")


@main.command()
@click.option("--commander", required=True, help="Commander card name (fuzzy).")
@click.option("--budget", required=True, type=float, help="Total deck budget in USD.")
@click.option("--seed", type=int, default=None, help="Vary tie-breaking deterministically.")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--out", type=click.Path(), default=None, help="Write decklist to a file.")
@click.option("--explain", "do_explain", is_flag=True, help="Print the reasoning report too.")
def build(commander: str, budget: float, seed: int | None, fmt: str,
          out: str | None, do_explain: bool) -> None:
    """Build the most powerful deck possible at the given budget."""
    from edhb.build.builder import BuildError, build_deck
    from edhb.report import explain as explain_mod
    from edhb.report import export

    conn = db.connect()
    try:
        result = build_deck(conn, commander, budget, seed=seed)
    except BuildError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    text = export.to_text(result) if fmt == "text" else export.to_json(result)
    if out:
        with open(out, "w") as f:
            f.write(text)
        click.echo(f"Wrote {out}")
    else:
        click.echo(text)
    if do_explain:
        click.echo(explain_mod.explain(result))


@main.command("suggest-commanders")
@click.option("--budget", required=True, type=float)
@click.option("--colors", default=None, help="Exact color identity filter, e.g. BG.")
@click.option("--top", default=20, type=int)
def suggest_commanders_cmd(budget: float, colors: str | None, top: int) -> None:
    """Rank obscure-but-synergetic commanders achievable at this budget."""
    from edhb.build.builder import suggest_commanders

    conn = db.connect()
    for r in suggest_commanders(conn, budget, colors, top):
        click.echo(
            f"{r['score']:>7.1f}  {r['name']:<40} {r['identity']:<6}"
            f" ${r['price']:<7.2f} combos={r['combos']}"
        )


@main.command()
@click.argument("name")
def card(name: str) -> None:
    """Debug: show a card's tags, price, and combo membership."""
    from edhb.tags.tagger import tags_for_card

    conn = db.connect()
    row = conn.execute(
        "SELECT * FROM cards WHERE lower(name) LIKE lower(?) ORDER BY length(name) LIMIT 1",
        (f"%{name}%",),
    ).fetchone()
    if not row:
        click.echo("not found", err=True)
        sys.exit(1)
    click.echo(f"{row['name']}  ${row['price_usd'] or 0:.2f}  {row['type_line']}")
    for tag_name, param, role in sorted(tags_for_card(conn, row["oracle_id"])):
        suffix = f"({param})" if param else ""
        click.echo(f"  {tag_name}{suffix} [{role}]")
    n = conn.execute(
        "SELECT COUNT(*) FROM combo_cards WHERE oracle_id = ?", (row["oracle_id"],)
    ).fetchone()[0]
    click.echo(f"  combos: {n}")


@main.command("price-check")
@click.option("--deck", "deck_path", required=True, type=click.Path(exists=True))
def price_check(deck_path: str) -> None:
    """Re-price a text decklist ("1 Card Name" lines) against current data."""
    conn = db.connect()
    total, missing = 0.0, []
    with open(deck_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            qty_str, _, name = line.partition(" ")
            qty = int(qty_str) if qty_str.isdigit() else 1
            row = conn.execute(
                "SELECT price_usd, type_line FROM cards WHERE lower(name) = lower(?)",
                (name.strip(),),
            ).fetchone()
            if row is None:
                missing.append(name)
                continue
            if "Basic" in (row["type_line"] or ""):
                continue  # basics count as $0
            total += (row["price_usd"] or 0.0) * qty
    click.echo(f"Total: ${total:.2f}")
    for name in missing:
        click.echo(f"  not found: {name}", err=True)


if __name__ == "__main__":
    main()
