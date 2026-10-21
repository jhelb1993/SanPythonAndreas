"""Import example_spawn_vehicle in main.py.

C: spawn, E: driver, Q: exit, D: remove, F3: health 500, F4: repair.

Use outdoors with room next to the player. Exit before removing the car.
"""
import math
import sanandreas as sa

_vehicle = None
_task = None


def _spawn():
    global _vehicle
    try:
        with (yield from sa.load_model(411, timeout=10)) as model:
            player = sa.player()
            if player is None:
                return
            # Five metres to the side. GTA's script factory handles placement;
            # there is no obstacle check, so choose an open area.
            angle = math.radians(player.heading)
            offset = sa.Vector3(math.cos(angle) * 5, math.sin(angle) * 5, 1)
            _vehicle = sa.spawn_vehicle(
                model.model_id, player.position + offset, heading=player.heading)
            sa.show_text("Infernus: E driver, Q exit, D remove, F3 damage, F4 repair.")
    except (TimeoutError, RuntimeError, ValueError) as error:
        print("Vehicle spawn failed:", error)
        sa.show_text("Cannot spawn here. See the Python log.")


@sa.on_key_down("C")
def spawn_infernus():
    global _task, _vehicle
    if _task is not None and not _task.done:
        sa.show_text("Model is still loading. D: cancel.")
        return
    if _vehicle is not None:
        if _vehicle.valid:
            sa.show_text("Remove your previous Infernus with D first.")
            return
        _vehicle.close()
        _vehicle = None
    _task = sa.start_task(_spawn())


@sa.on_key_down("D")
def remove_infernus():
    global _vehicle
    if _task is not None:
        _task.cancel()
    if _vehicle is None:
        return
    try:
        if _vehicle.valid:
            _vehicle.remove()
        else:
            _vehicle.close()
        _vehicle = None
        sa.show_text("Infernus removed.")
    except RuntimeError as error:
        print("Vehicle removal rejected:", error)
        sa.show_text("Exit the vehicle and detach trailers before removing it.")


@sa.on_key_down("E")
def enter_infernus():
    try:
        player = sa.player()
        if player is None or _vehicle is None:
            sa.show_text("Spawn an Infernus with C first.")
            return
        player.enter_vehicle(_vehicle)  # seat=-1 driver; seat=0 front passenger
        sa.show_text("Driver seat. Stop the car, then Q to exit.")
    except (RuntimeError, ValueError) as error:
        print("Vehicle entry rejected:", error)
        sa.show_text("Need a free seat in a nearby stationary car.")


@sa.on_key_down("F3")
def damage_infernus():
    try:
        if _vehicle is None:
            sa.show_text("Spawn an Infernus with C first.")
            return
        _vehicle.health = 500
        sa.show_text(f"Infernus health: {_vehicle.health:.0f}. F4: repair.")
    except (RuntimeError, ValueError) as error:
        print("Vehicle health change rejected:", error)
        sa.show_text("Cannot change this vehicle. See the Python log.")


@sa.on_key_down("F4")
def repair_infernus():
    try:
        if _vehicle is None:
            sa.show_text("Spawn an Infernus with C first.")
            return
        _vehicle.repair()
        sa.show_text(f"Infernus repaired. Health: {_vehicle.health:.0f}")
    except RuntimeError as error:
        print("Vehicle repair rejected:", error)
        sa.show_text("Cannot repair this vehicle. See the Python log.")


@sa.on_key_down("Q")
def leave_vehicle():
    try:
        player = sa.player()
        if player is not None:
            player.leave_vehicle()
    except RuntimeError as error:
        print("Vehicle exit rejected:", error)
        sa.show_text("Stop the car and finish any entry/exit first.")
