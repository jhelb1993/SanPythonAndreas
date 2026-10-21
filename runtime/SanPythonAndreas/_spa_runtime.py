"""Internal bootstrap; imported once by the native game-thread callback."""
import pathlib
import runpy
import sys
import traceback
import math
import time
from enum import IntEnum

import sanandreas as sa

BOOTSTRAP_API_VERSION = 12
if sys.platform == "win32" and sys.version_info[:2] != (3, 11):
    raise RuntimeError("This package requires bundled Python 3.11; loaded " + sys.version.split()[0])
if getattr(sa, "_host_api_version", None) != BOOTSTRAP_API_VERSION:
    raise RuntimeError("ASI/runtime/bootstrap versions differ; replace the complete matching package")

_root = pathlib.Path(__file__).resolve().parent
_log = (_root / "SanPythonAndreas.log").open("a", encoding="utf-8", buffering=1)
sys.stdout = _log
sys.stderr = _log
print("SanPythonAndreas", sa.__version__, "API", sa._host_api_version,
      "backend", sa._binding_backend, "SDK", sa._sdk_revision)
print("Python:", sys.version, "executable:", sys.executable)
print("Bootstrap:", __file__)
_ready_callbacks = []
_frame_callbacks = []
_key_callbacks = {}
_key_was_down = {}
_keys_active = False
_started = False
_loaded = False
_failed = False
_timers = {}
_next_timer_id = 0
_game_last = None
_game_elapsed = 0.0
_real_now = time.monotonic
_perf_now = time.perf_counter


class Timer:
    """Cancellation handle. Create with call_later/call_every on the game thread."""
    __slots__ = ("_id", "_callback", "_clock", "_interval", "_due", "_done", "_cancelled", "_owner")

    def __init__(self, token, callback, clock, interval, due):
        self._id, self._callback = token, callback
        self._clock, self._interval, self._due = clock, interval, due
        self._done = self._cancelled = False
        self._owner = getattr(callback, "__module__", "<unknown>")

    @property
    def done(self):
        return self._done

    @property
    def cancelled(self):
        return self._cancelled

    @property
    def owner(self):
        """Callback module for diagnostics; per-mod lifecycle management follows later."""
        return self._owner

    def cancel(self):
        sa._require_game_thread()
        if not self._done:
            self._cancelled = True
            _finish_timer(self)


def _finish_timer(timer):
    _timers.pop(timer._id, None)
    timer._done = True
    timer._callback = None


def _cancel_timers(clock=None):
    for timer in tuple(_timers.values()):
        if clock is None or timer._clock == clock:
            timer._cancelled = True
            _finish_timer(timer)


def _sample_game_clock():
    global _game_last, _game_elapsed
    current = sa._game_time_ms()
    if _game_last is not None:
        delta = (current - _game_last) & 0xFFFFFFFF
        if delta > 0x7FFFFFFF:
            # Backward clock reset (e.g. new game). Natural uint32 wrap is small.
            _cancel_timers("game")
            _game_elapsed = 0.0
            print("Game clock reset; cancelled game-time timers")
        else:
            _game_elapsed += delta / 1000.0
    _game_last = current
    return _game_elapsed


def _clock_now(clock):
    return _sample_game_clock() if clock == "game" else _real_now()


def _schedule(delay, callback, clock, repeat):
    global _next_timer_id
    sa._require_game_thread()
    if isinstance(delay, bool) or not isinstance(delay, (int, float)):
        raise TypeError("timer duration must be a number, not bool")
    delay = float(delay)
    if not math.isfinite(delay) or delay < 0 or (repeat and delay == 0):
        raise ValueError("timer duration must be finite and nonnegative (repeat interval > 0)")
    if not callable(callback):
        raise TypeError("timer callback must be callable")
    if not isinstance(clock, str):
        raise TypeError("clock must be 'game' or 'real'")
    if clock not in ("game", "real"):
        raise ValueError("clock must be 'game' or 'real'")
    now = _clock_now(clock)
    _next_timer_id += 1
    timer = Timer(_next_timer_id, callback, clock, delay if repeat else None, now + delay)
    _timers[timer._id] = timer
    return timer


def call_later(delay, callback, *, clock="game"):
    """Call once after delay seconds; zero means no earlier than the next tick."""
    return _schedule(delay, callback, clock, False)


def call_every(interval, callback, *, clock="game"):
    """Repeat with a delay after each call; missed intervals are never replayed."""
    return _schedule(interval, callback, clock, True)


