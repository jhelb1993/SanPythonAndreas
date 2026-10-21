"""Load with `import example_armour` in main.py. F9 restores standard armour."""
import sanandreas as sa


@sa.on_key_down("F9")
def equip_armour():
    player = sa.player()
    if player is None or player.health <= 0:
        return
    player.armour = 100
    print("Ruestung:", player.armour)
    sa.show_text("Ruestung aufgefuellt!")
