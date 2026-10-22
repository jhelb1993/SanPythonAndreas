# SanPythonAndreas

Extract zip folder to your GTA:SA Install folder

Requires classic GTA:SA 1.0 US and an ASI loader. Python is included.

Save this as `SanPythonAndreas/scripts/main.py`. Keys are listed in the comments; `print()` writes to the Python log.

```python
from pathlib import Path
import math
import sanandreas as sa

bookmark = None
vehicle = None
spawned_vehicle = None
car_bookmark = None
timers = []
task = None
job = None
script_path = Path(__file__)


def player():
    p = sa.player()
    if p is None:
        raise RuntimeError("Player unavailable")
    return p


def key(name):
    # Catch unavailable actions so the key remains usable.
    def register(action):
        @sa.on_key_down(name)
        def run():
            try:
                action()
            except (RuntimeError, ValueError) as error:
                print(f"{name}: {error}")
                sa.show_text("Action unavailable. See the Python log.")
        return run
    return register


@sa.on_game_ready
def ready():
    sa.show_text("Python ready! F5: heal, F9: weapons, F10: money")


@key("F5")  # Restore health and armour.
def heal():
    p = player()
    p.health = p.max_health
    p.armour = 100


@key("F6")  # Inspect player, weapon and current vehicle.
def inspect():
    p = player()
    print("Health:", p.health, "/", p.max_health, "Armour:", p.armour)
    print("Money:", p.money, "Wanted:", p.wanted_level, "Alive:", p.is_alive)
    print("Position:", tuple(p.position), "Heading:", p.heading, "Interior:", p.interior)
    print("Weapon:", p.current_weapon, "Ammo:", p.weapon_ammo)
    print("In vehicle:", p.in_vehicle, "Driver:", p.is_driver)
    info = p.vehicle  # Detached snapshot; None on foot.
    if info is not None:
        print("Vehicle:", info.model_id, info.health, tuple(info.position))
    if bookmark is not None and p.interior == bookmark[1]:
        print("Distance to bookmark:", p.position.distance_to(bookmark[0]))
    sa.show_text("Player details written to the Python log.")


@key("F7")  # Save position, interior and heading.
def save_position():
    global bookmark
    p = player()
    bookmark = (p.position, p.interior, p.heading)
    sa.show_text("Position saved. F8: return.")


@key("F8")  # Return across indoor/outdoor areas; moves a driven vehicle too.
def return_to_position():
    if bookmark is None:
        sa.show_text("Save a position with F7 first.")
        return
    position, interior, heading = bookmark
    p = player()
    p.teleport(position, interior=interior)
    p.heading = heading


@key("F9")  # On foot: give weapons. GTA replaces weapons in the same slot.
def give_weapons():
    p = player()
    p.give_weapon(sa.WeaponType.PISTOL, 100, equip=False)
    p.give_weapon(sa.WeaponType.M4, 250)


@key("N")  # Select the pistol given with F9.
def select_pistol():
    player().select_weapon(sa.WeaponType.PISTOL)


@key("M")  # Select fists/knuckles.
def select_unarmed():
    player().select_weapon(sa.WeaponType.UNARMED)


@key("K")  # Remove only the M4.
def remove_m4():
    player().remove_weapon(sa.WeaponType.M4)


@key("L")  # Remove ALL weapons, including existing inventory.
def clear_weapons():
    player().clear_weapons()


@key("F10")  # Add $1,000.
def add_money():
    p = player()
    p.money = min(999999999, max(0, p.money) + 1000)
    sa.show_text(f"Money: ${p.money}")


@key("F11")  # Clear wanted level.
def clear_wanted():
    player().wanted_level = 0


@key("F12")  # Request three stars; GTA may enforce a lower maximum.
def raise_wanted():
    p = player()
    p.wanted_level = 3
    sa.show_text(f"Wanted level: {p.wanted_level}")


@key("B")  # Remember the current vehicle, even after leaving it.
def remember_vehicle():
    global vehicle
    if vehicle is not None:
        vehicle.close()
    vehicle = player().vehicle_handle
    sa.show_text("Vehicle remembered." if vehicle is not None else "Enter a vehicle first.")


@key("Z")  # Read fresh data from the remembered vehicle.
def inspect_vehicle():
    if vehicle is None or not vehicle.valid:
        sa.show_text("No valid remembered vehicle.")
        return
    info = vehicle.snapshot
    print("Remembered vehicle:", info.model_id, info.health, tuple(info.position))


@key("X")  # Release the handle; this does not delete the vehicle.
def release_vehicle():
    global vehicle
    if vehicle is not None:
        vehicle.close()
        vehicle = None


@key("Y")  # Cancel timers.
def stop_timers():
    for timer in timers:
        timer.cancel()
    timers.clear()


@key("T")  # Repeating game timer and one-shot real-time timer.
def start_timers():
    stop_timers()
    timers.append(sa.call_every(2, lambda: print("Two game seconds elapsed.")))
    timers.append(sa.call_later(
        5, lambda: sa.show_text("Five real seconds elapsed."), clock="real"))
    # Even real-time callbacks wait for active gameplay.


def model_demo():
    global spawned_vehicle
    # Cooperative task: yield instead of blocking the game thread.
    try:
        for remaining in (3, 2, 1):
            sa.show_text(f"Loading model in {remaining}...")
            yield sa.wait(1)
        # Keep the model lease while creating an Infernus outdoors.
        with (yield from sa.load_model(411, timeout=10)) as model:
            print("Model ready:", model.model_id, model.ready)
            p = player()
            spawned_vehicle = sa.spawn_vehicle(
                model.model_id, p.position + sa.Vector3(5, 0, 1), heading=p.heading)
            sa.show_text("Infernus spawned. E: driver, Q: exit, D: remove.")
            yield sa.wait(3)
        sa.show_text("Model lease released.")
    except (TimeoutError, RuntimeError, ValueError) as error:
        print("Model task:", error)
    finally:
        print("Model task cleaned up.")


@key("C")  # Countdown, model streaming and spawning. Choose an open outdoor area.
def start_model_demo():
    global task, spawned_vehicle
    if spawned_vehicle is not None:
        if spawned_vehicle.valid:
            sa.show_text("Remove your previous Infernus with D first.")
            return
        spawned_vehicle.close()
        spawned_vehicle = None
    if task is not None:
        task.cancel()
    task = sa.start_task(model_demo())


@key("I")  # Cancel the task; its context manager releases the model.
def cancel_task():
    if task is not None:
        task.cancel()


@key("D")  # Remove only the spawned car; rejected with occupants or attachments.
def remove_spawned_vehicle():
    global spawned_vehicle
    cancel_task()
    if spawned_vehicle is not None:
        if spawned_vehicle.valid:
            spawned_vehicle.remove()
        else:
            spawned_vehicle.close()
        spawned_vehicle = None


@key("E")  # Warp into the spawned car: -1 driver, 0 front passenger, 1/2 rear.
def enter_spawned_vehicle():
    if spawned_vehicle is None:
        sa.show_text("Spawn an Infernus with C first.")
        return
    player().enter_vehicle(spawned_vehicle, seat=-1)
    # Requires a free seat, same interior, within 50 metres and a stationary car.


@key("F3")  # Change health only; leaves body and tyre damage as-is.
def damage_spawned_vehicle():
    if spawned_vehicle is not None:
        spawned_vehicle.health = 500  # Finite 0..1000; low values can ignite cars.


@key("F2")  # Cycle the two palette indices; visible areas depend on the model.
def cycle_vehicle_colors():
    if spawned_vehicle is not None:
        spawned_vehicle.primary_color = (spawned_vehicle.primary_color + 1) % 128
        spawned_vehicle.secondary_color = (spawned_vehicle.secondary_color + 1) % 128
        print("Colors:", spawned_vehicle.primary_color, spawned_vehicle.secondary_color)


@key("F1")  # Rotate yaw by 90 degrees without rotating linear velocity.
def turn_vehicle():
    if spawned_vehicle is not None:
        spawned_vehicle.heading += 90


@key("J")  # Bring the empty car nearby, including from another interior.
def bring_vehicle():
    if spawned_vehicle is not None and not spawned_vehicle.snapshot.is_driver:
        p = player()
        angle = math.radians(p.heading)
        target = p.position + sa.Vector3(math.cos(angle) * 5, math.sin(angle) * 5, 1)
        spawned_vehicle.teleport(target, interior=p.interior)


@key("U")  # Save the car's detached position, interior and heading.
def save_car_position():
    global car_bookmark
    if spawned_vehicle is not None:
        car_bookmark = (spawned_vehicle.position, spawned_vehicle.interior, spawned_vehicle.heading)


@key("R")  # Return; drive the car or stand within 100 m of the saved destination.
def restore_car_position():
    if spawned_vehicle is not None and car_bookmark is not None:
        position, interior, heading = car_bookmark
        spawned_vehicle.teleport(position, interior=interior)
        spawned_vehicle.heading = heading
        # spawned_vehicle.position = position also works, keeping its current area.


@key("G")  # Driver only: set forward velocity to 15 m/s (54 km/h).
def accelerate_vehicle():
    if spawned_vehicle is not None and spawned_vehicle.snapshot.is_driver:
        angle = math.radians(spawned_vehicle.heading)
        spawned_vehicle.velocity = sa.Vector3(-math.sin(angle) * 15, math.cos(angle) * 15, 0)
        print("Speed (km/h):", spawned_vehicle.velocity.length() * 3.6)


@key("H")  # Clear linear velocity once; gravity/input still apply afterwards.
def stop_vehicle():
    if spawned_vehicle is not None:
        spawned_vehicle.velocity = sa.Vector3()


@key("F4")  # Full repair: health, body, doors, windows, tyres and engine/fire state.
def repair_spawned_vehicle():
    if spawned_vehicle is not None:
        spawned_vehicle.repair()  # Normal cars only; cannot revive a wreck.


@key("Q")  # Request normal exit animation. Stop the car first.
def leave_vehicle():
    player().leave_vehicle()
    # Exit finishes in later frames; wait until in_vehicle is False before D.


def read_script():
    # Worker thread: file I/O only. Never call the GTA API here.
    return len(script_path.read_text(encoding="utf-8").splitlines())


def read_complete(lines):
    # Completion runs on the game thread; GTA calls are allowed.
    sa.show_text(f"Background read finished: {lines} lines.")


@key("O")  # Background file read with success and error callbacks.
def start_background_read():
    global job
    if job is not None:
        job.cancel()
    job = sa.run_in_background(read_script, read_complete, on_error=print)


@key("P")  # Suppress result delivery; running worker code may finish.
def cancel_background_read():
    if job is not None:
        job.cancel()
```
