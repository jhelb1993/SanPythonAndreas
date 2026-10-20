"""One-time visible diagnostic: put `import diagnose_f5` first in main.py."""
import ctypes
import sys
import traceback

_report = ["F5-Diagnose 1", "Python: " + sys.version.split()[0]]
_bootstrap = sys.modules.get("_spa_runtime")
_report.append("Bootstrap: " + str(getattr(_bootstrap, "__file__", "nicht geladen")))

try:
    import sanandreas as sa

    for _name in ("on_key_down", "player", "_is_key_down", "_has_focus",
                  "_player_health", "_set_player_health", "Vector3", "_player_position"):
        _report.append(_name + ": " + ("vorhanden" if hasattr(sa, _name) else "FEHLT"))

    @sa.on_key_down("F5")
    def _diagnostic_key_callback():
        pass

    _report.append("F5-Registrierung: OK")
    _player = sa.player()
    _report.append("Spieler: " + ("nicht vorhanden" if _player is None else
                   "health=" + str(_player.health) + ", max=" + str(_player.max_health)))
except BaseException:
    _report.append("FEHLER:\n" + traceback.format_exc())

ctypes.windll.user32.MessageBoxW(
    0, "\n".join(_report), "SanPythonAndreas - bitte diesen Text schicken", 0
)
