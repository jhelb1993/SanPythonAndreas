"""Editor types for the built-in GTA module; not an executable implementation."""
from collections.abc import Callable, Iterator, Generator
from typing import TypeVar, NamedTuple
from enum import IntEnum

__version__: str

_Callback = TypeVar("_Callback", bound=Callable[[], None])


def show_text(text: str, /) -> None:
    """Show 1–200 ASCII characters in the GTA help HUD on the game thread."""
    ...


def on_game_ready(callback: _Callback, /) -> _Callback: ...
def on_frame(callback: _Callback, /) -> _Callback: ...
def on_key_down(key: str | int, /) -> Callable[[_Callback], _Callback]:
    """One call per observed press; keys held during pause/focus changes are ignored."""
    ...


class Timer:
    """Cancellation handle returned by call_later/call_every."""
    @property
    def done(self) -> bool: ...
    @property
    def cancelled(self) -> bool: ...
    @property
    def owner(self) -> str:
        """Callback module for diagnostics; not a complete mod lifecycle identity."""
        ...
    def cancel(self) -> None:
        """Game thread only; safe to repeat. Releases the callback reference."""
        ...


def call_later(delay: float, callback: Callable[[], None], *, clock: str = "game") -> Timer:
    """Call once after seconds. Zero waits until at least the next tick.

    clock: 'game' follows GTA time; 'real' follows monotonic real time.
    All callbacks wait for active gameplay and run on the game thread.
    """
    ...


def call_every(interval: float, callback: Callable[[], None], *, clock: str = "game") -> Timer:
    """Repeat after a positive interval from the previous callback's completion.

    No catch-up burst. At most one call per timer per active frame; 64 total.
    Callback errors stop that timer. Cancel via the returned handle.
    """
    ...


class Wait(NamedTuple):
    seconds: float
    clock: str


class Task:
    """Cooperative generator task, created by start_task()."""
    @property
    def done(self) -> bool: ...
    @property
    def cancelled(self) -> bool: ...
    @property
    def owner(self) -> str: ...
    @property
    def result(self) -> object:
        """Return value after successful completion; otherwise None."""
        ...
    @property
    def error(self) -> str | None:
        """Execution/cleanup error description; does not retain the traceback."""
        ...
    def cancel(self) -> None:
        """Game thread only. Closes a started generator, running its finally.

        Self-cancellation takes effect after the current step yields/returns.
        Cleanup must not yield. Cancelling before the first step runs no body.
        """
        ...


def wait(seconds: float = 0, *, clock: str = "game") -> Wait:
    """Inert request: yield this from a task. Zero waits until the next tick."""
    ...


def start_task(generator: Generator[Wait, None, object]) -> Task:
    """Schedule a fresh generator object; async/await coroutines are unsupported.

    Starts next active tick and resumes on the game thread, sharing timer budget.
    """
    ...


class Model:
    """Explicit streaming lease. Use with/finally; release on the game thread."""
    @property
    def model_id(self) -> int: ...
    @property
    def released(self) -> bool: ...
    @property
    def ready(self) -> bool:
        """Check readiness; first successful check acquires an owned model/TXD ref."""
        ...
    def release(self) -> None:
        """Idempotent. Drops only this lease; does not force unloading shared models."""
        ...
    def __enter__(self) -> Model: ...
    def __exit__(self, exc_type: object, exc_value: object, exc_trace: object) -> bool: ...


def load_model(model_id: int, *, timeout: float = 10) -> Generator[Wait, None, Model]:
    """Use model = yield from load_model(id), then release via with/finally.

    Model IDs 1..19999; metadata and streamability are checked. Timeout uses real
    seconds and is checked at active frames; ready wins if both happen together.
    Cancelling a pending task releases the request. No blocking load-all call.
    """
    ...


class Vector3:
    """Immutable, finite coordinates. Changes through arithmetic return new values."""
    def __init__(self, x: float = 0, y: float = 0, z: float = 0) -> None: ...
    @property
    def x(self) -> float: ...
    @property
    def y(self) -> float: ...
    @property
    def z(self) -> float: ...
    def __add__(self, other: Vector3) -> Vector3: ...
    def __sub__(self, other: Vector3) -> Vector3: ...
    def __neg__(self) -> Vector3: ...
    def __mul__(self, scalar: float) -> Vector3: ...
    def __rmul__(self, scalar: float) -> Vector3: ...
    def __truediv__(self, scalar: float) -> Vector3: ...
    def __eq__(self, other: object) -> bool: ...
    def __ne__(self, other: object) -> bool: ...
    def __iter__(self) -> Iterator[float]: ...
    def length(self) -> float: ...
    def distance_to(self, other: Vector3) -> float: ...


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