def _run_timers(snapshot):
    dispatched = 0
    for timer in snapshot:
        if dispatched >= 64:
            break
        if timer._done or _timers.get(timer._id) is not timer:
            continue
        now = _clock_now(timer._clock)
        if timer._done or now < timer._due:
            continue
        dispatched += 1
        callback = timer._callback
        if timer._interval is None:
            _finish_timer(timer)
        started = _perf_now()
        try:
            callback()
        except BaseException:
            traceback.print_exc()
            _finish_timer(timer)
            print("Disabled failing timer:", timer.owner, getattr(callback, "__name__", repr(callback)))
        else:
            if not timer._done:
                due = _clock_now(timer._clock) + timer._interval
                # Round-robin for repeats when more than 64 timers are due.
                if not timer._done:
                    timer._due = due
                    _timers.pop(timer._id, None)
                    _timers[timer._id] = timer
        finally:
            elapsed = _perf_now() - started
            if elapsed >= 0.05:
                print(f"Slow timer callback ({elapsed * 1000:.1f} ms):", timer.owner,
                      getattr(callback, "__name__", repr(callback)))


def _register(callbacks, callback):
    if not callable(callback):
        raise TypeError("event callback must be callable")
    if callback not in callbacks:
        callbacks.append(callback)
    return callback


def on_game_ready(callback):
    """Register a no-argument callback, run once after main.py loads."""
    return _register(_ready_callbacks, callback)


def on_frame(callback):
    """Register a short no-argument callback for each active game frame."""
    return _register(_frame_callbacks, callback)


def _virtual_key(key):
    if isinstance(key, bool):
        raise TypeError("key must be a name or a virtual-key integer")
    if isinstance(key, int):
        if 1 <= key <= 254:
            return key
        raise ValueError("virtual key must be between 1 and 254")
    if not isinstance(key, str):
        raise TypeError("key must be a name or a virtual-key integer")
    name = key.strip().upper()
    if len(name) == 1 and ("A" <= name <= "Z" or "0" <= name <= "9"):
        return ord(name)
    if name.startswith("F") and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
        return 0x70 + int(name[1:]) - 1
    names = {"SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09, "ESC": 0x1B,
             "ESCAPE": 0x1B, "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12,
             "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28}
    if name not in names:
        raise ValueError("unknown key: " + key)
    return names[name]


def on_key_down(key):
    """Run once per observed press while GTA is active and has focus."""
    virtual_key = _virtual_key(key)

    def decorate(callback):
        if virtual_key not in _key_was_down:
            _key_was_down[virtual_key] = sa._is_key_down(virtual_key)
        return _register(_key_callbacks.setdefault(virtual_key, []), callback)

    return decorate


class WeaponType(IntEnum):
    UNARMED = 0
    BRASSKNUCKLE = 1
    GOLFCLUB = 2
    NIGHTSTICK = 3
    KNIFE = 4
    BASEBALLBAT = 5
    SHOVEL = 6
    POOLCUE = 7
    KATANA = 8
    CHAINSAW = 9
    DILDO1 = 10
    DILDO2 = 11
    VIBE1 = 12
    VIBE2 = 13
    FLOWERS = 14
    CANE = 15
    GRENADE = 16
    TEARGAS = 17
    MOLOTOV = 18
    PISTOL = 22
    PISTOL_SILENCED = 23
    DESERT_EAGLE = 24
    SHOTGUN = 25
    SAWNOFF = 26
    SPAS12 = 27
    MICRO_UZI = 28
    MP5 = 29
    AK47 = 30
    M4 = 31
    TEC9 = 32
    COUNTRYRIFLE = 33
    SNIPERRIFLE = 34
    RLAUNCHER = 35
    RLAUNCHER_HS = 36
    FLAMETHROWER = 37
    MINIGUN = 38
    SPRAYCAN = 41
    EXTINGUISHER = 42
    CAMERA = 43


class Player:
    """A view of the current player, resolved again on every property access."""
    __slots__ = ()

    @staticmethod
    def _stats():
        stats = sa._player_health()
        if stats is None:
            raise RuntimeError("no active player")
        return stats

    @property
    def health(self):
        return self._stats()[0]

    @health.setter
    def health(self, value):
        sa._set_player_health(value)

    @property
    def is_alive(self):
        return self.health > 0

    @property
    def vehicle(self):
        """Detached read-only vehicle snapshot, or None while on foot."""
        return sa._player_vehicle()

    @property
    def in_vehicle(self):
        return self.vehicle is not None

    @property
    def is_driver(self):
        vehicle = self.vehicle
        return vehicle is not None and vehicle.is_driver

    @property
    def current_weapon(self):
        """Active weapon ID; may include equipment outside WeaponType."""
        return sa._player_weapon()[0]

    @property
    def weapon_ammo(self):
        """Total ammunition for the active weapon, including its clip."""
        return sa._player_weapon()[1]

    def give_weapon(self, weapon, ammo=100, *, equip=True):
        sa._give_player_weapon(weapon, ammo, equip=equip)

    def select_weapon(self, weapon):
        sa._select_player_weapon(weapon)

    def remove_weapon(self, weapon):
        sa._remove_player_weapon(weapon)

    def clear_weapons(self):
        sa._clear_player_weapons()

    @property
    def money(self):
        return sa._player_money()

    @money.setter
    def money(self, value):
        sa._set_player_money(value)

    @property
    def wanted_level(self):
        return sa._player_wanted_level()

    @wanted_level.setter
    def wanted_level(self, value):
        sa._set_player_wanted_level(value)

    @property
    def armour(self):
        """Current armour; setting supports finite values from 0 to 100."""
        return sa._player_armour()

    @armour.setter
    def armour(self, value):
        sa._set_player_armour(value)

    @property
    def position(self):
        position = sa._player_position()
        if position is None:
            raise RuntimeError("no active player position")
        return position

    @position.setter
    def position(self, value):
        self.teleport(value)

    @property
    def heading(self):
        """Heading in degrees [0, 360); driver uses the vehicle's heading."""
        return sa._player_heading()

    @heading.setter
    def heading(self, value):
        sa._set_player_heading(value)

    @property
    def interior(self):
        return sa._player_interior()

    def teleport(self, target, *, interior=None):
        """Move to target; optional interior switches world area (0 is outside)."""
        sa._teleport_player(target, interior)

    @property
    def max_health(self):
        """Current player-specific health limit maintained by GTA."""
        return self._stats()[1]


def player():
    """Return a view of the current player, or None if no player is available."""
    return None if sa._player_health() is None else Player()


sa.on_game_ready = on_game_ready
sa.on_frame = on_frame
sa.on_key_down = on_key_down
sa.Player = Player
sa.WeaponType = WeaponType
sa.player = player
sa.Timer = Timer
sa.call_later = call_later
sa.call_every = call_every


def _notify_error(details):
    # Called on the game thread, outside DllMain. Visible even when the user
    # cannot locate the log; a popup failure must not hide the original error.
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, details + "\n\nBootstrap: " + str(__file__),
            "SanPythonAndreas - Python-Fehler", 0x10
        )
    except Exception:
        pass


