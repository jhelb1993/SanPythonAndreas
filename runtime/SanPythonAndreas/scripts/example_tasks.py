"""G starts/restarts a cooperative countdown; H cancels it. Import in main.py."""
import sanandreas as sa

_task = None


def _countdown():
    try:
        for remaining in (3, 2, 1):
            sa.show_text(f"Task-Countdown: {remaining}")
            yield sa.wait(1)
        sa.show_text("Task fertig!")
        return "fertig"
    finally:
        # Keep cleanup short. A clock reset can close the task while paused,
        # so cleanup should not depend on an active player or HUD access.
        print("Task-Countdown aufgeraeumt")


@sa.on_key_down("G")
def start_countdown_task():
    global _task
    if _task is not None and not _task.done:
        _task.cancel()
    _task = sa.start_task(_countdown())
    sa.show_text("Task geplant. H: abbrechen")


@sa.on_key_down("H")
def cancel_countdown_task():
    if _task is None or _task.done:
        sa.show_text("Kein laufender Task.")
        return
    _task.cancel()
    sa.show_text("Task abgebrochen.")
