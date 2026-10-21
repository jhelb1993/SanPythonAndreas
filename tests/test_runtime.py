"""Exercise lifecycle/error handling with a fake native API; no GTA required."""
import importlib.util
import pathlib
import shutil
import sys
import tempfile
import types
import unittest

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
        self.api._host_api_version = 11
        self.api._binding_backend = "test-host"
        self.api._sdk_revision = "test"
        self.api.show_text = self.output.append
        self.keys = set()
        self.focus = True
        self.stats = [25.0, 100.0]
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
        self.errors = []
        self.runtime._notify_error = self.errors.append

    def tearDown(self):
        sys.stdout, sys.stderr = self.stdout, self.stderr
        self.runtime._log.close()
        if self.previous_api is None:
            sys.modules.pop("sanandreas", None)
        else:
            sys.modules["sanandreas"] = self.previous_api
        self.temp.cleanup()

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
        self.api._host_api_version = 11

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
