"""Internal bootstrap; imported once by the native game-thread callback."""
import pathlib
import runpy
import sys
import traceback

import sanandreas as sa

BOOTSTRAP_API_VERSION = 6
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
        return self._stats()[1]


def player():
    """Return a view of the current player, or None if no player is available."""
    return None if sa._player_health() is None else Player()


sa.on_game_ready = on_game_ready
sa.on_frame = on_frame
sa.on_key_down = on_key_down
sa.Player = Player
sa.player = player


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
