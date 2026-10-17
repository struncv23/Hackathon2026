from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .constants import BLACK, WHITE

ARMY_KINDS = ("P", "N", "B", "R", "Q")
FARM_BASE_COST = 250
FARM_COST_STEP = 180
FARM_INCOME_PER_SECOND = 3.0
CITY_COST = 900
ARMORY_COST = 3_000
ARMY_LIMIT = 16
RECRUIT_COSTS = {"P": 800, "N": 1_200, "B": 1_200, "R": 1_900, "Q": 3_200}
UPGRADE_SOURCES = {"N": "P", "B": "N", "R": "B", "Q": "R"}


@dataclass
class Faction:
    coins: int = 450
    farms: int = 0
    farm_income_fraction: float = 0.0
    farm_sector: bool = False
    city: bool = False
    armory: bool = False
    army: dict[str, int] = field(
        default_factory=lambda: {kind: 0 for kind in ARMY_KINDS}
    )

    @property
    def army_size(self) -> int:
        return sum(self.army.values())


@dataclass
class Campaign:
    day: int = 1
    player: Faction = field(default_factory=Faction)
    rival: Faction = field(default_factory=Faction)

    def faction(self, color: str) -> Faction:
        return self.player if color == WHITE else self.rival

    def farm_cost(self, color: str) -> int:
        faction = self.faction(color)
        if not faction.farm_sector:
            return FARM_BASE_COST
        return FARM_BASE_COST + max(0, faction.farms - 1) * FARM_COST_STEP

    def build_farm(self, color: str) -> bool:
        faction = self.faction(color)
        cost = self.farm_cost(color)
        if faction.coins < cost or faction.farms >= 8:
            return False
        faction.coins -= cost
        if not faction.farm_sector:
            faction.farm_sector = True
            faction.farms = 1
        else:
            faction.farms += 1
        return True

    def build_city(self, color: str) -> bool:
        faction = self.faction(color)
        if faction.city or faction.farms < 3 or faction.coins < CITY_COST:
            return False
        faction.coins -= CITY_COST
        faction.city = True
        return True

    def build_armory(self, color: str) -> bool:
        faction = self.faction(color)
        if (
            not faction.city
            or faction.armory
            or faction.army_size < 3
            or faction.coins < ARMORY_COST
        ):
            return False
        faction.coins -= ARMORY_COST
        faction.armory = True
        return True

    def recruit(self, color: str, kind: str) -> bool:
        faction = self.faction(color)
        cost = RECRUIT_COSTS.get(kind)
        if (
            not faction.city
            or cost is None
            or faction.coins < cost
            or faction.army_size >= ARMY_LIMIT
        ):
            return False
        faction.coins -= cost
        faction.army[kind] += 1
        return True

    def upgrade_pawn(self, color: str, kind: str) -> bool:
        faction = self.faction(color)
        source = UPGRADE_SOURCES.get(kind)
        if source is None or faction.army[source] < 1:
            return False
        cost = RECRUIT_COSTS[kind] - RECRUIT_COSTS[source]
        if not faction.city or faction.coins < cost:
            return False
        faction.coins -= cost
        faction.army[source] -= 1
        faction.army[kind] += 1
        return True

    def select_army(self, color: str, limit: int) -> dict[str, int]:
        faction = self.faction(color)
        remaining = max(0, min(limit, ARMY_LIMIT))
        selected = {kind: 0 for kind in ARMY_KINDS}
        for kind in ("Q", "R", "N", "B", "P"):
            count = min(faction.army[kind], remaining)
            selected[kind] = count
            remaining -= count
            if remaining == 0:
                break
        return selected

    def resolve_battle(
        self,
        deployed: dict[str, dict[str, int]],
        survivors: dict[str, dict[str, int]],
    ) -> None:
        for color in (WHITE, BLACK):
            faction = self.faction(color)
            for kind in ARMY_KINDS:
                reserve = faction.army[kind] - deployed[color].get(kind, 0)
                faction.army[kind] = max(0, reserve) + survivors[color].get(kind, 0)

    def advance_day(self, color: str) -> int:
        self.day += 1
        return 0

    def accrue_income(self, elapsed_seconds: float) -> int:
        if elapsed_seconds <= 0:
            return 0

        total_earned = 0
        for faction in (self.player, self.rival):
            faction.farm_income_fraction += (
                faction.farms * FARM_INCOME_PER_SECOND * elapsed_seconds
            )
            earned = int(faction.farm_income_fraction)
            if earned:
                faction.coins += earned
                faction.farm_income_fraction -= earned
                total_earned += earned
        return total_earned

    def bot_action(self, difficulty: str = "medium") -> str | None:
        rival = self.rival
        if not rival.farm_sector and self.build_farm(BLACK):
            return "farm"
        if rival.farms < 3 and self.build_farm(BLACK):
            return "farm"
        if not rival.city and rival.farms >= 3 and self.build_city(BLACK):
            return "city"
        if rival.city and rival.army_size >= 3 and not rival.armory and self.build_armory(BLACK):
            return "armory"
        if rival.city and rival.army_size < ARMY_LIMIT:
            if difficulty != "easy" and rival.army["P"] > 0:
                for kind in ("N", "B", "R", "Q"):
                    if self.upgrade_pawn(BLACK, kind):
                        return f"upgrade:{kind}"
            if difficulty == "hard" and rival.army["N"] > 0:
                for kind in ("B", "R", "Q"):
                    if self.upgrade_pawn(BLACK, kind):
                        return f"upgrade:{kind}"
            if self.recruit(BLACK, "P"):
                return "recruit:P"
        return None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: object) -> Campaign:
        if not isinstance(data, dict):
            return cls()
        try:
            return cls(
                day=max(1, int(data.get("day", 1))),
                player=cls._faction_from_dict(data.get("player")),
                rival=cls._faction_from_dict(data.get("rival")),
            )
        except (TypeError, ValueError):
            return cls()

    @staticmethod
    def _faction_from_dict(data: object) -> Faction:
        if not isinstance(data, dict):
            return Faction()
        army_data = data.get("army")
        army = {
            kind: max(0, int(army_data.get(kind, 0)))
            if isinstance(army_data, dict)
            else 0
            for kind in ARMY_KINDS
        }
        return Faction(
            coins=max(0, int(data.get("coins", 450))),
            farms=max(0, min(8, int(data.get("farms", 0)))),
            farm_income_fraction=max(
                0.0,
                min(0.999999, float(data.get("farm_income_fraction", 0.0))),
            ),
            farm_sector=bool(data.get("farm_sector", data.get("farms", 0) > 0)),
            city=bool(data.get("city", False)),
            armory=bool(data.get("armory", False)),
            army=army,
        )