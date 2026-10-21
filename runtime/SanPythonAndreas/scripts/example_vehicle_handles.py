"""B remembers the current vehicle, Z reads it later, X closes the handle.

Import example_vehicle_handles in main.py. Exit/switch vehicles before pressing Z.
The handle does not prevent despawning and never deletes a vehicle.
"""
import sanandreas as sa

_saved = None


@sa.on_key_down("B")
def remember_vehicle():
    global _saved
    player = sa.player()
    if player is None:
        return
    try:
        vehicle = player.vehicle_handle
        if vehicle is None:
            sa.show_text("Zuerst in ein Fahrzeug setzen. Alter Handle bleibt erhalten.")
            return
        if _saved is not None:
            _saved.close()
        _saved = vehicle
        sa.show_text("Fahrzeug gespeichert. Z: lesen, X: Handle schliessen")
    except RuntimeError as error:
        print("Fahrzeug-Handle nicht verfuegbar:", error)
        sa.show_text("Fahrzeug-Handle derzeit nicht verfuegbar.")


@sa.on_key_down("Z")
def read_remembered_vehicle():
    if _saved is None or _saved.closed:
        sa.show_text("Zuerst mit B ein Fahrzeug speichern.")
        return
    try:
        snapshot = _saved.snapshot
        print("Gespeichertes Fahrzeug:", snapshot.model_id, snapshot.health, tuple(snapshot.position))
        sa.show_text(f"Gespeichert: Modell {snapshot.model_id}, Zustand {snapshot.health:.0f}")
    except sa.InvalidVehicleError:
        sa.show_text("Gespeichertes Fahrzeug existiert nicht mehr.")
    except RuntimeError as error:
        print("Fahrzeugdaten nicht verfuegbar:", error)
        sa.show_text("Fahrzeugdaten derzeit nicht verfuegbar.")


@sa.on_key_down("X")
def forget_vehicle():
    global _saved
    if _saved is not None:
        _saved.close()
        _saved = None
    sa.show_text("Handle geschlossen. Fahrzeug bleibt bestehen.")
