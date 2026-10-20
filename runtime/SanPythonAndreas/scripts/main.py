import sanandreas as sa


@sa.on_game_ready
def start():
    print("Python ist bereit! F5 heilt den Spieler.")
    sa.show_text("SanPythonAndreas bereit! F5: Spieler heilen")


@sa.on_key_down("SPACE")
def heal():
    player = sa.player()
    if player is None or player.health <= 0:
        return
    player.health = player.max_health
    print("Spieler geheilt:", player.health)
    sa.show_text("Spieler geheilt!")
