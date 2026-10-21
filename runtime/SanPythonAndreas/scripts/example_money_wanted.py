"""F10 adds $1000, F11 clears wanted stars, F12 requests three stars.

Load with `import example_money_wanted` in main.py.
"""
import sanandreas as sa


@sa.on_key_down("F10")
def add_money():
    player = sa.player()
    if player is None or player.health <= 0:
        return
    player.money = min(999999999, max(0, player.money + 1000))
    print("Geld:", player.money)
    sa.show_text(f"Geld: ${player.money}")


def _set_wanted(level):
    player = sa.player()
    if player is None or player.health <= 0:
        return
    player.wanted_level = level
    print("Fahndungslevel:", player.wanted_level)
    sa.show_text(f"Fahndungslevel: {player.wanted_level}")


@sa.on_key_down("F11")
def clear_wanted():
    _set_wanted(0)


@sa.on_key_down("F12")
def request_wanted():
    _set_wanted(3)
