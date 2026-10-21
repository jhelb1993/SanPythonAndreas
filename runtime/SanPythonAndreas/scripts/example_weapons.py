"""N: give/equip pistol, M: select unarmed, J: select pistol, K: remove pistol.

Load with `import example_weapons` in main.py. Changes require being on foot.
The pistol replaces any other handgun in its slot; this example does not restore it.
"""
import sanandreas as sa


def _act(action):
    player = sa.player()
    if player is None or player.health <= 0:
        return
    try:
        action(player)
        print("Waffe:", player.current_weapon, "Munition:", player.weapon_ammo)
        sa.show_text(f"Waffe: {player.current_weapon}, Munition: {player.weapon_ammo}")
    except (RuntimeError, ValueError) as error:
        print("Waffenaktion abgelehnt:", error)
        sa.show_text("Waffenaktion nicht moeglich. Details im Python-Log.")


@sa.on_key_down("N")
def give_pistol():
    _act(lambda player: player.give_weapon(sa.WeaponType.PISTOL, 100))


@sa.on_key_down("M")
def select_unarmed():
    _act(lambda player: player.select_weapon(sa.WeaponType.UNARMED))


@sa.on_key_down("J")
def select_pistol():
    _act(lambda player: player.select_weapon(sa.WeaponType.PISTOL))


@sa.on_key_down("K")
def remove_pistol():
    _act(lambda player: player.remove_weapon(sa.WeaponType.PISTOL))
