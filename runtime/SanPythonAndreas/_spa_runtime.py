"""Internal bootstrap; imported once by the native game-thread callback."""
import pathlib
import runpy
import sys
import traceback
import math
import time
import inspect
import types
import queue
import threading
from typing import NamedTuple
from enum import IntEnum

import sanandreas as sa

BOOTSTRAP_API_VERSION = 22
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
_tasks = {}
_claimed_generators = set()
_next_task_id = 0
_cancelling = False
_models = {}
_vehicles = {}
_background_jobs = {}
_next_background_id = 0
_work_queue = queue.Queue(maxsize=32)
_completed_work = queue.SimpleQueue()
_workers = []
_background_lock = threading.Lock()
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
    global _cancelling
    previous = _cancelling
    _cancelling = True
    try:
        for task in tuple(_tasks.values()):
            if clock is None or task._clock == clock:
                task.cancel()
        for timer in tuple(_timers.values()):
            if clock is None or timer._clock == clock:
                timer._cancelled = True
                _finish_timer(timer)
        # Leases describe streaming resources, not durable save-game identities.
        # Invalidate them on any detected game-clock reset, including real-time tasks.
        for model in tuple(_models.values()):
            model.release()
        sa._cleanup_owned_vehicles()
        for vehicle in tuple(_vehicles.values()):
            vehicle.close()
        for job in tuple(_background_jobs.values()):
            job.cancel()
        # Canceled workers cannot commit any more envelopes after this drain.
        with _background_lock:
            while True:
                try:
                    _completed_work.get_nowait()
                except queue.Empty:
                    break
    finally:
        _cancelling = previous


def _sample_game_clock():
    global _game_last, _game_elapsed
    current = sa._game_time_ms()
    if _game_last is not None:
        delta = (current - _game_last) & 0xFFFFFFFF
        if delta > 0x7FFFFFFF:
            # Backward clock reset (e.g. new game). Natural uint32 wrap is small.
            _game_last = current
            _game_elapsed = 0.0
            _cancel_timers("game")
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
    if _cancelling:
        raise RuntimeError("cannot schedule during runtime cleanup or clock reset")
    delay = _duration(delay, repeat)
    _validate_clock(clock)
    if not callable(callback):
        raise TypeError("timer callback must be callable")
    now = _clock_now(clock)
    _next_timer_id += 1
    timer = Timer(_next_timer_id, callback, clock, delay if repeat else None, now + delay)
    _timers[timer._id] = timer
    return timer


def _duration(delay, repeat=False):
    if isinstance(delay, bool) or not isinstance(delay, (int, float)):
        raise TypeError("duration must be a number, not bool")
    delay = float(delay)
    if not math.isfinite(delay) or delay < 0 or (repeat and delay == 0):
        raise ValueError("duration must be finite and nonnegative (repeat interval > 0)")
    return delay


def _validate_clock(clock):
    if not isinstance(clock, str):
        raise TypeError("clock must be 'game' or 'real'")
    if clock not in ("game", "real"):
        raise ValueError("clock must be 'game' or 'real'")


def call_later(delay, callback, *, clock="game"):
    """Call once after delay seconds; zero means no earlier than the next tick."""
    return _schedule(delay, callback, clock, False)


def call_every(interval, callback, *, clock="game"):
    """Repeat with a delay after each call; missed intervals are never replayed."""
    return _schedule(interval, callback, clock, True)


class Wait(NamedTuple):
    """Inert wait request. Use yield wait(...) inside a generator task."""
    seconds: float
    clock: str


def wait(seconds=0, *, clock="game"):
    seconds = _duration(seconds)
    _validate_clock(clock)
    return Wait(seconds, clock)


