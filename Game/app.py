from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from collections import OrderedDict, deque
from copy import deepcopy
import math
import random
from array import array

import pygame

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "Game"

from .constants import (
    BOT_DIFFICULTIES,
    BLACK,
    BOARD_VIEW_PIXELS,
    BOARD_LEFT,
    BOARD_SIZE,
    BOARD_TOP,
    CAMPAIGN_BOARD_SIZE,
    CLASSIC_BOARD_SIZE,
    CLASSIC_SQUARE_SIZE,
    FARM_INCOME_PER_SECOND,
    SQUARE_SIZE,
    WHITE,
    WINDOW_SIZE,
)
from .bot import choose_move
from .campaign import (
    ARMY_KINDS,
    ARMY_LIMIT,
    ARMORY_COST,
    ARMY_UPGRADE_COSTS,
    CITY_COST,
    FARM_LIMIT,
    PICKUP_RESPAWN_DELAY,
    POTION_HEAL,
    POTION_LIMIT,
    RECRUIT_COSTS,
    UPGRADE_SOURCES,
    Campaign,
)
from .effects import Effects
from .models import Move, Piece
from .renderer import BoardRenderer
from .progress import (
    load_campaign,
    load_audio_volumes,
    load_hardcore_enabled,
    load_language,
    load_tutorials_enabled,
    load_unlocked_level,
    save_campaign,
    save_audio_volumes,
    save_hardcore_enabled,
    save_language,
    save_tutorials_enabled,
    save_unlocked_level,
)
from .localization import translate
from .rules import ChessGame
from .textures import SceneTextures

CAMPAIGN_INTRO_ZOOM_DURATION_MS = 4500
CAMPAIGN_INTRO_START_ZOOM = 2.0
CAMERA_FOLLOW_SPEED = 8.0
WAR_VICTORY_SURRENDER_DURATION_MS = 4200
DIPLOMACY_REPLY_MIN_MS = 3000
DIPLOMACY_REPLY_MAX_MS = 5000
WAR_KING_MARCH_DURATION_MS = 3000
WAR_DEPLOYMENT_LIMIT = 8
FINAL_BATTLE_COUNTDOWN_SECONDS = 5 * 60
OPENING_RESULT_DURATION_MS = 4200
CAMPAIGN_MAP_VIEWPORT_LEFT = 236
ACHIEVEMENT_REWARD = 5_000
ACHIEVEMENT_NOTIFICATION_DURATION_MS = 6500
OPPONENT_THINK_MIN_MS = 1000
OPPONENT_THINK_MAX_MS = 3000
MOVE_ANIMATION_DURATION_SECONDS = 0.24
ACHIEVEMENTS = (
    ("baller", "Baller", "Ziskej 12 dam v armade."),
    ("businessman", "Businessman", "Postav vsech 12 farem."),
    ("zabijak", "Zabijak", "Poraz 10 nepratelskych pesaku."),
    ("alchemist", "Alchymista", "Vylec krale 10 lektvary."),
    (
        "hot_destinations",
        "Horké destinace",
        "Navstiv vsechna dostupna policka kampane.",
    ),
)


