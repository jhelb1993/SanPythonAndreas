# SanPythonAndreas

Python-Scripting-Prototyp als x86-ASI für das klassische GTA: San Andreas.
Python **3.11.9 x86** wird lokal mitgeliefert. Eine installierte Python-Version
oder ein Eintrag in PATH ist nicht mehr nötig.

Arbeitsplan und Fortschritt: [Gesamt-TODO](TODO.md).

SDK-/Binding-Umstellung: [Architektur und Abnahme](docs/BINDINGS.md).
Gesicherter funktionierender Stand: [Baseline](docs/BASELINE.md).

## Bauen

Für einen vollständigen, geprüften Neubuild `Build-Release.cmd` im Repository
starten. Der Aufruf baut ausdrücklich die ASI inklusive Runtime-Projekt neu und
prüft anschließend das Paket. Er benötigt Visual Studio mit C++-Buildwerkzeugen.

Alternativ `SanPythonAndreas.slnx` in Visual Studio öffnen und die **gesamte
Projektmappe** mit **Release / x86** neu erstellen. Nur das Projekt
`PythonRuntime` zu bauen aktualisiert die ASI nicht.
Beim ersten Build führt das Runtime-Projekt automatisch `tools/Setup-Python.ps1`
und `tools/Setup-Bindings.ps1` aus. Das Skript lädt über HTTPS:

- die offizielle Windows-x86-Embeddable-Runtime von Python.org;
- das passende `pythonx86`-NuGet-Paket für Header und `python311.lib`;
- Plugin-SDK und pybind11 mit den in `bindings-dependencies.json` fixierten Ständen.

Es prüft die veröffentlichte Runtime-Prüfsumme, die SHA512-Prüfsumme des SDKs,
die SDK-Version und die x86-Architektur der Python-DLL. Downloads werden unter
`dependencies/downloads` zwischengespeichert. Das SDK landet unter
`dependencies/python311-x86`, die Runtime unter
`runtime/SanPythonAndreas/python`. Python wird nicht in Windows installiert.
Folgebuilds benötigen bei vorhandenem Paket keinen Download.

Manuell vorbereiten (PowerShell im Repository):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Setup-Python.ps1
```

3.11.9 ist die letzte offizielle 3.11-Version mit regulären Windows-Binärpaketen;
es gibt neuere 3.11-Sicherheitsversionen als Quellcode. Diese Paketierung nutzt
gezielt das vorhandene offizielle x86-Binärpaket, nicht einen eigenen Python-Build.

Quellen: [Python 3.11.9](https://www.python.org/downloads/release/python-3119/),
[Embeddable-Paket und NuGet](https://docs.python.org/3.11/using/windows.html).

## Ins Spiel kopieren

Nach erfolgreichem Build diese Struktur aus `Release` ins GTA-Verzeichnis kopieren:

```text
gta_sa.exe
SanPythonAndreas.asi                 # einzige Plugin-Datei neben der EXE
SanPythonAndreas/
    SanPythonRuntime.dll            # Python-Bindings
    _spa_runtime.py
    sanandreas.pyi                   # Typen fuer den Editor
    scripts/
        main.py
        example_heal.py             # aktuelles F5-Beispiel
    python/                         # kompletten Ordner kopieren!
        python311.dll
        python3.dll
        python311.zip
        python311._pth
        python.exe
        vcruntime140.dll
        LICENSE.txt
        ...                         # weitere DLLs und .pyd-Dateien
```

Ein ASI-Loader wird weiterhin benötigt. Alte Plugin-Kopien ersetzen; frühere
`python38.dll`-Kopien werden von diesem Plugin nicht mehr gebraucht. Dateien, die
andere Mods benötigen, nicht löschen. Die alte Release-DLL aus früheren Builds
gehört nicht zum neuen Paket. Eigene Skripte liegen unter
`SanPythonAndreas/scripts`.

Der Build kopiert das vollständige Python-Paket inklusive Lizenz, Standardbibliothek,
`ctypes` und nativer Erweiterungen. Er aktualisiert `_spa_runtime.py`, überschreibt
aber eine vorhandene `Release/SanPythonAndreas/scripts/main.py` nicht.
Das aktuelle F5-Beispiel wird zusätzlich immer als `scripts/example_heal.py`
mitgeliefert. Bei einem vorhandenen `main.py` dieses Beispiel bewusst als `main.py`
übernehmen oder aus der eigenen `main.py` mit `import example_heal` laden.
Nach diesem Update **ASI und SanPythonRuntime.dll gemeinsam ersetzen**, da ihre
interne Schnittstelle um Spieler- und Tastaturfunktionen erweitert wurde.

## F6: Spielerposition

Der neue Stand (`0.3.0-dev.1`, Host-API 3) ergänzt einen unveränderlichen
`Vector3`-Wert und `player.position` als lesbare Momentaufnahme. Mit
`Build-Release.cmd` neu bauen und ASI sowie Datenordner zusammen ersetzen.
Die zusätzliche Datei `scripts/example_position.py` wird automatisch mitgeliefert.
In der eigenen `main.py` ergänzen:

```python
import example_position
```

F6 zeigt die aktuellen X-/Y-/Z-Koordinaten als HUD-Hilfetext und im Python-Log.
Das F5-Beispiel kann parallel geladen bleiben. Die vorhandene `main.py` wird
weiterhin nicht überschrieben.

Direkter API-Zugriff:

```python
player = sa.player()
if player is not None:
    position = player.position
    print(position.x, position.y, position.z)
    print(tuple(position))
    offset = position + sa.Vector3(0, 0, 5)
    print(position.distance_to(offset))  # 5.0
