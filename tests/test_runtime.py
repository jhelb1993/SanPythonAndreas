"""Exercise lifecycle/error handling with a fake native API; no GTA required."""
import importlib.util
import pathlib
import shutil
import sys
import tempfile
import types
import unittest
import threading
from unittest import mock

RUNTIME = pathlib.Path(__file__).resolve().parents[1] / "runtime" / "SanPythonAndreas"


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        shutil.copy(RUNTIME / "_spa_runtime.py", self.root)
        (self.root / "scripts").mkdir()
        self.output = []
        self.api = types.ModuleType("sanandreas")
        self.api.__version__ = "test"
        self.api._host_api_version = 15
        self.api._binding_backend = "test-host"
        self.api._sdk_revision = "test"
        self.api.show_text = self.output.append
        self.keys = set()
        self.focus = True
        self.stats = [25.0, 100.0]
        self.game_ms = 1000
        self.real_seconds = 0.0
        self.perf_seconds = 0.0
        self.game_thread = True
        self.game_thread_id = threading.get_ident()
        self.api._game_time_ms = lambda: self.game_ms
        self.api._require_game_thread = self.require_game_thread
        self.models_loaded = set()
        self.model_leases = {}
        self.model_refs = {}
        self.next_model_token = 0
        self.api._request_model = self.request_model
        self.api._model_ready = self.model_ready
        self.api._release_model = self.release_model
        self.api._is_key_down = lambda key: key in self.keys
        self.api._has_focus = lambda: self.focus
        self.api._player_health = lambda: tuple(self.stats) if self.stats is not None else None
        self.api._set_player_health = self.set_health
        self.armour = 10.0
        self.api._player_armour = self.read_armour
        self.api._set_player_armour = self.set_armour
        self.money = 500
        self.wanted = 1
        self.wanted_maximum = 6
        self.api._player_money = lambda: self.read_player_value("money")
        self.api._set_player_money = lambda value: self.set_player_value("money", value)
        self.api._player_wanted_level = lambda: self.read_player_value("wanted")
        self.api._set_player_wanted_level = lambda value: self.set_player_value("wanted", min(value, self.wanted_maximum))
        self.weapons = {}
        self.active_weapon = 0
        self.weapon_restricted = False
        self.api._player_weapon = self.read_weapon
        self.api._give_player_weapon = self.give_weapon
        self.api._select_player_weapon = self.select_weapon
        self.api._remove_player_weapon = self.remove_weapon
        self.api._clear_player_weapons = self.clear_weapons
        self.vehicle_data = None
        self.vehicle_error = False
        self.api._player_vehicle = self.read_vehicle
        self.position = (12.5, -34.0, 8.0)
        self.api._player_position = lambda: types.SimpleNamespace(
            x=self.position[0], y=self.position[1], z=self.position[2]
        ) if self.position is not None else None
        self.heading = 45.0
        self.api._player_heading = lambda: self.heading
        self.api._set_player_heading = self.set_heading
        self.interior = 0
        self.transition = False
        self.api._player_interior = lambda: self.interior
        self.api._teleport_player = self.teleport
        self.previous_api = sys.modules.get("sanandreas")
        self.stdout, self.stderr = sys.stdout, sys.stderr
        sys.modules["sanandreas"] = self.api
        spec = importlib.util.spec_from_file_location("_spa_runtime", self.root / "_spa_runtime.py")
        self.runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.runtime)
        self.real_ensure_workers = self.runtime._ensure_workers
        self.runtime._ensure_workers = lambda: None  # Deterministic queue execution in unit tests.
        self.runtime._real_now = lambda: self.real_seconds
        self.runtime._perf_now = lambda: self.perf_seconds
        self.errors = []
        self.runtime._notify_error = self.errors.append

    def tearDown(self):
        for _ in self.runtime._workers:
            self.runtime._work_queue.put_nowait(None)
        for worker in self.runtime._workers:
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
        sys.stdout, sys.stderr = self.stdout, self.stderr
        self.runtime._log.close()
        if self.previous_api is None:
            sys.modules.pop("sanandreas", None)
        else:
            sys.modules["sanandreas"] = self.previous_api
        self.temp.cleanup()

    def require_game_thread(self):
        if not self.game_thread or threading.get_ident() != self.game_thread_id:
            raise RuntimeError("requires game thread")

    def execute_one_background_job(self):
        job = self.runtime._work_queue.get_nowait()
        try:
            self.runtime._execute_background(job)
        finally:
            self.runtime._work_queue.task_done()

    def request_model(self, model):
        self.require_game_thread()
        if isinstance(model, bool) or not isinstance(model, int):
            raise TypeError("model must be int")
        if not 1 <= model <= 19999:
            raise ValueError("model out of bounds")
        if self.stats is None:
            raise RuntimeError("no active game")
        self.next_model_token += 1
        self.model_leases[self.next_model_token] = {"model": model, "pinned": False}
        return self.next_model_token

    def model_ready(self, token):
        self.require_game_thread()
        lease = self.model_leases.get(token)
        if lease is None:
            raise RuntimeError("invalid model lease")
        model = lease["model"]
        if model not in self.models_loaded:
            if lease["pinned"]:
                raise RuntimeError("forced unload")
            return False
        if not lease["pinned"]:
            self.model_refs[model] = self.model_refs.get(model, 0) + 1
            lease["pinned"] = True
        return True

    def release_model(self, token):
        self.require_game_thread()
        lease = self.model_leases.pop(token, None)
        if lease is not None and lease["pinned"]:
            model = lease["model"]
            self.model_refs[model] -= 1

    def read_vehicle(self):
        if self.stats is None or self.vehicle_error:
            raise RuntimeError("vehicle unavailable")
        return self.vehicle_data

    def read_weapon(self):
        if self.stats is None:
            raise RuntimeError("no active player")
        return self.active_weapon, self.weapons.get(self.active_weapon, 0)

    def require_weapon_change(self):
        if self.stats is None or self.stats[0] <= 0 or self.weapon_restricted:
            raise RuntimeError("weapon change unavailable")

    def give_weapon(self, weapon, ammo=100, *, equip=True):
        self.require_weapon_change()
        self.weapons[weapon] = self.weapons.get(weapon, 0) + ammo
        if equip:
            self.active_weapon = weapon

    def select_weapon(self, weapon):
        self.require_weapon_change()
        if weapon != 0 and weapon not in self.weapons:
            raise RuntimeError("not owned")
        self.active_weapon = weapon

    def remove_weapon(self, weapon):
        self.require_weapon_change()
        self.weapons.pop(weapon, None)
        if self.active_weapon == weapon:
            self.active_weapon = 0

    def clear_weapons(self):
        self.require_weapon_change()
        self.weapons.clear()
        self.active_weapon = 0

    def read_player_value(self, name):
        if self.stats is None:
            raise RuntimeError("no active player")
        return getattr(self, name)

    def set_player_value(self, name, value):
        if self.stats is None or self.stats[0] <= 0:
            raise RuntimeError("no active living player")
        setattr(self, name, value)

    def read_armour(self):
        if self.stats is None:
            raise RuntimeError("no active player")
        return self.armour

    def set_armour(self, value):
        if self.stats is None or self.stats[0] <= 0:
            raise RuntimeError("no active living player")
        self.armour = value

    def set_heading(self, value):
        self.heading = value

    def teleport(self, target, interior=None):
        if self.transition:
            raise RuntimeError("interior transition in progress")
        if interior is not None:
            self.interior = interior
        self.position = (target.x, target.y, target.z)

    def set_health(self, value):
        self.stats[0] = value

    def script(self, text):
        (self.root / "scripts" / "main.py").write_text(text, encoding="utf-8")

    def log(self):
        self.runtime._log.flush()
        return (self.root / "SanPythonAndreas.log").read_text(encoding="utf-8")

    def test_example_waits_for_game_and_runs_once(self):
        self.script((RUNTIME / "scripts" / "example_heal.py").read_text(encoding="utf-8"))
        self.runtime._tick(False)
        self.assertEqual(self.output, [])
        self.runtime._tick(True)
        self.runtime._tick(False)
        self.runtime._tick(True)
        self.assertEqual(self.output, ["SanPythonAndreas bereit! F5: Spieler heilen"])
        self.assertIn("Python ist bereit!", self.log())

    def test_frames_stop_during_pause(self):
        self.script("import sanandreas as sa\n@sa.on_frame\ndef frame(): sa.show_text('frame')\n")
        for ready in (True, True, False, True):
            self.runtime._tick(ready)
        self.assertEqual(self.output, ["frame"] * 3)

    def test_bad_callback_disabled_while_other_callbacks_continue(self):
        self.script("""import sanandreas as sa
@sa.on_frame
def bad(): raise SystemExit('do not exit GTA')
@sa.on_frame
def good(): sa.show_text('good')
""")
        self.runtime._tick(True)
        self.runtime._tick(True)
        self.assertEqual(self.output, ["good", "good"])
        log = self.log()
        self.assertIn("SystemExit: do not exit GTA", log)
        self.assertEqual(log.count("Disabled failing callback: bad"), 1)

    def test_script_failure_removes_partially_registered_callbacks(self):
        self.script("""import sanandreas as sa
@sa.on_game_ready
def start(): sa.show_text('must not run')
@sa.on_frame
def frame(): sa.show_text('must not run')
raise RuntimeError('broken startup')
""")
        self.runtime._tick(True)
        self.runtime._tick(True)
        self.assertEqual(self.output, [])
        self.assertEqual(self.log().count("RuntimeError: broken startup"), 1)

    def test_registration_during_dispatch_waits_for_next_frame(self):
        self.script("""import sanandreas as sa
@sa.on_frame
def first():
    sa.show_text('first')
    sa.on_frame(second)
def second(): sa.show_text('second')
""")
        self.runtime._tick(True)
        self.assertEqual(self.output, ["first"])
        self.runtime._tick(True)
        self.assertEqual(self.output, ["first", "first", "second"])

    def test_main_guard_and_script_logs(self):
        self.script("if __name__ == '__main__':\n    print('original main behavior')\n")
        self.runtime._tick(True)
        self.assertIn("original main behavior", self.log())

    def test_f5_example_heals_once_per_press(self):
        self.script((RUNTIME / "scripts" / "example_heal.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        self.keys.add(0x74)
        self.runtime._tick(True)
        self.assertEqual(self.stats[0], 100.0)
        self.stats[0] = 50.0
        self.runtime._tick(True)
        self.assertEqual(self.stats[0], 50.0)  # Holding F5 must not heal again.
        self.keys.clear()
        self.runtime._tick(True)
        self.keys.add(0x74)
        self.runtime._tick(True)
        self.assertEqual(self.stats[0], 100.0)
        self.assertEqual(self.output.count("Spieler geheilt!"), 2)

    def test_f5_example_uses_current_health_limit_after_stat_change(self):
        self.script((RUNTIME / "scripts" / "example_heal.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        for maximum in (100, 150, 176, 200):
            self.stats = [25, maximum]
            self.keys.add(0x74)
            self.runtime._tick(True)
            self.assertEqual(self.stats[0], maximum)
            self.keys.clear()
            self.runtime._tick(True)
        self.assertNotIn("Disabled failing callback", self.log())

    def test_held_key_during_start_pause_and_focus_change_is_ignored(self):
        self.script("import sanandreas as sa\n@sa.on_key_down('F5')\ndef heal(): sa.show_text('press')\n")
        self.keys.add(0x74)
        self.runtime._tick(True)  # Held at startup.
        self.keys.clear()
        self.runtime._tick(True)
        self.runtime._tick(False)
        self.keys.add(0x74)
        self.runtime._tick(True)  # Held at resume.
        self.focus = False
        self.keys.clear()
        self.runtime._tick(True)
        self.keys.add(0x74)
        self.focus = True
        self.runtime._tick(True)  # Held when regaining focus.
        self.assertEqual(self.output, [])
        self.keys.clear()
        self.runtime._tick(True)
        self.keys.add(0x74)
        self.runtime._tick(True)
        self.assertEqual(self.output, ["press"])

    def test_failing_key_callback_does_not_disable_other_callbacks(self):
        self.script("""import sanandreas as sa
@sa.on_key_down('F5')
def bad(): raise SystemExit('key failure')
@sa.on_key_down('F5')
def good(): sa.show_text('good')
""")
        self.runtime._tick(True)
        for _ in range(2):
            self.keys.add(0x74)
            self.runtime._tick(True)
            self.keys.clear()
            self.runtime._tick(True)
        self.assertEqual(self.output, ["good", "good"])
        self.assertEqual(self.log().count("Disabled failing callback: bad"), 1)

    def test_script_failure_removes_key_callbacks(self):
        self.script("""import sanandreas as sa
@sa.on_key_down('F5')
def heal(): sa.show_text('must not run')
raise RuntimeError('broken')
""")
        self.runtime._tick(True)
        self.runtime._tick(True)
        self.keys.add(0x74)
        self.runtime._tick(True)
        self.assertEqual(self.output, [])

    def test_player_view_rechecks_current_player(self):
        view = self.api.player()
        self.assertEqual(view.health, 25.0)
        self.assertEqual(view.max_health, 100.0)
        view.health = 75.0
        self.assertEqual(self.stats[0], 75.0)
        self.stats = None
        self.assertIsNone(self.api.player())
        with self.assertRaisesRegex(RuntimeError, "no active player"):
            _ = view.health
        self.stats = [10.0, 150.0]  # New player/loaded save, same view.
        self.assertEqual(view.max_health, 150.0)
        with self.assertRaises(AttributeError):
            view.max_health = 200.0

    def test_heal_skips_missing_and_dead_players_without_disabling_callback(self):
        self.script((RUNTIME / "scripts" / "example_heal.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        for stats in (None, [0.0, 100.0], [20.0, 150.0]):
            self.stats = stats
            self.keys.add(0x74)
            self.runtime._tick(True)
            self.keys.clear()
            self.runtime._tick(True)
        self.assertEqual(self.stats[0], 150.0)
        self.assertEqual(self.output.count("Spieler geheilt!"), 1)
        self.assertNotIn("Disabled failing callback", self.log())

    def test_key_names_and_invalid_keys(self):
        for key, code in ((" f5 ", 0x74), ("a", 0x41), ("SPACE", 0x20), ("F24", 0x87), (0x74, 0x74)):
            self.assertEqual(self.runtime._virtual_key(key), code)
        for key in ("F25", "F0", "typo", "", 0, 255):
            with self.assertRaises(ValueError):
                self.api.on_key_down(key)
        for key in (True, None, 2.5):
            with self.assertRaises(TypeError):
                self.api.on_key_down(key)

    def test_startup_error_is_reported_visibly_once(self):
        self.script("import sanandreas as sa\n@sa.missing_api('F5')\ndef heal(): pass\n")
        self.runtime._tick(True)
        self.runtime._tick(True)
        self.assertEqual(len(self.errors), 1)
        self.assertIn("AttributeError", self.errors[0])
        self.assertIn("missing_api", self.errors[0])

    def test_mixed_bootstrap_and_native_api_is_rejected(self):
        self.api._host_api_version = 1
        spec = importlib.util.spec_from_file_location("_spa_mismatch", self.root / "_spa_runtime.py")
        other = importlib.util.module_from_spec(spec)
        with self.assertRaisesRegex(RuntimeError, "versions differ"):
            spec.loader.exec_module(other)
        self.api._host_api_version = 15

    def test_position_property_rechecks_native_state(self):
        player = self.api.player()
        before = player.position
        self.assertEqual((before.x, before.y, before.z), (12.5, -34.0, 8.0))
        self.position = (100.0, 200.0, 300.0)
        self.assertEqual(player.position.x, 100.0)
        self.assertEqual(before.x, 12.5)
        player.position = before
        self.assertEqual(self.position, (12.5, -34.0, 8.0))
        self.position = None
        with self.assertRaisesRegex(RuntimeError, "no active player position"):
            _ = player.position

    def test_f6_example_displays_coordinates_once_per_press(self):
        self.script((RUNTIME / "scripts" / "example_position.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        self.keys.add(0x75)
        self.runtime._tick(True)
        self.runtime._tick(True)
        self.assertEqual(self.output, ["Position: X=12.50 Y=-34.00 Z=8.00"])
        self.keys.clear()
        self.runtime._tick(True)
        self.stats = None
        self.keys.add(0x75)
        self.runtime._tick(True)
        self.assertEqual(len(self.output), 1)
        self.assertNotIn("Disabled failing callback", self.log())

    def test_teleport_example_saves_returns_and_keeps_handler_after_rejection(self):
        self.script((RUNTIME / "scripts" / "example_teleport.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        def press(key):
            self.keys.clear()
            self.runtime._tick(True)
            self.keys.add(key)
            self.runtime._tick(True)
        press(0x77)  # F8 before saving.
        self.assertIn("Zuerst mit F7", self.output[-1])
        press(0x76)
        self.position = (100, 200, 300)
        self.interior = 1
        self.heading = 180.0
        self.transition = True
        press(0x77)
        self.assertEqual(self.position, (100, 200, 300))
        self.assertEqual(self.heading, 180.0)
        self.assertEqual(self.interior, 1)
        self.transition = False
        press(0x77)
        self.assertEqual(self.interior, 0)
        self.assertEqual(self.position, (12.5, -34, 8))
        self.assertEqual(self.heading, 45.0)
        self.assertNotIn("Disabled failing callback", self.log())

    def test_saved_interior_is_restored_from_outside_and_other_interiors(self):
        self.interior = 6
        self.script((RUNTIME / "scripts" / "example_teleport.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        self.keys.add(0x76)
        self.runtime._tick(True)
        for source_area in (0, 1):
            self.keys.clear()
            self.runtime._tick(True)
            self.interior = source_area
            self.position = (100, 200, 300)
            self.heading = 180
            self.keys.add(0x77)
            self.runtime._tick(True)
            self.assertEqual(self.interior, 6)
            self.assertEqual(self.position, (12.5, -34, 8))
            self.assertEqual(self.heading, 45)
        self.assertNotIn("Disabled failing callback", self.log())

    def test_armour_view_rechecks_current_player(self):
        player = self.api.player()
        self.assertEqual(player.armour, 10)
        player.armour = 75
        self.assertEqual(self.armour, 75)
        self.stats = None
        with self.assertRaises(RuntimeError):
            _ = player.armour
        with self.assertRaises(RuntimeError):
            player.armour = 100
        self.stats = [50, 100]
        self.armour = 20
        self.assertEqual(player.armour, 20)

    def test_f9_armour_example_skips_missing_dead_and_held_key(self):
        self.script((RUNTIME / "scripts" / "example_armour.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        for stats in (None, [0, 100], [25, 100]):
            self.stats = stats
            self.keys.add(0x78)
            self.runtime._tick(True)
            self.keys.clear()
            self.runtime._tick(True)
        self.assertEqual(self.armour, 100)
        self.assertEqual(self.output, ["Ruestung aufgefuellt!"])
        self.keys.add(0x78)
        self.runtime._tick(True)
        self.armour = 50
        self.runtime._tick(True)
        self.assertEqual(self.armour, 50)
        self.assertEqual(self.output.count("Ruestung aufgefuellt!"), 2)
        self.assertNotIn("Disabled failing callback", self.log())

    def test_money_and_wanted_view_rechecks_player(self):
        player = self.api.player()
        self.assertEqual(player.money, 500)
        self.assertEqual(player.wanted_level, 1)
        player.money = 1500
        player.wanted_level = 3
        self.assertEqual((self.money, self.wanted), (1500, 3))
        self.stats = None
        for name in ("money", "wanted_level"):
            with self.assertRaises(RuntimeError):
                getattr(player, name)
            with self.assertRaises(RuntimeError):
                setattr(player, name, 0)
        self.stats = [25, 100]
        self.money, self.wanted = 100, 0
        self.assertEqual((player.money, player.wanted_level), (100, 0))

    def test_money_wanted_example_handles_keys_caps_and_missing_player(self):
        self.script((RUNTIME / "scripts" / "example_money_wanted.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        def press(key):
            self.keys.clear()
            self.runtime._tick(True)
            self.keys.add(key)
            self.runtime._tick(True)
        press(0x79)  # F10
        self.assertEqual(self.money, 1500)
        self.runtime._tick(True)
        self.assertEqual(self.money, 1500)
        self.money = 999999900
        press(0x79)
        self.assertEqual(self.money, 999999999)
        self.wanted_maximum = 2
        press(0x7B)  # F12
        self.assertEqual(self.wanted, 2)
        self.assertEqual(self.output[-1], "Fahndungslevel: 2")
        press(0x7A)  # F11
        self.assertEqual(self.wanted, 0)
        count = len(self.output)
        for stats in (None, [0, 100]):
            self.stats = stats
            for key in (0x79, 0x7A, 0x7B):
                press(key)
        self.assertEqual(len(self.output), count)
        self.assertNotIn("Disabled failing callback", self.log())

    def test_weapon_view_delegates_and_rechecks_player(self):
        player = self.api.player()
        player.give_weapon(self.api.WeaponType.PISTOL, 50, equip=False)
        self.assertEqual(player.current_weapon, 0)
        player.select_weapon(self.api.WeaponType.PISTOL)
        self.assertEqual((player.current_weapon, player.weapon_ammo), (22, 50))
        self.stats = None
        for call in (lambda: player.current_weapon, lambda: player.weapon_ammo,
                     lambda: player.give_weapon(22), lambda: player.select_weapon(0),
                     lambda: player.remove_weapon(22), player.clear_weapons):
            with self.assertRaises(RuntimeError):
                call()
        self.stats = [25, 100]
        player.clear_weapons()
        self.assertEqual(player.current_weapon, 0)
        self.assertEqual(self.weapons, {})

    def test_weapon_example_recovers_after_restricted_and_missing_weapon(self):
        self.script((RUNTIME / "scripts" / "example_weapons.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        def press(key):
            self.keys.clear()
            self.runtime._tick(True)
            self.keys.add(ord(key))
            self.runtime._tick(True)
        press("J")  # Not owned yet; handler stays registered.
        self.weapon_restricted = True
        press("N")
        self.assertEqual(self.weapons, {})
        self.weapon_restricted = False
        press("N")
        self.assertEqual(self.read_weapon(), (22, 100))
        self.runtime._tick(True)  # Holding N must not add more ammo.
        self.assertEqual(self.read_weapon(), (22, 100))
        press("M")
        self.assertEqual(self.active_weapon, 0)
        press("J")
        self.assertEqual(self.active_weapon, 22)
        press("K")
        self.assertEqual(self.read_weapon(), (0, 0))
        count = len(self.output)
        for stats in (None, [0, 100]):
            self.stats = stats
            press("N")
        self.assertEqual(len(self.output), count)
        self.assertNotIn("Disabled failing callback", self.log())

    def test_player_states_and_vehicle_refresh_on_every_access(self):
        player = self.api.player()
        self.assertTrue(player.is_alive)
        self.assertFalse(player.in_vehicle)
        self.assertFalse(player.is_driver)
        self.assertIsNone(player.vehicle)
        self.vehicle_data = types.SimpleNamespace(model_id=411, is_driver=True, health=750, position=(1, 2, 3))
        before = player.vehicle
        self.assertTrue(player.in_vehicle)
        self.assertTrue(player.is_driver)
        self.vehicle_data = types.SimpleNamespace(model_id=400, is_driver=False, health=500, position=(4, 5, 6))
        self.assertFalse(player.is_driver)
        self.assertEqual(player.vehicle.model_id, 400)
        self.assertEqual(before.model_id, 411)
        self.vehicle_data = None
        self.assertFalse(player.in_vehicle)
        self.stats = [0, 100]
        self.assertFalse(player.is_alive)
        self.stats = None
        for name in ("is_alive", "vehicle", "in_vehicle", "is_driver"):
            with self.assertRaises(RuntimeError):
                getattr(player, name)

    def test_vehicle_example_handles_foot_driver_passenger_and_transition(self):
        self.script((RUNTIME / "scripts" / "example_vehicle.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        def press():
            self.keys.clear()
            self.runtime._tick(True)
            self.keys.add(ord("V"))
            self.runtime._tick(True)
        press()
        self.assertEqual(self.output[-1], "Spieler zu Fuss")
        self.vehicle_data = types.SimpleNamespace(model_id=411, is_driver=True, health=750, position=(1, 2, 3))
        press()
        self.assertEqual(self.output[-1], "Fahrer: Modell 411, Zustand 750")
        count = len(self.output)
        self.runtime._tick(True)
        self.assertEqual(len(self.output), count)
        self.vehicle_error = True
        press()
        self.assertIn("Fahrzeugwechsel", self.output[-1])
        self.vehicle_error = False
        self.vehicle_data = types.SimpleNamespace(model_id=400, is_driver=False, health=500, position=(4, 5, 6))
        press()
        self.assertEqual(self.output[-1], "Passagier: Modell 400, Zustand 500")
        self.assertIn("Fahrzeugposition: (4, 5, 6)", self.log())
        count = len(self.output)
        self.stats = None
        press()
        self.assertEqual(len(self.output), count)
        self.assertNotIn("Disabled failing callback", self.log())

    def test_timers_run_once_cancel_and_release_callbacks(self):
        self.script("pass")
        calls = []
        timer = self.api.call_later(1, lambda: calls.append("once"))
        cancelled = self.api.call_later(0, lambda: calls.append("cancelled"))
        cancelled.cancel()
        cancelled.cancel()
        self.assertTrue(cancelled.cancelled)
        self.assertTrue(cancelled.done)
        self.assertIsNone(cancelled._callback)
        self.runtime._tick(True)
        self.game_ms += 999
        self.runtime._tick(True)
        self.assertEqual(calls, [])
        self.game_ms += 1
        self.runtime._tick(True)
        self.runtime._tick(True)
        self.assertEqual(calls, ["once"])
        self.assertTrue(timer.done)
        self.assertFalse(timer.cancelled)
        self.assertIsNone(timer._callback)
        self.assertEqual(self.runtime._timers, {})

    def test_timer_clocks_have_explicit_pause_and_focus_behavior(self):
        self.script("pass")
        calls = []
        self.api.call_later(1, lambda: calls.append("game"))
        self.api.call_later(1, lambda: calls.append("real"), clock="real")
        self.runtime._tick(True)
        self.game_ms += 500
        self.real_seconds = 0.5
        self.runtime._tick(True)
        self.real_seconds = 5
        self.runtime._tick(False)
        self.assertEqual(calls, [])
        self.focus = False
        self.runtime._tick(True)
        self.assertEqual(calls, ["real"])
        self.game_ms += 500
        self.runtime._tick(True)
        self.assertEqual(calls, ["real", "game"])

    def test_repeating_timer_skips_missed_intervals_and_can_cancel_itself(self):
        self.script("pass")
        calls = []
        def callback():
            calls.append(self.game_ms)
            if len(calls) == 2:
                timer.cancel()
        timer = self.api.call_every(1, callback)
        self.runtime._tick(True)
        self.game_ms += 10000
        self.runtime._tick(True)
        self.runtime._tick(True)
        self.assertEqual(len(calls), 1)
        self.game_ms += 1000
        self.runtime._tick(True)
        self.game_ms += 1000
        self.runtime._tick(True)
        self.assertEqual(len(calls), 2)
        self.assertTrue(timer.cancelled)

    def test_timer_zero_delay_and_registration_during_dispatch_wait_for_next_tick(self):
        self.script("pass")
        calls = []
        def first():
            calls.append("first")
            self.api.call_later(0, lambda: calls.append("second"))
        self.api.call_later(0, first)
        self.runtime._tick(True)
        self.assertEqual(calls, ["first"])
        self.runtime._tick(True)
        self.assertEqual(calls, ["first", "second"])
        self.script("pass")

    def test_timer_failures_are_isolated_and_slow_callbacks_logged(self):
        self.script("pass")
        calls = []
        def bad():
            raise SystemExit("timer must not exit GTA")
        def slow():
            self.perf_seconds += 0.06
            calls.append("good")
        failed = self.api.call_every(1, bad)
        self.api.call_every(1, slow)
        self.runtime._tick(True)
        for _ in range(2):
            self.game_ms += 1000
            self.runtime._tick(True)
        self.assertTrue(failed.done)
        self.assertEqual(calls, ["good", "good"])
        self.assertEqual(self.log().count("Disabled failing timer:"), 1)
        self.assertIn("Slow timer callback", self.log())

    def test_script_failure_cancels_partially_registered_timers(self):
        self.script("import sanandreas as sa\nsa.call_later(0, lambda: sa.show_text('bad'))\nraise RuntimeError('broken')")
        self.runtime._tick(True)
        self.runtime._tick(True)
        self.assertEqual(self.runtime._timers, {})
        self.assertEqual(self.output, [])

    def test_timers_handle_clock_wrap_and_cancel_game_timers_on_backward_reset(self):
        self.script("pass")
        calls = []
        self.game_ms = 0xFFFFFFF0
        self.api.call_later(0.032, lambda: calls.append("wrap"))
        self.runtime._tick(True)
        self.game_ms = 16
        self.runtime._tick(True)
        self.assertEqual(calls, ["wrap"])
        self.game_ms = 10000
        self.runtime._tick(True)
        timer = self.api.call_later(10, lambda: calls.append("old game"))
        self.api.call_later(1, lambda: calls.append("real"), clock="real")
        self.game_ms = 0
        self.runtime._tick(True)
        self.assertTrue(timer.cancelled)
        self.real_seconds = 1
        self.runtime._tick(True)
        self.assertEqual(calls, ["wrap", "real"])

    def test_timer_validation_and_thread_guard(self):
        for duration in (True, "1", None):
            with self.assertRaises(TypeError):
                self.api.call_later(duration, lambda: None)
        for duration in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.api.call_later(duration, lambda: None)
        with self.assertRaises(ValueError):
            self.api.call_every(0, lambda: None)
        with self.assertRaises(TypeError):
            self.api.call_later(1, None)
        with self.assertRaises(ValueError):
            self.api.call_later(1, lambda: None, clock="wall")
        with self.assertRaises(TypeError):
            self.api.call_later(1, lambda: None, clock=None)
        timer = self.api.call_later(1, lambda: None)
        self.game_thread = False
        for call in (lambda: self.api.call_later(1, lambda: None),
                     lambda: self.api.call_every(1, lambda: None), timer.cancel):
            with self.assertRaisesRegex(RuntimeError, "game thread"):
                call()
        self.assertFalse(timer.done)

    def test_timer_dispatch_budget_defers_remaining_calls_fairly(self):
        self.script("pass")
        calls = []
        for i in range(70):
            self.api.call_later(0, lambda i=i: calls.append(i))
        self.runtime._tick(True)
        self.assertEqual(calls, list(range(64)))
        self.runtime._tick(True)
        self.assertEqual(calls, list(range(70)))
        repeats = [self.api.call_every(0.001, lambda: None) for _ in range(64)]
        self.api.call_later(0.001, lambda: calls.append("tail"))
        self.game_ms += 1
        self.runtime._tick(True)
        self.assertNotIn("tail", calls)
        self.game_ms += 1
        self.runtime._tick(True)
        self.assertIn("tail", calls)
        for timer in repeats:
            timer.cancel()

    def test_timer_example_countdown_pause_restart_and_cancel(self):
        self.script((RUNTIME / "scripts" / "example_timers.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        def press(key):
            self.keys.clear()
            self.runtime._tick(True)
            self.keys.add(ord(key))
            self.runtime._tick(True)
        press("T")
        self.assertEqual(self.output[-1], "Countdown: 3")
        for expected in ("Countdown: 2", "Countdown: 1", "Countdown fertig!"):
            self.game_ms += 1000
            self.runtime._tick(True)
            self.assertEqual(self.output[-1], expected)
        self.assertEqual(self.runtime._timers, {})
        press("R")
        self.real_seconds += 10
        self.runtime._tick(False)
        self.runtime._tick(True)
        self.assertEqual(self.output[-1], "Echtzeit-Timer fertig!")
        press("T")
        press("T")
        self.assertEqual(len(self.runtime._timers), 1)
        press("Y")
        self.assertEqual(self.runtime._timers, {})
        self.assertNotIn("Disabled failing", self.log())

    def test_task_steps_wait_and_return_without_blocking(self):
        self.script("pass")
        calls = []
        def work():
            calls.append("start")
            yield self.api.wait(1)
            calls.append("second")
            yield self.api.wait()
            return 42
        task = self.api.start_task(work())
        self.assertEqual(calls, [])
        self.runtime._tick(True)
        self.assertEqual(calls, ["start"])
        self.game_ms += 999
        self.runtime._tick(True)
        self.assertEqual(calls, ["start"])
        self.game_ms += 1
        self.runtime._tick(True)
        self.assertEqual(calls, ["start", "second"])
        self.assertFalse(task.done)
        self.runtime._tick(True)
        self.assertTrue(task.done)
        self.assertEqual(task.result, 42)
        self.assertIsNone(task.error)
        self.assertIsNone(task._generator)
        self.assertEqual(self.runtime._tasks, {})
        self.assertEqual(self.runtime._timers, {})

    def test_task_cancel_runs_finally_once_and_releases_wait(self):
        self.script("pass")
        calls = []
        def work():
            try:
                yield self.api.wait(100)
                calls.append("must not resume")
            finally:
                calls.append("cleanup")
        task = self.api.start_task(work())
        self.runtime._tick(True)
        task.cancel()
        task.cancel()
        self.game_ms += 100000
        self.runtime._tick(True)
        self.assertEqual(calls, ["cleanup"])
        self.assertTrue(task.done)
        self.assertTrue(task.cancelled)
        self.assertEqual(self.runtime._tasks, {})
        self.assertEqual(self.runtime._timers, {})
        self.assertEqual(self.runtime._claimed_generators, set())

    def test_task_self_cancel_defers_close_until_step_returns(self):
        self.script("pass")
        calls = []
        def work():
            try:
                task.cancel()
                calls.append("current step")
                yield self.api.wait()
                calls.append("must not resume")
            finally:
                calls.append("cleanup")
        task = self.api.start_task(work())
        self.runtime._tick(True)
        self.runtime._tick(True)
        self.assertEqual(calls, ["current step", "cleanup"])
        self.assertTrue(task.done)
        self.assertTrue(task.cancelled)
        self.assertIsNone(task.error)

    def test_task_errors_and_invalid_yields_do_not_stop_other_work(self):
        self.script("pass")
        calls = []
        def invalid():
            try:
                yield None
            finally:
                calls.append("invalid cleanup")
        def exits():
            raise SystemExit("do not exit GTA")
            yield
        invalid_task = self.api.start_task(invalid())
        exit_task = self.api.start_task(exits())
        self.api.call_later(0, lambda: calls.append("other timer"))
        self.runtime._tick(True)
        self.assertEqual(calls, ["invalid cleanup", "other timer"])
        self.assertIn("TypeError", invalid_task.error)
        self.assertIn("SystemExit", exit_task.error)
        self.assertTrue(invalid_task.done)
        self.assertTrue(exit_task.done)

    def test_task_cleanup_failure_is_logged_and_task_still_stops(self):
        self.script("pass")
        def work():
            try:
                yield self.api.wait(1)
            finally:
                raise RuntimeError("cleanup failed")
        task = self.api.start_task(work())
        self.runtime._tick(True)
        task.cancel()
        self.assertTrue(task.done)
        self.assertIn("cleanup failed", task.error)
        self.assertIn("Task cleanup failed", self.log())
        self.assertEqual(self.runtime._tasks, {})
        self.assertEqual(self.runtime._timers, {})

    def test_task_cancel_before_start_does_not_enter_generator_body(self):
        self.script("pass")
        calls = []
        def work():
            try:
                calls.append("start")
                yield self.api.wait()
            finally:
                calls.append("cleanup")
        task = self.api.start_task(work())
        task.cancel()
        self.runtime._tick(True)
        self.assertEqual(calls, [])
        self.assertTrue(task.done)

    def test_task_game_clock_reset_closes_game_wait_but_preserves_real_wait(self):
        self.script("pass")
        calls = []
        def work(clock):
            try:
                yield self.api.wait(10, clock=clock)
                calls.append(clock)
            finally:
                calls.append(clock + " cleanup")
        game = self.api.start_task(work("game"))
        real = self.api.start_task(work("real"))
        self.runtime._tick(True)
        self.game_ms = 0
        self.runtime._tick(False)
        self.assertTrue(game.cancelled)
        self.assertFalse(real.done)
        self.assertEqual(calls, ["game cleanup"])
        self.real_seconds = 10
        self.runtime._tick(True)
        self.assertTrue(real.done)
        self.assertEqual(calls, ["game cleanup", "real", "real cleanup"])

    def test_task_bulk_cleanup_cannot_schedule_orphan_work(self):
        self.script("pass")
        calls = []
        def work():
            try:
                yield self.api.wait(10)
            finally:
                try:
                    self.api.call_later(0, lambda: calls.append("orphan"))
                except RuntimeError:
                    calls.append("registration blocked")
        task = self.api.start_task(work())
        self.runtime._tick(True)
        self.game_ms = 0
        self.runtime._tick(False)
        self.assertTrue(task.done)
        self.assertEqual(calls, ["registration blocked"])
        self.assertEqual(self.runtime._tasks, {})
        self.assertEqual(self.runtime._timers, {})

    def test_task_validation_duplicate_generator_and_thread_guard(self):
        self.script("pass")
        def work():
            yield self.api.wait()
        for value in (None, work, iter([1])):
            with self.assertRaises(TypeError):
                self.api.start_task(value)
        generator = work()
        task = self.api.start_task(generator)
        with self.assertRaises(ValueError):
            self.api.start_task(generator)
        self.game_thread = False
        with self.assertRaises(RuntimeError):
            task.cancel()
        other = work()
        with self.assertRaises(RuntimeError):
            self.api.start_task(other)
        other.close()
        self.game_thread = True
        self.runtime._tick(True)
        task.cancel()
        with self.assertRaises(ValueError):
            self.api.start_task(generator)
        for value in (True, "1", None):
            with self.assertRaises(TypeError):
                self.api.wait(value)
        for value in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.api.wait(value)
        with self.assertRaises(ValueError):
            self.api.wait(clock="wall")

    def test_task_validates_direct_wait_tokens_and_script_failure_discards_tasks(self):
        self.script("pass")
        def work():
            yield self.api.Wait(-1, "game")
        task = self.api.start_task(work())
        self.runtime._tick(True)
        self.assertIn("ValueError", task.error)
        self.script("import sanandreas as sa\ndef work():\n    yield sa.wait()\nsa.start_task(work())\nraise RuntimeError('broken')")
        self.runtime._loaded = self.runtime._started = False
        self.runtime._tick(True)
        self.assertEqual(self.runtime._tasks, {})
        self.assertEqual(self.runtime._timers, {})

    def test_task_example_finishes_restarts_and_cancels(self):
        self.script((RUNTIME / "scripts" / "example_tasks.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        def press(key):
            self.keys.clear()
            self.runtime._tick(True)
            self.keys.add(ord(key))
            self.runtime._tick(True)
        press("G")
        self.runtime._tick(True)
        self.assertEqual(self.output[-1], "Task-Countdown: 3")
        for text in ("Task-Countdown: 2", "Task-Countdown: 1", "Task fertig!"):
            self.game_ms += 1000
            self.runtime._tick(True)
            self.assertEqual(self.output[-1], text)
        self.assertEqual(self.runtime._tasks, {})
        press("G")
        self.runtime._tick(True)
        press("G")
        self.assertEqual(len(self.runtime._tasks), 1)
        press("H")
        self.assertEqual(self.output[-1], "Task abgebrochen.")
        self.assertEqual(self.runtime._tasks, {})
        self.assertEqual(self.runtime._timers, {})
        self.assertIn("Task-Countdown aufgeraeumt", self.log())
        self.assertNotIn("Disabled failing", self.log())

    def test_async_model_waits_then_holds_reference_until_context_exit(self):
        self.script("pass")
        calls = []
        def work():
            with (yield from self.api.load_model(411)) as model:
                calls.append(model)
                self.assertTrue(model.ready)
                yield self.api.wait(1)
        task = self.api.start_task(work())
        self.runtime._tick(True)
        self.assertFalse(task.done)
        self.assertEqual(calls, [])
        self.assertEqual(len(self.model_leases), 1)
        self.models_loaded.add(411)
        self.runtime._tick(True)
        self.assertEqual(calls[0].model_id, 411)
        self.assertEqual(self.model_refs[411], 1)
        self.game_ms += 1000
        self.runtime._tick(True)
        self.assertTrue(task.done)
        self.assertTrue(calls[0].released)
        self.assertEqual(self.model_refs[411], 0)
        self.assertEqual(self.runtime._models, {})
        with self.assertRaises(RuntimeError):
            _ = calls[0].ready
        calls[0].release()

    def test_async_model_timeout_releases_pending_request(self):
        self.script("pass")
        calls = []
        def work():
            try:
                yield from self.api.load_model(411, timeout=2)
            except TimeoutError:
                calls.append("timeout")
        task = self.api.start_task(work())
        self.runtime._tick(True)
        self.real_seconds = 2
        self.runtime._tick(True)
        self.assertTrue(task.done)
        self.assertIsNone(task.error)
        self.assertEqual(calls, ["timeout"])
        self.assertEqual(self.model_leases, {})
        self.assertEqual(self.runtime._models, {})

    def test_async_model_cancellation_cleans_pending_and_loaded_requests(self):
        self.script("pass")
        def work():
            with (yield from self.api.load_model(411)):
                yield self.api.wait(100)
        pending = self.api.start_task(work())
        self.runtime._tick(True)
        pending.cancel()
        self.assertEqual(self.model_leases, {})
        self.models_loaded.add(411)
        loaded = self.api.start_task(work())
        self.runtime._tick(True)
        self.assertEqual(self.model_refs[411], 1)
        loaded.cancel()
        self.assertEqual(self.model_refs[411], 0)
        self.assertEqual(self.runtime._models, {})
        self.assertEqual(self.model_leases, {})

    def test_async_model_consumers_have_independent_references(self):
        self.script("pass")
        self.models_loaded.add(411)
        models = []
        def work():
            with (yield from self.api.load_model(411)) as model:
                models.append(model)
                yield self.api.wait(100)
        first = self.api.start_task(work())
        second = self.api.start_task(work())
        self.runtime._tick(True)
        self.assertEqual(self.model_refs[411], 2)
        first.cancel()
        self.assertEqual(self.model_refs[411], 1)
        self.assertTrue(models[1].ready)
        second.cancel()
        self.assertEqual(self.model_refs[411], 0)

    def test_async_model_ready_wins_over_timeout_on_resume(self):
        self.script("pass")
        def work():
            return (yield from self.api.load_model(411, timeout=1))
        task = self.api.start_task(work())
        self.runtime._tick(True)
        self.real_seconds = 10
        self.models_loaded.add(411)
        self.runtime._tick(False)
        self.assertFalse(task.done)
        self.runtime._tick(True)
        self.assertTrue(task.done)
        self.assertIsNone(task.error)
        self.assertTrue(task.result.ready)
        task.result.release()

    def test_async_model_clock_reset_invalidates_lease_and_no_orphan_wait_remains(self):
        self.script("pass")
        def work():
            yield from self.api.load_model(411)
        task = self.api.start_task(work())
        self.runtime._tick(True)
        self.game_ms = 0
        self.runtime._tick(False)
        self.assertEqual(self.runtime._models, {})
        self.assertEqual(self.model_leases, {})
        self.runtime._tick(True)
        self.assertTrue(task.done)
        self.assertIn("released", task.error)
        self.assertEqual(self.runtime._tasks, {})
        self.assertEqual(self.runtime._timers, {})

    def test_async_model_input_validation_and_thread_guard(self):
        for model in (True, 'infernus', 411.0, None):
            with self.assertRaises(TypeError):
                next(self.api.load_model(model))
        for model in (-1, 0, 20000):
            with self.assertRaises(ValueError):
                next(self.api.load_model(model))
        for timeout in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                next(self.api.load_model(411, timeout=timeout))
        with self.assertRaises(TimeoutError):
            next(self.api.load_model(411, timeout=0))
        self.game_thread = False
        with self.assertRaises(RuntimeError):
            next(self.api.load_model(411))
        self.assertEqual(self.model_leases, {})

    def test_script_failure_releases_model_request_started_during_import(self):
        self.script("import sanandreas as sa\nloader = sa.load_model(411)\nnext(loader)\nraise RuntimeError('broken import')")
        self.runtime._tick(True)
        self.assertTrue(self.runtime._failed)
        self.assertEqual(self.model_leases, {})
        self.assertEqual(self.runtime._models, {})

    def test_async_model_example_loads_releases_and_cancels(self):
        self.script((RUNTIME / "scripts" / "example_models.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        def press(key):
            self.keys.clear()
            self.runtime._tick(True)
            self.keys.add(ord(key))
            self.runtime._tick(True)
        press("U")
        self.runtime._tick(True)
        self.assertIn("asynchron", self.output[-1])
        self.models_loaded.add(411)
        self.runtime._tick(True)
        self.assertIn("bereit", self.output[-1])
        self.assertEqual(self.model_refs[411], 1)
        self.game_ms += 3000
        self.runtime._tick(True)
        self.assertEqual(self.output[-1], "Modell 411 freigegeben.")
        self.assertEqual(self.model_refs[411], 0)
        press("U")
        self.runtime._tick(True)
        press("I")
        self.assertEqual(self.model_refs[411], 0)
        self.assertEqual(self.runtime._models, {})
        self.assertEqual(self.runtime._tasks, {})
        self.assertNotIn("Disabled failing", self.log())

    def test_background_result_waits_for_active_game_and_runs_on_main_thread(self):
        self.script("pass")
        calls = []
        job = self.api.run_in_background(lambda: {"value": 42},
                                         lambda result: calls.append((threading.get_ident(), result)))
        self.execute_one_background_job()
        self.assertFalse(job.done)
        self.runtime._tick(False)
        self.assertEqual(calls, [])
        self.runtime._tick(True)
        self.assertEqual(calls, [(self.game_thread_id, {"value": 42})])
        self.assertTrue(job.done)
        self.assertEqual(job.result, {"value": 42})
        self.assertIsNone(job.error)
        self.assertIsNone(job._on_done)
        self.assertEqual(self.runtime._background_jobs, {})

    def test_background_cancel_skips_queued_work_and_suppresses_completed_result(self):
        self.script("pass")
        calls = []
        queued = self.api.run_in_background(lambda: calls.append("work"), lambda value: calls.append("callback"))
        queued.cancel()
        queued.cancel()
        self.execute_one_background_job()
        finished = self.api.run_in_background(lambda: 42, lambda value: calls.append(value))
        self.execute_one_background_job()
        finished.cancel()
        self.runtime._tick(True)
        self.assertEqual(calls, [])
        self.assertTrue(queued.cancelled)
        self.assertTrue(finished.done)
        self.assertIsNone(finished.result)

    def test_background_worker_and_callback_errors_are_isolated(self):
        self.script("pass")
        calls = []
        def bad_work():
            raise SystemExit("worker must not exit GTA")
        failed = self.api.run_in_background(bad_work, on_error=calls.append)
        def bad_callback(value):
            raise RuntimeError("completion broke")
        bad_delivery = self.api.run_in_background(lambda: 10, bad_callback)
        good = self.api.run_in_background(lambda: 42, calls.append)
        for _ in range(3):
            self.execute_one_background_job()
        self.runtime._tick(True)
        self.assertIn("SystemExit", calls[0])
        self.assertEqual(calls[-1], 42)
        self.assertIn("SystemExit", failed.error)
        self.assertIn("completion broke", bad_delivery.error)
        self.assertTrue(good.done)
        self.assertEqual(self.runtime._background_jobs, {})

    def test_background_limits_queue_and_result_dispatch_budget(self):
        self.script("pass")
        jobs = [self.api.run_in_background(lambda: 1) for _ in range(32)]
        with self.assertRaisesRegex(RuntimeError, "queue is full"):
            self.api.run_in_background(lambda: 1)
        self.assertEqual(len(self.runtime._background_jobs), 32)
        for _ in range(32):
            self.execute_one_background_job()
        jobs += [self.api.run_in_background(lambda: 1) for _ in range(32)]
        for _ in range(32):
            self.execute_one_background_job()
        with self.assertRaisesRegex(RuntimeError, "pending background"):
            self.api.run_in_background(lambda: 1)
        self.runtime._tick(True)
        self.assertEqual(sum(job.done for job in jobs), 32)
        self.runtime._tick(True)
        self.assertTrue(all(job.done for job in jobs))

    def test_background_reset_cancels_old_results_and_prevents_late_delivery(self):
        self.script("pass")
        self.runtime._tick(True)
        calls = []
        completed = self.api.run_in_background(lambda: 1, calls.append)
        self.execute_one_background_job()
        pending = self.api.run_in_background(lambda: 2, calls.append)
        self.game_ms = 0
        self.runtime._tick(False)
        self.assertTrue(completed.cancelled)
        self.assertTrue(pending.cancelled)
        self.execute_one_background_job()
        self.runtime._tick(True)
        self.assertEqual(calls, [])
        self.assertTrue(self.runtime._completed_work.empty())
        self.assertEqual(self.runtime._background_jobs, {})

    def test_background_script_failure_cancels_work_registered_during_import(self):
        self.script("import sanandreas as sa\nsa.run_in_background(lambda: 42, lambda result: sa.show_text('bad'))\nraise RuntimeError('broken')")
        self.runtime._tick(True)
        self.execute_one_background_job()
        self.assertEqual(self.runtime._background_jobs, {})
        self.assertTrue(self.runtime._completed_work.empty())
        self.assertEqual(self.output, [])

    def test_background_validation_and_wrong_thread_cancellation(self):
        def generator():
            yield 1
        async def coroutine():
            return 1
        for work in (None, 1, generator, coroutine):
            with self.assertRaises(TypeError):
                self.api.run_in_background(work)
        for callback in (1, 'callback'):
            with self.assertRaises(TypeError):
                self.api.run_in_background(lambda: 1, callback)
            with self.assertRaises(TypeError):
                self.api.run_in_background(lambda: 1, on_error=callback)
        job = self.api.run_in_background(lambda: 1)
        self.game_thread = False
        for call in (job.cancel, lambda: self.api.run_in_background(lambda: 1)):
            with self.assertRaisesRegex(RuntimeError, "game thread"):
                call()
        self.game_thread = True
        job.cancel()

    def test_background_uses_real_workers_without_game_api_access(self):
        self.script("pass")
        self.runtime._ensure_workers = self.real_ensure_workers
        release = threading.Event()
        started = threading.Event()
        calls = []
        worker_threads = []
        def work():
            worker_threads.append(threading.get_ident())
            try:
                self.api.call_later(0, lambda: None)
            except RuntimeError:
                calls.append("guarded")
            started.set()
            if not release.wait(timeout=2):
                raise RuntimeError("test release timed out")
            return 42
        job = self.api.run_in_background(work, lambda value: calls.append((threading.get_ident(), value)))
        try:
            self.assertTrue(started.wait(timeout=2))
            self.runtime._tick(True)
            self.assertFalse(job.done)
            release.set()
            completion = self.runtime._completed_work.get(timeout=2)
            self.runtime._completed_work.put(completion)
            self.runtime._tick(True)
            self.assertEqual(calls, ["guarded", (self.game_thread_id, 42)])
            self.assertNotEqual(worker_threads[0], self.game_thread_id)
            self.assertTrue(job.done)
            self.assertEqual(len(self.runtime._workers), 2)
        finally:
            release.set()

    def test_running_background_cancel_discards_late_result_and_blocks_event_registration(self):
        self.script("pass")
        self.runtime._ensure_workers = self.real_ensure_workers
        started, release = threading.Event(), threading.Event()
        calls = []
        def work():
            try:
                self.api.on_frame(lambda: calls.append("bad event"))
            except RuntimeError:
                calls.append("event guarded")
            started.set()
            if not release.wait(timeout=2):
                raise RuntimeError("test release timed out")
            return 42
        job = self.api.run_in_background(work, calls.append)
        try:
            self.assertTrue(started.wait(timeout=2))
            job.cancel()
            release.set()
            with self.runtime._work_queue.all_tasks_done:
                self.assertTrue(self.runtime._work_queue.all_tasks_done.wait_for(
                    lambda: self.runtime._work_queue.unfinished_tasks == 0, timeout=2))
            self.runtime._tick(True)
            self.assertEqual(calls, ["event guarded"])
            self.assertTrue(job.done)
            self.assertTrue(job.cancelled)
            self.assertIsNone(job.result)
            self.assertTrue(self.runtime._completed_work.empty())
        finally:
            release.set()

    def test_background_example_reads_file_and_cancel_suppresses_display(self):
        self.script((RUNTIME / "scripts" / "example_background.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        def press(key):
            self.keys.clear()
            self.runtime._tick(True)
            self.keys.add(ord(key))
            self.runtime._tick(True)
        press("O")
        with mock.patch("time.sleep"):
            self.execute_one_background_job()
        self.runtime._tick(True)
        self.assertIn("Datei gelesen:", self.output[-1])
        press("O")
        press("P")
        count = len(self.output)
        self.execute_one_background_job()
        self.runtime._tick(True)
        self.assertEqual(len(self.output), count)
        self.assertNotIn("Disabled failing", self.log())

    def test_heading_property_delegates_and_rechecks_current_value(self):
        player = self.api.player()
        self.assertEqual(player.heading, 45)
        self.heading = 123
        self.assertEqual(player.heading, 123)
        player.heading = 90
        self.assertEqual(self.heading, 90)

    def test_save_failure_keeps_old_location_and_key_handler(self):
        self.script((RUNTIME / "scripts" / "example_teleport.py").read_text(encoding="utf-8"))
        self.runtime._tick(True)
        self.keys.add(0x76)
        self.runtime._tick(True)
        self.keys.clear()
        self.runtime._tick(True)
        def unavailable():
            raise RuntimeError("passenger")
        self.api._player_heading = unavailable
        self.position = (1, 2, 3)
        self.keys.add(0x76)
        self.runtime._tick(True)
        self.keys.clear()
        self.runtime._tick(True)
        self.api._player_heading = lambda: self.heading
        self.keys.add(0x77)
        self.runtime._tick(True)
        self.assertEqual(self.position, (12.5, -34, 8))
        self.assertNotIn("Disabled failing callback", self.log())


if __name__ == "__main__":
    unittest.main()