class Task:
    """Cooperative generator task; each step runs on the game thread."""
    __slots__ = ("_id", "_generator", "_timer", "_clock", "_running", "_done",
                 "_cancelled", "_owner", "_result", "_error")

    def __init__(self, token, generator):
        self._id, self._generator = token, generator
        self._timer = None
        self._clock = "game"
        self._running = self._done = self._cancelled = False
        self._owner = generator.gi_frame.f_globals.get("__name__", "<unknown>")
        self._result = self._error = None

    @property
    def done(self):
        return self._done

    @property
    def cancelled(self):
        return self._cancelled

    @property
    def owner(self):
        return self._owner

    @property
    def result(self):
        """Generator return value; None until completion, on error or cancellation."""
        return self._result

    @property
    def error(self):
        """Error description, without retaining exception traceback/game objects."""
        return self._error

    def cancel(self):
        sa._require_game_thread()
        if self._done:
            return
        self._cancelled = True
        if not self._running:
            self._stop(close=True)

    def _stop(self, *, close, result=None):
        self._done = True
        self._result = None if self._cancelled or self._error else result
        _tasks.pop(self._id, None)
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        generator, self._generator = self._generator, None
        if generator is not None:
            _claimed_generators.discard(id(generator))
            if close:
                try:
                    generator.close()
                except BaseException as error:
                    traceback.print_exc()
                    self._error = f"{type(error).__name__}: {error}"
                    print("Task cleanup failed:", self.owner)

    def _arm(self, request):
        self._clock = request.clock
        timer = call_later(request.seconds, self._step, clock=request.clock)
        timer._owner = self.owner
        if self._done or self._cancelled:
            timer.cancel()
        else:
            self._timer = timer

    def _step(self):
        self._timer = None
        if self._done:
            return
        if self._cancelled:
            self._stop(close=True)
            return
        self._running = True
        try:
            request = next(self._generator)
        except StopIteration as finished:
            self._stop(close=False, result=finished.value)
            return
        except BaseException as error:
            traceback.print_exc()
            self._error = f"{type(error).__name__}: {error}"
            self._stop(close=True)
            print("Disabled failing task:", self.owner)
            return
        finally:
            self._running = False
        if self._cancelled:
            self._stop(close=True)
            return
        try:
            if not isinstance(request, Wait):
                raise TypeError("task must yield sa.wait(...); async/await and bare yield are unsupported")
            # Validate even if the request was built directly with Wait(...).
            self._arm(wait(request.seconds, clock=request.clock))
        except BaseException as error:
            traceback.print_exc()
            self._error = f"{type(error).__name__}: {error}"
            self._stop(close=True)
            print("Disabled failing task:", self.owner)


def start_task(generator):
    """Start a fresh generator on the next active tick; returns a Task handle."""
    global _next_task_id
    sa._require_game_thread()
    if _cancelling:
        raise RuntimeError("cannot start tasks during runtime cleanup or clock reset")
    if not isinstance(generator, types.GeneratorType):
        raise TypeError("pass a generator object, e.g. work(); async coroutines are unsupported")
    if id(generator) in _claimed_generators or inspect.getgeneratorstate(generator) != inspect.GEN_CREATED:
        raise ValueError("task requires a fresh generator that is not already scheduled")
    _next_task_id += 1
    task = Task(_next_task_id, generator)
    _tasks[task._id] = task
    _claimed_generators.add(id(generator))
    try:
        task._arm(wait())
    except BaseException:
        task._stop(close=True)
        raise
    return task


class Model:
    """Explicit lease for a loaded streaming resource; release on the game thread."""
    __slots__ = ("_model_id", "_token")

    def __init__(self, model_id, token):
        self._model_id, self._token = model_id, token

    @property
    def model_id(self):
        return self._model_id

    @property
    def released(self):
        return self._token == 0

    @property
    def ready(self):
        if self.released:
            raise RuntimeError("model lease has been released; load the model again")
        return sa._model_ready(self._token)

    def release(self):
        sa._require_game_thread()
        if not self.released:
            sa._release_model(self._token)
            _models.pop(self._token, None)
            self._token = 0

    def __enter__(self):
        if not self.ready:
            raise RuntimeError("model is not loaded")
        return self

    def __exit__(self, exc_type, exc_value, exc_trace):
        self.release()
        return False


def load_model(model_id, *, timeout=10):
    """Generator: model = yield from load_model(id). Timeout uses real seconds.

    Use a with block or finally to release the returned lease. Closing this
    generator while it is waiting releases its pending request automatically.
    """
    sa._require_game_thread()
    if _cancelling:
        raise RuntimeError("cannot request models during runtime cleanup or clock reset")
    timeout = _duration(timeout)
    token = sa._request_model(model_id)
    model = Model(model_id, token)
    _models[token] = model
    transferred = False
    deadline = _real_now() + timeout
    try:
        while True:
            if model.ready:
                transferred = True
                return model
            if _real_now() >= deadline:
                raise TimeoutError(f"model {model_id} did not load within {timeout:g} real seconds")
            yield wait(clock="real")
    finally:
        if not transferred:
            model.release()


class BackgroundJob:
    """Worker result handle. Cancellation suppresses delivery; running work may continue."""
    __slots__ = ("_id", "_work", "_on_done", "_on_error", "_owner", "_done",
                 "_cancelled", "_result", "_error")

    def __init__(self, token, work, on_done, on_error):
        self._id, self._work = token, work
        self._on_done, self._on_error = on_done, on_error
        self._owner = getattr(work, "__module__", "<unknown>")
        self._done = self._cancelled = False
        self._result = self._error = None

    @property
    def done(self):
        """Completed/delivered, failed or cancelled (not merely finished in the worker)."""
        return self._done

    @property
    def cancelled(self):
        return self._cancelled

    @property
    def owner(self):
        return self._owner

    @property
    def result(self):
        return self._result

    @property
    def error(self):
        """Formatted error text; no exception/traceback objects retained."""
        return self._error

    def cancel(self):
        sa._require_game_thread()
        with _background_lock:
            if self._done:
                return
            self._done = self._cancelled = True
        self._work = self._on_done = self._on_error = None
        _background_jobs.pop(self._id, None)