```

`Vector3(x=0, y=0, z=0)` hat lesbare Eigenschaften `x`, `y`, `z`, unterstützt
Unpacking, Addition, Subtraktion, Negation, skalare Multiplikation/Division sowie
`length()` und `distance_to(other)`. Komponenten müssen endlich sein; NaN und
Unendlich werden abgewiesen. Gleichheit vergleicht die Komponenten exakt.
Division durch null erzeugt `ZeroDivisionError`.

Die Position wird bei jedem Eigenschaftszugriff neu aus dem aktuellen Spieler
auf dem Spielthread gelesen. Ohne gültige Position wird `RuntimeError` ausgelöst;
`sa.player()` liefert bei fehlendem Spieler weiterhin `None`. Ein gelesener
Vektor bleibt unverändert, wenn der Spieler sich bewegt. Auch Vektorrechnung
bewegt den Spieler nicht. Ein Positionssetter und Teleportieren folgen separat.

## Ladeverhalten

Die ASI selbst importiert keine Python-DLL mehr. Sie schreibt zuerst die
Startdiagnose, installiert den GTA-Hook und lädt erst bei aktivem Spiel
`SanPythonAndreas/SanPythonRuntime.dll`. Dessen Python-Abhängigkeiten werden aus
`SanPythonAndreas/python` aufgelöst. Die bisherigen API-Funktionen werden nun
über pybind11 gebunden, die Gesundheits-/HUD-Anbindung verwendet Plugin-SDK-Typen. Fehler beim Laden werden mit Windows-Fehlercode
protokolliert. Python-Pfade werden relativ zur ASI über `PyConfig` gesetzt;
Registry, PATH und die bisherige Python-3.8-Installation werden nicht benötigt.

Die eigenen C++-Komponenten verwenden die statische MSVC-Runtime. Python bringt
seine Runtime-DLLs im Embeddable-Paket mit. Zielsystem: modernes Windows, x86-Spiel;
Python 3.11 unterstützt Windows 7 nicht.

Das Embeddable-Paket enthält kein pip. Python-Pakete müssen passend für CPython
3.11/Windows x86 mitgeliefert werden. Unterverzeichnisse in `scripts` sind möglich;
Pakete können auch direkt dort liegen. Es gibt keinen automatischen Paketdownload
beim Spielstart.

## Python-API

```python
import sanandreas as sa

@sa.on_key_down("F5")
def heal():
    player = sa.player()
    if player is not None and player.health > 0:
        player.health = player.max_health
        sa.show_text("Spieler geheilt!")
