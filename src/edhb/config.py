"""Central configuration: paths, HTTP constants, deck-building quotas."""

from __future__ import annotations

import os
from pathlib import Path

# --- Paths ---------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("EDHB_DATA_DIR", REPO_ROOT / "data"))
DOWNLOAD_DIR = DATA_DIR / "downloads"
DB_PATH = Path(os.environ.get("EDHB_DB", DATA_DIR / "edh.sqlite"))

# --- HTTP ----------------------------------------------------------------

# Scryfall rejects requests without a User-Agent.
USER_AGENT = "edhb/0.1 (budget EDH deck builder)"
HTTP_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

SCRYFALL_BULK_CATALOG = "https://api.scryfall.com/bulk-data"
SPELLBOOK_VARIANTS_JSON = "https://json.commanderspellbook.com/variants.json"
SPELLBOOK_BACKEND = "https://backend.commanderspellbook.com"

# --- Colors --------------------------------------------------------------

WUBRG = "WUBRG"
COLOR_BITS = {c: 1 << i for i, c in enumerate(WUBRG)}


def color_mask(colors: list[str] | str) -> int:
    """WUBRG color list -> bitmask. Subset checks become (a & ~b) == 0."""
    mask = 0
    for c in colors:
        mask |= COLOR_BITS.get(c.upper(), 0)
    return mask


def mask_colors(mask: int) -> str:
    return "".join(c for c in WUBRG if mask & COLOR_BITS[c]) or "C"


# --- Deck-building quotas -------------------------------------------------
# Role quotas are targets, not hard walls; the builder treats deficits as
# bonuses and surpluses as penalties. Lands are the exception (hard band).

DECK_SIZE = 100  # including commander

ROLE_QUOTAS = {
    "LAND": 36,
    "RAMP": 10,
    "DRAW": 10,
    "REMOVAL": 7,
    "WIPE": 2,
    "PROTECTION": 3,
    "WINCON": 8,
    # remaining slots are SYNERGY flex
}

# Budget sub-allocations (fractions of total budget)
MAX_SINGLE_CARD_FRACTION = 0.20  # no single card above 20% of budget
COMBO_BUDGET_FRACTION = 0.25     # combo packages capped at 25% of budget
LAND_BUDGET_FRACTION = 0.15      # nonbasic lands capped at 15% of budget

# Novelty: cards below this price get a small bonus (cheapness is our
# popularity-free proxy for "under the radar").
NOVELTY_PRICE_THRESHOLD = 0.50
NOVELTY_BONUS = 0.5
