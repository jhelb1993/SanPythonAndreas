"""Run the actual compiled bindings with a native fake host, outside GTA."""
import importlib.util
import pathlib
import sys
import unittest
import threading

module_path = pathlib.Path(sys.argv.pop(1)).resolve()
spec = importlib.util.spec_from_file_location('sanandreas', module_path)
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)


class NativeBindingsTests(unittest.TestCase):
    def setUp(self):
        sa._test_reset()
        sa._test_reset_weapons()
        sa._test_vehicle()
        sa._test_game_time(1000)
        sa._test_reset_models()
        sa._test_reset_vehicle_handles()

    def test_package_metadata(self):
        self.assertEqual(sa._host_api_version, 16)
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

    def test_health_setter_rechecks_player_limit_after_stat_changes(self):
        sa._test_max_health(150)
        self.assertEqual(sa._player_health(), (25, 150))
        sa._set_player_health(150)
        self.assertEqual(sa._player_health(), (150, 150))
        with self.assertRaises(ValueError):
            sa._set_player_health(151)
        sa._test_max_health(100)
        # Reading a lower maximum must not damage an over-healed player.
        self.assertEqual(sa._player_health(), (150, 100))
        with self.assertRaises(ValueError):
            sa._set_player_health(150)
        sa._set_player_health(100)
        self.assertEqual(sa._player_health(), (100, 100))

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
                 lambda: sa._set_player_heading(90), sa._player_armour,
                 lambda: sa._set_player_armour(100), sa._player_money,
                 lambda: sa._set_player_money(100), sa._player_wanted_level,
                 lambda: sa._set_player_wanted_level(3), sa._player_weapon,
                 lambda: sa._give_player_weapon(22), lambda: sa._select_player_weapon(0),
                 lambda: sa._remove_player_weapon(22), sa._clear_player_weapons, sa._player_vehicle,
                 sa._game_time_ms, sa._require_game_thread, lambda: sa._request_model(411),
                 lambda: sa._model_ready(1), lambda: sa._release_model(1), sa._capture_player_vehicle,
                 lambda: sa._vehicle_handle_valid(1), lambda: sa._vehicle_info(1), lambda: sa._close_vehicle_handle(1)]
        for call in calls:
            with self.assertRaisesRegex(RuntimeError, 'game thread'):
                call()

    def test_armour_reads_writes_and_rejects_invalid_values(self):
        self.assertEqual(sa._player_armour(), 10)
        for value in (0, 25.5, 100):
            sa._set_player_armour(value)
            self.assertEqual(sa._player_armour(), value)
        for value in (-1, 101, float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sa._set_player_armour(value)
        for value in (True, '100', None):
            with self.subTest(value=value), self.assertRaises(TypeError):
                sa._set_player_armour(value)
        self.assertEqual(sa._player_armour(), 100)
        self.assertEqual(sa._player_health(), (25, 100))

    def test_armour_checks_missing_and_dead_player(self):
        sa._test_dead()
        self.assertEqual(sa._player_armour(), 10)
        with self.assertRaises(RuntimeError):
            sa._set_player_armour(100)
        self.assertEqual(sa._player_armour(), 10)
        sa._test_ready(False)
        for call in (sa._player_armour, lambda: sa._set_player_armour(100)):
            with self.assertRaises(RuntimeError):
                call()

    def test_money_and_wanted_read_write_bounds(self):
        self.assertEqual(sa._player_money(), 500)
        self.assertEqual(sa._player_wanted_level(), 1)
        for setter, getter, maximum in ((sa._set_player_money, sa._player_money, 999999999),
                                         (sa._set_player_wanted_level, sa._player_wanted_level, 6)):
            for value in (0, 1, maximum):
                setter(value)
                self.assertEqual(getter(), value)
            for value in (-1, maximum + 1):
                with self.assertRaises(ValueError):
                    setter(value)
            for value in (True, False, 1.0, '1', None, float('nan'), float('inf')):
                with self.assertRaises(TypeError):
                    setter(value)
            for value in (10**100, -10**100):
                with self.assertRaises(OverflowError):
                    setter(value)
            self.assertEqual(getter(), maximum)
        self.assertEqual(sa._player_health(), (25, 100))

    def test_money_and_wanted_require_active_living_player_for_writes(self):
        sa._test_dead()
        for setter in (sa._set_player_money, sa._set_player_wanted_level):
            with self.assertRaises(RuntimeError):
                setter(0)
        self.assertEqual(sa._player_money(), 500)
        self.assertEqual(sa._player_wanted_level(), 1)
        sa._test_ready(False)
        for call in (sa._player_money, sa._player_wanted_level,
                     lambda: sa._set_player_money(0), lambda: sa._set_player_wanted_level(0)):
            with self.assertRaises(RuntimeError):
                call()

    def test_wanted_respects_host_limits_and_cheats(self):
        sa._test_wanted_maximum(2)
        sa._set_player_wanted_level(6)
        self.assertEqual(sa._player_wanted_level(), 2)
        sa._test_wanted_blocked(True)
        sa._set_player_wanted_level(0)
        self.assertEqual(sa._player_wanted_level(), 2)

    def test_weapons_give_select_remove_and_clear(self):
        self.assertEqual(sa._player_weapon(), (0, 0))
        sa._give_player_weapon(22, 100, equip=False)
        self.assertEqual(sa._player_weapon(), (0, 0))
        sa._select_player_weapon(22)
        self.assertEqual(sa._player_weapon(), (22, 100))
        sa._give_player_weapon(22, 50)
        self.assertEqual(sa._player_weapon(), (22, 150))
        sa._remove_player_weapon(24)  # Same slot, different weapon: must preserve pistol.
        self.assertEqual(sa._player_weapon(), (22, 150))
        sa._select_player_weapon(0)
        sa._select_player_weapon(22)
        sa._remove_player_weapon(22)
        self.assertEqual(sa._player_weapon(), (0, 0))
        sa._remove_player_weapon(22)  # Idempotent.
        with self.assertRaisesRegex(RuntimeError, 'own'):
            sa._select_player_weapon(22)
        sa._give_player_weapon(22)
        sa._give_player_weapon(31)
        sa._clear_player_weapons()
        self.assertEqual(sa._player_weapon(), (0, 0))
        for weapon in (22, 31):
            with self.assertRaises(RuntimeError):
                sa._select_player_weapon(weapon)

    def test_weapons_reject_invalid_ids_ammo_and_equip(self):
        for value in (-1, 19, 20, 21, 39, 40, 44, 45, 46, 47, 999):
            for call in (sa._give_player_weapon, sa._select_player_weapon, sa._remove_player_weapon):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    call(value)
        for value in (True, 22.0, 'PISTOL', None):
            for call in (sa._give_player_weapon, sa._select_player_weapon, sa._remove_player_weapon):
                with self.assertRaises(TypeError):
                    call(value)
        with self.assertRaises(ValueError):
            sa._give_player_weapon(0)
        for ammo in (-1, 100000):
            with self.assertRaises(ValueError):
                sa._give_player_weapon(22, ammo)
        for ammo in (True, 1.0, '100', None):
            with self.assertRaises(TypeError):
                sa._give_player_weapon(22, ammo)
        for equip in (1, None, 'yes'):
            with self.assertRaises(TypeError):
                sa._give_player_weapon(22, equip=equip)
        with self.assertRaises(OverflowError):
            sa._give_player_weapon(22, 10**100)
        self.assertEqual(sa._player_weapon(), (0, 0))

    def test_weapons_ammo_limit_slot_replacement_and_host_failures(self):
        sa._give_player_weapon(22, 99999)
        with self.assertRaises(ValueError):
            sa._give_player_weapon(22, 1)
        self.assertEqual(sa._player_weapon(), (22, 99999))
        sa._give_player_weapon(25, 10)
        sa._give_player_weapon(27, 20)
        self.assertEqual(sa._player_weapon(), (27, 30))
        for status in (1, 2, 5):
            sa._test_weapon_status(status)
            with self.assertRaises(RuntimeError):
                sa._give_player_weapon(31, 100)
            self.assertEqual(sa._player_weapon(), (27, 30))
        sa._test_weapon_status(2)
        for call in (lambda: sa._select_player_weapon(0), lambda: sa._remove_player_weapon(27), sa._clear_player_weapons):
            with self.assertRaises(RuntimeError):
                call()
        sa._test_weapon_status(0)
        sa._test_dead()
        with self.assertRaises(RuntimeError):
            sa._give_player_weapon(22)
        sa._test_ready(False)
        with self.assertRaises(RuntimeError):
            sa._player_weapon()

    def test_vehicle_snapshots_are_detached_and_immutable(self):
        self.assertIsNone(sa._player_vehicle())
        sa._test_vehicle(1)
        before = sa._player_vehicle()
        self.assertIsInstance(before, sa.VehicleInfo)
        self.assertEqual((before.model_id, before.health, before.is_driver), (411, 750, True))
        self.assertEqual(tuple(before.position), (10, 20, 30))
        sa._test_vehicle(1, 400, 500, False)
        sa._test_vehicle_position(100, 200, 300)
        after = sa._player_vehicle()
        self.assertEqual((after.model_id, after.health, after.is_driver), (400, 500, False))
        self.assertEqual(tuple(after.position), (100, 200, 300))
        self.assertEqual((before.model_id, before.health, before.is_driver), (411, 750, True))
        self.assertEqual(tuple(before.position), (10, 20, 30))
        for field, value in (("model_id", 400), ("health", 1000), ("is_driver", False), ("position", sa.Vector3())):
            with self.assertRaises(AttributeError):
                setattr(before, field, value)
        with self.assertRaises(AttributeError):
            before.position.x = 100
        sa._test_vehicle(0)
        self.assertIsNone(sa._player_vehicle())
        self.assertEqual(before.model_id, 411)

    def test_vehicle_query_handles_transitions_and_missing_player(self):
        sa._test_vehicle(-1)
        with self.assertRaises(RuntimeError):
            sa._player_vehicle()
        sa._test_vehicle(1, 411, -5, True)
        sa._test_dead()
        self.assertEqual(sa._player_vehicle().health, -5)
        sa._test_ready(False)
        with self.assertRaises(RuntimeError):
            sa._player_vehicle()

    def test_game_clock_is_unsigned_and_readable_while_paused(self):
        for milliseconds in (0, 1000, 0xFFFFFFFF):
            sa._test_game_time(milliseconds)
            self.assertEqual(sa._game_time_ms(), milliseconds)
        sa._test_ready(False)
        self.assertEqual(sa._game_time_ms(), 0xFFFFFFFF)

    def test_model_loading_pins_once_and_release_is_independent(self):
        first = sa._request_model(411)
        second = sa._request_model(411)
        self.assertNotEqual(first, second)
        self.assertFalse(sa._model_ready(first))
        self.assertEqual(sa._test_model_refs(411), 0)
        sa._test_model_loaded(411, True)
        self.assertTrue(sa._model_ready(first))
        self.assertTrue(sa._model_ready(first))
        self.assertTrue(sa._model_ready(second))
        self.assertEqual(sa._test_model_refs(411), 2)
        sa._test_ready(False)
        sa._release_model(first)  # Cleanup is allowed while paused.
        sa._release_model(first)
        self.assertEqual(sa._test_model_refs(411), 1)
        sa._test_ready(True)
        self.assertTrue(sa._model_ready(second))
        sa._release_model(second)
        self.assertEqual(sa._test_model_refs(411), 0)
        with self.assertRaises(RuntimeError):
            sa._model_ready(first)

    def test_model_loading_validates_ids_and_lease_limits(self):
        for model in (0, -1, 20000):
            with self.assertRaises(ValueError):
                sa._request_model(model)
        for model in (True, 411.0, 'infernus', None):
            with self.assertRaises(TypeError):
                sa._request_model(model)
        sa._test_model_invalid(True)
        with self.assertRaises(ValueError):
            sa._request_model(19999)
        sa._test_model_invalid(False)
        tokens = [sa._request_model(411) for _ in range(256)]
        with self.assertRaises(RuntimeError):
            sa._request_model(411)
        sa._release_model(tokens.pop())
        tokens.append(sa._request_model(411))
        for token in tokens:
            sa._release_model(token)

    def test_model_loading_detects_forced_unload_and_inactive_game(self):
        token = sa._request_model(411)
        sa._test_model_loaded(411, True)
        self.assertTrue(sa._model_ready(token))
        sa._test_model_loaded(411, False)
        with self.assertRaises(RuntimeError):
            sa._model_ready(token)
        sa._release_model(token)
        self.assertEqual(sa._test_model_refs(411), 0)
        sa._test_ready(False)
        with self.assertRaises(RuntimeError):
            sa._request_model(411)

    def test_actual_worker_thread_cannot_call_game_api(self):
        errors = []
        def worker():
            for call in (sa._require_game_thread, sa._player_health, lambda: sa.show_text('worker'),
                         lambda: sa._request_model(411)):
                try:
                    call()
                except RuntimeError as error:
                    errors.append(str(error))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 4)
        self.assertTrue(all('game thread' in error for error in errors))

    def test_vehicle_handle_tracks_original_vehicle_after_exit_and_switch(self):
        self.assertIsNone(sa._capture_player_vehicle())
        sa._test_vehicle(1)
        first = sa._capture_player_vehicle()
        old_snapshot = sa._vehicle_info(first)
        sa._test_handle_current(2)
        sa._test_vehicle(1, 400, 500, True)
        second = sa._capture_player_vehicle()
        self.assertNotEqual(first, second)
        sa._test_handle_data(1, 600, 40, 50, 60)
        current = sa._vehicle_info(first)
        self.assertEqual((current.model_id, current.health, current.is_driver), (411, 600, False))
        self.assertEqual(tuple(current.position), (40, 50, 60))
        self.assertEqual((old_snapshot.model_id, old_snapshot.health), (411, 750))
        self.assertEqual(sa._vehicle_info(second).model_id, 400)
        sa._test_vehicle(0)
        self.assertTrue(sa._vehicle_handle_valid(first))
        self.assertEqual(sa._vehicle_info(first).model_id, 411)
        sa._close_vehicle_handle(first)
        self.assertFalse(sa._vehicle_handle_valid(first))
        self.assertTrue(sa._vehicle_handle_valid(second))

    def test_vehicle_handle_rejects_reused_slot_even_when_generation_matches(self):
        sa._test_vehicle(1)
        old = sa._capture_player_vehicle()
        sa._test_handle_remove_and_reuse(1)
        self.assertFalse(sa._vehicle_handle_valid(old))
        with self.assertRaises(sa.InvalidVehicleError):
            sa._vehicle_info(old)
        new = sa._capture_player_vehicle()
        self.assertTrue(sa._vehicle_handle_valid(new))
        self.assertEqual(sa._vehicle_info(new).model_id, 400)
        sa._close_vehicle_handle(old)
        self.assertTrue(sa._vehicle_handle_valid(new))

    def test_vehicle_handles_validate_limits_pause_and_close(self):
        self.assertTrue(issubclass(sa.InvalidVehicleError, RuntimeError))
        sa._test_vehicle(1)
        sa._test_handle_reference_failure(True)
        with self.assertRaises(RuntimeError):
            sa._capture_player_vehicle()
        sa._test_handle_reference_failure(False)
        handles = [sa._capture_player_vehicle() for _ in range(128)]
        with self.assertRaises(RuntimeError):
            sa._capture_player_vehicle()
        sa._test_ready(False)
        self.assertFalse(sa._vehicle_handle_valid(handles[0]))
        with self.assertRaises(RuntimeError):
            sa._vehicle_info(handles[0])
        sa._close_vehicle_handle(handles[0])
        sa._close_vehicle_handle(handles[0])
        sa._test_ready(True)
        replacement = sa._capture_player_vehicle()
        self.assertNotEqual(replacement, handles[0])
        self.assertEqual(sa._vehicle_info(replacement).model_id, 411)
        for handle in handles + [replacement]:
            sa._close_vehicle_handle(handle)
        for value in (True, 1.0, '1', None):
            for call in (sa._vehicle_handle_valid, sa._vehicle_info, sa._close_vehicle_handle):
                with self.assertRaises(TypeError):
                    call(value)

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
