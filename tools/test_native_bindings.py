"""Run the actual compiled bindings with a native fake host, outside GTA."""
import importlib.util
import pathlib
import sys
import unittest

module_path = pathlib.Path(sys.argv.pop(1)).resolve()
spec = importlib.util.spec_from_file_location('sanandreas', module_path)
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)


class NativeBindingsTests(unittest.TestCase):
    def setUp(self):
        sa._test_reset()

    def test_package_metadata(self):
        self.assertEqual(sa._host_api_version, 6)
        self.assertEqual(sa._binding_backend, 'pybind11-2.13.6')
        self.assertEqual(len(sa._sdk_revision), 40)

    def test_health_read_write_and_missing_player(self):
        self.assertEqual(sa._player_health(), (25.0, 100.0))
        sa._set_player_health(100)
        self.assertEqual(sa._player_health(), (100.0, 100.0))
        sa._test_ready(False)
        self.assertIsNone(sa._player_health())
        with self.assertRaises(RuntimeError):
            sa._set_player_health(100)

    def test_health_rejects_invalid_values(self):
        for value in (-1, 101, float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sa._set_player_health(value)
        for value in (True, '100', None):
            with self.subTest(value=value), self.assertRaises(TypeError):
                sa._set_player_health(value)
        self.assertEqual(sa._player_health()[0], 25)

    def test_dead_player_cannot_be_revived(self):
        sa._test_dead()
        with self.assertRaises(RuntimeError):
            sa._set_player_health(100)

    def test_hud_text_validation(self):
        sa.show_text('Python bereit')
        self.assertEqual(sa._test_last_text(), 'Python bereit')
        for value in ('', 'a' * 201, 'a\0b'):
            with self.assertRaises(ValueError):
                sa.show_text(value)
        with self.assertRaises(UnicodeEncodeError):
            sa.show_text('Grüße')
        with self.assertRaises(TypeError):
            sa.show_text(b'bytes')
        sa._test_ready(False)
        with self.assertRaises(RuntimeError):
            sa.show_text('paused')

    def test_key_code_validation(self):
        self.assertTrue(sa._is_key_down(0x74))
        self.assertFalse(sa._is_key_down(0x75))
        for key in (0, 255):
            with self.assertRaises(ValueError):
                sa._is_key_down(key)
        with self.assertRaises(TypeError):
            sa._is_key_down('F5')

    def test_thread_guards(self):
        sa._test_thread(False)
        calls = [lambda: sa.show_text('x'), sa._player_health,
                 lambda: sa._set_player_health(100), lambda: sa._is_key_down(0x74), sa._has_focus, sa._player_position, sa._player_interior,
                 lambda: sa._teleport_player(sa.Vector3()), sa._player_heading,
                 lambda: sa._set_player_heading(90)]
        for call in calls:
            with self.assertRaisesRegex(RuntimeError, 'game thread'):
                call()

    def test_vector_operations(self):
        v = sa.Vector3(3, 4, 12)
        self.assertEqual(tuple(v), (3, 4, 12))
        self.assertEqual(sa.Vector3(), sa.Vector3(0, 0, 0))
        self.assertAlmostEqual(v.length(), 13)
        self.assertEqual(v + sa.Vector3(1, -2, 0), sa.Vector3(4, 2, 12))
        self.assertEqual(v - sa.Vector3(1, 2, 3), sa.Vector3(2, 2, 9))
        self.assertEqual(-v, sa.Vector3(-3, -4, -12))
        self.assertEqual(v * 2, 2 * v)
        self.assertEqual(v / 2, sa.Vector3(1.5, 2, 6))
        self.assertAlmostEqual(v.distance_to(sa.Vector3()), 13)
        self.assertNotEqual(v, sa.Vector3())
        self.assertNotEqual(v, (3, 4, 12))
        self.assertIn('Vector3(', repr(v))
        with self.assertRaises(AttributeError):
            v.x = 99

    def test_vector_rejects_invalid_components_and_division(self):
        for bad in (float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                sa.Vector3(bad, 0, 0)
            with self.assertRaises(ValueError):
                sa.Vector3(1, 2, 3) * bad
        with self.assertRaises(TypeError):
            sa.Vector3('wrong', 0, 0)
        with self.assertRaises(ZeroDivisionError):
            sa.Vector3(1, 2, 3) / 0

    def test_position_is_a_detached_snapshot(self):
        before = sa._player_position()
        self.assertIsInstance(before, sa.Vector3)
        self.assertEqual(tuple(before), (12.5, -34, 8))
        sa._test_position(100, 200, 300)
        self.assertEqual(tuple(before), (12.5, -34, 8))
        self.assertEqual(tuple(sa._player_position()), (100, 200, 300))
        sa._test_position_available(False)
        self.assertIsNone(sa._player_position())
        sa._test_ready(False)
        self.assertIsNone(sa._player_position())

    def test_teleport_updates_position_and_checks_state(self):
        self.assertEqual(sa._player_interior(), 0)
        sa._teleport_player(sa.Vector3(100, 200, 30))
        self.assertEqual(tuple(sa._player_position()), (100, 200, 30))
        sa._test_teleport_status(2)
        with self.assertRaisesRegex(RuntimeError, 'transition'):
            sa._teleport_player(sa.Vector3(), 1)
        self.assertEqual(tuple(sa._player_position()), (100, 200, 30))
        sa._test_teleport_status(3)
        with self.assertRaisesRegex(RuntimeError, 'driver'):
            sa._teleport_player(sa.Vector3())
        sa._test_dead()
        with self.assertRaises(RuntimeError):
            sa._teleport_player(sa.Vector3())
        sa._test_ready(False)
        with self.assertRaises(RuntimeError):
            sa._player_interior()

    def test_teleport_switches_interiors_and_preserves_area_when_omitted(self):
        for area in (1, 6, 255, 0):
            sa._teleport_player(sa.Vector3(100, 200, 30), area)
            self.assertEqual(sa._player_interior(), area)
            self.assertEqual(tuple(sa._player_position()), (100, 200, 30))
            sa._teleport_player(sa.Vector3())
            self.assertEqual(sa._player_interior(), area)

    def test_teleport_rejects_invalid_targets_and_interiors(self):
        for target in (sa.Vector3(1e100, 0, 0), sa.Vector3(0, -20001, 0),
                       sa.Vector3(0, 0, -1001), sa.Vector3(0, 0, 10001)):
            with self.assertRaises(ValueError):
                sa._teleport_player(target)
        for area in (-1, 256):
            with self.assertRaises(ValueError):
                sa._teleport_player(sa.Vector3(), area)
        for area in (True, 0.0, '0'):
            with self.assertRaises(TypeError):
                sa._teleport_player(sa.Vector3(), area)
        with self.assertRaises(TypeError):
            sa._teleport_player((1, 2, 3))
        self.assertEqual(tuple(sa._player_position()), (12.5, -34, 8))

    def test_heading_normalizes_degrees_and_rejects_invalid_values(self):
        self.assertEqual(sa._player_heading(), 45)
        for value, expected in ((90, 90), (360, 0), (-90, 270), (810, 90),
                                (-720, 0), (359.999999999, 0)):
            sa._set_player_heading(value)
            self.assertAlmostEqual(sa._player_heading(), expected)
        for value in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError):
                sa._set_player_heading(value)
        for value in (True, '90', None):
            with self.assertRaises(TypeError):
                sa._set_player_heading(value)

    def test_heading_handles_missing_player_dead_and_unsupported_vehicle(self):
        sa._test_heading_status(3)
        for call in (sa._player_heading, lambda: sa._set_player_heading(90)):
            with self.assertRaisesRegex(RuntimeError, 'driver'):
                call()
        sa._test_heading_status(0)
        sa._test_dead()
        with self.assertRaises(RuntimeError):
            sa._set_player_heading(90)
        sa._test_ready(False)
        for call in (sa._player_heading, lambda: sa._set_player_heading(90)):
            with self.assertRaises(RuntimeError):
                call()


if __name__ == '__main__':
    unittest.main(verbosity=2)