def _execute_background(job):
    # Worker code uses no GTA APIs. The job's immutable result envelope is
    # delivered by _tick; even BaseException must not silently kill a worker.
    function = job._work
    result = error = None
    try:
        if not job._cancelled and function is not None:
            result = function()
            if isinstance(result, (types.GeneratorType, types.CoroutineType, types.AsyncGeneratorType)):
                if hasattr(result, "close"):
                    result.close()
                raise TypeError("background work must return data, not a generator/coroutine")
    except BaseException:
        result = None
        error = traceback.format_exc()
    finally:
        job._work = None
    with _background_lock:
        if not job._cancelled:
            _completed_work.put((job, result, error))


def _background_worker():
    while True:
        job = _work_queue.get()
        try:
            if job is None:
                return
            _execute_background(job)
        finally:
            _work_queue.task_done()
            job = None  # Do not retain the last completed result handle while idle.


def _ensure_workers():
    # Lazy, process-lifetime daemon workers. No joins or waits on the game thread.
    while len(_workers) < 2:
        worker = threading.Thread(target=_background_worker,
                                  name=f"SanPythonAndreas-worker-{len(_workers) + 1}", daemon=True)
        worker.start()
        _workers.append(worker)


def run_in_background(work, on_done=None, *, on_error=None):
    """Run a no-argument function off-thread and deliver its result on the game thread."""
    global _next_background_id
    sa._require_game_thread()
    if _cancelling:
        raise RuntimeError("cannot submit background work during cleanup or clock reset")
    if (not callable(work) or inspect.isgeneratorfunction(work) or inspect.iscoroutinefunction(work)
            or inspect.isasyncgenfunction(work)):
        raise TypeError("background work must be a normal callable, not a generator/coroutine")
    for callback in (on_done, on_error):
        if callback is not None and not callable(callback):
            raise TypeError("completion callbacks must be callable or None")
    if len(_background_jobs) >= 64:
        raise RuntimeError("too many pending background results; wait or cancel unused jobs")
    _ensure_workers()
    _next_background_id += 1
    job = BackgroundJob(_next_background_id, work, on_done, on_error)
    _background_jobs[job._id] = job
    try:
        _work_queue.put_nowait(job)
    except queue.Full:
        job.cancel()
        raise RuntimeError("background work queue is full; retry later") from None
    return job


def _take_background_results():
    results = []
    for _ in range(32):
        try:
            results.append(_completed_work.get_nowait())
        except queue.Empty:
            break
    return results


def _deliver_background(results):
    for job, result, error in results:
        if job._cancelled or _background_jobs.get(job._id) is not job:
            continue
        _background_jobs.pop(job._id, None)
        job._done, job._result, job._error = True, result, error
        callback = job._on_error if error is not None else job._on_done
        job._on_done = job._on_error = None
        if error is not None:
            print("Background work failed:", job.owner, error)
        if callback is not None:
            started = _perf_now()
            try:
                callback(error if error is not None else result)
            except BaseException:
                details = traceback.format_exc()
                job._error = (error + "\n" if error else "") + details
                print("Background completion callback failed:", job.owner, details)
            finally:
                elapsed = _perf_now() - started
                if elapsed >= 0.05:
                    print(f"Slow background completion ({elapsed * 1000:.1f} ms):", job.owner)


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
    sa._require_game_thread()
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


