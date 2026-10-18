from typing import TypedDict


BOARD_SIZE = 25
VIEW_SIZE = BOARD_SIZE
SQUARE_SIZE = 24
CLASSIC_BOARD_SIZE = 8
CLASSIC_SQUARE_SIZE = 62
CAMPAIGN_BOARD_SIZE = 20
BOARD_VIEW_PIXELS = VIEW_SIZE * SQUARE_SIZE
BOARD_LEFT = 40
BOARD_TOP = 60
WINDOW_SIZE = (1040, 760)
STANDARD_START_COL = (BOARD_SIZE - 8) // 2
STANDARD_BLACK_BACK_ROW = (BOARD_SIZE - 8) // 2
STANDARD_WHITE_BACK_ROW = STANDARD_BLACK_BACK_ROW + 7
RANDOM_EXTRA_PIECES_PER_SIDE = 20

WHITE = "white"
BLACK = "black"
FARM_INCOME_PER_SECOND = 3.0
LOOT_FARM_SECONDS = 20
PROMOTION_PIECES = ("Q", "R", "B", "N")

PIECE_VALUES = {
    "P": 50,
    "N": 150,
    "B": 150,
    "R": 250,
    "Q": 300,
    "K": 600,
}

PURCHASE_COST_MULTIPLIER = 20
UPGRADE_COST_MULTIPLIER = 100
PURCHASE_COSTS = {
    kind: value * 2 * PURCHASE_COST_MULTIPLIER
    for kind, value in PIECE_VALUES.items()
    if kind != "K"
}
BASE_UPGRADE_COSTS = {
    "N": 200,
    "B": 200,
    "R": 250,
    "Q": 400,
    "K": 150,
}
UPGRADE_COSTS = {
    kind: cost * UPGRADE_COST_MULTIPLIER
    for kind, cost in BASE_UPGRADE_COSTS.items()
}

UPGRADE_NAMES = {
    "N": "Mina",
    "B": "Odraz strelce",
    "R": "Rentgen veze",
    "Q": "Leceni krale",
    "K": "Vyvolani pesce",
}

class BotDifficulty(TypedDict):
    label: str
    depth: int


BOT_DIFFICULTIES: dict[str, BotDifficulty] = {
    "easy": {"label": "Lehky ~100", "depth": 1},
    "medium": {"label": "Stredni ~200", "depth": 4},
    "hard": {"label": "Tezky+", "depth": 6},
}

TEAM_MAX_HEALTH = 4100
