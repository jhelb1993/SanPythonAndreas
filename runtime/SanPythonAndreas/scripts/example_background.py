"""O reads this script in the background; P cancels result delivery.

Import example_background in main.py. The worker waits two real seconds to make
continued gameplay observable. The delay runs ONLY on the worker, never in a GTA callback.
"""
from pathlib import Path
import time
import sanandreas as sa

_job = None
_script_path = Path(__file__)


def _read_summary():
    # No sanandreas API calls here. Use I/O timeouts for real files/network work.
    time.sleep(2)
    text = _script_path.read_text(encoding="utf-8")
    return {"lines": len(text.splitlines()), "characters": len(text)}


def _show_summary(result):
    # Completion always runs on the game thread during active gameplay.
    print("Hintergrund-Ergebnis:", result)
    sa.show_text(f"Datei gelesen: {result['lines']} Zeilen, {result['characters']} Zeichen")


def _show_error(details):
    print("Hintergrundfehler:", details)
    sa.show_text("Hintergrundfehler. Details im Python-Log.")


@sa.on_key_down("O")
def start_background_read():
    global _job
    if _job is not None and not _job.done:
        _job.cancel()
    try:
        _job = sa.run_in_background(_read_summary, _show_summary, on_error=_show_error)
        sa.show_text("Datei wird im Hintergrund gelesen. P: abbrechen")
    except RuntimeError as error:
        print("Hintergrundauftrag abgelehnt:", error)
        sa.show_text("Hintergrundwarteschlange voll. Spaeter erneut versuchen.")


@sa.on_key_down("P")
def cancel_background_read():
    if _job is not None:
        _job.cancel()
    sa.show_text("Hintergrund-Ergebniszustellung abgebrochen.")
