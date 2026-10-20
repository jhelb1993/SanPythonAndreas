"""Load with `import example_position` in main.py. F6 shows player coordinates."""
import sanandreas as sa


@sa.on_key_down("F6")
def show_position():
    player = sa.player()
    if player is None:
        return
    position = player.position
    text = f"Position: X={position.x:.2f} Y={position.y:.2f} Z={position.z:.2f}"
    print(text)
    sa.show_text(text)