class ChessApp:
    def __init__(self, effects: Effects | None = None) -> None:
        pygame.init()
        self._initialize_audio()
        pygame.display.set_caption("Šachová bitva")
        self.windowed_size = WINDOW_SIZE
        self.fullscreen = False
        self.surface = pygame.display.set_mode(WINDOW_SIZE)
        self.pause_shade_surface = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        self.pause_shade_surface.fill((8, 12, 10, 205))
        desktop_sizes = pygame.display.get_desktop_sizes()
        if desktop_sizes:
            desktop_width, desktop_height = desktop_sizes[0]
            window_x = max(0, (desktop_width - WINDOW_SIZE[0]) // 2)
            window_y = max(0, (desktop_height - WINDOW_SIZE[1]) // 2)
            pygame.display.set_window_position((window_x, window_y))
        self.clock = pygame.time.Clock()
        self._campaign_save_dirty = False
        self._last_campaign_save_at = pygame.time.get_ticks()
        self._campaign_save_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="campaign-save"
        )
        self._campaign_save_future: Future[None] | None = None
        self._rendered_text_cache: OrderedDict[
            tuple[int, str, tuple[int, int, int]], pygame.Surface
        ] = OrderedDict()
        self.language = load_language()
        self.tutorial_enabled = load_tutorials_enabled()
        self.hardcore_enabled = load_hardcore_enabled()
        pygame.display.set_caption(translate("Šachová bitva", self.language))
        self.tutorial_seen: set[str] = set()
        self.tutorial_queue: list[tuple[str, str]] = []
        self.tutorial_active: tuple[str, str] | None = None
        self.tutorial_until = 0
        self.tutorial_panel = pygame.Rect(
            WINDOW_SIZE[0] - 328, WINDOW_SIZE[1] - 146, 312, 128
        )
        self.tutorial_close_button = pygame.Rect(
            self.tutorial_panel.right - 30,
            self.tutorial_panel.y + 8,
            22,
            22,
        )
        self.unlocked_level = load_unlocked_level()
        self.campaign = load_campaign()
        self.selected_level = 1
        self.active_level = 1
        self.game = self._create_level_game(self.active_level)
        self.textures = SceneTextures()
        self.renderer = BoardRenderer(effects, self.textures)
        self.font = pygame.font.SysFont("consolas", 22)
        self.small_font = pygame.font.SysFont("consolas", 16)
        self.title_font = pygame.font.SysFont("consolas", 30, bold=True)
        self.diplomacy_font = pygame.font.SysFont("consolas", 13)
        self.diplomacy_bold_font = pygame.font.SysFont(
            "consolas", 13, bold=True
        )
        self.selected: tuple[int, int] | None = None
        self.legal_moves: list[Move] = []
        self.pending_promotion: list[Move] = []
        self.status = self.game.status()
        self.running = True
        self.screen = "menu"
        self.has_started_game = False
        self.bot_difficulty = "medium"
        self.zoom = 1.0
        self.camera_offset = (0, 0)
        self.camera_target_offset = (0, 0)
        self.pan_start: tuple[int, int] | None = None
        self.pan_start_offset = (0, 0)
        self.pan_moved = False
        self.level_buttons = {
            1: pygame.Rect(245, 372, 250, 58),
            2: pygame.Rect(545, 372, 250, 58),
        }
        self.difficulty_buttons = {
            "easy": pygame.Rect(210, 278, 190, 46),
            "medium": pygame.Rect(425, 278, 190, 46),
            "hard": pygame.Rect(640, 278, 190, 46),
        }
        self.menu_play_button = pygame.Rect(380, 455, 280, 54)
        self.menu_new_game_button = pygame.Rect(380, 522, 280, 54)
        self.menu_quit_button = pygame.Rect(380, 589, 280, 54)
        self.achievements_back_button = pygame.Rect(370, 680, 300, 48)
        self.pause_debug_button = pygame.Rect(916, 680, 60, 26)
        self.pause_debug_panel = pygame.Rect(688, 426, 286, 152)
        self.pause_debug_outcome_buttons = {
            "white": pygame.Rect(700, 462, 262, 30),
            "black": pygame.Rect(700, 498, 262, 30),
            "draw": pygame.Rect(700, 534, 262, 30),
        }
        self.pause_debug_gold_button = pygame.Rect(700, 472, 262, 34)
        self.pause_debug_random_gold_button = pygame.Rect(700, 516, 262, 34)
        self.opening_debug_buttons = {
            "white": self.pause_debug_outcome_buttons["white"],
            "black": self.pause_debug_outcome_buttons["black"],
            "draw": self.pause_debug_outcome_buttons["draw"],
        }
        self.pause_debug_visible = False
        self.tutorial_toggle_button = pygame.Rect(790, 20, 210, 40)
        self.language_toggle_button = pygame.Rect(790, 68, 210, 40)
        self.hardcore_toggle_button = pygame.Rect(790, 116, 210, 40)
        self.death_retry_button = pygame.Rect(370, 480, 300, 52)
        self.death_menu_button = pygame.Rect(370, 546, 300, 52)
        self.undo_button = pygame.Rect(720, 650, 280, 32)
        self.reset_button = pygame.Rect(720, 688, 280, 32)
        self.in_game_menu_button = pygame.Rect(720, 726, 280, 30)
        self.pause_resume_button = pygame.Rect(380, 500, 280, 52)
        self.pause_menu_button = pygame.Rect(380, 566, 280, 52)
        self.pause_level_buttons = {
            1: pygame.Rect(105, 170, 190, 48),
            2: pygame.Rect(315, 170, 190, 48),
        }
        self.pause_tutorial_button = pygame.Rect(105, 270, 400, 44)
        self.pause_language_button = pygame.Rect(105, 328, 400, 44)
        self.pause_hardcore_button = pygame.Rect(105, 386, 400, 44)
        self.pause_music_slider = pygame.Rect(610, 220, 280, 12)
        self.pause_sfx_slider = pygame.Rect(610, 330, 280, 12)
        self.pause_resume_button = pygame.Rect(570, 590, 200, 52)
        self.pause_menu_button = pygame.Rect(790, 590, 170, 52)
        self.pause_slider_drag: str | None = None
        self.diplomacy_panel_rect = pygame.Rect(8, 80, 220, 490)
        self.diplomacy_choice_buttons = [
            pygame.Rect(18, 390 + index * 40, 200, 34)
            for index in range(4)
        ]
        self.diplomacy_panel_surface = pygame.Surface(
            self.diplomacy_panel_rect.size, pygame.SRCALPHA
        )
        self.diplomacy_panel_surface.fill((20, 27, 24, 238))
        pygame.draw.rect(
            self.diplomacy_panel_surface,
            (205, 169, 99),
            self.diplomacy_panel_surface.get_rect(),
            width=2,
            border_radius=10,
        )
        self.music_volume, self.sfx_volume = load_audio_volumes()
        self.music_channel = pygame.mixer.Channel(0)
        self.sfx_channel = pygame.mixer.Channel(1)
        self.music_sound = self._create_background_music()
        self.sfx_sound = self._create_menu_sound()
        self.move_sound = self._create_gameplay_sound(
            (620.0,), 0.075, amplitude=0.13
        )
        self.damage_sound = self._create_gameplay_sound(
            (190.0, 143.0), 0.18, amplitude=0.20, stagger_seconds=0.035
        )
        self.achievement_sound = self._create_gameplay_sound(
            (523.25, 659.25, 783.99, 1046.5),
            0.62,
            amplitude=0.18,
            stagger_seconds=0.105,
        )
        self.music_channel.set_volume(self.music_volume)
        self.music_channel.play(self.music_sound, loops=-1)
        self.sfx_channel.set_volume(self.sfx_volume)
        self.move_channel = pygame.mixer.Channel(2)
        self.damage_channel = pygame.mixer.Channel(3)
        self.achievement_channel = pygame.mixer.Channel(4)
        self.move_channel.set_volume(self.sfx_volume)
        self.damage_channel.set_volume(self.sfx_volume)
        self.achievement_channel.set_volume(self.sfx_volume)
        self.last_action_was_bot = False
        self.bot_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="chess-bot"
        )
        self.bot_future: Future[Move | None] | None = None
        self.bot_due_at: int | None = None
        self.team_health_animations: dict[str, tuple[int, int, float]] = {}
        self.piece_move_animation: tuple[
            Piece, tuple[int, int], tuple[int, int], float
        ] | None = None
        self.piece_health_animations: dict[
            tuple[int, int], tuple[int, int, float]
        ] = {}
        self.damage_popups: list[tuple[tuple[int, int], int, float]] = []
        self.campaign_tab = "farms"
        self.kingdom_game: ChessGame | None = None
        self._campaign_navigation_game: ChessGame | None = None
        self.campaign_battle_active = False
        self.boss_deployment_active = False
        self.war_deployment_active = False
        self.boss_battle_active = False
        self.diplomacy_reply_text: str | None = None
        self.diplomacy_reply_elapsed_ms = 0.0
        self.diplomacy_reply_duration_ms = 0
        self.war_march_path: list[tuple[int, int]] | None = None
        self.war_march_king: Piece | None = None
        self.war_march_elapsed_ms = 0.0
        self.war_deployment_limit = 0
        self.war_victory_started_at: int | None = None
        self.war_victory_is_final_battle = False
        self.war_victory_won = False
        self.final_battle_active = False
        self.opening_position_counts: dict[tuple[object, ...], int] = {}
        self.opening_transition_outcome: str | None = None
        self.opening_transition_started_at: int | None = None
        self.achievement_return_screen = "menu"
        self.achievement_notifications: list[tuple[str, int]] = []
        self.pending_achievement_sounds = 0
        self.campaign_intro_zoom_started_at: int | None = None
        self.banter_started_at = pygame.time.get_ticks()
        self.boss_deployment: dict[str, int] = {
            kind: 0 for kind in ARMY_KINDS
        }
        self.boss_deployment_buttons = {
            kind: {
                "minus": pygame.Rect(840, 164 + index * 66, 48, 42),
                "plus": pygame.Rect(932, 164 + index * 66, 48, 42),
            }
            for index, kind in enumerate(ARMY_KINDS)
        }
        self.boss_start_button = pygame.Rect(510, 535, 450, 58)
        self.boss_cancel_button = pygame.Rect(510, 610, 450, 48)
        self.boss_deployed_army: dict[str, int] = {}
        self.deployment_limit = 3
        self.deployed_armies: dict[str, dict[str, int]] = {}
        self.shop_menu: str | None = None
        self.shop_confirmation: str | None = None
        self.shop_confirmation_buttons: dict[str, pygame.Rect] = {}
        self.shop_screen_buttons: dict[str, pygame.Rect] = {}
        self.shop_screen_back_button = pygame.Rect(44, 675, 200, 52)
        self.drag_start: tuple[int, int] | None = None
        shop_names = ("farm", "city", "armory", "recruit", "upgrade", "war")
        self.shop_cards = {
            name: pygame.Rect(
                40 + (index % 3) * 198,
                610 + (index // 3) * 56,
                190,
                50,
            )
            for index, name in enumerate(shop_names)
        }
        self.campaign_tab_buttons = {
            "farms": pygame.Rect(720, 210, 90, 34),
            "city": pygame.Rect(815, 210, 90, 34),
            "armory": pygame.Rect(910, 210, 90, 34),
        }
        self.farm_button = pygame.Rect(720, 302, 280, 42)
        self.city_button = pygame.Rect(720, 352, 280, 42)
        self.city_unlock_button = pygame.Rect(720, 302, 280, 34)
        self.armory_button = pygame.Rect(720, 302, 280, 42)
        self.recruit_buttons = {
            kind: pygame.Rect(720, 340 + index * 38, 280, 32)
            for index, kind in enumerate(ARMY_KINDS)
        }
        self.upgrade_buttons = {
            kind: pygame.Rect(720, 530 + index * 29, 280, 25)
            for index, kind in enumerate(("N", "B", "R", "Q"))
        }
        self.deployment_minus_button = pygame.Rect(720, 500, 48, 38)
        self.deployment_plus_button = pygame.Rect(952, 500, 48, 38)
        self.declare_war_button = pygame.Rect(720, 600, 280, 44)
        self.campaign_hud_surface = pygame.Surface(
            (WINDOW_SIZE[0], 68), pygame.SRCALPHA
        )
        self.campaign_hud_surface.fill((20, 27, 24, 228))

    @staticmethod
    def _initialize_audio() -> None:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init(frequency=22050, size=-16, channels=1)
        if pygame.mixer.get_init() is None or pygame.mixer.get_init()[1] != -16:
            raise RuntimeError("The game requires a signed 16-bit audio mixer.")

    @staticmethod
    def _sound_from_samples(samples: array) -> pygame.mixer.Sound:
        mixer_settings = pygame.mixer.get_init()
        if mixer_settings is None:
            raise RuntimeError("The audio mixer is not initialized.")
        channels = mixer_settings[2]
        if channels > 1:
            multi_channel_samples = array("h")
            for sample in samples:
                multi_channel_samples.extend((sample,) * channels)
            samples = multi_channel_samples
        return pygame.mixer.Sound(buffer=samples.tobytes())

    @classmethod
    def _create_background_music(cls) -> pygame.mixer.Sound:
        mixer_settings = pygame.mixer.get_init()
        if mixer_settings is None:
            raise RuntimeError("The audio mixer is not initialized.")
        sample_rate = mixer_settings[0]
        duration_seconds = 10
        melody = (
            392.00, 440.00, 523.25, 587.33, 523.25,
            440.00, 392.00, 329.63, 349.23, 392.00,
            440.00, 523.25, 440.00, 392.00, 349.23,
            329.63, 392.00, 349.23, 293.66, 329.63,
        )
        bass_notes = (98.00, 130.81, 110.00, 146.83, 98.00)
        samples = array("h")
        for sample_index in range(sample_rate * duration_seconds):
            time_seconds = sample_index / sample_rate
            beat_index = int(time_seconds / 0.5)
            beat_time = time_seconds % 0.5
            melody_frequency = melody[beat_index % len(melody)]
            melody_envelope = min(
                1.0,
                beat_time / 0.018,
                max(0.0, (0.46 - beat_time) / 0.12),
            )
            bass_index = int(time_seconds / 2.0) % len(bass_notes)
            bass_time = time_seconds % 2.0
            bass_envelope = min(
                1.0,
                bass_time / 0.025,
                max(0.0, (1.5 - bass_time) / 0.35),
            )
            melody_tone = (
                math.sin(2 * math.pi * melody_frequency * time_seconds)
                + 0.2
                * math.sin(2 * math.pi * melody_frequency * 2 * time_seconds)
            )
            bass_tone = math.sin(
                2 * math.pi * bass_notes[bass_index] * time_seconds
            )
            value = 0.26 * melody_envelope * melody_tone + 0.18 * bass_envelope * bass_tone
            samples.append(round(value * 32767))
        return cls._sound_from_samples(samples)

    @classmethod
    def _create_menu_sound(cls) -> pygame.mixer.Sound:
        mixer_settings = pygame.mixer.get_init()
        if mixer_settings is None:
            raise RuntimeError("The audio mixer is not initialized.")
        sample_rate = mixer_settings[0]
        duration_seconds = 0.09
        sample_count = int(sample_rate * duration_seconds)
        samples = array("h")
        for sample_index in range(sample_count):
            progress = sample_index / sample_count
            envelope = (1.0 - progress) ** 2
            frequency = 1450 + 850 * progress
            value = 0.3 * envelope * math.sin(
                2 * math.pi * frequency * sample_index / sample_rate
            )
            samples.append(round(value * 32767))
        return cls._sound_from_samples(samples)

    @classmethod
    def _create_gameplay_sound(
        cls,
        frequencies: tuple[float, ...],
        duration_seconds: float,
        *,
        amplitude: float,
        stagger_seconds: float = 0.0,
    ) -> pygame.mixer.Sound:
        mixer_settings = pygame.mixer.get_init()
        if mixer_settings is None:
            raise RuntimeError("The audio mixer is not initialized.")
        sample_rate = mixer_settings[0]
        sample_count = int(sample_rate * duration_seconds)
        samples = array("h")
        note_count = len(frequencies)
        for sample_index in range(sample_count):
            time_seconds = sample_index / sample_rate
            value = 0.0
            for note_index, frequency in enumerate(frequencies):
                note_time = time_seconds - note_index * stagger_seconds
                if note_time < 0:
                    continue
                attack = min(1.0, note_time / 0.012)
                decay = math.exp(-4.2 * note_time / duration_seconds)
                fundamental = math.sin(2 * math.pi * frequency * note_time)
                overtone = 0.28 * math.sin(
                    2 * math.pi * frequency * 2.01 * note_time
                )
                value += (fundamental + overtone) * attack * decay
            value = amplitude * value / max(1, note_count)
            samples.append(round(max(-1.0, min(1.0, value)) * 32767))
        return cls._sound_from_samples(samples)

    @staticmethod
    def _create_level_game(level: int) -> ChessGame:
        if level == 1:
            return ChessGame(
                board_size=CLASSIC_BOARD_SIZE,
                random_armies=False,
                capture_majority=True,
                piece_health_multiplier=0.5,
            )
        if level == 2:
            return ChessGame(
                board_size=CAMPAIGN_BOARD_SIZE,
                random_armies=False,
                king_only=True,
                campaign_map=True,
            )
        raise ValueError(f"Unknown game level: {level}")

    def run(self) -> None:
        try:
            while self.running:
                elapsed_seconds = self.clock.tick(120) / 1000
                self._handle_events()
                self._advance_diplomacy(elapsed_seconds)
                self._advance_war_march(elapsed_seconds)
                self._advance_opening_transition()
                shop_is_open = (
                    self.active_level == 2
                    and self.shop_menu is not None
                    and not self.campaign_battle_active
                )
                if self.screen == "game" and not shop_is_open:
                    self._update_bot_turn()
                elif self.bot_due_at is not None:
                    self.bot_due_at += round(elapsed_seconds * 1000)
                self._check_achievements()
                self._update_achievement_sfx()
                self._advance_campaign_intro_zoom()
                self._update_camera_follow(elapsed_seconds)
                self._draw()
                self._draw_achievement_notifications()
                pygame.display.flip()
                self._advance_realtime_campaign(elapsed_seconds)
                self._flush_campaign_save()
        finally:
            try:
                self._flush_campaign_save(force=True)
            finally:
                self._campaign_save_executor.shutdown(wait=True)
                self.bot_executor.shutdown(wait=False, cancel_futures=True)

    def _advance_realtime_campaign(self, elapsed_seconds: float) -> None:
        if (
            self.active_level != 2
            or self.campaign_battle_active
            or self.shop_menu is not None
            or self.diplomacy_reply_text is not None
            or self.war_march_path is not None
            or self.war_deployment_active
            or self.campaign.king_dead
            or self.screen != "game"
        ):
            return

        zombies_were_active = self.campaign.raiders_started_at is not None
        blocked_raider_squares = (
            set(self.game.building_tiles)
            | set(self.game.shop_tiles)
            | set(self.game.loot)
            | self.game.loot_reserved_squares
            | set(self.campaign.potions)
        )
        blocked_raider_squares.update(
            (row, col)
            for row, board_row in enumerate(self.game.board)
            for col, piece in enumerate(board_row)
            if piece is not None
        )
        self.campaign.advance_realtime(
            elapsed_seconds,
            self.game.board_size,
            blocked_raider_squares,
        )
        final_battle_due = False
        if self.campaign.final_battle_countdown is not None:
            self.campaign.final_battle_countdown = max(
                0.0,
                self.campaign.final_battle_countdown - elapsed_seconds,
            )
            if self.campaign.final_battle_countdown == 0:
                self.campaign.final_battle_countdown = None
                self.campaign.final_battle_pending = True
                final_battle_due = True
        king_square = self._king_square(WHITE)
        if self.campaign.raiders and king_square is not None:
            health_before = self.game.team_health[WHITE]
            raider_damage = self.campaign.move_raiders(
                elapsed_seconds,
                king_square,
                blocked_raider_squares,
                self.game.board_size,
                king_max_health=self.game.team_health_max[WHITE],
            )
            if raider_damage:
                health_after = max(0, health_before - raider_damage)
                self.game.team_health[WHITE] = health_after
                now = pygame.time.get_ticks() / 1000
                self.team_health_animations[WHITE] = (
                    health_before,
                    health_after,
                    now,
                )
                self.damage_popups.append(
                    (king_square, health_before - health_after, now)
                )
                self._play_damage_sfx()
                if health_after == 0:
                    self.campaign.king_dead = True
                    self.campaign.king_death_reason = (
                        "Kral padl pod utoky zombiku."
                    )
                    self.screen = "death"
                    self._clear_selection()
                    self._cancel_bot_turn()
                self._mark_campaign_dirty()
        changed = elapsed_seconds > 0
        earned = self.campaign.accrue_income(elapsed_seconds)
        if (
            not zombies_were_active
            and self.campaign.raiders_started_at is not None
        ):
            self.campaign.potions_active = True
            self._ensure_campaign_potions()
            self._show_tutorial(
                "campaign.zombies",
                "Pesaci-zombici jdou po kralovi a utoci na nej. Poraz je "
                "kralem; za jednu sekundu se vrati jeden pesec.",
            )
            self._show_tutorial(
                "campaign.potions",
                "Cervene lektvary se objevi, jakmile zacnou zombici. Kralem "
                "je seberes a kazdy ti vrati az 150 HP.",
            )
        due_loot = [
            spawn_at
            for spawn_at in self.campaign.loot_respawns
            if spawn_at <= self.campaign.realtime_seconds
        ]
        self.campaign.loot_respawns = [
            spawn_at
            for spawn_at in self.campaign.loot_respawns
            if spawn_at > self.campaign.realtime_seconds
        ]
        for _ in due_loot:
            previous_count = len(self.game.loot)
            self.game._spawn_loot(
                previous_count + 1,
                blocked_squares={
                    (int(raider.row), int(raider.col))
                    for raider in self.campaign.raiders
                }
                | set(self.campaign.potions),
            )
            if len(self.game.loot) == previous_count:
                self.campaign.loot_respawns.append(
                    self.campaign.realtime_seconds + PICKUP_RESPAWN_DELAY
                )
            changed = True
        if self.campaign.raiders_started_at is not None:
            self.campaign.potions_active = True
            if not self.campaign.potions and not self.campaign.potion_respawns:
                self._ensure_campaign_potions()
                changed = True
        while any(
            spawn_at <= self.campaign.realtime_seconds
            for spawn_at in self.campaign.potion_respawns
        ):
            due_index = next(
                index
                for index, spawn_at in enumerate(self.campaign.potion_respawns)
                if spawn_at <= self.campaign.realtime_seconds
            )
            self.campaign.potion_respawns.pop(due_index)
            previous_count = len(self.campaign.potions)
            self._ensure_campaign_potions()
            if len(self.campaign.potions) == previous_count:
                self.campaign.potion_respawns.append(
                    self.campaign.realtime_seconds + PICKUP_RESPAWN_DELAY
                )
            changed = True
        if changed or earned:
            self._mark_campaign_dirty()
        if final_battle_due and not self.campaign.king_dead:
            self._mark_campaign_dirty()
            self._begin_final_battle_deployment()
        elif final_battle_due:
            self._mark_campaign_dirty()

    def _advance_diplomacy(self, elapsed_seconds: float) -> None:
        if (
            self.diplomacy_reply_text is None
            or self.screen != "game"
            or self.shop_menu is not None
            or self.active_level != 2
        ):
            return
        self.diplomacy_reply_elapsed_ms += max(0.0, elapsed_seconds) * 1000
        if self.diplomacy_reply_elapsed_ms < self.diplomacy_reply_duration_ms:
            return

        war_was_declared = self.campaign.rival_war_declared
        self.campaign.finish_diplomacy()
        self.diplomacy_reply_text = None
        self.diplomacy_reply_elapsed_ms = 0.0
        self.diplomacy_reply_duration_ms = 0
        self._mark_campaign_dirty()
        if not war_was_declared and self.campaign.rival_war_declared:
            self._ensure_campaign_potions()
            self._begin_war_march()

    def _advance_war_march(self, elapsed_seconds: float) -> None:
        if (
            self.war_march_path is None
            or self.screen != "game"
            or self.shop_menu is not None
        ):
            return
        self.war_march_elapsed_ms += max(0.0, elapsed_seconds) * 1000
        if self.war_march_elapsed_ms < WAR_KING_MARCH_DURATION_MS:
            return

        if self.war_march_king is not None and self.war_march_path:
            start = self._king_square(WHITE)
            destination = self.war_march_path[-1]
            if start is not None:
                self.game.board[start[0]][start[1]] = None
            self.game.board[destination[0]][destination[1]] = self.war_march_king
            self._record_campaign_square(destination)
        self.war_march_path = None
        self.war_march_king = None
        self.war_march_elapsed_ms = 0.0
        self._begin_war_deployment()

    def _opening_position_key(self) -> tuple[object, ...]:
        board = tuple(
            tuple(
                None
                if piece is None
                else (
                    piece.color,
                    piece.kind,
                    piece.health,
                    piece.level,
                    piece.experience,
                    tuple(sorted(piece.upgrades)),
                )
                for piece in row
            )
            for row in self.game.board
        )
        return (
            board,
            self.game.turn,
            tuple(sorted(self.game.castling_rights)),
            self.game.en_passant_target,
        )

    def _track_opening_position(self) -> bool:
        if self.active_level != 1 or self.screen != "game":
            return False
        key = self._opening_position_key()
        occurrences = self.opening_position_counts.get(key, 0) + 1
        self.opening_position_counts[key] = occurrences
        if occurrences < 5:
            return False
        self._finish_opening_match("draw")
        return True

    def _finish_opening_match(self, outcome: str) -> None:
        if outcome not in ("win", "loss", "draw"):
            raise ValueError(f"Invalid opening battle outcome: {outcome}")
        self._cancel_bot_turn()
        self._clear_selection()
        self.opening_transition_outcome = outcome
        self.opening_transition_started_at = pygame.time.get_ticks()
        self.screen = f"opening_{outcome}"
        self.status = {
            "win": "Vyhrál jsi úvodní bitvu.",
            "loss": "Černý král tě porazil.",
            "draw": "Pětkrát se opakovala stejná pozice. Remíza.",
        }[outcome]

    def _advance_opening_transition(self, *, force: bool = False) -> None:
        started_at = self.opening_transition_started_at
        outcome = self.opening_transition_outcome
        if started_at is None or outcome is None:
            return
        if (
            not force
            and pygame.time.get_ticks() - started_at < OPENING_RESULT_DURATION_MS
        ):
            return
        self.opening_transition_started_at = None
        self.opening_transition_outcome = None
        if outcome == "win":
            self.unlocked_level = max(self.unlocked_level, 2)
            save_unlocked_level(self.unlocked_level)
            self.selected_level = 2
            self._start_new_game(reset_campaign=False, abandon_current=True)
        else:
            self.selected_level = 1
            self._start_new_game(reset_campaign=False, abandon_current=True)
        self.screen = "game"

    def _king_square(
        self, color: str, game: ChessGame | None = None
    ) -> tuple[int, int] | None:
        board = (game or self.game).board
        for row_index, row in enumerate(board):
            for col_index, piece in enumerate(row):
                if piece is not None and piece.color == color and piece.kind == "K":
                    return row_index, col_index
        return None

    def _mark_campaign_dirty(self) -> None:
        self._campaign_save_dirty = True

    def _flush_campaign_save(self, *, force: bool = False) -> None:
        now = pygame.time.get_ticks()
        if self._campaign_save_future is not None:
            if force:
                self._campaign_save_future.result()
                self._campaign_save_future = None
            elif self._campaign_save_future.done():
                self._campaign_save_future.result()
                self._campaign_save_future = None
        if self._campaign_save_future is not None:
            return
        if not self._campaign_save_dirty or (
            not force and now - self._last_campaign_save_at < 3000
        ):
            return
        snapshot = deepcopy(self.campaign)
        self._campaign_save_future = self._campaign_save_executor.submit(
            save_campaign, snapshot
        )
        self._campaign_save_dirty = False
        self._last_campaign_save_at = now
        if force:
            self._campaign_save_future.result()
            self._campaign_save_future = None

    def _ensure_boss_chest_position(self) -> bool:
        if (
            self.campaign.boss_chest_claimed
            or self.campaign.player.army_size < 2
        ):
            return False
        created = self.campaign.boss_chest_position is None
        if created:
            board_size = self.game.board_size
            candidates = [
                (row, col)
                for row in range(
                    max(0, board_size - 14), min(board_size - 1, board_size - 6)
                )
                for col in range(6, min(14, board_size - 1))
                if all(
                    self.game.board[tile_row][tile_col] is None
                    and (tile_row, tile_col) not in self.game.shop_tiles
                    and (tile_row, tile_col) not in self.game.building_tiles
                    and (tile_row, tile_col) not in self.game.loot
                    for tile_row in (row, row + 1)
                    for tile_col in (col, col + 1)
                )
            ]
            if not candidates:
                raise RuntimeError("Unable to place the boss chest on the campaign map.")
            self.campaign.boss_chest_position = random.choice(candidates)
        chest_row, chest_col = self.campaign.boss_chest_position
        self.game.loot_reserved_squares = {
            (chest_row, chest_col),
            (chest_row, chest_col + 1),
            (chest_row + 1, chest_col),
            (chest_row + 1, chest_col + 1),
        }
        self.game.loot = {
            square: value
            for square, value in self.game.loot.items()
            if square not in self.game.loot_reserved_squares
        }
        if self.game.king_only:
            self._ensure_campaign_loot()
        return created

    def _ensure_campaign_loot(self) -> None:
        target_count = max(0, 3 - len(self.campaign.loot_respawns))
        while len(self.game.loot) > target_count:
            self.game.loot.pop(next(iter(self.game.loot)))
        self.game._spawn_loot(target_count)

    def _ensure_campaign_potions(self) -> bool:
        previous = list(self.campaign.potions)
        if not self.campaign.potions_active:
            self.campaign.potions.clear()
            self.game.loot_reserved_squares = (
                self._boss_chest_square_set() | set(self.campaign.potions)
            )
            return False
        saved_potion_squares = set(self.campaign.potions)
        if saved_potion_squares:
            self.game.loot = {
                square: value
                for square, value in self.game.loot.items()
                if square not in saved_potion_squares
            }
        occupied_raider_squares = {
            (int(raider.row), int(raider.col)) for raider in self.campaign.raiders
        }
        valid_potions = []
        for square in self.campaign.potions:
            row, col = square
            if (
                0 <= row < self.game.board_size
                and 0 <= col < self.game.board_size
                and self.game.board[row][col] is None
                and square not in self.game.building_tiles
                and square not in self.game.shop_tiles
                and square not in self.game.loot
                and square not in self.game.loot_reserved_squares
                and square not in occupied_raider_squares
                and square not in valid_potions
            ):
                valid_potions.append(square)
        self.campaign.potions = valid_potions[:POTION_LIMIT]
        candidates = [
            (row, col)
            for row in range(
                max(0, self.game.board_size - 14),
                min(self.game.board_size, self.game.board_size - 6),
            )
            for col in range(self.game.board_size)
            if self.game.board[row][col] is None
            and (row, col) not in self.game.building_tiles
            and (row, col) not in self.game.shop_tiles
            and (row, col) not in self.game.loot
            and (row, col) not in self.game.loot_reserved_squares
            and (row, col) not in occupied_raider_squares
            and (row, col) not in self.campaign.potions
        ]
        needed = max(
            0,
            POTION_LIMIT
            - len(self.campaign.potions)
            - len(self.campaign.potion_respawns),
        )
        if needed > 0 and candidates:
            self.campaign.potions.extend(
                random.sample(candidates, min(needed, len(candidates)))
            )
        chest_squares = self._boss_chest_square_set()
        self.game.loot_reserved_squares = chest_squares | set(self.campaign.potions)
        self._ensure_campaign_loot()
        return self.campaign.potions != previous

    def _boss_chest_square_set(self) -> set[tuple[int, int]]:
        chest_squares: set[tuple[int, int]] = set()
        if (
            not self.campaign.boss_chest_claimed
            and self.campaign.player.army_size >= 2
            and self.campaign.boss_chest_position is not None
        ):
            chest_row, chest_col = self.campaign.boss_chest_position
            chest_squares = {
                (chest_row, chest_col),
                (chest_row, chest_col + 1),
                (chest_row + 1, chest_col),
                (chest_row + 1, chest_col + 1),
            }
        return chest_squares

    def _collect_campaign_potion(self, square: tuple[int, int]) -> int:
        if square not in self.campaign.potions:
            return 0
        king = self.game.piece_at(square)
        if king is None or king.kind != "K" or king.color != WHITE:
            return 0
        old_health = self.game.team_health[WHITE]
        new_health = min(
            self.game.team_health_max[WHITE],
            old_health + POTION_HEAL,
        )
        if new_health <= old_health:
            return 0
        self.game.team_health[WHITE] = new_health
        self.campaign.potions.remove(square)
        self.campaign.king_potion_heals += 1
        now = pygame.time.get_ticks() / 1000
        self.team_health_animations[WHITE] = (
            old_health,
            new_health,
            now,
        )
        self.campaign.potion_respawns.append(
            self.campaign.realtime_seconds + PICKUP_RESPAWN_DELAY
        )
        self._show_tutorial(
            "campaign.potion-pickup",
            "Lektvar obnovil zdravi krale. Ztracene zdravi doplnis sbiranim "
            "dalsich lektvaru, maximum zdravi se neprekroci.",
        )
        self._mark_campaign_dirty()
        return new_health - old_health

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif (
                self.campaign_intro_zoom_started_at is not None
                and event.type != pygame.KEYDOWN
            ):
                continue
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key, event.mod)
            elif (
                event.type == pygame.MOUSEWHEEL
                and self.screen == "game"
                and self.active_level == 2
            ):
                self.zoom = min(2.0, max(0.5, self.zoom * (1.1 ** event.y)))
                self._follow_king_camera()
            elif (
                event.type == pygame.MOUSEMOTION
                and self.screen == "pause"
                and self.pause_slider_drag is not None
            ):
                if event.buttons[0]:
                    self._set_audio_volume_from_position(
                        self.pause_slider_drag, event.pos
                    )
            elif event.type == pygame.MOUSEMOTION and self.pan_start is not None:
                if event.buttons[0]:
                    delta = (
                        event.pos[0] - self.pan_start[0],
                        event.pos[1] - self.pan_start[1],
                    )
                    if abs(delta[0]) + abs(delta[1]) > 6:
                        self.pan_moved = True
                    if self.pan_moved:
                        self.camera_offset = (
                            self.pan_start_offset[0] + delta[0],
                            self.pan_start_offset[1] + delta[1],
                        )
                        self._clamp_camera_offset()
                        self.camera_target_offset = self.camera_offset
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.drag_start = None
                if self.boss_deployment_active or self.war_deployment_active:
                    self._handle_click(event.pos)
                elif (
                    self.screen == "game"
                    and self.active_level == 2
                    and not self.campaign_battle_active
                    and self.shop_menu is None
                    and self.diplomacy_panel_rect.collidepoint(event.pos)
                ):
                    self._handle_click(event.pos)
                elif (
                    self.screen == "game"
                    and self.active_level == 2
                    and (
                        self.diplomacy_reply_text is not None
                        or self.war_march_path is not None
                    )
                ):
                    self._handle_click(event.pos)
                elif (
                    self.screen == "game"
                    and self.shop_menu is None
                    and (
                        not self._bot_is_thinking()
                        or self._is_realtime_campaign()
                    )
                ):
                    square = self._board_square_at(event.pos)
                    piece = self.game.piece_at(square) if square is not None else None
                    if piece is not None and piece.color == self.game.turn:
                        self.drag_start = square
                    if (
                        self.active_level == 2
                        and not self.campaign_battle_active
                        and piece is None
                    ):
                        self.pan_start = event.pos
                        self.pan_start_offset = self.camera_offset
                        self.pan_moved = False
                    else:
                        self._handle_click(event.pos)
                else:
                    self._handle_click(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.pause_slider_drag is not None:
                    self._set_audio_volume_from_position(
                        self.pause_slider_drag, event.pos
                    )
                    self.pause_slider_drag = None
                    save_audio_volumes(self.music_volume, self.sfx_volume)
                elif self.pan_start is not None:
                    if not self.pan_moved:
                        self._handle_click(event.pos)
                    self.pan_start = None
                    self.pan_moved = False
                else:
                    self._handle_drag_release(event.pos)

    def _handle_key(self, key: int, modifiers: int = 0) -> None:
        if key == pygame.K_F11:
            self._toggle_fullscreen()
            return

        if self.screen in ("opening_win", "opening_loss", "opening_draw"):
            self._advance_opening_transition(force=True)
            return

        if self.boss_deployment_active:
            if key == pygame.K_ESCAPE:
                self._cancel_boss_deployment()
            return
        if self.war_deployment_active:
            if key == pygame.K_ESCAPE:
                self._cancel_war_deployment()
            return

        if self.screen == "pause":
            if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self._resume_from_pause()
            return

        if self.screen == "war_victory":
            if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                if self.war_victory_is_final_battle and not self.war_victory_won:
                    self.screen = "game"
                    self._begin_final_battle_deployment()
                elif self.war_victory_is_final_battle:
                    self.screen = "menu"
                else:
                    self.screen = "game"
                    self._schedule_bot_turn()
            return
        if self.screen == "achievements":
            if key in (pygame.K_l, pygame.K_ESCAPE):
                self.screen = self.achievement_return_screen
            return
        if key == pygame.K_l and self.screen in ("game", "menu"):
            self.achievement_return_screen = self.screen
            self.screen = "achievements"
            return

        if self.screen == "death":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.hardcore_enabled:
                    self.screen = "menu"
                else:
                    self._retry_after_death()
            elif key == pygame.K_ESCAPE:
                self.screen = "menu"
            return

        if self.screen == "menu":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self._start_or_continue()
            return
        if (
            self.diplomacy_reply_text is not None
            or self.war_march_path is not None
        ):
            if key == pygame.K_ESCAPE and self.active_level == 2:
                self.screen = "pause"
            return

        if (
            self.active_level == 2
            and not self.campaign_battle_active
            and self.shop_menu is None
        ):
            directions = {
                pygame.K_w: (-1, 0),
                pygame.K_s: (1, 0),
                pygame.K_a: (0, -1),
                pygame.K_d: (0, 1),
            }
            direction = directions.get(key)
            if direction is not None:
                self._move_king_with_wasd(*direction)
                return

        if key == pygame.K_ESCAPE:
            if self.active_level == 2 and not self.campaign_battle_active:
                self.screen = "pause"
                return
            if self.shop_menu is not None:
                self.shop_menu = None
                self.shop_confirmation = None
            elif self.selected is not None or self.pending_promotion:
                self._clear_selection()
            else:
                self.screen = "pause"
        elif key == pygame.K_z and modifiers & pygame.KMOD_CTRL:
            self._undo()
        elif key == pygame.K_p:
            if self.game.pass_turn():
                self._play_move_sfx()
                self.status = self.game.status()
                self._clear_selection()
                self.last_action_was_bot = False
                self._schedule_bot_turn()
        elif key == pygame.K_r and not self.pending_promotion:
            if self.active_level == 2 and self.campaign_battle_active:
                self.status = "Bitvu nelze prerusit resetem."
            else:
                self._cancel_bot_turn()
                self.game.reset()
                self.status = self.game.status()
                self.last_action_was_bot = False
                self._clear_selection()
                if self.active_level == 1:
                    self.opening_position_counts.clear()
                    self.opening_position_counts[self._opening_position_key()] = 1
        elif self._bot_is_thinking():
            return
        elif self.pending_promotion:
            choices = {
                pygame.K_q: "Q",
                pygame.K_r: "R",
                pygame.K_b: "B",
                pygame.K_n: "N",
            }
            selected_piece = choices.get(key)
            if selected_piece is not None:
                move = next(
                    move
                    for move in self.pending_promotion
                    if move.promotion == selected_piece
                )
                self._play_move(move)

    def _toggle_fullscreen(self) -> None:
        if self.fullscreen:
            self.surface = pygame.display.set_mode(self.windowed_size)
            self.fullscreen = False
            return

        self.windowed_size = self.surface.get_size()
        self.surface = pygame.display.set_mode(
            WINDOW_SIZE,
            pygame.FULLSCREEN | pygame.SCALED,
        )
        self.fullscreen = True

    def _handle_pause_click(self, position: tuple[int, int]) -> None:
        pause_controls = (
            *self.pause_level_buttons.values(),
            self.pause_tutorial_button,
            self.pause_language_button,
            self.pause_hardcore_button,
            self.pause_debug_button,
            self.pause_resume_button,
            self.pause_menu_button,
            self.pause_music_slider.inflate(0, 20),
            self.pause_sfx_slider.inflate(0, 20),
        )
        if any(rect.collidepoint(position) for rect in pause_controls):
            self._play_menu_sfx()

        selected_level = next(
            (
                level
                for level, rect in self.pause_level_buttons.items()
                if rect.collidepoint(position)
            ),
            None,
        )
        if selected_level is not None:
            self.selected_level = selected_level
        elif self.pause_tutorial_button.collidepoint(position):
            self._toggle_tutorials()
        elif self.pause_language_button.collidepoint(position):
            self._toggle_language()
        elif self.pause_hardcore_button.collidepoint(position):
            self._toggle_hardcore(from_pause=True)
        elif self.pause_debug_button.collidepoint(position):
            self.pause_debug_visible = not self.pause_debug_visible
        elif self.pause_debug_visible and self.active_level == 1:
            debug_outcomes = {
                "white": "win",
                "black": "loss",
                "draw": "draw",
            }
            outcome = next(
                (
                    result
                    for option, result in debug_outcomes.items()
                    if self.pause_debug_outcome_buttons[option].collidepoint(
                        position
                    )
                ),
                None,
            )
            if outcome is not None:
                self._finish_opening_match(outcome)
        elif self.pause_debug_visible and self.active_level == 2:
            if self.pause_debug_gold_button.collidepoint(position):
                self.campaign.player.coins += 10_000
                self._mark_campaign_dirty()
                self._flush_campaign_save(force=True)
            elif self.pause_debug_random_gold_button.collidepoint(position):
                self.campaign.player.coins += random.randint(1, 1_000_000)
                self._mark_campaign_dirty()
                self._flush_campaign_save(force=True)
        elif self.pause_resume_button.collidepoint(position):
            self._resume_from_pause()
        elif self.pause_menu_button.collidepoint(position):
            self.pause_debug_visible = False
            self.screen = "menu"
        else:
            for name, slider in (
                ("music", self.pause_music_slider),
                ("sfx", self.pause_sfx_slider),
            ):
                if slider.inflate(0, 20).collidepoint(position):
                    self.pause_slider_drag = name
                    self._set_audio_volume_from_position(name, position)
                    return

    def _resume_from_pause(self) -> None:
        self.pause_debug_visible = False
        if self.selected_level != self.active_level:
            self._start_new_game(reset_campaign=False, abandon_current=True)
        self.screen = (
            "death"
            if self.active_level == 2 and self.campaign.king_dead
            else "game"
        )
        if (
            self.screen == "game"
            and self.active_level == 2
            and self.campaign.final_battle_pending
            and not self.campaign.final_battle_complete
        ):
            self._begin_final_battle_deployment()

    def _handle_click(self, position: tuple[int, int]) -> None:
        if self.screen in ("opening_win", "opening_loss", "opening_draw"):
            self._advance_opening_transition(force=True)
            return
        if self.war_deployment_active:
            self._handle_war_deployment_click(position)
            return
        if self.boss_deployment_active and self.screen != "menu":
            self._handle_boss_deployment_click(position)
            return
        if (
            self.screen == "game"
            and self.active_level == 2
            and not self.campaign_battle_active
            and self.shop_menu is None
            and self.diplomacy_panel_rect.collidepoint(position)
        ):
            choice = next(
                (
                    index
                    for index, rect in enumerate(self.diplomacy_choice_buttons)
                    if rect.collidepoint(position)
                ),
                None,
            )
            if choice is not None:
                if (
                    self.campaign.rival_war_won
                    or self.diplomacy_reply_text is not None
                ):
                    return
                if self.campaign.rival_war_declared:
                    if (
                        self.campaign.rival_battle_wins >= 3
                        or self.campaign.final_battle_countdown is not None
                    ):
                        self.status = "Poslední bitva se blíží."
                        return
                    if choice == 0:
                        self._begin_war_march()
                    return
                _, reply = self.campaign.begin_diplomacy(choice)
                self.diplomacy_reply_text = reply
                self.diplomacy_reply_elapsed_ms = 0.0
                self.diplomacy_reply_duration_ms = min(
                    DIPLOMACY_REPLY_MAX_MS,
                    max(
                        DIPLOMACY_REPLY_MIN_MS,
                        2500 + len(reply) * 18,
                    ),
                )
                self._mark_campaign_dirty()
                self._play_menu_sfx()
            return
        if (
            self.screen == "game"
            and (
                self.diplomacy_reply_text is not None
                or self.war_march_path is not None
            )
        ):
            return
        if self.screen == "pause":
            self._handle_pause_click(position)
            return
        if self.screen == "death":
            if (
                not self.hardcore_enabled
                and self.death_retry_button.collidepoint(position)
            ):
                self._retry_after_death()
            elif self.death_menu_button.collidepoint(position):
                self.screen = "menu"
            return
        if self.screen == "achievements":
            if self.achievements_back_button.collidepoint(position):
                self.screen = self.achievement_return_screen
            return
        if self.screen == "war_victory":
            return
        if (
            self.tutorial_active is not None
            and self.tutorial_panel.collidepoint(position)
        ):
            if self.tutorial_close_button.collidepoint(position):
                self.tutorial_until = 0
            return
        if self.screen == "menu":
            menu_controls = (
                *self.level_buttons.values(),
                *self.difficulty_buttons.values(),
                self.menu_play_button,
                self.menu_new_game_button,
                self.menu_quit_button,
                self.tutorial_toggle_button,
                self.language_toggle_button,
                self.hardcore_toggle_button,
            )
            if any(rect.collidepoint(position) for rect in menu_controls):
                self._play_menu_sfx()
            level_choice = next(
                (
                    level
                    for level, rect in self.level_buttons.items()
                    if rect.collidepoint(position)
                    and (level <= self.unlocked_level or level == 2)
                ),
                None,
            )
            difficulty_choice = next(
                (
                    difficulty
                    for difficulty, rect in self.difficulty_buttons.items()
                    if rect.collidepoint(position)
                ),
                None,
            )
            if level_choice is not None:
                self.selected_level = level_choice
            elif difficulty_choice is not None:
                self.bot_difficulty = difficulty_choice
            elif self.tutorial_toggle_button.collidepoint(position):
                self._toggle_tutorials()
            elif self.language_toggle_button.collidepoint(position):
                self._toggle_language()
            elif self.hardcore_toggle_button.collidepoint(position):
                self._toggle_hardcore()
            elif self.menu_play_button.collidepoint(position):
                self._start_or_continue()
            elif self.menu_new_game_button.collidepoint(position):
                if not (
                    self.hardcore_enabled
                    and self.campaign.king_dead
                    and self.selected_level == 2
                ):
                    self._start_new_game(abandon_current=True)
                    self.screen = "game"
            elif self.menu_quit_button.collidepoint(position):
                self.running = False
            return
        if self.shop_menu is not None and self.active_level == 2 and not self.campaign_battle_active:
            self._handle_shop_screen_click(position)
            return

        if self.active_level == 2 and self.in_game_menu_button.collidepoint(position):
            self._play_menu_sfx()
            self._clear_selection()
            self.screen = "pause"
            return
        if self.active_level == 2:
            self._handle_campaign_board_click(position)
            return

        if self.pending_promotion:
            return
        if self.in_game_menu_button.collidepoint(position):
            self._clear_selection()
            self.screen = "pause"
            return
        if self.active_level == 2 and self.undo_button.collidepoint(position):
            self._undo()
            return
        if self.reset_button.collidepoint(position):
            if self.campaign_battle_active:
                self.status = "Bitvu nelze prerusit resetem."
            else:
                self._start_new_game()
            return
        if self._bot_is_thinking():
            return
        if self.active_level == 2 and not self.campaign_battle_active:
            card = next(
                (
                    kind
                    for kind, rect in self.shop_cards.items()
                    if rect.collidepoint(position)
                ),
                None,
            )
            if card is not None:
                self._activate_shop_card(card)
                return
            if self._handle_campaign_click(position):
                return
        square = self._board_square_at(position)
        if square is None:
            return

        if self.selected is not None:
            candidates = [move for move in self.legal_moves if move.end == square]
            if candidates:
                if len(candidates) > 1 and candidates[0].promotion is not None:
                    self.pending_promotion = candidates
                else:
                    self._play_move(candidates[0])
                return

        piece = self.game.piece_at(square)
        if piece is not None and piece.color == self.game.turn == WHITE:
            self.selected = square
            self.legal_moves = self.game.legal_moves_from(square)
        else:
            self._clear_selection()

    def _set_audio_volume_from_position(
        self, name: str, position: tuple[int, int]
    ) -> None:
        slider = (
            self.pause_music_slider if name == "music" else self.pause_sfx_slider
        )
        volume = min(1.0, max(0.0, (position[0] - slider.left) / slider.width))
        if name == "music":
            self.music_volume = volume
            self.music_channel.set_volume(volume)
        else:
            self.sfx_volume = volume
            for channel in (
                self.sfx_channel,
                self.move_channel,
                self.damage_channel,
                self.achievement_channel,
            ):
                channel.set_volume(volume)

    def _play_menu_sfx(self) -> None:
        self.sfx_channel.play(self.sfx_sound)

    def _play_move_sfx(self) -> None:
        self.move_channel.play(self.move_sound)

    def _play_damage_sfx(self) -> None:
        self.damage_channel.play(self.damage_sound)

    def _play_achievement_sfx(self) -> None:
        self.pending_achievement_sounds += 1

    def _update_achievement_sfx(self) -> None:
        if (
            self.pending_achievement_sounds > 0
            and not self.achievement_channel.get_busy()
        ):
            self.achievement_channel.play(self.achievement_sound)
            self.pending_achievement_sounds -= 1

    def _handle_campaign_board_click(self, position: tuple[int, int]) -> None:
        if self.pending_promotion or (
            self._bot_is_thinking() and not self._is_realtime_campaign()
        ):
            return
        square = self._board_square_at(position)
        if square is None:
            return
        if self.selected is not None:
            selected_piece = self.game.piece_at(self.selected)
            building = self.game.building_tiles.get(square)
            if (
                selected_piece is not None
                and selected_piece.kind == "K"
                and building is not None
                and building[0] == WHITE
            ):
                self._open_campaign_building(building[1])
                self._clear_selection()
                return
            candidates = [move for move in self.legal_moves if move.end == square]
            if candidates:
                self._play_move(candidates[0])
                return
        piece = self.game.piece_at(square)
        if piece is not None and piece.color == self.game.turn == WHITE:
            self.selected = square
            self.legal_moves = self.game.legal_moves_from(square)
        else:
            self._clear_selection()

    def _move_king_with_wasd(self, row_step: int, col_step: int) -> None:
        if self.game.turn != WHITE or (
            self._bot_is_thinking() and not self._is_realtime_campaign()
        ):
            return
        king_square = next(
            (
                (row, col)
                for row, board_row in enumerate(self.game.board)
                for col, piece in enumerate(board_row)
                if piece is not None and piece.color == WHITE and piece.kind == "K"
            ),
            None,
        )
        if king_square is None:
            return
        destination = (king_square[0] + row_step, king_square[1] + col_step)
        if not self.game._inside(*destination):
            return
        building = self.game.building_tiles.get(destination)
        if building is not None and building[0] == WHITE:
            self._open_campaign_building(building[1])
            return
        move = next(
            (
                candidate
                for candidate in self.game.legal_moves_from(king_square)
                if candidate.end == destination
            ),
            None,
        )
        if move is not None:
            self._play_move(move)

    def _open_campaign_building(self, kind: str) -> None:
        self.shop_menu = kind
        self.shop_confirmation = None
        self.status = f"Vstoupil jsi do: {self._shop_name(kind)}."
        self._show_farm_purchase_tutorial(kind)

    def _show_farm_purchase_tutorial(self, kind: str) -> None:
        if kind == "farm" and self.campaign.player.farms == 0:
            self._show_tutorial(
                "campaign.first-farm",
                "Kup svou prvni farmu za 250 minci. Farma ti bude automaticky "
                "vydelavat 3 mince za sekundu.",
            )

    def _campaign_shop_owner(self, square: tuple[int, int]) -> str:
        return BLACK if square[0] < self.game.board_size // 2 else WHITE

    def _board_layout(self) -> tuple[int, tuple[float, float]]:
        if self.active_level == 2 and not self.campaign_battle_active:
            square_size = max(24, round(32 * self.zoom))
            board_width = self.game.board_size * square_size
            board_height = self.game.board_size * square_size
            viewport = self._campaign_map_viewport()
            base_x = viewport.x + max(0, (viewport.width - board_width) // 2)
            base_y = viewport.y + max(0, (viewport.height - board_height) // 2)
            return square_size, (
                base_x + self.camera_offset[0],
                base_y + self.camera_offset[1],
            )
        base_square_size = (
            CLASSIC_SQUARE_SIZE
            if self.game.board_size == CLASSIC_BOARD_SIZE
            else SQUARE_SIZE
        )
        square_size = max(12, round(base_square_size * self.zoom))
        board_offset = (
            BOARD_VIEW_PIXELS - self.game.board_size * square_size
        ) // 2
        return square_size, (BOARD_LEFT + board_offset, BOARD_TOP + board_offset)

    @staticmethod
    def _campaign_map_viewport() -> pygame.Rect:
        return pygame.Rect(
            CAMPAIGN_MAP_VIEWPORT_LEFT,
            68,
            WINDOW_SIZE[0] - CAMPAIGN_MAP_VIEWPORT_LEFT,
            WINDOW_SIZE[1] - 68,
        )

    def _clamp_camera_offset(self) -> None:
        self.camera_offset = self._clamped_camera_offset(
            self.camera_offset, keep_king_visible=False
        )

    def _clamped_camera_offset(
        self,
        offset: tuple[float, float],
        *,
        keep_king_visible: bool = True,
    ) -> tuple[float, float]:
        if self.active_level != 2 or self.campaign_battle_active:
            return (0, 0)
        square_size = max(24, round(32 * self.zoom))
        board_width = self.game.board_size * square_size
        board_height = board_width
        viewport = self._campaign_map_viewport()
        base_x = viewport.x + max(0, (viewport.width - board_width) // 2)
        base_y = viewport.y + max(0, (viewport.height - board_height) // 2)
        min_x = min(0, viewport.width - board_width) - (base_x - viewport.x)
        max_x = max(0, viewport.width - board_width) - (base_x - viewport.x)
        min_y = min(0, viewport.height - board_height) - (base_y - viewport.y)
        max_y = max(0, viewport.height - board_height) - (base_y - viewport.y)
        king_square = self._king_square(WHITE)
        if keep_king_visible and self.zoom > 1.0 and king_square is not None:
            king_row, king_col = king_square
            min_x = max(
                viewport.x - base_x - board_width + square_size,
                viewport.x - base_x - king_col * square_size,
            )
            max_x = min(
                viewport.right - base_x - square_size,
                viewport.right - base_x - (king_col + 1) * square_size,
            )
            min_y = max(
                viewport.y - base_y - board_height + square_size,
                viewport.y - base_y - king_row * square_size,
            )
            max_y = min(
                viewport.bottom - base_y - (king_row + 1) * square_size,
                viewport.bottom - base_y - square_size,
            )
        return (
            min(max_x, max(min_x, offset[0])),
            min(max_y, max(min_y, offset[1])),
        )

    def _follow_king_camera(self) -> None:
        if (
            self.active_level != 2
            or self.campaign_battle_active
            or self.zoom <= 1.0
        ):
            self.camera_target_offset = self._clamped_camera_offset((0, 0))
            return
        king_square = self._king_square(WHITE)
        if king_square is None:
            self.camera_target_offset = self._clamped_camera_offset(
                self.camera_target_offset
            )
            return

        square_size = max(24, round(32 * self.zoom))
        board_width = self.game.board_size * square_size
        viewport = self._campaign_map_viewport()
        base_x = viewport.x + max(0, (viewport.width - board_width) // 2)
        base_y = viewport.y + max(0, (viewport.height - board_width) // 2)
        row, col = king_square
        target = (
            viewport.centerx - base_x - (col * square_size + square_size // 2),
            viewport.centery - base_y - (row * square_size + square_size // 2),
        )
        self.camera_target_offset = self._clamped_camera_offset(target)

    def _update_camera_follow(self, elapsed_seconds: float) -> None:
        self.camera_target_offset = self._clamped_camera_offset(
            self.camera_target_offset
        )
        blend = 1 - math.exp(-CAMERA_FOLLOW_SPEED * min(elapsed_seconds, 0.1))
        self.camera_offset = tuple(
            current + (target - current) * blend
            for current, target in zip(
                self.camera_offset, self.camera_target_offset
            )
        )
        if all(
            abs(current - target) < 0.1
            for current, target in zip(
                self.camera_offset, self.camera_target_offset
            )
        ):
            self.camera_offset = self.camera_target_offset
        self._clamp_camera_offset()

    def _board_square_at(
        self, position: tuple[int, int]
    ) -> tuple[int, int] | None:
        viewport = (
            self._campaign_map_viewport()
            if self.active_level == 2 and not self.campaign_battle_active
            else pygame.Rect((0, 0), WINDOW_SIZE)
            if self.active_level == 2
            else pygame.Rect(
                BOARD_LEFT, BOARD_TOP, BOARD_VIEW_PIXELS, BOARD_VIEW_PIXELS
            )
        )
        if not viewport.collidepoint(position):
            return None
        square_size, (origin_x, origin_y) = self._board_layout()
        col = math.floor((position[0] - origin_x) / square_size)
        row = math.floor((position[1] - origin_y) / square_size)
        return (row, col) if self.game._inside(row, col) else None

    def _handle_drag_release(self, position: tuple[int, int]) -> None:
        start = self.drag_start
        self.drag_start = None
        if (
            start is None
            or self.screen != "game"
            or self.shop_menu is not None
            or (
                self._bot_is_thinking()
                and not self._is_realtime_campaign()
            )
        ):
            return
        destination = self._board_square_at(position)
        if destination is None or destination == start:
            return
        if self.selected != start:
            self.selected = start
            self.legal_moves = self.game.legal_moves_from(start)
        square_size, (origin_x, origin_y) = self._board_layout()
        destination_position = (
            round(origin_x + destination[1] * square_size + square_size // 2),
            round(origin_y + destination[0] * square_size + square_size // 2),
        )
        self._handle_click(destination_position)

    def _start_or_continue(self) -> None:
        if not self.has_started_game or self.active_level != self.selected_level:
            self._start_new_game(reset_campaign=self.selected_level != 2)
        self.screen = (
            "death"
            if self.active_level == 2 and self.campaign.king_dead
            else "game"
        )
        if (
            self.screen == "game"
            and self.active_level == 2
            and self.campaign.final_battle_pending
            and not self.campaign.final_battle_complete
        ):
            self._begin_final_battle_deployment()

    def _retry_after_death(self) -> None:
        if self.hardcore_enabled:
            self.screen = "menu"
            return
        self.campaign.king_dead = False
        self.campaign.king_death_reason = None
        self._start_new_game(reset_campaign=False)
        self._mark_campaign_dirty()
        self.screen = "game"
        if self.campaign.final_battle_pending:
            self._begin_final_battle_deployment()

    def _start_new_game(
        self, *, reset_campaign: bool = True, abandon_current: bool = False
    ) -> None:
        if (
            not abandon_current
            and (
                self.campaign_battle_active
                or self.boss_deployment_active
                or self.war_deployment_active
                or self.war_march_path is not None
            )
        ):
            self.status = "Bitvu nelze prerusit resetem."
            return
        self._cancel_bot_turn()
        self.active_level = self.selected_level
        self.campaign_intro_zoom_started_at = None
        if self.active_level == 2 and reset_campaign:
            self.campaign = Campaign()
            self.achievement_notifications.clear()
        self.game = self._create_level_game(self.active_level)
        if self.active_level == 2:
            self._record_campaign_square(self._king_square(WHITE))
        if self.active_level == 2:
            changed = self._ensure_boss_chest_position()
            changed = self._ensure_campaign_potions() or changed
            if changed or reset_campaign:
                self._mark_campaign_dirty()
                self._flush_campaign_save(force=True)
        self.campaign_battle_active = False
        self.boss_battle_active = False
        self.war_victory_started_at = None
        self.war_victory_is_final_battle = False
        self.war_victory_won = False
        self.final_battle_active = False
        self.opening_transition_outcome = None
        self.opening_transition_started_at = None
        self.opening_position_counts.clear()
        self.pause_debug_visible = False
        self.boss_deployment_active = False
        self.war_deployment_active = False
        self.war_march_path = None
        self.war_march_king = None
        self.diplomacy_reply_text = None
        self.diplomacy_reply_elapsed_ms = 0.0
        self.diplomacy_reply_duration_ms = 0
        self.war_march_elapsed_ms = 0.0
        self.war_deployment_limit = 0
        self.boss_deployment = {kind: 0 for kind in ARMY_KINDS}
        self.boss_deployed_army = {}
        self.deployed_armies = {}
        self.piece_move_animation = None
        self.kingdom_game = None
        self.zoom = 1.0
        self.camera_offset = (0, 0)
        self.camera_target_offset = (0, 0)
        self.shop_menu = None
        self.shop_confirmation = None
        self.status = self.game.status()
        self.has_started_game = True
        self.last_action_was_bot = False
        self.banter_started_at = pygame.time.get_ticks()
        self._clear_selection()
        if self.active_level == 1:
            self.opening_position_counts[self._opening_position_key()] = 1
        if self.active_level == 1:
            self._show_tutorial(
                "classic.start",
                "Pohyb: klikni na svoji figurku a potom na cilove pole. "
                "Vyhrat muzes JEN zabitim cerneho krale. Zasahy poskozuji "
                "figurky, ale snizeni HP samo o sobe hru neukonci.",
            )
        else:
            self._show_tutorial(
                "campaign.start",
                "Kralem se pohybuj pomoci WASD nebo kliknutim na cil. Tvuj prvni "
                "cil: vstup do farmy a kup prvni farmu za 250 minci; vydela "
                "3 mince za sekundu.",
            )
            self.campaign_intro_zoom_started_at = pygame.time.get_ticks()
            self.zoom = CAMPAIGN_INTRO_START_ZOOM
            self._follow_king_camera()
        if self._is_realtime_campaign():
            self._schedule_bot_turn()

    def _play_move(self, move: Move) -> None:
        game_before = self.game
        moving_piece = self.game.piece_at(move.start)
        target_before = self.game.piece_at(move.end)
        if (
            self._is_realtime_campaign()
            and moving_piece is not None
            and moving_piece.color == WHITE
            and moving_piece.kind == "K"
            and move.end in self.game.shop_tiles
            and self._campaign_shop_owner(move.end) != WHITE
        ):
            self.status = "Nemuzes vstoupit do budov soupere."
            return
        if (
            self._is_realtime_campaign()
            and moving_piece is not None
            and moving_piece.color == WHITE
            and moving_piece.kind == "K"
            and move.end in self._boss_chest_tiles()
        ):
            self._begin_boss_deployment()
            return
        battle_finished = False
        realtime_campaign = self._is_realtime_campaign()
        potion_heal = 0
        if realtime_campaign:
            self.game.turn = WHITE
        team_health_before = self.game.team_health.copy()
        raiders_defeated = 0
        if self.game.play(move):
            self._play_move_sfx()
            if (
                realtime_campaign
                and moving_piece is not None
                and moving_piece.color == WHITE
                and moving_piece.kind == "K"
            ):
                self._record_campaign_square(move.end)
            if (
                self.active_level == 1
                and moving_piece is not None
                and moving_piece.color == WHITE
            ):
                if target_before is not None and target_before.color != WHITE:
                    self._show_tutorial(
                        "classic.capture",
                        "Zasah ubira figurce HP. Opakovanymi zasahy ji vyradis. "
                        "Vyhrat ale muzes jen zabitim cerneho krale.",
                    )
                elif move.promotion is not None:
                    self._show_tutorial(
                        "classic.promotion",
                        "Pesec dosahl posledni rady a povysil se na silnejsi "
                        "figurku. Damu zvol pro nejvetsi utocnou silu.",
                    )
            if (
                self._is_realtime_campaign()
                and moving_piece is not None
                and moving_piece.color == WHITE
                and moving_piece.kind == "K"
            ):
                raiders_defeated = self.campaign.remove_raiders_near(
                    move.end, self.campaign.realtime_seconds
                )
                if raiders_defeated:
                    self.campaign.raiders_defeated_total += raiders_defeated
                    self._mark_campaign_dirty()
                potion_heal = self._collect_campaign_potion(move.end)
                if self.campaign.boss_chest_position is not None:
                    self._show_tutorial(
                        "campaign.chest",
                        "Zlata truhla spousti souboj s bossy. Vyber az 4 "
                        "figurky a po vitezstvi ziskas odmenu.",
                    )
            if moving_piece is not None:
                self.piece_move_animation = (
                    moving_piece,
                    move.start,
                    move.end,
                    pygame.time.get_ticks() / 1000,
                )
            if realtime_campaign:
                self.game.turn = WHITE
            self.status = self.game.status()
            if raiders_defeated:
                self.status = f"Kral porazil {raiders_defeated} nepratelske pesce."
            if potion_heal:
                self.status = f"Kral se vylecil o {potion_heal} HP."
            self._record_damage_animations(team_health_before)
            if self.active_level == 1 and self._track_opening_position():
                self._clear_selection()
                return
            self._sync_campaign_progress()
            if self.game is not game_before:
                self._clear_selection()
                return
            if (
                self.active_level == 2
                and not self.campaign_battle_active
                and moving_piece is not None
                and moving_piece.color == WHITE
                and moving_piece.kind == "K"
            ):
                self._follow_king_camera()
                self.shop_confirmation = None
                shop_kind = self.game.shop_tiles.get(move.end)
                building = self.game.building_tiles.get(move.end)
                if shop_kind is None and building is not None and building[0] == WHITE:
                    shop_kind = building[1]
                if shop_kind is not None:
                    self._open_campaign_building(shop_kind)
                    self.campaign_tab = {
                        "farm": "farms",
                        "city": "city",
                        "recruit": "city",
                        "upgrade": "city",
                        "armory": "armory",
                        "war": "armory",
                    }[self.shop_menu]
                    self.status = "Obchod otevren: " + self._shop_name(self.shop_menu)
            if self.campaign_battle_active and self.game.winner() is not None:
                self._resolve_campaign_battle()
                battle_finished = True
            elif self.active_level == 2 and not self.campaign_battle_active:
                self._collect_campaign_loot(self.game.last_loot_color)
                self._advance_campaign_action(WHITE)
        self._clear_selection()
        self.last_action_was_bot = False
        if not battle_finished:
            self._schedule_bot_turn()
        if raiders_defeated:
            self.status = f"Kral porazil {raiders_defeated} nepratelske pesce."

    def _handle_campaign_click(self, position: tuple[int, int]) -> bool:
        for tab, button in self.campaign_tab_buttons.items():
            if button.collidepoint(position):
                self.campaign_tab = tab
                if tab == "farms" and self.campaign.player.farms == 0:
                    self._show_tutorial(
                        "campaign.first-farm",
                        "Kup svou prvni farmu za 250 minci. Farma ti bude "
                        "automaticky vydelavat 3 mince za sekundu.",
                    )
                return True

        if self.game.turn != WHITE:
            return False
        if self.campaign_tab == "farms":
            if self.farm_button.collidepoint(position):
                if self.campaign.build_farm(WHITE):
                    self._campaign_action_done("Farma postavena.")
                else:
                    self.status = "Na dalsi farmu nemas dost penez."
                return True
            if self.city_button.collidepoint(position):
                if self.campaign.build_city(WHITE):
                    self._campaign_action_done("Mesto odemceno.")
                else:
                    self.status = f"Mesto vyzaduje 3 farmy a {CITY_COST} minci."
                return True
        elif self.campaign_tab == "city":
            if self.city_unlock_button.collidepoint(position):
                if self.campaign.build_city(WHITE):
                    self._campaign_action_done("Mesto odemceno.")
                else:
                    self.status = f"Mesto vyzaduje 3 farmy a {CITY_COST} minci."
                return True
            kind = next(
                (
                    kind
                    for kind, button in self.recruit_buttons.items()
                    if button.collidepoint(position)
                ),
                None,
            )
            if kind is not None:
                if self.campaign.recruit(WHITE, kind):
                    self._campaign_action_done(
                        f"Najata figurka {self._piece_name(kind)}."
                    )
                else:
                    self.status = "Najem vyzaduje mesto, penize a volne misto."
                return True
            upgrade = next(
                (
                    kind
                    for kind, button in self.upgrade_buttons.items()
                    if button.collidepoint(position)
                ),
                None,
            )
            if upgrade is not None:
                if self.campaign.upgrade_pawn(WHITE, upgrade):
                    self._campaign_action_done(
                        f"Pesec povysen na {self._piece_name(upgrade)}."
                    )
                else:
                    self.status = "Povyseni vyzaduje mesto, pesce a penize."
                return True
        elif self.campaign_tab == "armory":
            if self.armory_button.collidepoint(position):
                if self.campaign.build_armory(WHITE):
                    self._campaign_action_done("Zbrojnice postavena.")
                else:
                    self.status = self._purchase_block_reason("armory") or "Zbrojnice se nepodarila postavit."
                return True
            if self.deployment_minus_button.collidepoint(position):
                self.deployment_limit = max(1, self.deployment_limit - 1)
                return True
            if self.deployment_plus_button.collidepoint(position):
                self.deployment_limit = min(8, self.deployment_limit + 1)
                return True
            if self.declare_war_button.collidepoint(position):
                if (
                    self.campaign.player.armory
                    and self.campaign.player.army_size > 0
                    and self.campaign.rival.armory
                    and self.campaign.rival.army_size > 0
                ):
                    self._start_campaign_battle()
                else:
                    self.status = "Ty i souper potrebujete zbrojnici a armadu."
                return True
        return False

    def _start_campaign_battle(self) -> None:
        self._start_campaign_battle_with_army()

    def _start_campaign_battle_with_army(
        self, selected_player_army: dict[str, int] | None = None
    ) -> None:
        final_battle = self.campaign.final_battle_pending
        player_army = (
            self.campaign.select_army(WHITE, self.deployment_limit)
            if selected_player_army is None
            else selected_player_army.copy()
        )
        if final_battle:
            rival_army = {"P": 0, "N": 2, "B": 2, "R": 2, "Q": 1}
        else:
            battle_limit = (
                self.deployment_limit
                if selected_player_army is None
                else max(1, sum(player_army.values()))
            )
            rival_army = self.campaign.select_army(BLACK, battle_limit)
        if not any(player_army.values()) or not any(rival_army.values()):
            self.status = "Oba kralovstvi potrebuji bojove jednotky."
            return

        if not final_battle:
            self.campaign.rival_war_declared = True
        self.kingdom_game = self.game
        self.piece_move_animation = None
        self.deployed_armies = {WHITE: player_army, BLACK: rival_army}
        battle = ChessGame(
            board_size=CLASSIC_BOARD_SIZE,
            random_armies=False,
        )
        battle.configure_battle(self.deployed_armies)
        self.game = battle
        self.campaign_battle_active = True
        self.war_deployment_active = False
        self.war_deployment_limit = 0
        self.boss_battle_active = False
        self.final_battle_active = final_battle
        self.status = (
            "Poslední bitva 8 x 8. Poraz černého krále doopravdy."
            if final_battle
            else "Bitva 8 x 8 zacala. Poraz souperova krale."
        )
        if not final_battle:
            self._show_tutorial(
                "campaign.war",
                "Vstoupil jsi do valky. Poraz kralem cerneho krale; prezivsi "
                "armada se vrati do mesta.",
            )
        self.zoom = 1.0
        self._clear_selection()

    def _begin_war_march(self) -> None:
        if (
            self.war_march_path is not None
            or self.war_deployment_active
            or self.campaign.rival_war_won
            or self.campaign.rival_battle_wins >= 3
            or self.campaign.final_battle_countdown is not None
            or self.campaign.final_battle_pending
        ):
            return
        king_square = self._king_square(WHITE)
        king = (
            None
            if king_square is None
            else self.game.board[king_square[0]][king_square[1]]
        )
        armory_gate = next(
            (
                square
                for square, kind in self.game.shop_tiles.items()
                if kind == "armory" and square[0] >= self.game.board_size // 2
            ),
            None,
        )
        if king_square is None or king is None or armory_gate is None:
            self.status = "Krále nebo vstup do zbrojnice se nepodařilo najít."
            return

        blocked = (
            set(self.game.building_tiles)
            | set(self.game.loot)
            | self.game.loot_reserved_squares
            | set(self.campaign.potions)
        )
        blocked.update(
            (row, col)
            for row, board_row in enumerate(self.game.board)
            for col, piece in enumerate(board_row)
            if piece is not None and (row, col) != king_square
        )
        blocked.update(
            (int(raider.row), int(raider.col))
            for raider in self.campaign.raiders
        )
        blocked.update(
            square for square in self.game.shop_tiles if square != armory_gate
        )
        previous: dict[tuple[int, int], tuple[int, int] | None] = {
            king_square: None
        }
        frontier = deque([king_square])
        while frontier and armory_gate not in previous:
            row, col = frontier.popleft()
            for next_square in (
                (row - 1, col),
                (row + 1, col),
                (row, col - 1),
                (row, col + 1),
            ):
                next_row, next_col = next_square
                if (
                    not self.game._inside(next_row, next_col)
                    or next_square in blocked
                    or next_square in previous
                ):
                    continue
                previous[next_square] = (row, col)
                frontier.append(next_square)
        if armory_gate not in previous:
            self.status = "Cesta do zbrojnice je zablokovaná."
            return

        path = [armory_gate]
        while path[-1] != king_square:
            parent = previous[path[-1]]
            if parent is None:
                self.status = "Cestu do zbrojnice se nepodařilo sestavit."
                return
            path.append(parent)
        path.reverse()
        self._cancel_bot_turn()
        self.shop_menu = None
        self.shop_confirmation = None
        self._clear_selection()
        self.piece_move_animation = None
        self.war_march_path = path
        self.war_march_king = king
        self.war_march_elapsed_ms = 0.0
        self.status = "Král vyráží do zbrojnice."
        self._play_menu_sfx()

    def _begin_war_deployment(self) -> None:
        if self.campaign.player.army_size == 0:
            self.campaign.player.city = True
            self.campaign.player.armory = True
            self.campaign.player.army["P"] = 3
            self._mark_campaign_dirty()
            self.status = "Město povolalo tři pěšáky do obrany."
        else:
            self.status = "Vyber jednotky z městské armády pro závěrečnou bitvu."
        self.boss_deployment = {kind: 0 for kind in ARMY_KINDS}
        self.war_deployment_limit = min(
            WAR_DEPLOYMENT_LIMIT, self.campaign.player.army_size
        )
        self.war_deployment_active = True
        self._cancel_bot_turn()

    def _begin_final_battle_deployment(self) -> None:
        if (
            not self.campaign.final_battle_pending
            or self.campaign.final_battle_complete
            or self.campaign_battle_active
        ):
            return
        if self.campaign.player.army_size == 0:
            self.campaign.player.city = True
            self.campaign.player.armory = True
            self.campaign.player.army["P"] = 3
            self._mark_campaign_dirty()
        self.boss_deployment = {kind: 0 for kind in ARMY_KINDS}
        self.war_deployment_limit = min(
            WAR_DEPLOYMENT_LIMIT, self.campaign.player.army_size
        )
        self.war_deployment_active = True
        self.status = "Připrav se na poslední bitvu. Vyber své figurky."
        self._cancel_bot_turn()

    def _handle_war_deployment_click(self, position: tuple[int, int]) -> None:
        if self.boss_cancel_button.collidepoint(position):
            self._cancel_war_deployment()
            return
        for kind, buttons in self.boss_deployment_buttons.items():
            if buttons["minus"].collidepoint(position):
                self.boss_deployment[kind] = max(
                    0, self.boss_deployment[kind] - 1
                )
                return
            if buttons["plus"].collidepoint(position):
                selected = sum(self.boss_deployment.values())
                if (
                    selected < self.war_deployment_limit
                    and self.boss_deployment[kind]
                    < self.campaign.player.army[kind]
                ):
                    self.boss_deployment[kind] += 1
                return
        if self.boss_start_button.collidepoint(position):
            if sum(self.boss_deployment.values()) == 0:
                self.status = "Vyber alespoň jednu jednotku."
                return
            self._start_campaign_battle_with_army(self.boss_deployment)

    def _cancel_war_deployment(self) -> None:
        if self.campaign.final_battle_pending:
            self.status = "Poslední bitvu už nelze odložit."
            return
        self.war_deployment_active = False
        self.boss_deployment = {kind: 0 for kind in ARMY_KINDS}
        self.war_deployment_limit = 0
        self.status = "Armáda čeká u zbrojnice; výběr můžeš otevřít znovu."
        self._schedule_bot_turn()

    def _boss_chest_tiles(self) -> set[tuple[int, int]]:
        if (
            self.active_level != 2
            or self.campaign_battle_active
            or self.campaign.boss_chest_claimed
            or self.campaign.player.army_size < 2
        ):
            return set()
        if self.campaign.boss_chest_position is None:
            return set()
        row, col = self.campaign.boss_chest_position
        return {(row, col), (row, col + 1), (row + 1, col), (row + 1, col + 1)}

    def _begin_boss_deployment(self) -> None:
        self._cancel_bot_turn()
        self.kingdom_game = self.game
        self.boss_deployment = {kind: 0 for kind in ARMY_KINDS}
        self.boss_deployment_active = True
        self.shop_menu = None
        self.shop_confirmation = None
        self.status = "Vyber nejvyse 4 figurky do souboje s bossy."
        self._clear_selection()

    def _handle_boss_deployment_click(self, position: tuple[int, int]) -> None:
        if self.boss_cancel_button.collidepoint(position):
            self._cancel_boss_deployment()
            return
        for kind, buttons in self.boss_deployment_buttons.items():
            if buttons["minus"].collidepoint(position):
                self.boss_deployment[kind] = max(
                    0, self.boss_deployment[kind] - 1
                )
                return
            if buttons["plus"].collidepoint(position):
                selected = sum(self.boss_deployment.values())
                available = self.campaign.player.army[kind]
                if selected < 4 and self.boss_deployment[kind] < available:
                    self.boss_deployment[kind] += 1
                return
        if self.boss_start_button.collidepoint(position):
            if sum(self.boss_deployment.values()) == 0:
                self.status = "Vyber alespon jednu figurku."
                return
            self._start_boss_battle()

    def _cancel_boss_deployment(self) -> None:
        self.boss_deployment_active = False
        self.boss_deployment = {kind: 0 for kind in ARMY_KINDS}
        self.kingdom_game = None
        self.status = "K truhle se muzes vratit pozdeji."
        self._schedule_bot_turn()

    def _start_boss_battle(self) -> None:
        player_army = self.boss_deployment.copy()
        progression = min(
            3,
            max(0, (self.campaign.player.army_size - 3) // 3)
            + self.campaign.boss_losses,
        )
        difficulty_range = {"easy": 1, "medium": 2, "hard": 2}
        boss_count = random.randint(
            1,
            min(4, difficulty_range[self.bot_difficulty] + progression),
        )
        difficulty_rank = {"easy": 0, "medium": 1, "hard": 2}[
            self.bot_difficulty
        ]
        strength = min(4, difficulty_rank + progression)
        boss_kinds = random.choices(
            ("P", "N", "B", "R", "Q"),
            weights=(
                max(1, 8 - strength * 2),
                3 + strength,
                3 + strength,
                1 + strength * 2,
                1 + strength * 2,
            ),
            k=boss_count,
        )
        boss_army = {kind: boss_kinds.count(kind) for kind in ARMY_KINDS}
        self.boss_deployed_army = player_army
        self.deployed_armies = {WHITE: player_army, BLACK: boss_army}
        self.piece_move_animation = None
        battle = ChessGame(
            board_size=6,
            random_armies=False,
            king_only=True,
        )
        battle.configure_battle(self.deployed_armies)
        self.game = battle
        self.boss_deployment_active = False
        self.boss_battle_active = True
        self.campaign_battle_active = True
        self.status = "Souboj o truhlu 6 x 6. Poraz krale bossu."
        self.zoom = 1.0
        self.camera_offset = (0, 0)
        self.camera_target_offset = (0, 0)
        self._clear_selection()

    def _resolve_campaign_battle(self) -> None:
        if self.boss_battle_active:
            self._resolve_boss_battle()
            return

        final_battle = self.final_battle_active
        survivors = {WHITE: {}, BLACK: {}}
        for color in (WHITE, BLACK):
            survivors[color] = {kind: 0 for kind in ARMY_KINDS}
        for row in self.game.board:
            for piece in row:
                if piece is not None and piece.kind != "K":
                    survivors[piece.color][piece.kind] += 1

        winner = self.game.winner()
        self.campaign.resolve_battle(self.deployed_armies, survivors)
        self.campaign.player.coins += self.game.coins[WHITE]
        if winner == WHITE:
            self.campaign.faction(winner).coins += 250
            if final_battle:
                self.campaign.final_battle_pending = False
                self.campaign.final_battle_countdown = None
                self.campaign.final_battle_complete = True
                self.campaign.rival_war_won = True
            else:
                self.campaign.rival_battle_wins = min(
                    3, self.campaign.rival_battle_wins + 1
                )
                if self.campaign.rival_battle_wins >= 3:
                    self.campaign.final_battle_countdown = (
                        FINAL_BATTLE_COUNTDOWN_SECONDS
                    )
                else:
                    rival = self.campaign.rival
                    rival.city = True
                    rival.armory = True
                    for kind in (
                        ("R",)
                        if self.campaign.rival_battle_wins == 1
                        else ("R", "Q")
                    ):
                        if rival.army_size < ARMY_LIMIT:
                            rival.army[kind] += 1
        if winner in (WHITE, BLACK):
            result = "Vitezstvi" if winner == WHITE else "Porazka"
            if final_battle and winner == WHITE:
                self.status = "Vyhráli jste finální bitvu. Království je vaše!"
            elif final_battle:
                self.status = "Černý král vyhrál. Připrav armádu a zkus to znovu."
            elif winner == WHITE and self.campaign.rival_war_declared:
                self.status = (
                    f"Vyhráli jste bitvu "
                    f"{self.campaign.rival_battle_wins}/3. Tohle není naposledy."
                )
            else:
                self.status = f"{result}. Prezivsi jednotky se vraci do kralovstvi."
        else:
            self.status = (
                "Bitva skoncila. Prezivsi jednotky se vraci domů."
                if not final_battle
                else "Finální bitva skončila remízou. Zkus to znovu."
            )

        self._mark_campaign_dirty()
        battle_result = self.status
        if self.kingdom_game is not None:
            self.game = self.kingdom_game
        self.kingdom_game = None
        self.piece_move_animation = None
        self.campaign_battle_active = False
        self.war_deployment_active = False
        self.war_deployment_limit = 0
        self.final_battle_active = False
        self.deployed_armies = {}
        self.game.turn = WHITE
        self._clear_selection()
        self.status = battle_result
        if winner == WHITE or final_battle:
            self.screen = "war_victory"
            self.war_victory_started_at = pygame.time.get_ticks()
            self.war_victory_is_final_battle = final_battle
            self.war_victory_won = winner == WHITE
        self._flush_campaign_save(force=True)

    def _resolve_boss_battle(self) -> None:
        winner = self.game.winner()
        survivors = {kind: 0 for kind in ARMY_KINDS}
        for row in self.game.board:
            for piece in row:
                if piece is not None and piece.color == WHITE and piece.kind != "K":
                    survivors[piece.kind] += 1

        player = self.campaign.player
        for kind in ARMY_KINDS:
            reserve = max(0, player.army[kind] - self.boss_deployed_army[kind])
            player.army[kind] = reserve + (
                survivors[kind] if winner == WHITE else 0
            )

        if winner == WHITE:
            reward = round(
                180 * FARM_INCOME_PER_SECOND * player.farms
            )
            player.coins += reward
            self.campaign.boss_chest_claimed = True
            result = f"Vitezstvi! Truhla obsahuje {reward} zlata (3 minuty prijmu farem)."
        else:
            self.campaign.boss_losses += 1
            result = "Porazka. Nasazene figurky jsi ztratil a truhla zustava."

        if self.kingdom_game is not None:
            self.game = self.kingdom_game
        self.kingdom_game = None
        self.piece_move_animation = None
        self.campaign_battle_active = False
        self.boss_battle_active = False
        self.boss_deployment_active = False
        self.boss_deployed_army = {}
        self.deployed_armies = {}
        self.game.turn = WHITE
        self._clear_selection()
        self.status = result
        self._mark_campaign_dirty()
        self._flush_campaign_save(force=True)
        self._schedule_bot_turn()

    def _campaign_action_done(self, message: str) -> None:
        self._advance_campaign_action(WHITE)
        if message.startswith("Farma"):
            self._show_tutorial(
                "campaign.farm",
                "Farmy automaticky vydelavaji mince kazdou sekundu. Dalsi farma "
                "je drazsi a mesto odemkne dalsi rozvoj.",
            )
        elif message.startswith("Mesto"):
            self._show_tutorial(
                "campaign.city",
                "Mesto odemyka najem pesaku a dalsich figurek. Najmi alespon "
                "dve jednotky, aby se objevila pokladova truhla.",
            )
        elif message.startswith("Najata"):
            self._show_tutorial(
                "campaign.recruit",
                "Jednotky najimas v zalozce Mesto. Najmi dve pro odemceni "
                "truhly a tri pro pristup do zbrojnice.",
            )
        elif message.startswith("Pesec povysen"):
            self._show_tutorial(
                "campaign.upgrade",
                "V zalozce Mesto muzes povysit pesce na silnejsi figurku. "
                "Vylepseni stoji mince a spotrebuje puvodni jednotku.",
            )
        elif message.startswith("Zbrojnice"):
            self._show_tutorial(
                "campaign.armory",
                "Zbrojnice otevre pripravu valky. Vyber velikost oddilu a "
                "nasad jednotky; v bitve hraje bot proti tobe.",
            )
        elif message.startswith("Valka") or message.startswith("Bitva"):
            self._show_tutorial(
                "campaign.battle",
                "V bitve ovladas figurky stejne jako v uvodni hre. Poraz "
                "soupere a prezivsi jednotky se vrati do armady.",
            )
        if self.active_level == 2 and not self.campaign_battle_active:
            if self._ensure_boss_chest_position():
                self._mark_campaign_dirty()
                self._show_tutorial(
                    "campaign.chest-unlocked",
                    "Truhla se odemkla! Kralem dojdi k truhle, vyber az 4 "
                    "jednotky a poraz strazce pro poklad.",
                )
        if not self._is_realtime_campaign():
            self.game.turn = BLACK
        self.status = message
        self.shop_confirmation = None
        self._clear_selection()
        self.last_action_was_bot = False
        self._schedule_bot_turn()

    def _toggle_tutorials(self) -> None:
        self.tutorial_enabled = not self.tutorial_enabled
        save_tutorials_enabled(self.tutorial_enabled)
        self.tutorial_seen.clear()
        self.tutorial_queue.clear()
        self.tutorial_active = None
        self.tutorial_until = 0
        if not self.tutorial_enabled:
            return
        if self.screen == "game" and self.active_level == 2:
            self._show_tutorial(
                "campaign.start",
                "Kralem se pohybuj pomoci WASD nebo kliknutim na cil. Tvuj prvni "
                "cil: vstup do farmy a kup prvni farmu za 250 minci; vydela "
                "3 mince za sekundu.",
            )
        elif self.screen == "game":
            self._show_tutorial(
                "classic.start",
                "Klikni na svoji figurku a potom na cilove pole. Poraz cerneho "
                "krale, abys vyhral.",
            )

    def _toggle_language(self) -> None:
        self.language = "en" if self.language == "cs" else "cs"
        save_language(self.language)
        pygame.display.set_caption(translate("Šachová bitva", self.language))
        self._rendered_text_cache.clear()

    def _toggle_hardcore(self, *, from_pause: bool = False) -> None:
        disabling = self.hardcore_enabled
        self.hardcore_enabled = not self.hardcore_enabled
        save_hardcore_enabled(self.hardcore_enabled)
        if not disabling:
            return

        return_screen = "pause" if from_pause else "menu"
        self._cancel_bot_turn()
        self.campaign_battle_active = False
        self.boss_battle_active = False
        self.boss_deployment_active = False
        self.war_deployment_active = False
        self.war_march_path = None
        self.war_march_king = None
        self.kingdom_game = None
        self.selected_level = 2
        self.tutorial_seen.clear()
        self.tutorial_queue.clear()
        self.tutorial_active = None
        self.tutorial_until = 0
        self._start_new_game(reset_campaign=True, abandon_current=from_pause)
        self.screen = return_screen

    def _advance_campaign_action(self, color: str) -> None:
        self.campaign.advance_day(color)
        if color == BLACK:
            self.campaign.bot_action(self.bot_difficulty)
        self._mark_campaign_dirty()

    def _collect_campaign_loot(self, color: str | None) -> None:
        if color != WHITE or self.game.last_loot_value <= 0:
            return
        faction = self.campaign.player
        loot_value = round(
            self.game.last_loot_value * max(1, faction.farms)
        )
        faction.coins += loot_value
        self.campaign.loot_respawns.append(
            self.campaign.realtime_seconds + PICKUP_RESPAWN_DELAY
        )
        self.status = f"Kral sebral {loot_value} zlata."
        self._show_tutorial(
            "campaign.coins",
            "Zlate mince sbiras kralem. Kazda se obnovi samostatne po jedne "
            "sekunde a odmena roste s poctem farem.",
        )
        self._mark_campaign_dirty()

    @staticmethod
    def _shop_name(kind: str) -> str:
        return {
            "farm": "Farma",
            "city": "Mesto",
            "armory": "Zbrojnice",
            "recruit": "Najem",
            "upgrade": "Vylepseni",
            "war": "Valka",
        }[kind]

    def _purchase_is_available(self, kind: str) -> bool:
        return self._purchase_block_reason(kind) is None

    def _purchase_block_reason(self, kind: str) -> str | None:
        player = self.campaign.player
        if kind == "farm":
            if player.farms >= FARM_LIMIT:
                return f"Uz mas maximalni pocet {FARM_LIMIT} farem."
            cost = self.campaign.farm_cost(WHITE)
            if player.coins < cost:
                return f"Farma stoji {cost} zlata, mas jen {player.coins}."
            return None
        if kind == "city":
            if player.city:
                return "Mesto uz vlastnis."
            if player.farms < 3:
                return f"Mesto vyzaduje 3 farmy; mas {player.farms}."
            if player.coins < CITY_COST:
                return f"Mesto stoji {CITY_COST} zlata, mas jen {player.coins}."
            return None
        if kind == "armory":
            if player.armory:
                return "Zbrojnici uz vlastnis."
            if not player.city:
                return "Zbrojnice vyzaduje nejdriv postavene mesto."
            if player.army_size < 3:
                return f"Zbrojnice vyzaduje 3 jednotky; mas {player.army_size}."
            if player.coins < ARMORY_COST:
                return f"Zbrojnice stoji {ARMORY_COST} zlata, mas jen {player.coins}."
            return None
        if kind.startswith("recruit_"):
            piece_kind = kind.removeprefix("recruit_")
            cost = RECRUIT_COSTS.get(piece_kind)
            if not player.city:
                return "Najem je dostupny az po postaveni mesta."
            if player.army_size >= 16:
                return "Armada uz ma maximalnich 16 jednotek."
            if cost is not None and player.coins < cost:
                return f"Figurka stoji {cost} zlata, mas jen {player.coins}."
            return None
        if kind.startswith("upgrade_"):
            piece_kind = kind.removeprefix("upgrade_")
            source = UPGRADE_SOURCES.get(piece_kind)
            if source is None:
                return "Tento upgrade neni dostupny."
            if not player.city:
                return "Vylepseni je dostupne az po postaveni mesta."
            if player.army[source] < 1:
                return f"K vylepseni na {self._piece_name(piece_kind)} potrebujes {self._piece_name(source)}."
            cost = ARMY_UPGRADE_COSTS[piece_kind]
            if player.coins < cost:
                return f"Vylepseni stoji {cost} zlata, mas jen {player.coins}."
            return None
        return "Tento nakup neni dostupny."

    def _building_visuals(
        self,
    ) -> dict[tuple[int, int], tuple[str, str, bool, int, int]]:
        result = {}
        for square, (owner, kind) in self.game.building_tiles.items():
            faction = self.campaign.faction(owner)
            owned = {
                "farm": faction.farm_sector,
                "city": faction.city,
                "armory": faction.armory,
            }[kind]
            progress = (
                faction.farms
                if kind == "farm"
                else min(12, faction.army_size)
                if kind == "city"
                else int(owned)
            )
            level = min(6, progress // 2)
            result[square] = (kind, owner, owned, progress, level)
        return result

    def _shop_screen_kind(self) -> str:
        if self.shop_menu in ("city", "recruit", "upgrade"):
            return "city"
        if self.shop_menu in ("armory", "war"):
            return "armory"
        return "farm"

    def _draw_shop_screen(self) -> None:
        screen_kind = self._shop_screen_kind()
        player = self.campaign.player
        titles = {"farm": "FARMA", "city": "MESTO", "armory": "ZBROJNICE"}
        palettes = {
            "farm": (67, 112, 67),
            "city": (66, 101, 132),
            "armory": (143, 75, 60),
        }
        self.surface.fill((24, 31, 29))
        pygame.draw.rect(self.surface, palettes[screen_kind], (0, 0, 1040, 108))
        self._text(titles[screen_kind], self.title_font, (255, 244, 214), (48, 34))
        self._text(
            f"Den {self.campaign.day}   Zlato {player.coins}",
            self.font,
            (255, 244, 214),
            (720, 42),
        )
        self._draw_button(self.shop_screen_back_button, "Zpet na mapu")

        building = pygame.Rect(48, 132, 324, 488)
        pygame.draw.rect(self.surface, (37, 46, 40), building, border_radius=8)
        cell_width = 82
        cell_height = 96
        origin_x = building.x + 38
        origin_y = building.y + 46
        owned = {
            "farm": player.farm_sector,
            "city": player.city,
            "armory": player.armory,
        }[screen_kind]
        base_color = palettes[screen_kind] if owned else tuple(
            max(35, component - 26) for component in palettes[screen_kind]
        )
        progress = (
            player.farms
            if screen_kind == "farm"
            else min(12, player.army_size)
            if screen_kind == "city"
            else int(owned)
        )
        level = min(6, progress // 2)
        for index in range(12):
            row, col = divmod(index, 3)
            tile = pygame.Rect(
                origin_x + col * cell_width,
                origin_y + row * cell_height,
                cell_width - 4,
                cell_height - 4,
            )
            active = owned and (
                index < progress or (screen_kind == "city" and index == 0)
            )
            improved = (
                active
                and index % 2 == 1
                and (index + 1) // 2 <= level
            )
            self.renderer._draw_building_tile(
                self.surface, tile, screen_kind, base_color, active, improved
            )
        if screen_kind == "farm":
            preview_status = f"{player.farms}/{FARM_LIMIT} farm | stupen {level}"
        elif screen_kind == "city":
            preview_status = f"{player.army_size} jednotek | stupen {level}"
        else:
            preview_status = "zbrojnice postavena" if owned else "volna plocha"
        self._center_text(
            preview_status,
            self.small_font,
            (255, 244, 214),
            (building.centerx, building.bottom - 58),
        )
        building_label = self.title_font.render(
            translate(titles[screen_kind], self.language),
            True,
            (255, 244, 214),
        )
        self.surface.blit(
            building_label,
            building_label.get_rect(center=(building.centerx, building.bottom - 18)),
        )

        pygame.draw.rect(self.surface, (34, 42, 38), (405, 132, 587, 488), border_radius=8)
        self._text(
            "Vlastnis" if owned else "Dosud nepostaveno",
            self.font,
            (171, 224, 160) if owned else (238, 194, 133),
            (440, 158),
        )
        buttons: dict[str, pygame.Rect] = {}
        if screen_kind == "farm":
            cost = self.campaign.farm_cost(WHITE)
            self._text(
                f"Vlastni farmy: {player.farms}   Prijem: +{player.farms * FARM_INCOME_PER_SECOND:g} zl/s",
                self.font,
                (232, 235, 224),
                (440, 220),
            )
            buttons["farm"] = pygame.Rect(440, 292, 510, 64)
            self._draw_button(
                buttons["farm"],
                (
                    f"Koupit sektor a prvni farmu - {cost} zl"
                    if not player.farm_sector
                    else f"Postavit dalsi farmu - {cost} zl"
                ),
                enabled=self._purchase_is_available("farm"),
            )
            self._text(
                f"Za kazde 2 farmy se v oblasti postavi sklad ({player.farms // 2}/6).",
                self.small_font,
                (190, 202, 191),
                (440, 382),
            )
            self._text(
                "Farmy generuji zlato prubezne v realnem case.",
                self.small_font,
                (190, 202, 191),
                (440, 406),
            )
        elif screen_kind == "city":
            if not player.city:
                buttons["city"] = pygame.Rect(440, 250, 510, 64)
                self._draw_button(
                    buttons["city"],
                    f"Postavit mesto - {CITY_COST} zl",
                    enabled=self._purchase_is_available("city"),
                )
                self._text("Mesto se odemkne po postaveni tri farem.", self.small_font, (190, 202, 191), (440, 338))
            else:
                self._text("Mesto verbuje pouze pesaky", self.small_font, (232, 235, 224), (440, 208))
                button = pygame.Rect(440, 234, 510, 56)
                buttons["recruit_P"] = button
                self._draw_button(
                    button,
                    f"Pesec x{player.army['P']} - {RECRUIT_COSTS['P']} zl",
                    enabled=self._purchase_is_available("recruit_P"),
                )
                self._text("Vylepsit pesaka", self.small_font, (232, 235, 224), (440, 420))
                for index, kind in enumerate(("N", "B", "R", "Q")):
                    source = UPGRADE_SOURCES[kind]
                    cost = ARMY_UPGRADE_COSTS[kind]
                    button = pygame.Rect(440 + (index % 2) * 260, 446 + (index // 2) * 58, 248, 48)
                    buttons[f"upgrade_{kind}"] = button
                    self._draw_button(
                        button,
                        f"{self._piece_name(source)} na {self._piece_name(kind)} - {cost} zl",
                        enabled=player.army[source] > 0 and player.coins >= cost,
                    )
        elif screen_kind == "armory":
            if not player.armory:
                buttons["armory"] = pygame.Rect(440, 250, 510, 64)
                self._draw_button(
                    buttons["armory"],
                    f"Postavit zbrojnici - {ARMORY_COST} zl",
                    enabled=self._purchase_is_available("armory"),
                )
                self._text("Zbrojnice vyzaduje mesto a tri jednotky.", self.small_font, (190, 202, 191), (440, 338))
            else:
                self._text("Oddil do dalsi bitvy", self.font, (232, 235, 224), (440, 222))
                buttons["deploy_minus"] = pygame.Rect(440, 278, 64, 52)
                buttons["deploy_plus"] = pygame.Rect(790, 278, 64, 52)
                self._draw_button(buttons["deploy_minus"], "-", enabled=True)
                self._draw_button(buttons["deploy_plus"], "+", enabled=True)
                self._center_text(str(self.deployment_limit), self.title_font, (255, 244, 214), (750, 304))
                ready = player.army_size > 0 and self.campaign.rival.armory and self.campaign.rival.army_size > 0
                buttons["war"] = pygame.Rect(440, 370, 510, 64)
                self._draw_button(buttons["war"], "Vyhlasit valku", enabled=ready)
                self._text(
                    f"Tvoje jednotky: {player.army_size}   Souper: {self.campaign.rival.army_size}",
                    self.small_font,
                    (190, 202, 191),
                    (440, 458),
                )
        self.shop_screen_buttons = buttons
        self._text(self.status, self.small_font, (216, 224, 214), (440, 576))
        self.shop_confirmation_buttons = {}
        if self.shop_confirmation is not None:
            overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            overlay.fill((8, 12, 10, 190))
            self.surface.blit(overlay, (0, 0))
            panel = pygame.Rect(245, 224, 550, 300)
            pygame.draw.rect(self.surface, (36, 45, 39), panel, border_radius=8)
            pygame.draw.rect(self.surface, (218, 188, 115), panel, width=2, border_radius=8)
            name = self._shop_name(self.shop_confirmation)
            self._center_text(
                f"Opravdu koupit: {name}?",
                self.title_font,
                (255, 244, 214),
                (panel.centerx, panel.y + 64),
            )
            price = {
                "farm": self.campaign.farm_cost(WHITE),
                "city": CITY_COST,
                "armory": ARMORY_COST,
            }[self.shop_confirmation]
            self._center_text(
                f"Cena {price} zlata | mas {player.coins}",
                self.font,
                (230, 224, 204),
                (panel.centerx, panel.y + 122),
            )
            reason = self._purchase_block_reason(self.shop_confirmation)
            self._center_text(
                reason or "Splnujes podminky pro nakup.",
                self.small_font,
                (244, 170, 142) if reason else (171, 224, 160),
                (panel.centerx, panel.y + 160),
            )
            self.shop_confirmation_buttons = {
                "yes": pygame.Rect(panel.x + 72, panel.y + 190, 170, 56),
                "no": pygame.Rect(panel.x + 308, panel.y + 190, 170, 56),
            }
            self._draw_button(
                self.shop_confirmation_buttons["yes"],
                "Ano",
                enabled=self._purchase_is_available(self.shop_confirmation),
            )
            self._draw_button(self.shop_confirmation_buttons["no"], "Ne")

    def _handle_shop_screen_click(self, position: tuple[int, int]) -> None:
        if self.shop_screen_back_button.collidepoint(position):
            self.shop_menu = None
            self.shop_confirmation = None
            return
        if not self._is_realtime_campaign() and (
            self._bot_is_thinking() or self.game.turn != WHITE
        ):
            return
        if self.shop_confirmation is not None:
            answer = next(
                (
                    name
                    for name, rect in self.shop_confirmation_buttons.items()
                    if rect.collidepoint(position)
                ),
                None,
            )
            if answer == "no":
                self.shop_confirmation = None
            elif answer == "yes":
                kind = self.shop_confirmation
                reason = self._purchase_block_reason(kind)
                if reason is not None:
                    self.status = reason
                    return
                bought = {
                    "farm": self.campaign.build_farm,
                    "city": self.campaign.build_city,
                    "armory": self.campaign.build_armory,
                }[kind](WHITE)
                if bought:
                    self.shop_confirmation = None
                    self._campaign_action_done(
                        {
                            "farm": "Farmarsky sektor a prvni farma postaveny.",
                            "city": "Mesto postaveno.",
                            "armory": "Zbrojnice postavena.",
                        }[kind]
                    )
            return
        action = next(
            (name for name, rect in self.shop_screen_buttons.items() if rect.collidepoint(position)),
            None,
        )
        if action is None:
            return
        if action == "deploy_minus":
            self.deployment_limit = max(1, self.deployment_limit - 1)
        elif action == "deploy_plus":
            self.deployment_limit = min(8, self.deployment_limit + 1)
        elif action == "war":
            self._advance_campaign_action(WHITE)
            self.shop_menu = None
            self._start_campaign_battle()
        elif action.startswith("recruit_"):
            kind = action.removeprefix("recruit_")
            if self.campaign.recruit(WHITE, kind):
                self._campaign_action_done(f"Najata figurka {self._piece_name(kind)}.")
            else:
                self.status = self._purchase_block_reason(action) or "Nabor se nepodaril."
        elif action.startswith("upgrade_"):
            kind = action.removeprefix("upgrade_")
            if self.campaign.upgrade_pawn(WHITE, kind):
                self._campaign_action_done(f"Pesec povysen na {self._piece_name(kind)}.")
            else:
                self.status = self._purchase_block_reason(action) or "Vylepseni se nepodarilo."
        elif action == "farm":
            if self.campaign.build_farm(WHITE):
                self._campaign_action_done(
                    "Farmarsky sektor a prvni farma postaveny."
                    if self.campaign.player.farms == 1
                    else "Farma postavena."
                )
            else:
                self.status = self._purchase_block_reason("farm") or "Farmu se nepodarilo postavit."
        elif action == "city":
            self.shop_confirmation = "city"
        elif action == "armory":
            self.shop_confirmation = "armory"

    def _activate_shop_card(self, kind: str) -> None:
        if self.shop_menu != kind:
            self.status = "Vejdi kralem na barevnou branu teto karty."
            return
        self._show_farm_purchase_tutorial(kind)
        if self.game.turn != WHITE or self._bot_is_thinking():
            return

        success = False
        message = "Na tento nakup nemas dost penez nebo nesplnujes podminky."
        if kind == "farm":
            success = self.campaign.build_farm(WHITE)
            message = "Farma postavena. Okamzite zvysuje prijem."
        elif kind == "city":
            success = self.campaign.build_city(WHITE)
            message = "Mesto postaveno."
        elif kind == "armory":
            success = self.campaign.build_armory(WHITE)
            message = "Zbrojnice postavena."
        elif kind == "recruit":
            success = self.campaign.recruit(WHITE, "P")
            message = "Pesec naverbovan."
        elif kind == "upgrade":
            source = UPGRADE_SOURCES["N"]
            success = self.campaign.upgrade_pawn(WHITE, "N")
            message = "Pesec vylepsen na kone."
        elif kind == "war":
            if (
                self.campaign.player.armory
                and self.campaign.player.army_size > 0
                and self.campaign.rival.armory
                and self.campaign.rival.army_size > 0
            ):
                self._advance_campaign_action(WHITE)
                self.shop_menu = None
                self._start_campaign_battle()
                return
            self.status = "Pro bitvu potrebujes dve zbrojnice a armady."
            return

        if success:
            self._campaign_action_done(message)
        else:
            self.status = message

    def _shop_card_info(
        self, kind: str
    ) -> tuple[str, str, bool, bool]:
        player = self.campaign.player
        if kind == "farm":
            return (
                f"Farma x{player.farms}" if player.farms else "Farma",
                f"{self.campaign.farm_cost(WHITE)} zl | +{FARM_INCOME_PER_SECOND:g} zl/s",
                player.coins >= self.campaign.farm_cost(WHITE)
                and player.farms < FARM_LIMIT,
                player.farms > 0,
            )
        if kind == "city":
            return (
                "Mesto",
                "Vlastni" if player.city else f"{CITY_COST} zl | potrebuje 3 farmy",
                player.city or (player.farms >= 3 and player.coins >= CITY_COST),
                player.city,
            )
        if kind == "armory":
            return (
                "Zbrojnice",
                "Vlastni" if player.armory else f"{ARMORY_COST} zl | potrebuje mesto",
                player.armory or (player.city and player.coins >= ARMORY_COST),
                player.armory,
            )
        if kind == "recruit":
            return (
                "Najem pesce",
                f"{RECRUIT_COSTS['P']} zl | potrebuje mesto",
                player.city and player.coins >= RECRUIT_COSTS["P"] and player.army_size < 16,
                False,
            )
        if kind == "upgrade":
            source = UPGRADE_SOURCES["N"]
            cost = ARMY_UPGRADE_COSTS["N"]
            return (
                "Pesec na kone",
                f"{cost} zl | potrebuje pesce",
                player.city and player.army["P"] > 0 and player.coins >= cost,
                False,
            )
        ready = (
            player.armory
            and player.army_size > 0
            and self.campaign.rival.armory
            and self.campaign.rival.army_size > 0
        )
        return "Vyhlasit valku", "Priprav armadu" if not ready else "Vstup do bitvy", ready, False

    def _draw_shop_cards(self) -> None:
        labels = {
            "farm": "F",
            "city": "M",
            "armory": "Z",
            "recruit": "+",
            "upgrade": "^",
            "war": "!",
        }
        for kind, rect in self.shop_cards.items():
            title, detail, affordable, owned = self._shop_card_info(kind)
            accessible = self.shop_menu == kind and self.game.turn == WHITE
            color = (
                (83, 142, 84)
                if owned
                else (205, 169, 99)
                if accessible and affordable
                else (87, 119, 91)
                if affordable
                else (83, 75, 69)
            )
            pygame.draw.rect(self.surface, (27, 34, 31), rect, border_radius=5)
            tile = rect.inflate(-3, -3)
            pygame.draw.rect(self.surface, color, tile, border_radius=4)
            icon = self.small_font.render(labels[kind], True, (255, 247, 220))
            self.surface.blit(icon, (rect.x + 8, rect.y + 5))
            text_color = (255, 248, 225) if accessible else (218, 222, 211)
            self._text(title, self.small_font, text_color, (rect.x + 34, rect.y + 4))
            self._text(detail, self.small_font, text_color, (rect.x + 34, rect.y + 25))
            indicator = "OK" if affordable else "-"
            indicator_image = self.small_font.render(
                indicator,
                True,
                (170, 245, 171) if affordable else (235, 157, 142),
            )
            self.surface.blit(
                indicator_image,
                indicator_image.get_rect(midright=(rect.right - 8, rect.centery)),
            )

    def _undo(self) -> None:
        if self.hardcore_enabled:
            self.status = "Hardcore: tahy nelze vracet."
            return
        if self.active_level == 1:
            return
        if self.active_level == 2 and not self.campaign_battle_active:
            self.status = "Ekonomicke tahy kampane nelze vratit."
            return
        self._cancel_bot_turn()
        if self.game.undo():
            if self.last_action_was_bot:
                self.game.undo()
            self.last_action_was_bot = False
            self.status = self.game.status()
            success = False
            message = ""
    def _schedule_bot_turn(self) -> None:
        if self._is_realtime_campaign():
            if self.game.winner() is not None or self.campaign.king_dead:
                return
            if self.bot_due_at is not None or self.bot_future is not None:
                return
            self.bot_due_at = pygame.time.get_ticks() + random.randint(
                OPPONENT_THINK_MIN_MS, OPPONENT_THINK_MAX_MS
            )
            self.status = "Souper rozviji kralovstvi..."
            return
        if self.game.turn != BLACK or self.game.winner() is not None:
            self.status = self.game.status()
            return
        self.bot_due_at = pygame.time.get_ticks() + random.randint(
            OPPONENT_THINK_MIN_MS, OPPONENT_THINK_MAX_MS
        )
        self.status = "Souper na tahu..."

    def _current_bot_difficulty(self) -> str:
        if not self.campaign_battle_active:
            return self.bot_difficulty
        levels = ("easy", "medium", "hard")
        if self.final_battle_active:
            return "hard"
        base_level = levels.index(self.bot_difficulty)
        progression = min(2, self.campaign.rival_battle_wins)
        return levels[min(len(levels) - 1, base_level + progression)]

    def _update_bot_turn(self) -> None:
        if self.screen != "game" or (
            self.active_level == 2
            and self.shop_menu is not None
            and not self.campaign_battle_active
        ):
            return
        realtime_campaign = self._is_realtime_campaign()
        if self.bot_due_at is not None:
            if pygame.time.get_ticks() < self.bot_due_at:
                return
            self.bot_due_at = None
            game_snapshot = deepcopy(self.game)
            if realtime_campaign:
                game_snapshot.turn = BLACK
            self.bot_future = self.bot_executor.submit(
                choose_move, game_snapshot, self._current_bot_difficulty()
            )

        if self.bot_future is None or not self.bot_future.done():
            return

        future = self.bot_future
        self.bot_future = None
        if (
            (not realtime_campaign and self.game.turn != BLACK)
            or self.game.winner() is not None
        ):
            return

        move = future.result()
        game_before = self.game
        moving_piece = self.game.piece_at(move.start) if move is not None else None
        if realtime_campaign:
            self.game.turn = BLACK
        team_health_before = self.game.team_health.copy()

        if move is None:
            if realtime_campaign:
                self.game.turn = WHITE
                self._advance_campaign_action(BLACK)
                self.status = "Souper rozviji kralovstvi..."
                self._schedule_bot_turn()
                return
            if self.game.pass_turn():
                self._play_move_sfx()
                self.status = self.game.status()
                self.last_action_was_bot = True
                return
            self.status = self.game.status()
            self.last_action_was_bot = False
            return

        if (
            realtime_campaign
            and moving_piece is not None
            and moving_piece.color == BLACK
            and moving_piece.kind == "K"
            and move.end in self._boss_chest_tiles()
        ):
            safe_moves = [
                candidate
                for candidate in self.game.all_legal_moves()
                if candidate.end not in self._boss_chest_tiles()
            ]
            if safe_moves:
                move = random.choice(safe_moves)
                moving_piece = self.game.piece_at(move.start)

        if not self.game.play(move):
            legal_moves = self.game.all_legal_moves()
            if not legal_moves:
                if realtime_campaign:
                    self.game.turn = WHITE
                    self._advance_campaign_action(BLACK)
                    self._schedule_bot_turn()
                else:
                    self.status = self.game.status()
                return
            move = random.choice(legal_moves)
            moving_piece = self.game.piece_at(move.start)
            if not self.game.play(move):
                if realtime_campaign:
                    self.game.turn = WHITE
                self.status = "Souper upravuje svuj tah..."
                self._schedule_bot_turn()
                return

        self._play_move_sfx()
        if moving_piece is not None:
            self.piece_move_animation = (
                moving_piece,
                move.start,
                move.end,
                pygame.time.get_ticks() / 1000,
            )
        if realtime_campaign:
            self.game.turn = WHITE
        self.status = self.game.status()
        self._record_damage_animations(team_health_before)
        if self.active_level == 1 and self._track_opening_position():
            return
        self.last_action_was_bot = True
        self._sync_campaign_progress()
        if self.game is not game_before:
            return
        if realtime_campaign:
            self._collect_campaign_loot(self.game.last_loot_color)
            self._advance_campaign_action(BLACK)
            self._schedule_bot_turn()
            return
        if self.campaign_battle_active and self.game.winner() is not None:
            self._resolve_campaign_battle()

    def _sync_campaign_progress(self) -> None:
        if self.active_level == 1 and self.screen == "game":
            winner = self.game.winner()
            if winner is not None:
                outcome = (
                    "draw"
                    if winner == "draw"
                    else "win"
                    if winner == WHITE
                    else "loss"
                )
                self._finish_opening_match(outcome)

    def _advance_campaign_intro_zoom(self) -> None:
        if self.campaign_intro_zoom_started_at is None:
            return
        elapsed = pygame.time.get_ticks() - self.campaign_intro_zoom_started_at
        progress = min(1.0, max(0.0, elapsed / CAMPAIGN_INTRO_ZOOM_DURATION_MS))
        eased = progress * progress * progress * (
            progress * (progress * 6 - 15) + 10
        )
        self.zoom = CAMPAIGN_INTRO_START_ZOOM - (
            CAMPAIGN_INTRO_START_ZOOM - 1.0
        ) * eased
        self._follow_king_camera()
        if progress >= 1.0:
            self.campaign_intro_zoom_started_at = None
            self.zoom = 1.0
            self.camera_offset = (0, 0)
            self.camera_target_offset = (0, 0)

    def _cancel_bot_turn(self) -> None:
        self.bot_due_at = None
        if self.bot_future is not None:
            self.bot_future.cancel()
            self.bot_future = None

    def _bot_is_thinking(self) -> bool:
        return self.bot_due_at is not None or self.bot_future is not None

    def _is_realtime_campaign(self) -> bool:
        return self.active_level == 2 and not self.campaign_battle_active

    def _record_damage_animations(
        self, team_health_before: dict[str, int]
    ) -> None:
        started_at = pygame.time.get_ticks() / 1000
        for color in (WHITE, BLACK):
            before = team_health_before[color]
            after = self.game.team_health[color]
            if before != after:
                self.team_health_animations[color] = (before, after, started_at)
        if self.game.last_damage or any(
            self.game.team_health[color] < team_health_before[color]
            for color in (WHITE, BLACK)
        ):
            self._play_damage_sfx()

        damage_by_square: dict[tuple[int, int], int] = {}
        for square, damage in self.game.last_damage:
            damage_by_square[square] = damage_by_square.get(square, 0) + damage
            self.damage_popups.append((square, damage, started_at))

        for square, damage in damage_by_square.items():
            piece = self.game.piece_at(square)
            if piece is not None and (piece.health or 0) + damage <= piece.max_health:
                self.piece_health_animations[square] = (
                    (piece.health or 0) + damage,
                    piece.health or 0,
                    started_at,
                )

    @staticmethod
    def _animated_health(
        animation: tuple[int, int, float] | None,
        fallback: int,
        now: float,
    ) -> int:
        if animation is None:
            return fallback
        start, end, started_at = animation
        progress = min(1.0, max(0.0, (now - started_at) / 0.45))
        eased = progress * progress * (3 - 2 * progress)
        return round(start + (end - start) * eased)

    def _clear_selection(self) -> None:
        self.selected = None
        self.legal_moves = []
        self.pending_promotion = []

    def _achievement_progress(self) -> dict[str, tuple[int, int]]:
        accessible_squares = self._accessible_campaign_squares()
        visited_squares = set(self.campaign.visited_campaign_squares)
        return {
            "baller": (
                min(12, self.campaign.player.army["Q"]),
                12,
            ),
            "businessman": (
                min(FARM_LIMIT, self.campaign.player.farms),
                FARM_LIMIT,
            ),
            "zabijak": (
                min(10, self.campaign.raiders_defeated_total),
                10,
            ),
            "alchemist": (
                min(10, self.campaign.king_potion_heals),
                10,
            ),
            "hot_destinations": (
                len(visited_squares & accessible_squares),
                len(accessible_squares),
            ),
        }

    def _campaign_navigation_board(self) -> ChessGame:
        if self.game.campaign_map:
            return self.game
        if self.kingdom_game is not None:
            return self.kingdom_game
        if self._campaign_navigation_game is None:
            self._campaign_navigation_game = self._create_level_game(2)
        return self._campaign_navigation_game

    def _accessible_campaign_squares(self) -> set[tuple[int, int]]:
        board = self._campaign_navigation_board()
        inaccessible = set(board.building_tiles)
        inaccessible.update(
            square
            for square in board.shop_tiles
            if square[0] < board.board_size // 2
        )
        return {
            (row, col)
            for row in range(board.board_size)
            for col in range(board.board_size)
            if (row, col) not in inaccessible
        }

    def _record_campaign_square(
        self, square: tuple[int, int] | None
    ) -> None:
        if (
            square is not None
            and square in self._accessible_campaign_squares()
            and square not in self.campaign.visited_campaign_squares
        ):
            self.campaign.visited_campaign_squares.append(square)
            self._mark_campaign_dirty()

    def _check_achievements(self) -> None:
        progress = self._achievement_progress()
        now = pygame.time.get_ticks()
        for achievement_id, _, _ in ACHIEVEMENTS:
            current, target = progress[achievement_id]
            if (
                current < target
                or achievement_id in self.campaign.unlocked_achievements
            ):
                continue
            self.campaign.unlocked_achievements.append(achievement_id)
            self.campaign.player.coins += ACHIEVEMENT_REWARD
            self.achievement_notifications.append((achievement_id, now))
            self._play_achievement_sfx()
            self._mark_campaign_dirty()

    def _draw_achievements(self) -> None:
        self.surface.fill((24, 31, 29))
        self._center_text(
            "ACHIEVEMENTS",
            self.title_font,
            (255, 232, 177),
            (520, 78),
        )
        self._center_text(
            "Stiskni L nebo ESC pro navrat",
            self.small_font,
            (190, 199, 188),
            (520, 125),
        )

        progress = self._achievement_progress()
        unlocked = set(self.campaign.unlocked_achievements)
        for index, (achievement_id, name, description) in enumerate(ACHIEVEMENTS):
            card = pygame.Rect(130, 154 + index * 104, 780, 88)
            complete = achievement_id in unlocked
            pygame.draw.rect(
                self.surface,
                (55, 75, 61) if complete else (39, 48, 44),
                card,
                border_radius=10,
            )
            pygame.draw.rect(
                self.surface,
                (214, 177, 104) if complete else (82, 94, 85),
                card,
                width=2,
                border_radius=10,
            )
            current, target = progress[achievement_id]
            self._text(
                name,
                self.font,
                (255, 224, 143) if complete else (232, 235, 224),
                (card.x + 18, card.y + 9),
            )
            self._text(
                description,
                self.small_font,
                (218, 223, 212),
                (card.x + 210, card.y + 12),
            )
            self._text(
                f"Postup: {current}/{target}",
                self.small_font,
                (168, 214, 170) if complete else (190, 199, 188),
                (card.x + 18, card.y + 54),
            )
            self._text(
                "Splneno! +5000 zlata" if complete else "Odměna: 5000 zlata",
                self.small_font,
                (255, 224, 143) if complete else (190, 199, 188),
                (card.x + 390, card.y + 54),
            )

        self._draw_menu_button(self.achievements_back_button, "Zpet")

    def _draw_achievement_notifications(self) -> None:
        now = pygame.time.get_ticks()
        self.achievement_notifications = [
            (achievement_id, started_at)
            for achievement_id, started_at in self.achievement_notifications
            if now - started_at < ACHIEVEMENT_NOTIFICATION_DURATION_MS
        ]
        for index, (achievement_id, started_at) in enumerate(
            self.achievement_notifications[-len(ACHIEVEMENTS):]
        ):
            elapsed = now - started_at
            entrance = min(1.0, max(0.0, elapsed / 380))
            entrance = entrance * entrance * (3 - 2 * entrance)
            remaining = ACHIEVEMENT_NOTIFICATION_DURATION_MS - elapsed
            exit_progress = min(1.0, max(0.0, remaining / 450))
            exit_progress = exit_progress * exit_progress * (
                3 - 2 * exit_progress
            )
            slide = min(entrance, exit_progress)
            rect = pygame.Rect(
                round(1040 - 350 * slide), 18 + index * 72, 330, 62
            )
            toast = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                toast, (38, 55, 43, 240), toast.get_rect(), border_radius=8
            )
            pygame.draw.rect(
                toast,
                (224, 190, 119, 255),
                toast.get_rect(),
                width=2,
                border_radius=8,
            )
            badge_center = (30, 31)
            pygame.draw.circle(toast, (34, 40, 34), badge_center, 22)
            pygame.draw.circle(toast, (228, 185, 88), badge_center, 18)
            pygame.draw.circle(toast, (255, 234, 151), badge_center, 13)
            pygame.draw.polygon(
                toast,
                (133, 91, 39),
                (
                    (30, 18),
                    (33, 27),
                    (42, 27),
                    (35, 32),
                    (38, 41),
                    (30, 35),
                    (22, 41),
                    (25, 32),
                    (18, 27),
                    (27, 27),
                ),
            )
            name = next(
                name
                for item_id, name, _ in ACHIEVEMENTS
                if item_id == achievement_id
            )
            title = translate("Achievement odemcen", self.language)
            reward = translate("+5000 zlata", self.language)
            toast.blit(
                self._cached_text(title, self.small_font, (255, 232, 177)),
                (54, 7),
            )
            toast.blit(
                self._cached_text(
                    name, self.small_font, (255, 249, 220)
                ),
                (54, 25),
            )
            toast.blit(
                self._cached_text(
                    reward, self.small_font, (220, 235, 214)
                ),
                (54, 42),
            )
            toast.set_alpha(round(255 * slide))
            self.surface.blit(toast, rect)

    def _draw(self) -> None:
        now = pygame.time.get_ticks() / 1000
        self.piece_health_animations = {
            square: animation
            for square, animation in self.piece_health_animations.items()
            if now - animation[2] < 0.45
        }
        self.team_health_animations = {
            color: animation
            for color, animation in self.team_health_animations.items()
            if now - animation[2] < 0.45
        }
        self.damage_popups = [
            popup for popup in self.damage_popups if now - popup[2] < 0.65
        ]
        if self.screen == "menu":
            self._draw_menu()
            self._draw_tutorial()
            return
        if self.screen == "achievements":
            self._draw_achievements()
            return
        if self.screen == "death":
            self._draw_death_screen()
            self._draw_king_banter()
            return
        if self.screen in ("opening_win", "opening_loss", "opening_draw"):
            self._draw_opening_result(now)
            return
        if self.screen == "war_victory":
            self._draw_war_victory(now)
            return

        if self.boss_deployment_active:
            self._draw_boss_deployment()
            self._draw_king_banter()
            return
        if self.war_deployment_active:
            self._draw_war_deployment()
            return

        if self.shop_menu is not None and self.active_level == 2 and not self.campaign_battle_active:
            self.surface.fill((24, 31, 29))
            self._draw_shop_screen()
            self._draw_tutorial()
            self._draw_king_banter()
            if self.screen == "pause":
                self._draw_pause_menu()
            return

        if (
            self.piece_move_animation is not None
            and now - self.piece_move_animation[3]
            >= MOVE_ANIMATION_DURATION_SECONDS
        ):
            self.piece_move_animation = None

        self.surface.fill((28, 36, 34))
        square_size, board_origin = self._board_layout()
        self.renderer.draw(
            self.surface,
            self.game,
            self.selected,
            self.legal_moves,
            None,
            now,
            self.game.mines,
            self.piece_health_animations,
            self.damage_popups,
            square_size=square_size,
            board_origin=board_origin,
            loot=self.game.loot,
            shop_tiles=self.game.shop_tiles,
            buildings=self._building_visuals(),
            boss_chest_tiles=self._boss_chest_tiles(),
            piece_animation=self.piece_move_animation,
            piece_animation_duration=MOVE_ANIMATION_DURATION_SECONDS,
            viewport_rect=(
                self._campaign_map_viewport()
                if self.active_level == 2 and not self.campaign_battle_active
                else pygame.Rect((0, 0), WINDOW_SIZE)
                if self.active_level == 2
                else None
            ),
            raiders=[
                (raider.row, raider.col) for raider in self.campaign.raiders
            ]
            if self.active_level == 2 and not self.campaign_battle_active
            else [],
            potions=set(self.campaign.potions)
            if self.active_level == 2 and not self.campaign_battle_active
            else set(),
            king_attack_progress=(
                1.0 - self.campaign.king_raider_kill_cooldown
                if (
                    self.active_level == 2
                    and not self.campaign_battle_active
                    and self.campaign.king_raider_kill_cooldown > 0
                )
                else None
            ),
            language=self.language,
            king_health_ratio=(
                self._animated_health(
                    self.team_health_animations.get(WHITE),
                    self.game.team_health[WHITE],
                    now,
                )
                / max(1, self.game.team_health_max[WHITE])
                if self.active_level == 2 and not self.campaign_battle_active
                else None
            ),
            hidden_piece_square=(
                self.war_march_path[0]
                if self.war_march_path is not None
                else None
            ),
        )
        self._draw_war_march()
        self._sync_campaign_progress()
        if self.active_level == 2:
            self._draw_campaign_hud()
        else:
            self._draw_sidebar()
        if self.screen != "pause":
            self._draw_tutorial()
        if self.pending_promotion:
            self._draw_promotion_prompt()
        if self.screen != "pause":
            self._draw_king_banter()
        if (
            self.active_level == 2
            and not self.campaign_battle_active
            and self.shop_menu is None
        ):
            self._draw_diplomacy_chat()
        if self.screen == "pause":
            self._draw_pause_menu()

    def _draw_diplomacy_chat(self) -> None:
        self.surface.blit(self.diplomacy_panel_surface, self.diplomacy_panel_rect)
        self._center_text(
            "Diplomacie",
            self.small_font,
            (255, 232, 177),
            (self.diplomacy_panel_rect.centerx, 99),
        )
        trust = self.campaign.diplomacy_trust
        trust_label = (
            "Válka vyhrána"
            if self.campaign.rival_war_won
            else "Válka vyhlášena"
            if self.campaign.rival_war_declared
            else f"Důvěra: {trust:+d}/10"
        )
        trust_color = (
            (232, 112, 91)
            if self.campaign.rival_war_declared or trust < 0
            else (153, 209, 147)
        )
        self._center_text(
            trust_label,
            self.diplomacy_font,
            trust_color,
            (self.diplomacy_panel_rect.centerx, 122),
        )
        meter = pygame.Rect(20, 135, 196, 5)
        pygame.draw.rect(self.surface, (59, 67, 61), meter, border_radius=3)
        meter_fill = meter.copy()
        meter_fill.width = round(meter.width * (trust + 10) / 20)
        if meter_fill.width:
            pygame.draw.rect(
                self.surface,
                (195, 94, 77) if trust < 0 else (115, 174, 112),
                meter_fill,
                border_radius=3,
            )

        messages = self.campaign.diplomacy_history[-2:]
        if self.diplomacy_reply_text is not None:
            progress = min(
                1.0,
                self.diplomacy_reply_elapsed_ms
                / max(1, self.diplomacy_reply_duration_ms),
            )
            character_count = round(len(self.diplomacy_reply_text) * progress)
            typed_reply = self.diplomacy_reply_text[:character_count]
            if pygame.time.get_ticks() // 350 % 2 == 0:
                typed_reply += "|"
            messages = [
                *self.campaign.diplomacy_history[-1:],
                ("king", typed_reply),
            ]
        if not messages:
            messages = [
                (
                    "king",
                    "Cizí králi, co mi nabízíš? Mír, obchod, nebo další hrozby?",
                )
            ]
        cursor_y = 358
        for speaker, message in reversed(messages):
            lines = self._wrap_diplomacy_text(
                translate(message, self.language), self.diplomacy_font, 190
            )
            message_height = 15 + len(lines) * 15 + 4
            cursor_y -= message_height
            speaker_label = "Ty" if speaker == "player" else "Král"
            speaker_color = (
                (163, 199, 233)
                if speaker == "player"
                else (255, 216, 139)
            )
            self._text(
                speaker_label,
                self.diplomacy_bold_font,
                speaker_color,
                (18, cursor_y),
            )
            for line_index, line in enumerate(lines):
                self._text(
                    line,
                    self.diplomacy_font,
                    (231, 234, 224),
                    (18, cursor_y + 15 + line_index * 15),
                )

        self._center_text(
            "Válka je vyhraná."
            if self.campaign.rival_war_won
            else "Jsi ve válce."
            if self.campaign.rival_war_declared
            else "Král píše..."
            if self.diplomacy_reply_text is not None
            else "Vyber odpověď:",
            self.diplomacy_font,
            (205, 212, 201),
            (self.diplomacy_panel_rect.centerx, 377),
        )
        choices = (
            ("", "", "", "")
            if self.campaign.rival_war_won
            else ("Jít do zbrojnice", "", "", "")
            if self.campaign.rival_war_declared
            else (
                "Nabízím mír",
                "Nabízím obchod",
                "Žádám o příměří",
                "Vyhrožuji válkou",
            )
        )
        for label, rect in zip(choices, self.diplomacy_choice_buttons):
            if not label:
                continue
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            color = (
                (170, 119, 65)
                if label == "Vyhrožuji válkou" and hovered
                else (133, 75, 63)
                if label == "Vyhrožuji válkou"
                else (205, 169, 99)
                if hovered
                else (75, 91, 82)
            )
            if self.diplomacy_reply_text is not None:
                color = (54, 64, 56)
            pygame.draw.rect(self.surface, color, rect, border_radius=7)
            self._center_text(
                label,
                self.diplomacy_font,
                (245, 242, 226),
                rect.center,
            )

    def _draw_war_march(self) -> None:
        path = self.war_march_path
        king = self.war_march_king
        if not path or king is None:
            return

        progress = min(
            1.0,
            self.war_march_elapsed_ms / WAR_KING_MARCH_DURATION_MS,
        )
        step_position = progress * max(0, len(path) - 1)
        step_index = min(int(step_position), len(path) - 1)
        step_progress = step_position - step_index
        row, col = path[step_index]
        if step_index + 1 < len(path):
            next_row, next_col = path[step_index + 1]
            row += (next_row - row) * step_progress
            col += (next_col - col) * step_progress
        square_size, (origin_x, origin_y) = self._board_layout()
        center = (
            round(origin_x + (col + 0.5) * square_size),
            round(origin_y + (row + 0.5) * square_size),
        )
        pygame.draw.circle(
            self.surface,
            (244, 199, 107),
            center,
            max(6, square_size // 2 - 2),
            width=2,
        )
        self.renderer.draw_piece_sprite(
            self.surface,
            pygame.Rect(
                center[0] - square_size // 2 + 2,
                center[1] - square_size // 2 + 2,
                square_size - 4,
                square_size - 4,
            ),
            king.kind,
            king.color,
        )
        self._center_text(
            "Král míří do zbrojnice",
            self.diplomacy_bold_font,
            (255, 232, 177),
            (self._campaign_map_viewport().centerx, 92),
        )

    @staticmethod
    def _wrap_diplomacy_text(
        text: str, font: pygame.font.Font, max_width: int
    ) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and font.size(candidate)[0] > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def _draw_boss_deployment(self) -> None:
        self.surface.fill((24, 31, 29))
        self._center_text(
            "TRUHLA S POKLADEM",
            self.title_font,
            (255, 224, 143),
            (520, 60),
        )
        self._center_text(
            "Vyber az 4 vlastni figurky. Sestavu bossu uvidis az po stisku Hrat.",
            self.small_font,
            (220, 225, 214),
            (520, 101),
        )

        board_left, board_top, tile_size = 54, 142, 56
        preview = pygame.Rect(board_left, board_top, tile_size * 6, tile_size * 6)
        for row in range(6):
            for col in range(6):
                rect = pygame.Rect(
                    board_left + col * tile_size,
                    board_top + row * tile_size,
                    tile_size,
                    tile_size,
                )
                color = (110, 133, 112) if (row + col) % 2 else (190, 184, 154)
                pygame.draw.rect(self.surface, color, rect)
                pygame.draw.rect(self.surface, (39, 48, 41), rect, width=1)
        self._draw_preview_piece((0, 3), "K", BLACK, board_left, board_top, tile_size)
        self._draw_preview_piece((5, 3), "K", WHITE, board_left, board_top, tile_size)
        self._center_text(
            "?",
            self.title_font,
            (244, 190, 79),
            (preview.centerx, board_top + tile_size * 2),
        )

        selected_kinds = [
            kind
            for kind in ARMY_KINDS
            for _ in range(self.boss_deployment[kind])
        ]
        for index, kind in enumerate(selected_kinds):
            row, col = 4 - index // 3, 1 + index % 3
            self._draw_preview_piece(
                (row, col), kind, WHITE, board_left, board_top, tile_size
            )

        panel = pygame.Rect(455, 135, 540, 520)
        pygame.draw.rect(self.surface, (37, 46, 40), panel, border_radius=10)
        total = sum(self.boss_deployment.values())
        self._text(
            f"Nasazeno: {total}/4",
            self.font,
            (255, 224, 143),
            (500, 145),
        )
        names = {
            "P": "Pesec",
            "N": "Kun",
            "B": "Strelec",
            "R": "Vez",
            "Q": "Dama",
        }
        for index, kind in enumerate(ARMY_KINDS):
            y = 177 + index * 66
            self._text(
                f"{names[kind]}: {self.boss_deployment[kind]}/{self.campaign.player.army[kind]}",
                self.font,
                (232, 235, 224),
                (500, y + 6),
            )
            self._draw_button(
                self.boss_deployment_buttons[kind]["minus"],
                "-",
                enabled=self.boss_deployment[kind] > 0,
            )
            can_add = (
                total < 4
                and self.boss_deployment[kind] < self.campaign.player.army[kind]
            )
            self._draw_button(
                self.boss_deployment_buttons[kind]["plus"],
                "+",
                enabled=can_add,
            )
            total = sum(self.boss_deployment.values())

        self._draw_button(
            self.boss_start_button,
            "HRAT - vstoupit do souboje 6 x 6",
            enabled=sum(self.boss_deployment.values()) > 0,
        )
        self._draw_button(self.boss_cancel_button, "Zpet ke kralovstvi")
        self._center_text(
            self.status,
            self.small_font,
            (232, 202, 151),
            (520, 703),
        )

    def _draw_war_deployment(self) -> None:
        self.surface.fill((24, 31, 29))
        self._center_text(
            "ZÁVĚREČNÁ BITVA" if self.campaign.final_battle_pending else "MOBILIZACE KRÁLOVSTVÍ",
            self.title_font,
            (255, 224, 143),
            (520, 60),
        )
        self._center_text(
            (
                "Vyber armádu. Černý král nasazuje 2 věže, 2 jezdce, 2 střelce a dámu."
                if self.campaign.final_battle_pending
                else "Vyber až 8 figurek ze své městské armády."
            ),
            self.small_font,
            (220, 225, 214),
            (520, 101),
        )

        final_battle = self.campaign.final_battle_pending
        preview_size = 8 if final_battle else 6
        board_left, board_top = 54, 132
        tile_size = 44 if final_battle else 56
        for row in range(preview_size):
            for col in range(preview_size):
                rect = pygame.Rect(
                    board_left + col * tile_size,
                    board_top + row * tile_size,
                    tile_size,
                    tile_size,
                )
                color = (110, 133, 112) if (row + col) % 2 else (190, 184, 154)
                pygame.draw.rect(self.surface, color, rect)
                pygame.draw.rect(self.surface, (39, 48, 41), rect, width=1)
        if final_battle:
            self._draw_preview_piece((1, 4), "K", BLACK, board_left, board_top, tile_size)
            self._draw_preview_piece((6, 4), "K", WHITE, board_left, board_top, tile_size)
            black_lineup = (
                ((2, 0), "R"),
                ((2, 1), "N"),
                ((2, 2), "B"),
                ((2, 3), "Q"),
                ((2, 5), "B"),
                ((2, 6), "N"),
                ((2, 7), "R"),
            )
            for square, kind in black_lineup:
                self._draw_preview_piece(
                    square, kind, BLACK, board_left, board_top, tile_size
                )
        else:
            self._draw_preview_piece((0, 3), "K", BLACK, board_left, board_top, tile_size)
            self._draw_preview_piece((5, 3), "K", WHITE, board_left, board_top, tile_size)
        selected_kinds = [
            kind
            for kind in ARMY_KINDS
            for _ in range(self.boss_deployment[kind])
        ]
        for index, kind in enumerate(selected_kinds):
            row, col = (
                (5 - index // 4, index % 4)
                if final_battle
                else (4 - index // 3, 1 + index % 3)
            )
            self._draw_preview_piece(
                (row, col),
                kind,
                WHITE,
                board_left,
                board_top,
                tile_size,
            )

        panel = pygame.Rect(455, 135, 540, 520)
        pygame.draw.rect(self.surface, (37, 46, 40), panel, border_radius=10)
        total = sum(self.boss_deployment.values())
        self._text(
            f"Nasazeno: {total}/{self.war_deployment_limit}",
            self.font,
            (255, 224, 143),
            (500, 145),
        )
        names = {
            "P": "Pesec",
            "N": "Kun",
            "B": "Strelec",
            "R": "Vez",
            "Q": "Dama",
        }
        for index, kind in enumerate(ARMY_KINDS):
            y = 177 + index * 66
            self._text(
                f"{names[kind]}: {self.boss_deployment[kind]}/"
                f"{self.campaign.player.army[kind]}",
                self.font,
                (232, 235, 224),
                (500, y + 6),
            )
            self._draw_button(
                self.boss_deployment_buttons[kind]["minus"],
                "-",
                enabled=self.boss_deployment[kind] > 0,
            )
            self._draw_button(
                self.boss_deployment_buttons[kind]["plus"],
                "+",
                enabled=(
                    total < self.war_deployment_limit
                    and self.boss_deployment[kind]
                    < self.campaign.player.army[kind]
                ),
            )
            total = sum(self.boss_deployment.values())

        self._draw_button(
            self.boss_start_button,
            "ZAHÁJIT FINÁLNÍ BITVU"
            if final_battle
            else "ZAHÁJIT ZÁVĚREČNOU BITVU",
            enabled=sum(self.boss_deployment.values()) > 0,
        )
        self._draw_button(
            self.boss_cancel_button,
            "Nelze ustoupit" if final_battle else "Zpět ke království",
            enabled=not final_battle,
        )
        self._center_text(
            self.status,
            self.small_font,
            (232, 202, 151),
            (520, 703),
        )

    def _draw_death_screen(self) -> None:
        self.surface.fill((20, 25, 23))
        panel = pygame.Rect(215, 205, 610, 390)
        pygame.draw.rect(self.surface, (42, 49, 43), panel, border_radius=14)
        pygame.draw.rect(self.surface, (156, 73, 61), panel, width=3, border_radius=14)
        self._center_text(
            "KRAL PADL",
            self.title_font,
            (239, 143, 124),
            (520, 280),
        )
        self._center_text(
            self.campaign.king_death_reason or "Kral zemrel.",
            self.font,
            (239, 229, 209),
            (520, 345),
        )
        if self.hardcore_enabled:
            self._center_text(
                "Hardcore: kral je mrtev. Kralovstvi uz nelze obnovit.",
                self.small_font,
                (239, 143, 124),
                (520, 398),
            )
            self.death_menu_button.y = 480
        else:
            self._center_text(
                "Zkus to znovu, nebo se vrat do hlavniho menu.",
                self.small_font,
                (195, 204, 193),
                (520, 398),
            )
            self._draw_menu_button(self.death_retry_button, "Zkusit znovu")
            self.death_menu_button.y = 546
        self._draw_menu_button(self.death_menu_button, "Hlavni menu")

    def _draw_opening_result(self, now: float) -> None:
        elapsed = (
            0
            if self.opening_transition_started_at is None
            else pygame.time.get_ticks() - self.opening_transition_started_at
        )
        progress = min(1.0, elapsed / OPENING_RESULT_DURATION_MS)
        self.surface.fill((18, 27, 29))
        width, height = self.surface.get_size()
        center = (width // 2, height // 2)
        if self.opening_transition_outcome == "win":
            radius = round(85 + 42 * math.sin(now * 8))
            pygame.draw.circle(self.surface, (120, 91, 188), center, radius, 3)
            pygame.draw.circle(
                self.surface,
                (206, 174, 255),
                center,
                round(radius * 0.68),
                2,
            )
            piece_size = round(190 - 145 * progress)
            king_surface = pygame.Surface(
                (piece_size, piece_size), pygame.SRCALPHA
            )
            self.renderer.draw_piece_sprite(
                king_surface,
                pygame.Rect(0, 0, piece_size, piece_size),
                "K",
                BLACK,
            )
            self.surface.blit(king_surface, king_surface.get_rect(center=center))
            self._center_text(
                "VYHRÁLI JSTE ÚVODNÍ BITVU",
                self.title_font,
                (255, 229, 158),
                (center[0], 112),
            )
            self._center_text(
                "Černý král se magií mění v šachovou figurku...",
                self.font,
                (224, 210, 250),
                (center[0], height - 116),
            )
        elif self.opening_transition_outcome == "loss":
            self.renderer.draw_piece_sprite(
                self.surface,
                pygame.Rect(center[0] - 80, center[1] - 80, 160, 160),
                "K",
                BLACK,
            )
            self._center_text(
                "ČERNÝ KRÁL VYHRÁL",
                self.title_font,
                (239, 143, 124),
                (center[0], 128),
            )
            self._center_text(
                "Tohle byla tvoje nejlepší strategie? Zkus to znovu.",
                self.font,
                (245, 232, 196),
                (center[0], height - 116),
            )
        else:
            self._center_text(
                "REMÍZA",
                self.title_font,
                (255, 229, 158),
                (center[0], center[1] - 20),
            )
            self._center_text(
                "Úvodní bitva se znovu začíná.",
                self.font,
                (224, 229, 218),
                (center[0], center[1] + 30),
            )
        self._center_text(
            "Klikni nebo stiskni Enter pro pokračování",
            self.small_font,
            (181, 192, 181),
            (center[0], height - 48),
        )

    def _draw_war_victory(self, now: float) -> None:
        started_at = self.war_victory_started_at
        elapsed_ms = (
            0 if started_at is None else pygame.time.get_ticks() - started_at
        )
        width, height = self.surface.get_size()
        self.surface.fill((18, 27, 29))
        pygame.draw.rect(
            self.surface,
            (27, 43, 43),
            pygame.Rect(0, height // 2, width, height // 2),
        )
        pygame.draw.line(
            self.surface,
            (140, 116, 75),
            (0, height - 112),
            (width, height - 112),
            3,
        )

        if elapsed_ms < WAR_VICTORY_SURRENDER_DURATION_MS:
            progress = min(
                1.0,
                elapsed_ms / WAR_VICTORY_SURRENDER_DURATION_MS,
            )
            pole_x = width // 2 + 60
            pole_top = round(height * (0.49 - 0.12 * progress))
            pole_bottom = height - 112
            pygame.draw.line(
                self.surface,
                (180, 155, 103),
                (pole_x, pole_top),
                (pole_x, pole_bottom),
                8,
            )
            wave = round(math.sin(now * 5) * 9)
            flag_points = [
                (pole_x + 4, pole_top + 8),
                (pole_x + 112, pole_top + 18 + wave),
                (pole_x + 96, pole_top + 68 + wave),
                (pole_x + 4, pole_top + 58),
            ]
            pygame.draw.polygon(self.surface, (244, 242, 224), flag_points)
            pygame.draw.polygon(
                self.surface,
                (201, 190, 157),
                flag_points,
                width=3,
            )

            king_size = round(160 + 10 * progress)
            king_surface = pygame.Surface(
                (king_size, king_size),
                pygame.SRCALPHA,
            )
            self.renderer.draw_piece_sprite(
                king_surface,
                pygame.Rect(8, 8, king_size - 16, king_size - 16),
                "K",
                BLACK,
            )
            bowed_king = pygame.transform.rotozoom(
                king_surface,
                -8 * progress,
                1,
            )
            self.surface.blit(
                bowed_king,
                bowed_king.get_rect(
                    midbottom=(width // 2 - 75, height - 112)
                ),
            )
            surrender_text = (
                "Černý král tě porazil"
                if self.war_victory_is_final_battle and not self.war_victory_won
                else "Černý král se vzdává"
            )
            self._center_text(
                surrender_text,
                self.title_font,
                (245, 232, 196),
                (width // 2, 112),
            )
            return

        pygame.draw.rect(
            self.surface,
            (204, 171, 103),
            pygame.Rect(48, 48, width - 96, height - 96),
            width=3,
            border_radius=18,
        )
        victory_font = pygame.font.SysFont("consolas", 76, bold=True)
        ending_font = pygame.font.SysFont("consolas", 48, bold=True)
        if self.war_victory_is_final_battle:
            title = "VYHRÁLI JSTE" if self.war_victory_won else "PORÁŽKA"
            subtitle = (
                "KRÁLOVSTVÍ JE VAŠE"
                if self.war_victory_won
                else "ČERNÝ KRÁL: ZKUS TO ZNOVU"
            )
            prompt = (
                "Stiskni Enter pro hlavní menu"
                if self.war_victory_won
                else "Stiskni Enter a připrav další pokus"
            )
        else:
            title = "VYHRÁLI JSTE BITVU"
            subtitle = f"BITVA {self.campaign.rival_battle_wins}/3"
            prompt = "Černý král: Tohle není naposledy. Stiskni Enter pro návrat."
        self._center_text(
            title,
            victory_font,
            (255, 229, 158) if self.war_victory_won else (239, 143, 124),
            (width // 2, height // 2 - 58),
        )
        self._center_text(
            subtitle,
            ending_font,
            (245, 242, 226),
            (width // 2, height // 2 + 22),
        )
        self._center_text(
            prompt,
            self.small_font,
            (181, 192, 181),
            (width // 2, height - 88),
        )

    def _show_tutorial(self, key: str, message: str) -> None:
        if not self.tutorial_enabled or key in self.tutorial_seen:
            return
        self.tutorial_seen.add(key)
        self.tutorial_queue.append((key, message))
        if self.tutorial_active is None:
            self.tutorial_active = self.tutorial_queue.pop(0)
            self.tutorial_until = pygame.time.get_ticks() + 8000

    def _draw_tutorial(self) -> None:
        if not self.tutorial_enabled:
            return
        now = pygame.time.get_ticks()
        if self.tutorial_active is not None and now >= self.tutorial_until:
            self.tutorial_active = (
                self.tutorial_queue.pop(0) if self.tutorial_queue else None
            )
            self.tutorial_until = now + 8000 if self.tutorial_active else 0
        if self.tutorial_active is None:
            return

        _, message = self.tutorial_active
        message = translate(message, self.language)
        panel = self.tutorial_panel
        pygame.draw.rect(self.surface, (24, 31, 28), panel, border_radius=9)
        pygame.draw.rect(self.surface, (224, 190, 119), panel, width=2, border_radius=9)
        self._text("RYCHLY NAVOD", self.small_font, (255, 224, 143), (panel.x + 12, panel.y + 8))
        pygame.draw.rect(self.surface, (82, 91, 84), self.tutorial_close_button, border_radius=4)
        self._center_text("X", self.small_font, (245, 245, 235), self.tutorial_close_button.center)

        words = message.split()
        lines: list[str] = []
        line = ""
        max_width = panel.width - 24
        for word in words:
            candidate = f"{line} {word}".strip()
            if line and self.small_font.size(candidate)[0] > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        for index, text in enumerate(lines[:4]):
            self._text(
                text,
                self.small_font,
                (232, 235, 224),
                (panel.x + 12, panel.y + 38 + index * 20),
            )
        if self.tutorial_queue:
            count = len(self.tutorial_queue) + 1
            self._text(
                f"Dalsi navod {count - 1}x",
                self.small_font,
                (170, 184, 174),
                (panel.x + 12, panel.bottom - 22),
            )

    def _draw_preview_piece(
        self,
        square: tuple[int, int],
        kind: str,
        color: str,
        board_left: int,
        board_top: int,
        tile_size: int,
    ) -> None:
        row, col = square
        self.renderer.draw_piece_sprite(
            self.surface,
            pygame.Rect(
                board_left + col * tile_size,
                board_top + row * tile_size,
                tile_size,
                tile_size,
            ),
            kind,
            color,
        )

    def _draw_campaign_hud(self) -> None:
        self.surface.blit(self.campaign_hud_surface, (0, 0))
        player = self.campaign.player
        title = (
            "BOSSOVI"
            if self.boss_battle_active
            else "BITVA"
            if self.campaign_battle_active
            else "KRALOVSTVI"
        )
        self._text(title, self.title_font, (238, 220, 175), (20, 10))
        self._text(
            f"Den {self.campaign.day} | Zlato {player.coins} | Farmy {player.farms} (+{player.farms * FARM_INCOME_PER_SECOND:g} zl/s) | Armada {player.army_size}",
            self.small_font,
            (230, 224, 204),
            (220, 15),
        )
        self._text(self.status, self.small_font, (246, 239, 220), (760, 15))
        if self.campaign.final_battle_countdown is not None:
            seconds = math.ceil(self.campaign.final_battle_countdown)
            self._text(
                f"Poslední bitva za {seconds // 60}:{seconds % 60:02d}",
                self.small_font,
                (255, 205, 140),
                (520, 43),
            )

    def _draw_king_banter(self) -> None:
        now = pygame.time.get_ticks()
        show_bubble = True
        if self.active_level == 1:
            lines = (
                (BLACK, "Tak ses konecne odvazil mi postavit?"),
                (WHITE, "Jsem tu, abych te porazil. Jsi na tahu."),
                (BLACK, "Uz se unavujes? Ja teprve zacinam."),
                (WHITE, "Mluvis hodne na nekoho, kdo porad ustupuje."),
                (BLACK, "Tvoje figurky padaji jedna po druhe."),
                (WHITE, "A tvuj kral se porad schovava za nimi."),
                (BLACK, "Tenhle tah jsi mel promyslet lip."),
                (WHITE, "Alespon vim, kde je tvuj kral."),
                (BLACK, "Sach. Tak co s tim udelas?"),
                (WHITE, "Neschovavej se. Tohle je mezi nami."),
                (BLACK, "Muj kral se te neboji. Zatim."),
                (WHITE, "Az dojde na krale, zadna vymluva ti nepomuze."),
                (BLACK, "Vazne sis myslel, ze staci porazit par figurek?"),
                (WHITE, "Jeste porad stojim. A ted jsi na tahu ty."),
            )
        else:
            lines = (
                (BLACK, "Tak ses dostal az sem. Uvidime, jak dlouho vydrzis."),
                (WHITE, "Tohle kralovstvi bude moje."),
                (BLACK, "Moji vojaci te uz vyhlizeji."),
                (WHITE, "Tvoje obrana ma vic der nez moje kapsa minci."),
                (BLACK, "Zlato ti odvahu nekoupi."),
                (WHITE, "Ale farmy mi koupi dost casu."),
                (BLACK, "Muj kral se te neboji. Zatim."),
                (WHITE, "Az dojde na krale, zadna vymluva ti nepomuze."),
                (BLACK, "Ten poklad nepatri tobe."),
                (WHITE, "Tak si ho zkus vzit."),
                (BLACK, "Armada vypada lip nez tvoje sance."),
                (WHITE, "Tak se prestan schovavat a posli ji."),
            )
        cycle_position = (now - self.banter_started_at) % 8000
        show_bubble = cycle_position < 4000
        index = ((now - self.banter_started_at) // 8000) % len(lines)
        speaker, message = lines[index]

        if self.active_level == 2:
            portrait_size = 48
            white_portrait = pygame.Rect(126, 690, portrait_size, portrait_size)
            black_portrait = pygame.Rect(866, 82, portrait_size, portrait_size)
            bubble = pygame.Rect(
                250,
                91 if speaker == BLACK else 617,
                590,
                54,
            )
        else:
            portrait_size = 58
            white_portrait = pygame.Rect(4, 695, portrait_size, portrait_size)
            black_portrait = pygame.Rect(4, 2, portrait_size, portrait_size)
            bubble = pygame.Rect(
                74,
                5 if speaker == BLACK else 681,
                560,
                67,
            )

        portraits = [(black_portrait, BLACK)]
        if self.active_level != 2:
            portraits.append((white_portrait, WHITE))
        for portrait, color in portraits:
            chair_color = (142, 98, 48) if color == WHITE else (55, 75, 89)
            pygame.draw.rect(
                self.surface,
                chair_color,
                (portrait.x + 5, portrait.y + 2, portrait.width - 10, portrait.height - 2),
            )
            pygame.draw.rect(
                self.surface,
                (75, 52, 34),
                (portrait.x + 1, portrait.bottom - 8, portrait.width - 2, 8),
            )
            self.renderer.draw_piece_sprite(
                self.surface, portrait.inflate(-8, -4), "K", color
            )

        if not show_bubble:
            return
        label = "TY" if speaker == WHITE else "CERNY KRAL"
        translated_label = translate(label, self.language)
        translated_message = translate(message, self.language)
        available_width = bubble.width - 24
        lines: list[str] = []
        current = ""
        for word in f"{translated_label}: {translated_message}".split():
            candidate = f"{current} {word}".strip()
            if current and self.small_font.size(candidate)[0] > available_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        line_height = self.small_font.get_linesize()
        total_height = len(lines) * line_height
        bubble.height = max(bubble.height, total_height + 16)
        if speaker == WHITE:
            bubble.bottom = WINDOW_SIZE[1] - (
                89 if self.active_level == 2 else 12
            )
        pygame.draw.rect(self.surface, (24, 31, 29), bubble)
        pygame.draw.rect(self.surface, (203, 166, 102), bubble, 3)
        pygame.draw.line(
            self.surface,
            (203, 166, 102),
            (bubble.left + 10, bubble.bottom - 5),
            (bubble.right - 10, bubble.bottom - 5),
            2,
        )
        text_y = bubble.centery - total_height // 2
        for index, line in enumerate(lines):
            self._center_text(
                line,
                self.small_font,
                (255, 232, 185),
                (bubble.centerx, text_y + index * line_height + line_height // 2),
            )

    def _draw_menu(self) -> None:
        self.surface.fill((28, 36, 34))
        for row in range(4):
            for col in range(4):
                rect = pygame.Rect(80 + col * 80, 82 + row * 80, 80, 80)
                color = (52, 67, 61) if (row + col) % 2 else (68, 83, 74)
                pygame.draw.rect(self.surface, color, rect)

        title = pygame.font.SysFont("consolas", 58, bold=True)
        subtitle = pygame.font.SysFont("consolas", 20)
        self._center_text("Šachová bitva", title, (255, 232, 177), (520, 150))
        self._center_text(
            "Hraješ za bílé proti botovi, který hraje za černé",
            subtitle,
            (245, 242, 226),
            (520, 210),
        )
        self._center_text(
            "Obtížnost bota (ELO)",
            subtitle,
            (245, 242, 226),
            (520, 253),
        )
        for difficulty, rect in self.difficulty_buttons.items():
            self._draw_difficulty_button(
                rect,
                BOT_DIFFICULTIES[difficulty]["label"],
                selected=difficulty == self.bot_difficulty,
            )
        self._center_text(
            "Vyber část hry",
            subtitle,
            (245, 242, 226),
            (520, 350),
        )
        level_labels = {
            1: "Úvodní bitva 8×8",
            2: "Království RPG 20×20",
        }
        for level, rect in self.level_buttons.items():
            enabled = level <= self.unlocked_level or level == 2
            color = (
                (205, 169, 99)
                if enabled and self.selected_level == level
                else (75, 91, 82) if enabled else (57, 65, 60)
            )
            pygame.draw.rect(self.surface, color, rect, border_radius=10)
            self._center_text(
                level_labels[level],
                self.small_font,
                (31, 39, 36) if enabled else (224, 228, 217),
                rect.center,
            )
        play_label = (
            "Pokracovat"
            if self.has_started_game and self.active_level == self.selected_level
            else "Vstoupit do království"
            if self.selected_level == 2
            else "Začít úvodní bitvu"
        )
        self._draw_menu_button(self.menu_play_button, play_label)
        new_game_label = (
            "Hardcore run skoncil"
            if self.hardcore_enabled
            and self.campaign.king_dead
            and self.selected_level == 2
            else "Restartovat kralovstvi"
            if self.selected_level == 2
            else "Nova hra"
        )
        if (
            self.hardcore_enabled
            and self.campaign.king_dead
            and self.selected_level == 2
        ):
            pygame.draw.rect(
                self.surface,
                (82, 91, 84),
                self.menu_new_game_button,
                border_radius=10,
            )
            self._center_text(
                new_game_label,
                self.font,
                (174, 181, 172),
                self.menu_new_game_button.center,
            )
        else:
            self._draw_menu_button(self.menu_new_game_button, new_game_label)
        self._draw_menu_button(self.menu_quit_button, "Ukončit")
        tutorial_label = (
            "Návody: zapnuto"
            if self.tutorial_enabled
            else "Návody: vypnuto"
        )
        tutorial_color = (
            (113, 164, 86) if self.tutorial_enabled else (95, 102, 96)
        )
        pygame.draw.rect(
            self.surface,
            tutorial_color,
            self.tutorial_toggle_button,
            border_radius=8,
        )
        self._center_text(
            tutorial_label,
            self.small_font,
            (245, 245, 235),
            self.tutorial_toggle_button.center,
        )
        language_label = (
            "Jazyk: čeština" if self.language == "cs" else "Language: English"
        )
        pygame.draw.rect(
            self.surface,
            (75, 91, 82),
            self.language_toggle_button,
            border_radius=8,
        )
        self._center_text(
            language_label,
            self.small_font,
            (245, 245, 235),
            self.language_toggle_button.center,
        )
        hardcore_label = (
            "Hardcore: zapnuto"
            if self.hardcore_enabled
            else "Hardcore: vypnuto"
        )
        pygame.draw.rect(
            self.surface,
            (151, 71, 67) if self.hardcore_enabled else (75, 91, 82),
            self.hardcore_toggle_button,
            border_radius=8,
        )
        self._center_text(
            hardcore_label,
            self.small_font,
            (245, 245, 235),
            self.hardcore_toggle_button.center,
        )
        hint = pygame.font.SysFont("consolas", 16)
        self._center_text(
            "V první části vyhraješ jen zabitím černého krále.",
            hint,
            (222, 228, 216),
            (520, 665),
        )
        if self.hardcore_enabled:
            self._center_text(
                "Vypnutí Hardcore smaže království a začne druhou část znovu.",
                hint,
                (239, 178, 150),
                (520, 692),
            )

    def _draw_pause_menu(self) -> None:
        self.surface.blit(self.pause_shade_surface, (0, 0))
        panel = pygame.Rect(52, 42, 936, 676)
        pygame.draw.rect(self.surface, (28, 36, 34), panel, border_radius=16)
        pygame.draw.rect(
            self.surface, (205, 169, 99), panel, width=2, border_radius=16
        )
        self._center_text("Pauza", self.title_font, (255, 232, 177), (520, 86))
        self._center_text(
            "Vyber režim a nastavení; režim se změní po pokračování.",
            self.small_font,
            (190, 199, 188),
            (520, 121),
        )
        self._center_text(
            "Režim hry",
            self.font,
            (255, 232, 177),
            (305, 149),
        )
        level_labels = {
            1: "Úvodní bitva 8×8",
            2: "Království RPG 20×20",
        }
        for level, rect in self.pause_level_buttons.items():
            self._draw_pause_option_button(
                rect,
                level_labels[level],
                selected=self.selected_level == level,
            )

        self._center_text(
            "Nastavení",
            self.font,
            (255, 232, 177),
            (305, 241),
        )
        tutorial_label = (
            "Návody: zapnuto"
            if self.tutorial_enabled
            else "Návody: vypnuto"
        )
        language_label = (
            "Jazyk: čeština"
            if self.language == "cs"
            else "Language: English"
        )
        hardcore_label = (
            "Hardcore: zapnuto"
            if self.hardcore_enabled
            else "Hardcore: vypnuto"
        )
        self._draw_pause_option_button(
            self.pause_tutorial_button,
            tutorial_label,
            selected=self.tutorial_enabled,
        )
        self._draw_pause_option_button(
            self.pause_language_button,
            language_label,
            selected=self.language == "en",
        )
        self._draw_pause_option_button(
            self.pause_hardcore_button,
            hardcore_label,
            selected=self.hardcore_enabled,
        )
        if self.hardcore_enabled:
            self._center_text(
                "Vypnutí Hardcore smaže postup království.",
                self.diplomacy_font,
                (239, 178, 150),
                (305, 450),
            )

        pygame.draw.line(
            self.surface,
            (75, 91, 82),
            (550, 145),
            (550, 475),
            2,
        )
        self._center_text(
            "Zvuk",
            self.font,
            (255, 232, 177),
            (750, 149),
        )
        self._center_text(
            "Hudba na pozadí",
            self.small_font,
            (245, 242, 226),
            (750, 187),
        )
        self._draw_audio_slider(self.pause_music_slider, self.music_volume)
        self._center_text(
            f"{round(self.music_volume * 100)} %",
            self.small_font,
            (220, 225, 214),
            (920, self.pause_music_slider.centery),
        )
        self._center_text(
            "Zvuky menu",
            self.small_font,
            (245, 242, 226),
            (750, 297),
        )
        self._draw_audio_slider(self.pause_sfx_slider, self.sfx_volume)
        self._center_text(
            f"{round(self.sfx_volume * 100)} %",
            self.small_font,
            (220, 225, 214),
            (920, self.pause_sfx_slider.centery),
        )
        self._center_text(
            "Volba jiného režimu spustí novou hru tohoto typu.",
            self.diplomacy_font,
            (190, 199, 188),
            (750, 411),
        )
        if self.pause_debug_visible:
            self._draw_pause_debug_panel()
        self._draw_menu_button(self.pause_resume_button, "Pokračovat")
        self._draw_menu_button(self.pause_menu_button, "Hlavní menu")
        debug_button_color = (
            (222, 187, 112)
            if self.pause_debug_visible
            else (101, 125, 106)
            if self.pause_debug_button.collidepoint(pygame.mouse.get_pos())
            else (62, 78, 69)
        )
        pygame.draw.rect(
            self.surface,
            debug_button_color,
            self.pause_debug_button,
            border_radius=5,
        )
        self._center_text(
            "Debug",
            self.diplomacy_font,
            (29, 35, 31) if self.pause_debug_visible else (241, 240, 228),
            self.pause_debug_button.center,
        )

    def _draw_pause_debug_panel(self) -> None:
        pygame.draw.rect(
            self.surface,
            (24, 31, 28),
            self.pause_debug_panel,
            border_radius=8,
        )
        pygame.draw.rect(
            self.surface,
            (205, 169, 99),
            self.pause_debug_panel,
            width=2,
            border_radius=8,
        )
        if self.active_level == 1:
            self._text(
                "Vynutit vysledek",
                self.diplomacy_font,
                (255, 232, 177),
                (self.pause_debug_panel.x + 12, self.pause_debug_panel.y + 8),
            )
            for option, label in (
                ("white", "Bílý vyhraje"),
                ("black", "Černý vyhraje"),
                ("draw", "Remíza"),
            ):
                self._draw_pause_option_button(
                    self.pause_debug_outcome_buttons[option],
                    label,
                    selected=False,
                )
            return

        self._text(
            f"Zlato v kralovstvi: {self.campaign.player.coins}",
            self.diplomacy_font,
            (255, 232, 177),
            (self.pause_debug_panel.x + 12, self.pause_debug_panel.y + 10),
        )
        self._draw_pause_option_button(
            self.pause_debug_gold_button,
            "Pridat 10000 zlata",
            selected=False,
        )
        self._draw_pause_option_button(
            self.pause_debug_random_gold_button,
            "Pridat nahodne zlato (1-1000000)",
            selected=False,
        )

    def _draw_pause_option_button(
        self, rect: pygame.Rect, label: str, *, selected: bool
    ) -> None:
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        color = (
            (222, 187, 112)
            if selected
            else (101, 125, 106)
            if hovered
            else (62, 78, 69)
        )
        pygame.draw.rect(self.surface, color, rect, border_radius=9)
        pygame.draw.rect(
            self.surface,
            (235, 207, 150) if selected else (104, 120, 108),
            rect,
            width=2,
            border_radius=9,
        )
        self._center_text(
            label,
            self.diplomacy_font,
            (29, 35, 31) if selected else (241, 240, 228),
            rect.center,
        )

    def _draw_audio_slider(self, rect: pygame.Rect, volume: float) -> None:
        pygame.draw.rect(self.surface, (63, 75, 68), rect, border_radius=6)
        filled = rect.copy()
        filled.width = round(rect.width * volume)
        if filled.width:
            pygame.draw.rect(self.surface, (205, 169, 99), filled, border_radius=6)
        pygame.draw.circle(
            self.surface,
            (255, 232, 177),
            (rect.left + round(rect.width * volume), rect.centery),
            10,
        )

    def _draw_difficulty_button(
        self, rect: pygame.Rect, label: str, *, selected: bool
    ) -> None:
        color = (205, 169, 99) if selected else (75, 91, 82)
        pygame.draw.rect(self.surface, color, rect, border_radius=10)
        self._center_text(label, self.small_font, (31, 39, 36), rect.center)

    def _draw_menu_button(self, rect: pygame.Rect, label: str) -> None:
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        color = (205, 169, 99) if hovered else (179, 143, 78)
        pygame.draw.rect(self.surface, color, rect, border_radius=10)
        text = translate(label, self.language)
        font = self.font
        max_width = rect.width - 20
        while font.size(text)[0] > max_width and font.get_height() > 14:
            font = pygame.font.SysFont("consolas", font.get_height() - 1, bold=True)
        self._center_text(
            label,
            font,
            (24, 29, 27),
            rect.center,
        )

    def _center_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        center: tuple[int, int],
    ) -> None:
        text = translate(text, self.language)
        image = self._cached_text(text, font, color)
        self.surface.blit(image, image.get_rect(center=center))

    def _draw_sidebar(self) -> None:
        if self.active_level == 2:
            self._draw_campaign_sidebar()
            return

        left = 720
        self._text("RPG ŠACHY", self.title_font, (238, 220, 175), (left, 32))
        self._text(self.status, self.small_font, (240, 240, 231), (left, 76))
        self._draw_team_health(WHITE, 90)
        self._draw_team_health(BLACK, 128)
        self._text(
            "JEDINY CIL: ZABIJ CERNEHO KRALE",
            self.small_font,
            (255, 205, 125),
            (left, 168),
        )
        self._text("Sebrane bile: " + self._captured_text(WHITE),
                   self.small_font, (246, 239, 220), (left, 214))
        self._text("Sebrane cerne: " + self._captured_text(BLACK),
                   self.small_font, (246, 239, 220), (left, 236))
        selected_piece = (
            self.game.piece_at(self.selected) if self.selected is not None else None
        )
        if selected_piece is not None and selected_piece.color == self.game.turn:
            displayed_max_health = max(
                1,
                round(
                    selected_piece.max_health * self.game.piece_health_multiplier
                ),
            )
            health_text = (
                f"{self._piece_name(selected_piece.kind)} "
                f"HP {selected_piece.health}/{displayed_max_health}"
            )
            self._text(
                health_text, self.small_font, (220, 225, 214), (left, 274)
            )
        self._text(
            "Tah: klikni figuru a cil.",
            self.small_font,
            (220, 225, 214),
            (left, 305),
        )
        if self.active_level == 2:
            self._draw_button(
                self.undo_button,
                "Vratit tah",
                enabled=bool(self.game.history) and not self.hardcore_enabled,
            )
        self._draw_button(self.reset_button, "Nova hra")
        self._draw_button(self.in_game_menu_button, "Pauza")

    def _draw_campaign_sidebar(self) -> None:
        if self.campaign_battle_active:
            self._draw_battle_sidebar()
            return

        left = 720
        player = self.campaign.player
        rival = self.campaign.rival
        self._text("KRAJINA", self.title_font, (238, 220, 175), (left, 32))
        self._text(self.status, self.small_font, (240, 240, 231), (left, 76))
        self._draw_team_health(WHITE, 90)
        self._draw_team_health(BLACK, 128)
        self._text(
            f"Den {self.campaign.day}   Tvoje zlato {player.coins}",
            self.small_font,
            (220, 194, 123),
            (left, 168),
        )
        shop_message = (
            "Obchod: " + self._shop_name(self.shop_menu)
            if self.shop_menu is not None
            else "Vstup kralem na barevnou branu."
        )
        self._text(shop_message, self.small_font, (195, 205, 194), (left, 190))
        for tab, button in self.campaign_tab_buttons.items():
            selected = tab == self.campaign_tab
            pygame.draw.rect(
                self.surface,
                (205, 169, 99) if selected else (75, 91, 82),
                button,
                border_radius=6,
            )
            label = translate(
                {"farms": "Farmy", "city": "Mesto", "armory": "Zbrojnice"}[tab],
                self.language,
            )
            image = self.small_font.render(label, True, (31, 39, 36))
            self.surface.blit(image, image.get_rect(center=button.center))

        if self.campaign_tab == "farms":
            self._text(
                f"Farmy {player.farms}  |  prijem +{player.farms * FARM_INCOME_PER_SECOND:g} zl/s",
                self.small_font,
                (220, 225, 214),
                (left, 264),
            )
            self._draw_button(
                self.farm_button,
                f"Postavit farmu - {self.campaign.farm_cost(WHITE)}",
                enabled=player.coins >= self.campaign.farm_cost(WHITE)
                and player.farms < FARM_LIMIT,
            )
            city_label = f"Odemknout mesto - {CITY_COST}" if not player.city else "Mesto je odemceno"
            self._draw_button(
                self.city_button,
                city_label,
                enabled=not player.city and player.farms >= 3 and player.coins >= CITY_COST,
            )
            self._text(
                f"Souper: {rival.farms} farem, mesto {'ano' if rival.city else 'ne'}",
                self.small_font,
                (195, 205, 194),
                (left, 418),
            )
        elif self.campaign_tab == "city":
            self._text(
                "Najem figur a postupne vylepsovani armady",
                self.small_font,
                (220, 225, 214),
                (left, 264),
            )
            self._draw_button(
                self.city_unlock_button,
                "Mesto odemceno" if player.city else f"Postavit mesto - {CITY_COST}",
                enabled=player.city or (player.farms >= 3 and player.coins >= CITY_COST),
            )
            for kind, button in self.recruit_buttons.items():
                self._draw_button(
                    button,
                    f"Najmout {self._piece_name(kind)} ({player.army[kind]}) - {RECRUIT_COSTS[kind]}",
                    enabled=player.city
                    and player.coins >= RECRUIT_COSTS[kind]
                    and player.army_size < 16,
                )
            for kind, button in self.upgrade_buttons.items():
                source = UPGRADE_SOURCES[kind]
                upgrade_cost = ARMY_UPGRADE_COSTS[kind]
                self._draw_button(
                    button,
                    f"Povysit {self._piece_name(source)} na {self._piece_name(kind)} - {upgrade_cost}",
                    enabled=player.city
                    and player.army[source] > 0
                    and player.coins >= upgrade_cost,
                )
        else:
            self._draw_button(
                self.armory_button,
                "Zbrojnice odemcena" if player.armory else f"Postavit zbrojnici - {ARMORY_COST}",
                enabled=player.armory or (player.city and player.coins >= ARMORY_COST),
            )
            self._text("Pripravena armada", self.small_font, (220, 225, 214), (left, 360))
            army_text = "  ".join(
                f"{kind}: {player.army[kind]}" for kind in ARMY_KINDS
            )
            self._text(army_text, self.small_font, (246, 239, 220), (left, 386))
            self._draw_button(self.deployment_minus_button, "-", enabled=True)
            self._draw_button(self.deployment_plus_button, "+", enabled=True)
            self._text(
                f"Nasadit jednotek: {self.deployment_limit}",
                self.small_font,
                (220, 225, 214),
                (left + 58, 510),
            )
            self._draw_button(
                self.declare_war_button,
                "Vyhlasit valku",
                enabled=player.armory and player.army_size > 0,
            )
            self._text(
                f"Souper ma {rival.army_size} jednotek",
                self.small_font,
                (195, 205, 194),
                (left, 556),
            )
        self._draw_button(
            self.undo_button,
            "Vratit tah",
            enabled=(
                self.campaign_battle_active
                and bool(self.game.history)
                and not self.hardcore_enabled
            ),
        )
        self._draw_button(self.reset_button, "Nova hra")
        self._draw_button(self.in_game_menu_button, "Pauza")

    def _draw_battle_sidebar(self) -> None:
        left = 720
        self._text("BITVA", self.title_font, (238, 220, 175), (left, 32))
        self._text(self.status, self.small_font, (240, 240, 231), (left, 76))
        self._draw_team_health(WHITE, 90)
        self._draw_team_health(BLACK, 128)
        self._text("Poraz souperova krale.", self.small_font, (238, 220, 175), (left, 168))
        for index, color in enumerate((WHITE, BLACK)):
            army = self.deployed_armies.get(color, {})
            side = "Tvoje" if color == WHITE else "Souperovy"
            label = "  ".join(
                f"{kind}:{army.get(kind, 0)}" for kind in ARMY_KINDS
            )
            self._text(
                f"{side}: {label}",
                self.small_font,
                (220, 225, 214),
                (left, 216 + index * 28),
            )
        self._text("Figurky maji vlastni HP bary.", self.small_font, (195, 205, 194), (left, 282))
        self._draw_button(
            self.undo_button,
            "Vratit tah",
            enabled=bool(self.game.history) and not self.hardcore_enabled,
        )
        self._draw_button(self.reset_button, "Nova hra")
        self._draw_button(self.in_game_menu_button, "Pauza")

    def _draw_team_health(self, color: str, y: int) -> None:
        label = (
            "Bili hrac"
            if color == WHITE
            else f"Cerny bot ({BOT_DIFFICULTIES[self.bot_difficulty]['label']})"
        )
        self._text(label, self.small_font, (220, 225, 214), (720, y))
        rect = pygame.Rect(720, y + 20, 280, 12)
        pygame.draw.rect(self.surface, (47, 54, 50), rect, border_radius=6)
        now = pygame.time.get_ticks() / 1000
        animation = self.team_health_animations.get(color)
        current = self._animated_health(
            animation,
            self.game.team_health[color],
            now,
        )
        maximum = self.game.team_health_max[color]
        current = min(maximum, max(0, current))
        fill = rect.copy()
        fill.width = int(rect.width * current / maximum) if maximum else 0
        if fill.width:
            bar_color = (81, 190, 107) if color == WHITE else (202, 79, 72)
            pygame.draw.rect(self.surface, bar_color, fill, border_radius=6)
        value = self.small_font.render(f"{current}/{maximum}", True, (245, 244, 233))
        self.surface.blit(value, (rect.right - value.get_width(), y))

    def _draw_button(
        self, rect: pygame.Rect, label: str, enabled: bool = True
    ) -> None:
        color = (179, 143, 78) if enabled else (82, 91, 84)
        pygame.draw.rect(self.surface, color, rect, border_radius=8)
        label = translate(label, self.language)
        text = self.small_font.render(label, True, (31, 39, 36) if enabled else (174, 181, 172))
        self.surface.blit(text, text.get_rect(center=rect.center))

    def _piece_name(self, kind: str) -> str:
        return translate({
            "P": "Pesec",
            "N": "Kun",
            "B": "Strelec",
            "R": "Vez",
            "Q": "Dama",
            "K": "Kral",
        }[kind], self.language)

    def _draw_promotion_prompt(self) -> None:
        panel = pygame.Rect(220, 325, 600, 110)
        pygame.draw.rect(self.surface, (28, 36, 34), panel, border_radius=12)
        pygame.draw.rect(self.surface, (220, 194, 123), panel, width=2, border_radius=12)
        text = self.font.render(
            translate(
                "Promena pesce: Q dama, R vez, B strelec, N kun",
                self.language,
            ),
            True,
            (246, 239, 220),
        )
        self.surface.blit(text, text.get_rect(center=(panel.centerx, panel.centery)))

    def _captured_text(self, color: str) -> str:
        pieces = self.game.captured[color]
        return " ".join(piece.kind for piece in pieces) if pieces else "—"

    def _text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        position: tuple[int, int],
    ) -> None:
        text = translate(text, self.language)
        self.surface.blit(self._cached_text(text, font, color), position)

    def _cached_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        key = (id(font), text, color)
        image = self._rendered_text_cache.get(key)
        if image is None:
            image = font.render(text, True, color)
            self._rendered_text_cache[key] = image
        else:
            self._rendered_text_cache.move_to_end(key)
        if len(self._rendered_text_cache) > 512:
            self._rendered_text_cache.popitem(last=False)
        return image



def run_game() -> None:
    app = ChessApp()
    try:
        app.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    run_game()
