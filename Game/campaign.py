from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
import random

from .constants import BLACK, FARM_INCOME_PER_SECOND, WHITE

ARMY_KINDS = ("P", "N", "B", "R", "Q")
FARM_LIMIT = 12
FARM_BASE_COST = 250
FARM_COST_STEP = 400
CITY_COST = 3_600
RAIDER_SPEED = 0.9
RAIDER_ATTACK_INTERVAL = 3.0
RAIDER_RESPAWN_DELAY = 1.0
RAIDER_DAMAGE = 200
KING_RAIDER_KILL_COOLDOWN = 1.0
RAIDER_MIN_SPACING = 1.0
POTION_HEAL = 150
POTION_LIMIT = 3
PICKUP_RESPAWN_DELAY = 1.0
ARMORY_COST = 3_000
ARMY_LIMIT = 16
RECRUIT_COST_MULTIPLIER = 20
BASE_RECRUIT_COSTS = {"P": 800, "N": 1_200, "B": 1_200, "R": 1_900, "Q": 3_200}
RECRUIT_COSTS = {
    kind: cost * RECRUIT_COST_MULTIPLIER
    for kind, cost in BASE_RECRUIT_COSTS.items()
}
UPGRADE_SOURCES = {"N": "P", "B": "N", "R": "B", "Q": "R"}
BASE_ARMY_UPGRADE_COSTS = {"N": 400, "B": 400, "R": 700, "Q": 1_300}
ARMY_UPGRADE_COST_MULTIPLIER = 100
ARMY_UPGRADE_COSTS = {
    kind: cost * ARMY_UPGRADE_COST_MULTIPLIER
    for kind, cost in BASE_ARMY_UPGRADE_COSTS.items()
}


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
class Raider:
    row: float
    col: float
    attack_cooldown: float = 0.0