class VehicleInfo:
    """Immutable snapshot, not a handle. Read player.vehicle again to refresh."""
    @property
    def model_id(self) -> int: ...
    @property
    def is_driver(self) -> bool: ...
    @property
    def health(self) -> float:
        """Raw GTA vehicle health; normally 1000 when undamaged, may be negative."""
        ...
    @property
    def position(self) -> Vector3: ...


class Player:
    """View of the current player. Every access rechecks game state and thread."""
    @property
    def health(self) -> float: ...
    @health.setter
    def health(self, value: float) -> None: ...
    @property
    def armour(self) -> float:
        """Current armour; setter accepts 0..100 and requires a living player."""
        ...
    @armour.setter
    def armour(self, value: float) -> None: ...
    @property
    def money(self) -> int:
        """Current balance. Setter accepts integers 0..999999999; HUD updates immediately."""
        ...
    @money.setter
    def money(self, value: int) -> None: ...
    @property
    def wanted_level(self) -> int:
        """Stars 0..6; setter respects the game's current maximum and cheats.

        Read back after setting to obtain the effective level. This is not a lock.
        """
        ...
    @wanted_level.setter
    def wanted_level(self, value: int) -> None: ...
    @property
    def current_weapon(self) -> int:
        """Active weapon ID, including equipment not listed in WeaponType."""
        ...
    @property
    def weapon_ammo(self) -> int:
        """Total ammo for the active weapon, including the clip."""
        ...
    def give_weapon(self, weapon: WeaponType | int, ammo: int = 100, *, equip: bool = True) -> None:
        """On foot only. Synchronously loads models; may briefly pause the game.

        Adds ammo or replaces the weapon in its slot using GTA's rules.
        Ammo argument and existing slot ammo together must be <=99999.
        Supports IDs 1..18, 22..38, 41..43. Equipment/satchel support is deferred.
        """
        ...
    def select_weapon(self, weapon: WeaponType | int) -> None:
        """On foot only; requires ownership. ID 0 selects the fists/knuckles slot."""
        ...
    def remove_weapon(self, weapon: WeaponType | int) -> None:
        """On foot only; missing weapon or ID 0 is a no-op. Exact ID match."""
        ...
    def clear_weapons(self) -> None:
        """On foot only; removes the entire inventory, including existing weapons/equipment."""
        ...
    @property
    def max_health(self) -> float:
        """Read-only player-specific health limit, maintained by GTA."""
        ...
    @property
    def is_alive(self) -> bool:
        """Health > 0. Missing player raises RuntimeError, as other properties do."""
        ...
    @property
    def vehicle(self) -> VehicleInfo | None:
        """Fresh snapshot for driver or passenger; None on foot.

        Inconsistent seats during entry/exit and missing player raise RuntimeError.
        """
        ...
    @property
    def in_vehicle(self) -> bool: ...
    @property
    def is_driver(self) -> bool:
        """False on foot and in a passenger seat."""
        ...
    @property
    def position(self) -> Vector3:
        """Detached snapshot. Assignment keeps the current interior; teleport can change it."""
        ...

    @position.setter
    def position(self, value: Vector3) -> None: ...
    @property
    def heading(self) -> float:
        """Degrees in [0, 360); driver uses vehicle. Setter normalizes finite angles."""
        ...
    @heading.setter
    def heading(self, value: float) -> None: ...
    @property
    def interior(self) -> int: ...
    def teleport(self, target: Vector3, *, interior: int | None = None) -> None:
        """Optional interior switches world area; 0 is outside, None keeps it.

        Driver vehicle and occupants move too; speed is cleared.
        Calls during a door transition raise RuntimeError. Area changes reset
        the camera and portal context; shop/mission scripts are not activated.

        Synchronously streams the destination; may briefly pause the game.
        Does not find ground or guarantee the destination is unobstructed.
        """
        ...


def player() -> Player | None:
    """Return None when paused/loading or no player exists; game thread only."""
    ...
