"""V displays player state and the current vehicle snapshot. Import in main.py."""
import sanandreas as sa


@sa.on_key_down("V")
def show_vehicle():
    player = sa.player()
    if player is None:
        return
    try:
        vehicle = player.vehicle
        if vehicle is None:
            text = "Spieler zu Fuss" if player.is_alive else "Spieler tot"
        else:
            role = "Fahrer" if vehicle.is_driver else "Passagier"
            text = f"{role}: Modell {vehicle.model_id}, Zustand {vehicle.health:.0f}"
            print("Fahrzeugposition:", tuple(vehicle.position))
        print(text)
        sa.show_text(text)
    except RuntimeError as error:
        print("Fahrzeugabfrage nicht verfuegbar:", error)
        sa.show_text("Fahrzeugwechsel laeuft. Erneut V druecken.")