def _dispatch(callbacks):
    # Snapshot allows registration during dispatch without unbounded iteration.
    for callback in tuple(callbacks):
        try:
            callback()
        except BaseException:
            # Includes SystemExit: a script must not close the game.
            traceback.print_exc()
            callbacks.remove(callback)
            print("Disabled failing callback:", getattr(callback, "__name__", repr(callback)))


def _poll_keys(active):
    global _keys_active
    if not active or not sa._has_focus():
        _keys_active = False
        return
    # Update all keys before dispatching callbacks. On first frame/resume regain
    # a baseline: keys already held down must be released before they can fire.
    current = {key: sa._is_key_down(key) for key in tuple(_key_callbacks)}
    pressed = [key for key, down in current.items()
               if down and not _key_was_down.get(key, down)] if _keys_active else []
    _key_was_down.update(current)
    _keys_active = True
    for key in pressed:
        _dispatch(_key_callbacks[key])


def _tick(ready):
    global _loaded, _started, _failed
    if _failed:
        return
    _sample_game_clock()
    timer_snapshot = tuple(_timers.values())
    if not ready:
        _poll_keys(False)
        return
    if not _loaded:
        _loaded = True
        try:
            # run_path executes as __main__, retaining the original script behavior.
            runpy.run_path(str(_root / "scripts" / "main.py"), run_name="__main__")
        except BaseException:
            _failed = True
            details = traceback.format_exc()
            print(details)
            _ready_callbacks.clear()
            _frame_callbacks.clear()
            _key_callbacks.clear()
            _key_was_down.clear()
            _cancel_timers()
            print("main.py failed; restart the game after fixing the script")
            _notify_error(details)
            return
        print("main.py loaded")
    if not _started:
        _started = True
        _dispatch(_ready_callbacks)
        _ready_callbacks.clear()
    _poll_keys(True)
    _dispatch(_frame_callbacks)
    _run_timers(timer_snapshot)
