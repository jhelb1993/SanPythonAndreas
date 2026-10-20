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
        self.api._host_api_version = 5
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
        self.position = (12.5, -34.0, 8.0)
        self.api._player_position = lambda: types.SimpleNamespace(
            x=self.position[0], y=self.position[1], z=self.position[2]
        ) if self.position is not None else None
        self.heading = 45.0
        self.api._player_heading = lambda: self.heading
        self.api._set_player_heading = self.set_heading
        self.interior = 0
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

    def set_heading(self, value):
        self.heading = value

    def teleport(self, target, interior=None):
        if interior is not None and interior != self.interior:
            raise RuntimeError("interior mismatch")
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
        self.api._host_api_version = 5

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
        press(0x77)
        self.assertEqual(self.position, (100, 200, 300))
        self.assertEqual(self.heading, 180.0)
        self.interior = 0
        press(0x77)
        self.assertEqual(self.position, (12.5, -34, 8))
        self.assertEqual(self.heading, 45.0)
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
