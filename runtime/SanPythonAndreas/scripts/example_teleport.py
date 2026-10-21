"""F7 saves position, interior and heading; F8 restores all three across areas.

Load with `import example_teleport` in main.py. On foot or in the driver seat.
Save on clear, level ground with room for your vehicle. No ground search occurs.
"""
import sanandreas as sa

_saved = None


@sa.on_key_down("F7")
def save_location():
    global _saved
    player = sa.player()
    if player is not None:
        try:
            saved = (player.position, player.interior, player.heading)
        except RuntimeError as error:
            print("Speichern abgelehnt:", error)
            sa.show_text("Speichern nicht moeglich. Details im Python-Log.")
            return
        _saved = saved
        sa.show_text("Position gespeichert. F8: zurueck teleportieren")


@sa.on_key_down("F8")
def return_to_location():
    player = sa.player()
    if player is None:
        return
    if _saved is None:
        sa.show_text("Zuerst mit F7 eine Position speichern.")
        return
    try:
        player.teleport(_saved[0], interior=_saved[1])
        player.heading = _saved[2]
    except RuntimeError as error:
        # An unavailable teleport must not disable this key handler.
        print("Teleport abgelehnt:", error)
        sa.show_text("Teleport nicht moeglich. Details im Python-Log.")
    else:
        sa.show_text("Zur gespeicherten Position teleportiert.")