```

- `on_game_ready`: einmal pro Spielprozess nach erfolgreichem Laden von `main.py`.
- `on_frame`: pro Spielcallback bei vorhandenem Spieler, ohne Code-/Benutzerpause.
- `on_key_down(key)`: Callback ohne Argumente bei einer beobachteten neuen
  Tastenbetätigung. Unterstützt F1–F24, A–Z, 0–9, SPACE, ENTER, TAB, ESC/ESCAPE,
  SHIFT, CTRL, ALT, LEFT/RIGHT/UP/DOWN oder Windows-Virtual-Key-Codes 1–254.
  Tastennamen sind unabhängig von Groß-/Kleinschreibung. Kein Autorepeat.
  Nur bei aktivem Spiel mit GTA im Vordergrund; nach Start, Pause oder
  Fokuswechsel werden bereits gehaltene Tasten zunächst ignoriert. Kurze
  Tastendrücke vollständig zwischen zwei Spielcallbacks können übersehen werden.
- `player()`: aktuelle Spieleransicht oder `None`, wenn kein aktiver Spieler
  verfügbar ist. `health` ist les- und schreibbar, `max_health` nur lesbar.
  Werte kommen aus den CPed-Gesundheitsfeldern des aktuellen Spielers. Schreiben
  erlaubt endliche Zahlen zwischen 0 und `max_health`; `bool`, NaN und Unendlich
  werden abgewiesen. Tote Spieler können damit nicht wiederbelebt werden.
  Eine aufbewahrte Ansicht prüft bei jedem Zugriff den aktuellen Spieler neu;
  sie bindet sich nicht dauerhaft an einen Ped. Fehlt der Spieler inzwischen,
  löst ein Eigenschaftszugriff `RuntimeError` aus. Alle Zugriffe nur auf dem
  Spielthread. Das Beispiel überspringt fehlende und tote Spieler.
- `sanandreas.pyi`: Typdefinitionen für Autovervollständigung. Im Editor den
  `SanPythonAndreas`-Datenordner öffnen, damit das Modul gefunden wird.
- `show_text(text)`: GTA-Hilfetext, 1–200 ASCII-Zeichen ohne NUL; normale
  GTA-Anzeigedauer. Das Spiel kann Hilfetexte während Zwischensequenzen unterdrücken.
- `print()` und Python-Tracebacks: `SanPythonAndreas/SanPythonAndreas.log`.
- Native Startdiagnose: `C:\log.txt`. Scheitert das Öffnen, wird
  `%TEMP%\SanPythonAndreas.log` verwendet; dort steht auch der Windows-Fehlercode.

`main.py` läuft als `__main__`. Dein bisheriges `ctypes`-MessageBox-Beispiel kann
weiterhin verwendet werden. Es hält den Spielthread bis zum Schließen an.

Callbacks laufen auf dem Spielthread. Kein `time.sleep()`, keine Endlosschleifen
und keine langen Datei-/Netzwerkzugriffe. Python-Worker dürfen `show_text()` nicht
direkt aufrufen. Fehlerhafte Callbacks werden protokolliert und deaktiviert;
andere laufen weiter. Auch `SystemExit` wird abgefangen. Bei Fehlern beim Laden
von `main.py` werden teilweise registrierte Callbacks verworfen. Nach Änderungen
das Spiel neu starten; Hot Reload und Scheduler fehlen noch.

## GTA-Kompatibilität

Der bisherige Prototyp-Hook unterstützt **GTA SA 1.0 US Compact/Hoodlum** mit
Basisadresse `0x400000`. Versionssignatur und der
unveränderte Aufruf an `0x53E981` werden vor dem Patchen geprüft. Andere Versionen
oder Konflikte mit anderen Hooks werden abgewiesen und protokolliert.

Installation des Hooks nur beim frühen ASI-Start; spätes Injizieren und dynamisches
Entladen sind nicht unterstützt. Interpreter und Runtime-DLL bleiben bis zum
Prozessende erhalten. Der GIL wird zwischen Frames freigegeben.

Adressreferenzen (Plugin-SDK, GTA Community):
[Events](https://github.com/DK22Pac/plugin-sdk/blob/master/shared/Events.h),
[Versionen](https://github.com/DK22Pac/plugin-sdk/blob/master/shared/GameVersion.cpp),
[CGame](https://github.com/DK22Pac/plugin-sdk/blob/master/plugin_sa/game_sa/CGame.cpp),
[Spieler](https://github.com/DK22Pac/plugin-sdk/blob/master/plugin_sa/game_sa/common.cpp),
[Timer](https://github.com/DK22Pac/plugin-sdk/blob/master/plugin_sa/game_sa/CTimer.cpp),
[HUD](https://github.com/DK22Pac/plugin-sdk/blob/master/plugin_sa/game_sa/CHud.cpp),
[CPed-Gesundheitsfelder](https://github.com/DK22Pac/plugin-sdk/blob/master/plugin_sa/game_sa/CPed.h).

## Prüfen

Nach dem Windows-Build testet dieser Aufruf die mitgelieferte Python-Runtime
(Version, x86, Standardbibliothek, ctypes, SSL und SQLite):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\Test-Bundle.ps1
```

Die Spielcallbacks und Fehlerbehandlung lassen sich ohne GTA prüfen:

```text
python -B -m unittest discover -s tests -v
```

Die Tests prüfen auch Tastendruckflanken, Pause/Fokuswechsel, das F5-Beispiel
und Spielerwechsel mit einer simulierten nativen API. Diese Tests ersetzen
keinen Windows-Build oder Spieltest. Das native Modul `sanandreas` ist nur im
Spiel verfügbar, nicht beim eigenständigen Aufruf von `python.exe`.

## Sichtbare F5-Diagnose

Bei einem Ladefehler von `main.py` zeigt die aktuelle Bootstrap-Version den
Traceback auch als Windows-Dialog. Bei einer bereits installierten älteren
Version die mitgelieferte `scripts/diagnose_f5.py` neben `main.py` kopieren
und ganz oben in `main.py` vor allen Dekoratoren `import diagnose_f5` ergänzen.
Nach dem Spielneustart erscheint ein Dialog mit Python-Version, tatsächlich
geladenem Bootstrap-Pfad, vorhandenen API-Funktionen und dem Fehler bei der
F5-Registrierung. Nach der Diagnose die Importzeile wieder entfernen.