@dataclass
class Campaign:
    day: int = 1
    player: Faction = field(default_factory=Faction)
    rival: Faction = field(default_factory=lambda: Faction(coins=0))
    boss_chest_claimed: bool = False
    boss_chest_position: tuple[int, int] | None = None
    boss_losses: int = 0
    rival_action_count: int = 0
    realtime_seconds: float = 0.0
    rival_next_action_at: float = 10.0
    raiders_started_at: float | None = None
    loot_respawns: list[float] = field(default_factory=list)
    potion_respawns: list[float] = field(default_factory=list)
    potions_active: bool = False
    king_raider_kill_cooldown: float = 0.0
    king_dead: bool = False
    king_death_reason: str | None = None
    raiders: list[Raider] = field(default_factory=list)
    raider_respawns: list[float] = field(default_factory=list)
    potions: list[tuple[int, int]] = field(default_factory=list)

    def faction(self, color: str) -> Faction:
        return self.player if color == WHITE else self.rival

    def farm_cost(self, color: str) -> int:
        faction = self.faction(color)
        if not faction.farm_sector:
            return FARM_BASE_COST
        return FARM_BASE_COST + faction.farms * FARM_COST_STEP

    def build_farm(self, color: str) -> bool:
        faction = self.faction(color)
        cost = self.farm_cost(color)
        if (color == WHITE and faction.coins < cost) or faction.farms >= FARM_LIMIT:
            return False
        if color == WHITE:
            faction.coins -= cost
        if not faction.farm_sector:
            faction.farm_sector = True
            faction.farms = 1
        else:
            faction.farms += 1
        return True

    def build_city(self, color: str) -> bool:
        faction = self.faction(color)
        if (
            faction.city
            or faction.farms < 3
            or (color == WHITE and faction.coins < CITY_COST)
        ):
            return False
        if color == WHITE:
            faction.coins -= CITY_COST
        faction.city = True
        return True

    def build_armory(self, color: str) -> bool:
        faction = self.faction(color)
        if (
            not faction.city
            or faction.armory
            or faction.army_size < 3
            or (color == WHITE and faction.coins < ARMORY_COST)
        ):
            return False
        if color == WHITE:
            faction.coins -= ARMORY_COST
        faction.armory = True
        return True

    def recruit(self, color: str, kind: str) -> bool:
        faction = self.faction(color)
        cost = RECRUIT_COSTS.get(kind)
        if (
            not faction.city
            or cost is None
            or (color == WHITE and faction.coins < cost)
            or faction.army_size >= ARMY_LIMIT
        ):
            return False
        if color == WHITE:
            faction.coins -= cost
        faction.army[kind] += 1
        return True

    def upgrade_pawn(self, color: str, kind: str) -> bool:
        faction = self.faction(color)
        source = UPGRADE_SOURCES.get(kind)
        if source is None or faction.army[source] < 1:
            return False
        cost = ARMY_UPGRADE_COSTS[kind]
        if not faction.city or (color == WHITE and faction.coins < cost):
            return False
        if color == WHITE:
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

        faction = self.player
        faction.farm_income_fraction += (
            faction.farms * FARM_INCOME_PER_SECOND * elapsed_seconds
        )
        total_earned = int(faction.farm_income_fraction)
        if total_earned:
            faction.coins += total_earned
            faction.farm_income_fraction -= total_earned
        return total_earned

    def advance_realtime(
        self,
        elapsed_seconds: float,
        board_size: int,
        blocked_tiles: set[tuple[int, int]] | None = None,
    ) -> bool:
        if elapsed_seconds <= 0:
            return False
        self.realtime_seconds += elapsed_seconds
        self.king_raider_kill_cooldown = max(
            0.0, self.king_raider_kill_cooldown - elapsed_seconds
        )
        changed = False
        if self.rival.city:
            if self.raiders_started_at is None:
                self.raiders_started_at = self.realtime_seconds
                changed = True
            center = board_size // 2
            spawn_points = (
                (5.5, center - 0.5),
                (5.5, center + 1.5),
                (6.5, center + 0.5),
            )
            required_raiders = (
                3
                if self.realtime_seconds - self.raiders_started_at >= 45
                else 2
            )
            due_respawns = [
                respawn_at
                for respawn_at in self.raider_respawns
                if respawn_at <= self.realtime_seconds
            ]
            self.raider_respawns = [
                respawn_at
                for respawn_at in self.raider_respawns
                if respawn_at > self.realtime_seconds
            ]
            occupied = [(raider.row, raider.col) for raider in self.raiders]
            for _ in due_respawns:
                blocked = blocked_tiles or set()
                available_points = [
                    (row + 0.5, col + 0.5)
                    for row in range(board_size)
                    for col in range(board_size)
                    if (row, col) not in blocked
                    if all(
                        (row + 0.5 - occupied_row) ** 2
                        + (col + 0.5 - occupied_col) ** 2
                        >= RAIDER_MIN_SPACING**2
                        for occupied_row, occupied_col in occupied
                    )
                ]
                if not available_points:
                    self.raider_respawns.append(
                        self.realtime_seconds + RAIDER_RESPAWN_DELAY
                    )
                    continue
                row, col = random.choice(available_points)
                raider = Raider(row, col)
                self.raiders.append(raider)
                occupied.append((raider.row, raider.col))
                changed = True
            while len(self.raiders) + len(self.raider_respawns) < required_raiders:
                available_points = [
                    point
                    for point in spawn_points
                    if all(
                        (point[0] - row) ** 2 + (point[1] - col) ** 2
                        >= RAIDER_MIN_SPACING**2
                        for row, col in occupied
                    )
                ]
                if not available_points:
                    break
                row, col = available_points[0]
                raider = Raider(row, col)
                self.raiders.append(raider)
                occupied.append((raider.row, raider.col))
                changed = True
        else:
            if self.raiders or self.raiders_started_at is not None:
                self.raiders.clear()
                self.raider_respawns.clear()
                self.raiders_started_at = None
                changed = True
        return changed

    def move_raiders(
        self,
        elapsed_seconds: float,
        king_square: tuple[int, int] | None,
        blocked_tiles: set[tuple[int, int]] | None = None,
        board_size: int = 20,
        king_motion: tuple[tuple[int, int], tuple[int, int]] | None = None,
    ) -> int:
        if elapsed_seconds <= 0 or king_square is None:
            return 0

        blocked = blocked_tiles or set()
        distances = self._raider_path_distances(king_square, board_size, blocked)
        king_row, king_col = king_square[0] + 0.5, king_square[1] + 0.5
        damage = 0
        for raider in self.raiders:
            raider.attack_cooldown = max(
                0.0, raider.attack_cooldown - elapsed_seconds
            )
            delta_row = king_row - raider.row
            delta_col = king_col - raider.col
            distance = (delta_row * delta_row + delta_col * delta_col) ** 0.5
            attack_distance = distance
            if king_motion is not None:
                (start_row, start_col), (end_row, end_col) = king_motion
                start = (start_row + 0.5, start_col + 0.5)
                end = (end_row + 0.5, end_col + 0.5)
                segment_row = end[0] - start[0]
                segment_col = end[1] - start[1]
                segment_length_squared = (
                    segment_row * segment_row + segment_col * segment_col
                )
                if segment_length_squared:
                    projection = (
                        (raider.row - start[0]) * segment_row
                        + (raider.col - start[1]) * segment_col
                    ) / segment_length_squared
                    projection = min(1.0, max(0.0, projection))
                    closest_row = start[0] + projection * segment_row
                    closest_col = start[1] + projection * segment_col
                    motion_distance = (
                        (raider.row - closest_row) ** 2
                        + (raider.col - closest_col) ** 2
                    ) ** 0.5
                    attack_distance = min(attack_distance, motion_distance)
            if attack_distance <= 1.2:
                if raider.attack_cooldown <= 0:
                    damage += RAIDER_DAMAGE
                    raider.attack_cooldown = RAIDER_ATTACK_INTERVAL
                continue

            current = (int(raider.row), int(raider.col))
            options = (
                (current[0] - 1, current[1]),
                (current[0] + 1, current[1]),
                (current[0], current[1] - 1),
                (current[0], current[1] + 1),
            )
            next_tiles = sorted(
                (
                    tile
                    for tile in options
                    if tile in distances and tile not in blocked
                ),
                key=lambda tile: distances[tile],
            )
            for next_tile in next_tiles:
                target_row, target_col = next_tile
                target_row += 0.5
                target_col += 0.5
                step_row = target_row - raider.row
                step_col = target_col - raider.col
                step_distance = (step_row * step_row + step_col * step_col) ** 0.5
                if step_distance == 0:
                    continue
                travel = min(step_distance, RAIDER_SPEED * elapsed_seconds)
                new_row = raider.row + step_row / step_distance * travel
                new_col = raider.col + step_col / step_distance * travel
                if (int(new_row), int(new_col)) in blocked:
                    continue
                if any(
                    (new_row - other.row) ** 2 + (new_col - other.col) ** 2
                    < RAIDER_MIN_SPACING**2
                    for other in self.raiders
                    if other is not raider
                ):
                    continue
                raider.row = new_row
                raider.col = new_col
                break
        return damage

    @staticmethod
    def _raider_path_distances(
        king_square: tuple[int, int],
        board_size: int,
        blocked: set[tuple[int, int]],
    ) -> dict[tuple[int, int], int]:
        from collections import deque

        if king_square in blocked:
            return {}
        distances = {king_square: 0}
        queue = deque([king_square])
        while queue:
            row, col = queue.popleft()
            for neighbor in (
                (row - 1, col),
                (row + 1, col),
                (row, col - 1),
                (row, col + 1),
            ):
                if (
                    0 <= neighbor[0] < board_size
                    and 0 <= neighbor[1] < board_size
                    and neighbor not in blocked
                    and neighbor not in distances
                ):
                    distances[neighbor] = distances[(row, col)] + 1
                    queue.append(neighbor)
        return distances

    def remove_raiders_near(
        self, square: tuple[int, int], current_time: float | None = None
    ) -> int:
        if self.king_raider_kill_cooldown > 0:
            return 0

        row, col = square
        nearby_raiders = [
            (
                (raider.row - row) ** 2 + (raider.col - col) ** 2,
                index,
            )
            for index, raider in enumerate(self.raiders)
            if (raider.row - row) ** 2 + (raider.col - col) ** 2 <= 1.35**2
        ]
        if not nearby_raiders:
            return 0

        _, defeated_index = min(nearby_raiders)
        del self.raiders[defeated_index]
        respawn_at = (
            self.realtime_seconds if current_time is None else current_time
        ) + RAIDER_RESPAWN_DELAY
        self.raider_respawns.append(respawn_at)
        self.king_raider_kill_cooldown = KING_RAIDER_KILL_COOLDOWN
        return 1

    def bot_action(self, difficulty: str = "medium") -> str | None:
        if self.realtime_seconds < self.rival_next_action_at:
            return None

        rival = self.rival
        action = None
        if not rival.farm_sector and self.build_farm(BLACK):
            action = "farm"
        elif rival.farms < 3 and self.build_farm(BLACK):
            action = "farm"
        elif not rival.city and rival.farms >= 3 and self.build_city(BLACK):
            action = "city"
        elif rival.city and rival.army_size >= 3 and not rival.armory and self.build_armory(BLACK):
            action = "armory"
        elif rival.city and rival.army_size < ARMY_LIMIT:
            if difficulty != "easy" and rival.army["P"] > 0:
                for kind in ("N", "B", "R", "Q"):
                    if self.upgrade_pawn(BLACK, kind):
                        action = f"upgrade:{kind}"
                        break
            if difficulty == "hard" and rival.army["N"] > 0:
                if action is None:
                    for kind in ("B", "R", "Q"):
                        if self.upgrade_pawn(BLACK, kind):
                            action = f"upgrade:{kind}"
                            break
            if action is None and self.recruit(BLACK, "P"):
                action = "recruit:P"

        if action is not None:
            self.rival_action_count += 1
            if action == "farm":
                delay = 12.0
            elif action == "city":
                delay = 20.0
            elif action == "armory":
                delay = 14.0
            else:
                delay = 10.0
            self.rival_next_action_at = self.realtime_seconds + delay
        return action

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: object) -> Campaign:
        if not isinstance(data, dict):
            return cls()
        try:
            has_rival_growth_timer = "rival_next_action_at" in data
            rival = (
                cls._faction_from_dict(data.get("rival"))
                if has_rival_growth_timer
                else Faction(coins=0)
            )
            rival.coins = 0
            rival.farm_income_fraction = 0.0
            return cls(
                day=max(1, int(data.get("day", 1))),
                player=cls._faction_from_dict(data.get("player")),
                rival=rival,
                boss_chest_claimed=bool(data.get("boss_chest_claimed", False)),
                boss_chest_position=cls._read_chest_position(
                    data.get("boss_chest_position")
                ),
                boss_losses=max(0, int(data.get("boss_losses", 0))),
                rival_action_count=(
                    max(0, int(data.get("rival_action_count", 0)))
                    if has_rival_growth_timer
                    else 0
                ),
                realtime_seconds=max(0.0, float(data.get("realtime_seconds", 0.0))),
                rival_next_action_at=max(
                    10.0,
                    float(
                        data.get(
                            "rival_next_action_at",
                            max(10.0, float(data.get("realtime_seconds", 0.0)) + 10.0),
                        )
                    ),
                ),
                raiders_started_at=cls._read_optional_nonnegative_float(
                    data.get("raiders_started_at")
                ),
                loot_respawns=cls._read_respawn_times(
                    data.get(
                        "loot_respawns",
                        [data["loot_respawn_at"]]
                        if data.get("loot_respawn_at") is not None
                        else [],
                    )
                ),
                potion_respawns=cls._read_respawn_times(
                    data.get(
                        "potion_respawns",
                        [data["potion_respawn_at"]]
                        if data.get("potion_respawn_at") is not None
                        else [],
                    )
                ),
                potions_active=bool(data.get("potions_active", False)),
                king_raider_kill_cooldown=min(
                    1.0,
                    cls._read_optional_nonnegative_float(
                        data.get("king_raider_kill_cooldown")
                    )
                    or 0.0,
                ),
                king_dead=bool(data.get("king_dead", False)),
                king_death_reason=(
                    data.get("king_death_reason")
                    if isinstance(data.get("king_death_reason"), str)
                    else None
                ),
                raiders=cls._read_raiders(data.get("raiders")),
                raider_respawns=cls._read_respawn_times(
                    data.get("raider_respawns")
                ),
                potions=cls._read_potions(data.get("potions")),
            )
        except (TypeError, ValueError):
            return cls()

    @staticmethod
    def _read_chest_position(value: object) -> tuple[int, int] | None:
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(isinstance(part, int) for part in value)
            and 6 <= value[0] <= 13
            and 6 <= value[1] <= 13
        ):
            return value[0], value[1]
        return None

    @staticmethod
    def _read_raiders(value: object) -> list[Raider]:
        if not isinstance(value, list):
            return []
        raiders = []
        for item in value[:3]:
            if not isinstance(item, dict):
                continue
            try:
                row = float(item["row"])
                col = float(item["col"])
                cooldown = float(item.get("attack_cooldown", 0.0))
            except (KeyError, TypeError, ValueError):
                continue
            if all(
                isfinite(number) and abs(number) < 1_000_000
                for number in (row, col, cooldown)
            ):
                raiders.append(
                    Raider(
                        row=row,
                        col=col,
                        attack_cooldown=max(0.0, min(RAIDER_ATTACK_INTERVAL, cooldown)),
                    )
                )
        return raiders

    @staticmethod
    def _read_respawn_times(value: object) -> list[float]:
        if not isinstance(value, list):
            return []
        respawn_times = []
        for item in value[:3]:
            try:
                timestamp = float(item)
            except (TypeError, ValueError):
                continue
            if isfinite(timestamp) and timestamp >= 0:
                respawn_times.append(timestamp)
        return respawn_times

    @staticmethod
    def _read_optional_nonnegative_float(value: object) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, number) if isfinite(number) else None

    @staticmethod
    def _read_potions(value: object) -> list[tuple[int, int]]:
        if not isinstance(value, list):
            return []
        potions = []
        for square in value:
            if (
                isinstance(square, (list, tuple))
                and len(square) == 2
                and all(isinstance(part, int) for part in square)
                and 0 <= square[0] < 20
                and 0 <= square[1] < 20
            ):
                position = (square[0], square[1])
                if position not in potions:
                    potions.append(position)
            if len(potions) == POTION_LIMIT:
                break
        return potions

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
            farms=max(0, min(FARM_LIMIT, int(data.get("farms", 0)))),
            farm_income_fraction=max(
                0.0,
                min(0.999999, float(data.get("farm_income_fraction", 0.0))),
            ),
            farm_sector=bool(data.get("farm_sector", data.get("farms", 0) > 0)),
            city=bool(data.get("city", False)),
            armory=bool(data.get("armory", False)),
            army=army,
        )