class Vehicle:
    """Checked handle to one vehicle. Closing unregisters it, never deletes it."""
    __slots__ = ("_token",)

    def __init__(self, token):
        self._token = token

    @property
    def closed(self):
        return self._token == 0

    @property
    def valid(self):
        return not self.closed and sa._vehicle_handle_valid(self._token)

    @property
    def snapshot(self):
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        return sa._vehicle_info(self._token)

    @property
    def model_id(self):
        return self.snapshot.model_id

    @property
    def health(self):
        return self.snapshot.health

    @health.setter
    def health(self, value):
        sa._require_game_thread()
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        sa._set_vehicle_health(self._token, value)

    def repair(self):
        """Restore normal-car health and damage; cannot resurrect a wreck."""
        sa._require_game_thread()
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        sa._repair_vehicle(self._token)

    @property
    def position(self):
        return self.snapshot.position

    @position.setter
    def position(self, value):
        self.teleport(value)

    @property
    def interior(self):
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        return sa._vehicle_interior(self._token)

    def teleport(self, target, *, interior=None):
        """Move this car, clearing velocity. None keeps its current interior.

        A player-driven car moves its occupants and can change world area.
        Empty cars may target only the player's area within 100 m.
        """
        sa._require_game_thread()
        if _cancelling:
            raise RuntimeError("cannot teleport vehicles during cleanup or clock reset")
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        sa._teleport_vehicle(self._token, target, interior)

    def _colors(self):
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        return sa._vehicle_colors(self._token)

    def _motion(self):
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        return sa._vehicle_motion(self._token)

    @property
    def heading(self):
        return self._motion()[0]

    @heading.setter
    def heading(self, value):
        sa._require_game_thread()
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        sa._set_vehicle_heading(self._token, value)

    @property
    def velocity(self):
        return self._motion()[1]

    @velocity.setter
    def velocity(self, value):
        sa._require_game_thread()
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        sa._set_vehicle_velocity(self._token, value)

    def _set_color(self, channel, value):
        sa._require_game_thread()
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        sa._set_vehicle_color(self._token, channel, value)

    @property
    def primary_color(self):
        return self._colors()[0]

    @primary_color.setter
    def primary_color(self, value):
        self._set_color(0, value)

    @property
    def secondary_color(self):
        return self._colors()[1]

    @secondary_color.setter
    def secondary_color(self, value):
        self._set_color(1, value)

    def close(self):
        sa._require_game_thread()
        if not self.closed:
            sa._close_vehicle_handle(self._token)
            _vehicles.pop(self._token, None)
            self._token = 0

    def remove(self):
        """Delete a script-created, empty, unattached vehicle, then close this handle."""
        sa._require_game_thread()
        if self.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        sa._remove_vehicle(self._token)
        self.close()

    def __enter__(self):
        _ = self.snapshot  # Validate state and object identity before entering.
        return self

    def __exit__(self, exc_type, exc_value, exc_trace):
        self.close()
        return False


class Player:
    """A view of the current player, resolved again on every property access."""
    __slots__ = ()

    def enter_vehicle(self, vehicle, *, seat=-1):
        """Warp into a free seat of a nearby stationary car: -1 driver, 0..2 passenger."""
        sa._require_game_thread()
        if _cancelling:
            raise RuntimeError("cannot enter vehicles during cleanup or clock reset")
        if not isinstance(vehicle, Vehicle):
            raise TypeError("vehicle must be a Vehicle handle")
        if vehicle.closed:
            raise sa.InvalidVehicleError("vehicle handle is closed")
        sa._enter_player_vehicle(vehicle._token, seat)

    def leave_vehicle(self):
        """Request animated exit from a stationary car; on foot is a no-op."""
        sa._require_game_thread()
        if _cancelling:
            raise RuntimeError("cannot leave vehicles during cleanup or clock reset")
        sa._leave_player_vehicle()

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
    def vehicle_handle(self):
        """New checked handle to this vehicle, or None on foot. Close when unused."""
        if _cancelling:
            raise RuntimeError("cannot acquire vehicle handles during cleanup or clock reset")
        token = sa._capture_player_vehicle()
        if token is None:
            return None
        vehicle = Vehicle(token)
        _vehicles[token] = vehicle
        return vehicle

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


def spawn_vehicle(model_id, position, *, heading=0):
    """Create a normal automobile outdoors; its model must already be loaded.

    Keep a load_model() lease while calling. Position is passed to GTA's script
    factory; no obstacle checks. remove() deletes it; close() only closes a handle.
    Up to 32 owned cars. Reset/error cleanup deletes empty cars and returns
    occupied/attached cars to GTA. Ownership is runtime-wide, not per mod.
    """
    sa._require_game_thread()
    if _cancelling:
        raise RuntimeError("cannot spawn vehicles during cleanup or clock reset")
    token = sa._spawn_vehicle(model_id, position, heading)
    vehicle = Vehicle(token)
    _vehicles[token] = vehicle
    return vehicle


def player():
    """Return a view of the current player, or None if no player is available."""
    return None if sa._player_health() is None else Player()


sa.on_game_ready = on_game_ready
sa.on_frame = on_frame
sa.on_key_down = on_key_down
sa.Player = Player
sa.Vehicle = Vehicle
sa.spawn_vehicle = spawn_vehicle
sa.WeaponType = WeaponType
sa.player = player
sa.Timer = Timer
sa.call_later = call_later
sa.call_every = call_every
sa.Wait = Wait
sa.Task = Task
sa.wait = wait
sa.start_task = start_task
sa.Model = Model
sa.load_model = load_model
sa.BackgroundJob = BackgroundJob
sa.run_in_background = run_in_background


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
    background_results = _take_background_results()
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
    _deliver_background(background_results)
    _run_timers(timer_snapshot)