## Teleportieren (API 4)

Das Paket `0.4.0-dev.1` ergänzt `player.teleport(Vector3(...))` und das Setzen
von `player.position`. `player.interior` zeigt den aktuellen Innenraum-Bereich.
Der Teleport bleibt im aktuellen Interior. Beim Fahren wird das Fahrzeug mitbewegt;
Passagiere, Züge und Gespanne werden abgewiesen. Gesundheit muss größer als null sein.
Bewegung und Drehgeschwindigkeit werden zurückgesetzt; die Ausrichtung bleibt erhalten.

In der vorhandenen `scripts/main.py` ergänzen:

```python
import example_teleport
```

F7 speichert Position und Interior, F8 kehrt dorthin zurück. Einen freien Platz
auf ebenem Boden wählen; die Zielhöhe wird exakt übernommen, ohne Bodensuche
oder Hindernisprüfung. Szene und Kollisionen werden synchron angefordert/geladen;
dabei kann das Spiel kurz stocken. Ein erfolgreicher Aufruf garantiert keine freie
oder begehbare Zielfläche. Grenzen: x/y ±20000, z −1000 bis 10000.

Nach `Build-Release.cmd` ASI und kompletten Datenordner zusammen kopieren.
18 Python-Tests bestehen; die zwölf nativen Windows-Tests und der Spieltest der
Teleport-Erweiterung stehen noch aus. Test: zu Fuß und als Fahrer speichern,
wegbewegen und zurückspringen; anschließend einen Interior-Wechsel versuchen
und die erwartete Ablehnung prüfen. Ein gespeicherter Ort gilt nur für die laufende
Sitzung und wird bei einem Spielstandwechsel nicht automatisch verworfen.


## Ausrichtung lesen und setzen (API 5)

```python
player = sa.player()
if player is not None:
    print(player.heading)
    player.heading = 90.0
```

`heading` verwendet Grad im Bereich `[0, 360)`. Beim Setzen werden endliche
Winkel normalisiert: `-90` wird `270`, `450` wird `90`. Als Fahrer wird das
Fahrzeug ausgerichtet; Passagiere, Züge und Gespanne werden abgewiesen.
Zu Fuß werden auch die Ped-Rotationsfelder aktualisiert. Setzen erfordert einen
lebenden Spieler; Winkelgeschwindigkeit wird gelöscht. Die Eigenschaft speichert
nur den Heading-Winkel, keine vollständige Neigung eines Fahrzeugs.

Das aktualisierte `example_teleport` speichert mit F7 auch Heading und stellt es
mit F8 nach dem Teleport wieder her. Bestehendes `import example_teleport` reicht.
Paketversion `0.5.0-dev.1`, Host-API 5: ASI und Datenordner gemeinsam aktualisieren.
API 5: Windows-Build, 14 native Tests, Paketprüfung und Heading-Spieltest wurden
vom Nutzer als erfolgreich bestätigt. API-4-Teleportieren ist ebenfalls bestätigt.

## Innen- und Außenräume wechseln (API 6)

Paket `0.6.0-dev.1`, Host-API 6: `player.teleport(target, interior=6)` wechselt
jetzt den Weltbereich. `interior=0` führt nach draußen; `None` und die Zuweisung
an `player.position` behalten den aktuellen Bereich bei. Die ID muss zur
Zielposition passen; eine Interior-ID allein bezeichnet kein bestimmtes Gebäude.

F7 speichert weiterhin Position, Interior und Heading. F8 stellt diese Werte
jetzt auch nach einem Wechsel nach drinnen oder draußen wieder her. Keine neue
Importzeile nötig, wenn das Beispiel bereits geladen wird.

Spieler, Fahrerfahrzeug und dessen Insassen erhalten den Zielbereich. Die alte
Umgebung wird entladen, Zielszene und Kollision werden synchron geladen; bei
Bereichswechsel werden Kamera, Extra-Farbfilter und alter Portal-Kontext
zurückgesetzt. Während eines laufenden Türübergangs wird der Aufruf abgewiesen;
F8 bleibt danach nutzbar. Shop- und Missionsskripte werden nicht aktiviert,
eine zum Zielgebäude passende Portal-/Radar-Zuordnung wird nicht rekonstruiert.
Keine Bodensuche oder Hindernisprüfung; Fahrzeugziele brauchen genügend Platz.

ASI und kompletten Datenordner gemeinsam aktualisieren. Spielabnahme offen:
draußen F7, Gebäude betreten, nach abgeschlossenem Türübergang F8; danach
drinnen F7, Gebäude verlassen und F8. Auch Interior A nach B sowie anschließendes
normales Verlassen durch die Tür, Kamera, sichtbare Umgebung und Kollision prüfen.
