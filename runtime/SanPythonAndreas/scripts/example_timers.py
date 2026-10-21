"""T: three-second game-time countdown. R: message after five real seconds.

Y cancels both. Import example_timers in main.py. All callbacks use the game thread.
"""
import sanandreas as sa

_countdown = None
_message = None
_remaining = 0


def _step():
    global _remaining, _countdown
    _remaining -= 1
    if _remaining <= 0:
        _countdown.cancel()
        _countdown = None
        sa.show_text("Countdown fertig!")
        print("Countdown fertig")
    else:
        sa.show_text(f"Countdown: {_remaining}")


@sa.on_key_down("T")
def start_countdown():
    global _countdown, _remaining
    if _countdown is not None:
        _countdown.cancel()
    _remaining = 3
    sa.show_text("Countdown: 3")
    _countdown = sa.call_every(1, _step)


def _real_message():
    global _message
    _message = None
    sa.show_text("Echtzeit-Timer fertig!")
    print("Echtzeit-Timer fertig")


@sa.on_key_down("R")
def start_real_timer():
    global _message
    if _message is not None:
        _message.cancel()
    _message = sa.call_later(5, _real_message, clock="real")
    sa.show_text("Nachricht in 5 Echtzeit-Sekunden. Y: abbrechen")


@sa.on_key_down("Y")
def cancel_timers():
    global _countdown, _message
    for timer in (_countdown, _message):
        if timer is not None:
            timer.cancel()
    _countdown = _message = None
    sa.show_text("Timer abgebrochen.")
