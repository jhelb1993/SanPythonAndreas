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
  `health` kommt aus CPed, `max_health` aus dem spielerspezifischen
  `CPlayerInfo::m_nMaxHealth` (ab API 9). Schreiben
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

Callbacks laufen auf dem Spielthread. Für Wartezeiten ab API 12 `call_later()`
und `call_every()` verwenden. Kein `time.sleep()`, keine Endlosschleifen
und keine langen Datei-/Netzwerkzugriffe. Python-Worker dürfen `show_text()` nicht
direkt aufrufen. Fehlerhafte Callbacks werden protokolliert und deaktiviert;
andere laufen weiter. Auch `SystemExit` wird abgefangen. Bei Fehlern beim Laden
von `main.py` werden teilweise registrierte Callbacks verworfen. Nach Änderungen
das Spiel neu starten; Hot Reload fehlt noch. Generator-Tasks sind ab API 13 verfügbar.

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

API-6-Spielabnahme vom Nutzer bestätigt. Geprüft werden sollte weiterhin:
draußen F7, Gebäude betreten, nach abgeschlossenem Türübergang F8; danach
drinnen F7, Gebäude verlassen und F8. Auch Interior A nach B sowie anschließendes
normales Verlassen durch die Tür, Kamera, sichtbare Umgebung und Kollision prüfen.

## Rüstung lesen und setzen (API 7)

Paket `0.7.0-dev.1`, Host-API 7 ergänzt `player.armour`:

```python
player = sa.player()
if player is not None and player.health > 0:
    print(player.armour)
    player.armour = 100
```

Schreiben erlaubt endliche Zahlen von 0 bis 100; `bool`, NaN, Unendlich und
Werte außerhalb dieses Bereichs werden abgewiesen. Lesen liefert den aktuellen
Rüstungswert, auch wenn andere Spielmechaniken höhere Werte erlauben. Schreiben
benötigt einen lebenden Spieler; Gesundheit wird nicht verändert. Eine gespeicherte
Spieleransicht löst den aktuellen Spieler bei jedem Zugriff neu auf.

Für das F9-Beispiel in der eigenen `main.py` ergänzen:

```python
import example_armour
```

ASI und Datenordner gemeinsam aus `Release` aktualisieren. F9 füllt die Rüstung
auf 100 auf. Funktion vom Nutzer im Spiel bestätigt.

## Geld und Fahndungslevel (API 8)

Paket `0.8.0-dev.1`, Host-API 8:

```python
player = sa.player()
if player is not None and player.health > 0:
    player.money = 10000
    player.wanted_level = 0
    print(player.money, player.wanted_level)
```

`money` unterstützt beim Schreiben ganze Zahlen von 0 bis 999999999 und
aktualisiert die Geldanzeige sofort. Lesen liefert den tatsächlichen Kontostand,
auch bei negativen Werten aus anderen Spielmechaniken. `wanted_level` unterstützt
ganze Zahlen von 0 bis 6. `bool`, Fließkommazahlen und Zeichenketten werden bei
beiden Settern abgewiesen; zu große Python-Integer erzeugen `OverflowError`.
Schreiben benötigt einen lebenden Spieler und den Spielthread.

Der Fahndungslevel wird über GTAs `SetWantedLevel` gesetzt. Spiel-/Missionslimits
und aktive Cheats werden berücksichtigt; der tatsächlich erreichte Level kann
niedriger sein oder unverändert bleiben. Nach dem Setzen zurücklesen. Die API
sperrt die Fahndung nicht dauerhaft: neue Straftaten können wieder Sterne auslösen.

In der eigenen `main.py` für das Beispiel ergänzen:

```python
import example_money_wanted
```

- F10: 1000 Dollar hinzufügen, bis zum API-Limit.
- F11: Fahndungslevel 0 anfordern.
- F12: Fahndungslevel 3 anfordern; HUD und Log zeigen den tatsächlichen Wert.

API-8-Funktion vom Nutzer im Spiel bestätigt. Spieltest:
Geldanzeige und Kontostand kontrollieren, Sterne erhöhen und wieder entfernen;
Pause, Fokuswechsel, Fahrzeug sowie fehlenden/toten Spieler berücksichtigen.

## Spielerspezifische maximale Gesundheit (API 9)

Paket `0.9.0-dev.1`, Host-API 9: `player.max_health` liest jetzt das aktuelle
`CPlayerInfo::m_nMaxHealth` anstelle des allgemeinen `CPed::m_fMaxHealth`.
Dieses Spielerlimit verwendet GTA auch beim Auffüllen der Gesundheit. Der
Rohwert der Statistik `STAT_MAX_HEALTH` wird nicht als Gesundheit interpretiert.
Die API verändert weder Statistiken noch das Maximum und bleibt nur lesbar.

F5 und `player.health = player.max_health` verwenden das aktuelle Spielerlimit.
Kein neuer Import nötig. Auch die Prüfung beim Gesundheitsschreiben liest das
Limit jedes Mal neu. Bloßes Lesen senkt überhöhte Gesundheit nicht ab.

API-9-Funktion vom Nutzer im Spiel bestätigt. Spieltest:
mit normalem Spielstand und einem Spielstand mit erhöhter Maximalgesundheit
Schaden nehmen, F5 drücken und die vollständige Heilung kontrollieren. Nach
Spielstandwechsel erneut prüfen; fehlende und tote Spieler bleiben ausgeschlossen.

## Waffenverwaltung (API 10)

Paket `0.10.0-dev.1`, Host-API 10:

```python
player = sa.player()
if player is not None and player.health > 0:
    player.give_weapon(sa.WeaponType.PISTOL, 100)  # geben und auswählen
    print(player.current_weapon, player.weapon_ammo)
    player.select_weapon(sa.WeaponType.UNARMED)
    player.select_weapon(sa.WeaponType.PISTOL)
    player.remove_weapon(sa.WeaponType.PISTOL)
    # player.clear_weapons()  # entfernt das gesamte Inventar, auch vorhandene Ausrüstung
```

Unterstützt sind Waffen-IDs 1..18, 22..38 und 41..43 als Integer oder
`WeaponType`-Konstanten. IDs 19..21 sind Projektile; Satchel/Zünder (39/40),
Sichtgeräte und Fallschirm (44..46) sind bei Einzelaktionen noch ausgeschlossen.
`current_weapon` liefert die tatsächliche aktive ID, auch für Sonderausrüstung.
`weapon_ammo` enthält die gesamte Munition inklusive Magazin; beide nur lesbar.

Änderungen verlangen einen lebenden Spieler zu Fuß. Fahrzeug-/Jetpack-Zustände,
gesicherte/versteckte Waffen und laufende Türübergänge werden abgewiesen.
Modelle werden vor Geben/Auswählen synchron geladen und geprüft; das kann kurz
stocken. Es werden keine dauerhaften Streaming-Flags hinzugefügt oder fremde
Flags gelöscht. Fehlendes Modell führt vor der Inventaränderung zu `RuntimeError`.

`give_weapon(weapon, ammo=100, equip=True)` addiert Munition bei gleicher Waffe;
eine andere Waffe im gleichen Slot wird nach GTA-Regeln ersetzt, teilweise mit
Munitionsübernahme. `equip=False` verzichtet auf ausdrückliche Auswahl, ersetzt
aber weiterhin eine vorhandene Waffe im selben Slot. Das Beispiel stellt sie
nicht wieder her. `ammo` muss eine ganze Zahl sein; Argument plus bisherige
Slotmunition dürfen 99999 nicht überschreiten (sonst `ValueError`).

`select_weapon` verlangt Besitz; ID 0 wählt den Faust-/Schlagring-Slot.
`remove_weapon` entfernt nur bei genau passender ID, andernfalls passiert nichts;
ID 0 ist ebenfalls ein No-op. `clear_weapons` entfernt ausdrücklich alle Waffen
und Ausrüstung, unabhängig davon, ob sie durch Python vergeben wurden.

Für das Beispiel in der eigenen `main.py` ergänzen:

```python
import example_weapons
```

- N: Pistole mit 100 zusätzlicher Munition geben und auswählen.
- M: Faust-/Schlagring-Slot auswählen.
- J: vorhandene Pistole auswählen.
- K: Pistole entfernen.

API-10-Funktion vom Nutzer im Spiel bestätigt. Spieltest:
zu Fuß N/M/J/K prüfen, schießen und Munitionsanzeige kontrollieren, N wiederholen;
mit anderer Handfeuerwaffe den Slotwechsel prüfen. Im Fahrzeug muss die Aktion
abgewiesen werden und nach Aussteigen wieder funktionieren. Auch Pause,
Fokuswechsel, Tod und Spielstandwechsel prüfen.

## Spielerzustände und aktuelles Fahrzeug (API 11)

Paket `0.11.0-dev.1`, Host-API 11:

```python
player = sa.player()
if player is not None:
    print(player.is_alive, player.in_vehicle, player.is_driver)
    vehicle = player.vehicle
    if vehicle is not None:
        print(vehicle.model_id, vehicle.health, vehicle.position, vehicle.is_driver)
```

`is_alive` prüft `health > 0`. `in_vehicle` gilt für Fahrer und Passagiere;
`is_driver` ist zu Fuß und auf dem Beifahrersitz falsch. Bei fehlendem Spieler
lösen Eigenschaften wie bisher `RuntimeError` aus; `sa.player()` liefert `None`.

`player.vehicle` liefert zu Fuß `None`, sonst eine unveränderliche `VehicleInfo`
mit `model_id`, `health`, `position` (Vector3) und `is_driver`. Das ist eine
abgetrennte Momentaufnahme ohne Spielzeiger. Gespeicherte Daten bleiben nach
Aussteigen, Fahrzeugzerstörung oder Spielstandwechsel lesbar, aktualisieren sich
aber nicht. Für aktuelle Werte `player.vehicle` erneut abfragen. Dauerhafte
Handles, Fahrzeugänderungen und Spawn-Funktionen folgen separat.

Die Sitzzuordnung wird gegen Fahrer und Passagierliste geprüft. Während eines
unvollständigen Ein-/Ausstiegs kann `RuntimeError` auftreten; im nächsten Frame
erneut versuchen. Gesundheit ist GTAs roher Fahrzeugwert (normalerweise 1000
bei unbeschädigtem Fahrzeug), kein Prozentwert; auch negative Werte sind möglich.
Es wird kein Maximalwert und keine Aussage über Fahrbereitschaft abgeleitet.

In der eigenen `main.py` ergänzen:

```python
import example_vehicle
```

V zeigt Fuß-/Fahrzeugzustand, Sitzrolle, Modell-ID und Gesundheit im HUD;
die Position steht zusätzlich im Python-Log. ASI und Datenordner gemeinsam aus
`Release` aktualisieren. API-11-Funktion vom Nutzer im Spiel bestätigt. Zu Fuß, als Fahrer und als Passagier
prüfen; aussteigen, anderes Fahrzeug betreten und erneut V drücken. Nach Pause,
Alt-Tab, Tod und Spielstandwechsel kontrollieren. Gespeicherte Momentaufnahmen
dürfen sich dabei nicht verändern.

## Timer ohne blockierendes Warten (API 12)

Paket `0.12.0-dev.1`, Host-API 12:

```python
timer = sa.call_later(3, lambda: sa.show_text("Drei Spielsekunden vorbei"))
repeating = sa.call_every(1, lambda: print("Tick"))
# repeating.cancel()  # mehrfaches Abbrechen ist erlaubt
real_timer = sa.call_later(5, lambda: sa.show_text("Echtzeit vorbei"), clock="real")
```

Zeitangaben sind Sekunden. `call_later` erlaubt 0 (frühestens nächster Tick),
`call_every` verlangt ein positives Intervall. Ungültige Typen, bool, negative
Werte, NaN und Unendlich werden abgewiesen. Callback ohne Argumente übergeben;
zusätzliche Werte lassen sich mit einer Closure binden.

- `clock="game"` (Standard) folgt GTAs Spieltimer, einschließlich dessen
  Pausen-/Zeitskalierungsverhalten. Es handelt sich nicht um die Tagesuhr.
- `clock="real"` verwendet monotone Echtzeit, die während Pause und Laden
  weiterläuft. Ein überfälliger Timer wird im nächsten aktiven Frame ausgeführt.
- Alle Aufrufe laufen auf dem Spielthread nach Tastatur- und Framecallbacks.
  Ohne aktiven Spieler bzw. während Pause werden keine Timer zugestellt.
  Fokusverlust allein stoppt Timer nicht, sofern GTA weitersimuliert.
- Wiederholungen werden ab Callback-Ende neu geplant. Verpasste Intervalle
  werden nicht gesammelt nachgeholt; pro Timer höchstens ein Aufruf pro Frame.
  Insgesamt maximal 64 Timeraufrufe pro Frame; übrige werden fair verschoben.
- Registrierung und `cancel()` sind nur auf dem Spielthread erlaubt. Ein im
  laufenden Frame registrierter Timer startet frühestens im nächsten Frame.

`Timer.done` zeigt Abschluss, Abbruch oder Fehler an; `Timer.cancelled` zeigt
ausdrücklichen Abbruch bzw. Uhrreset. `owner` enthält das Callback-Modul für
Diagnose. Eine vollständige Mod-Verwaltung ist das noch nicht. Fertige und
abgebrochene Timer geben ihre Callback-Referenz frei. Fehler einschließlich
`SystemExit` stoppen nur den betroffenen Timer; Aufrufe ab 50 ms werden geloggt,
aber nicht unterbrochen. Lange Arbeit darf weiterhin nicht im Callback laufen.

Ein natürlicher 32-Bit-Uhrüberlauf wird verarbeitet. Bei erkanntem Rücksprung
der Spieluhr werden Spielzeit-Timer abgebrochen; Echtzeit-Timer bleiben bestehen.
Nicht jeder Spielstandwechsel ist damit erkennbar. Timer müssen für einen
bestimmten Spielstand ihre Voraussetzungen im Callback erneut prüfen und bei
Bedarf explizit abgebrochen werden. Timer werden nicht im Spielstand gespeichert.

Für das Beispiel in der eigenen `main.py` ergänzen:

```python
import example_timers
```

- T: Countdown 3–2–1 in Spielzeit starten oder neu beginnen.
- R: Nachricht nach fünf Echtzeit-Sekunden planen.
- Y: beide abbrechen.

API-12-Funktion vom Nutzer im Spiel bestätigt. Spieltest:
Countdown während Pause anhalten lassen, Echtzeit-Timer über eine Pause hinweg
prüfen und mit Y vor Ablauf abbrechen. Wiederholt starten darf keine doppelten
Timer hinterlassen. Generator-Tasks folgen in API 13; asynchrones Modellladen
ist weiterhin offen.

## Kooperative Generator-Tasks (API 13)

Paket `0.13.0-dev.1`, Host-API 13:

```python
def countdown():
    try:
        for remaining in (3, 2, 1):
            sa.show_text(f"Countdown: {remaining}")
            yield sa.wait(1)
        return "fertig"
    finally:
        print("Countdown aufgeraeumt")

task = sa.start_task(countdown())
# task.cancel()  # kann z.B. von einem Tastencallback aufgerufen werden
```

`start_task` übernimmt einen frischen Generator, z.B. `countdown()`, und startet
ihn frühestens im nächsten aktiven Tick. Der Aufruf einer normalen Funktion,
ein bereits begonnener oder doppelt eingeplanter Generator und async/await-
Coroutinen werden nicht akzeptiert. Jeder Schritt muss kurz bleiben; die Engine
kann laufenden Python-Code nicht unterbrechen.

`yield sa.wait(seconds, clock="game")` gibt den Spielthread frei. Spiel-/Echtzeit
und Pause verhalten sich wie bei Timern; `yield sa.wait()` wartet bis mindestens
zum nächsten Tick. Nur Wait-Anforderungen sind erlaubt, kein nacktes `yield`,
kein `time.sleep()` und keine asyncio-Futures. `sa.wait()` allein ist nur ein
unveränderlicher Wert und wartet nicht ohne `yield`.

`task.cancel()` schließt einen begonnenen Generator und führt sein `finally`
auf dem Spielthread aus. Mehrfaches Abbrechen ist erlaubt. Selbstabbruch wird
nach Rückkehr des aktuellen Schritts wirksam. Beim Abbruch vor dem ersten Schritt
wird der Generatorinhalt einschließlich finally noch nicht betreten; Ressourcen
deshalb innerhalb des Tasks anfordern. Cleanup darf nicht yielden oder blockieren.
Ein Uhrreset kann beim pausierten Spiel aufräumen: HUD-/Spielerzugriff im finally
nur mit erneut geprüften Voraussetzungen. Während globalem Cleanup oder Uhrreset
dürfen keine neuen Timer oder Tasks angelegt werden.

`done`, `cancelled` und `owner` beschreiben den Zustand und das Generator-Modul.
`result` enthält den Rückgabewert nach erfolgreichem Abschluss, andernfalls None.
`error` enthält bei Fehlern eine Beschreibung als Text. Fehler einschließlich
SystemExit und fehlerhaftes Cleanup werden geloggt und stoppen den betroffenen
Task. Generator-/Callback-Referenzen werden freigegeben, Fehler-Tracebacks nicht
im Handle aufbewahrt. Ein laufender Schritt ab 50 ms wird über die Timerdiagnose
geloggt. Task-Schritte teilen sich das 64-Aufrufe-Budget mit normalen Timern.

Bei erkanntem Spieluhr-Rücksprung werden Tasks abgebrochen, die gerade auf
Spielzeit warten. Auf Echtzeit wartende Tasks bleiben bestehen. Das ist keine
vollständige Spielstand-Erkennung; Voraussetzungen vor Spielzugriff erneut prüfen.
Hot Reload und Mod-Unload folgen separat. Asynchrones Modellladen ergänzt API 14,
Hintergrundjobs mit Ergebnisqueue ergänzt API 15.

Für das Beispiel in der eigenen `main.py` ergänzen:

```python
import example_tasks
```

G startet/erneuert den Countdown, H bricht ihn ab. Im Log steht beim normalen
Ende und beim Abbruch eines begonnenen Tasks `Task-Countdown aufgeraeumt`.
API-13-Funktion vom Nutzer im Spiel bestätigt. Spieltest:
G drücken und während des Countdowns bewegen, Pause/Fortsetzen prüfen, erneut
starten und mit H abbrechen. Es dürfen keine alten Countdown-Schritte nachlaufen.

## Asynchrones Modellladen (API 14)

Paket `0.14.0-dev.1`, Host-API 14:

```python
def prepare_model():
    try:
        with (yield from sa.load_model(411, timeout=10)) as model:
            print("Infernus-Modell bereit:", model.model_id, model.ready)
            yield sa.wait(3)
    except TimeoutError:
        print("Modell konnte nicht rechtzeitig geladen werden")

task = sa.start_task(prepare_model())
```

`load_model` ist ein Generator für `yield from` innerhalb eines Tasks. Die
Anforderung startet beim ersten Task-Schritt. Unterstützt sind ganze Modell-IDs
1..19999 mit vorhandenen Metadaten und Streamingressource; bool und Namen werden
abgewiesen. Modell 0 (CJ/Spezialaufbau) ist ausgeschlossen. Fahrzeug-/Ped-Erzeugung
und Namensauflösung folgen später.

Das Laden verwendet `RequestModel` ohne persistente Streaming-Flags und prüft
den Status in folgenden aktiven Frames. Es gibt keinen synchronen Load-all-Aufruf.
Sobald geladen, hält die API eine eigene Modell-/Textur-Referenz. Andere Nutzer
und deren Flags bleiben erhalten. Maximal 256 offene Anforderungen/Referenzen
sind möglich; ungenutzte Modelle daher freigeben.

`timeout` sind endliche, nichtnegative Echtzeit-Sekunden (Standard 10). Der Wert
wird erst im nächsten aktiven Frame geprüft, auch nach einer Pause. Ist das
Modell dann bereits bereit, gewinnt Bereitschaft vor Timeout. 0 prüft einmal
sofort und löst andernfalls `TimeoutError` aus. Abbruch während des Wartens gibt
die Anforderung automatisch frei. Eine schon gemeinsam eingereihte GTA-Anforderung
wird nicht aus der globalen Ladequeue entfernt und kann später fertig werden.

Der zurückgegebene `Model` bietet `model_id`, `ready`, `released` und `release()`.
`with` gibt die eigene Referenz bei Ende, Fehler oder Task-Abbruch frei. Alternativ
in einem finally `model.release()` aufrufen. Nach Rückgabe gehört die Referenz
dem Skript; sie wird nicht automatisch durch Garbage Collection freigegeben.
Freigabe ist wiederholbar und auch während Pause auf dem Spielthread erlaubt.
Sie erzwingt kein sofortiges Entladen: GTA darf das Modell weiter benötigen oder
im Cache behalten. `ready` nach Freigabe/Invalidierung führt zu `RuntimeError`.

Erkannte Spieluhr-Resets und globale Fehlerbereinigung invalidieren alle offenen
Model-Anforderungen/Referenzen, auch in Echtzeit-Tasks. Eine ausstehende Ladeabfrage
meldet das beim Fortsetzen als `RuntimeError`. Modelle sind keine dauerhaften
Spielstand-Handles; nach Spielstandwechsel neu laden und Voraussetzungen prüfen.

Für das Beispiel in der eigenen `main.py` ergänzen:

```python
import example_models
```

U lädt das Infernus-Modell 411, hält es drei Spielsekunden und gibt es frei;
I bricht ab. Es wird noch kein Fahrzeug erzeugt. ASI und Datenordner gemeinsam
aus `Release` aktualisieren. API-14-Funktion vom Nutzer im Spiel bestätigt. U, Bereitschaft und Freigabe im
HUD/Log prüfen, dabei bewegen und Pause/Fortsetzen testen; erneut U und mit I
abbrechen. Laden darf den Spielthread nicht durch synchrones Warten anhalten.

## Hintergrundarbeit und Ergebnisse auf dem Spielthread (API 15)

Paket `0.15.0-dev.1`, Host-API 15:

```python
from pathlib import Path

def read_config():
    # Worker: Daten lesen/berechnen, keine Spielzugriffe.
    return Path("meine_config.txt").read_text(encoding="utf-8")

def apply_config(text):
    # Wieder auf dem Spielthread; hier sind GTA-Aufrufe möglich.
    print("Konfiguration geladen:", len(text), "Zeichen")
    sa.show_text("Konfiguration geladen")

job = sa.run_in_background(read_config, apply_config,
                           on_error=lambda details: print(details))
# job.cancel()  # Ergebniszustellung abbrechen
```

Der Aufruf erfolgt auf dem Spielthread. `work` ist eine normale Funktion ohne
Argumente und liefert Daten zurück; zusätzliche Eingaben lassen sich per Closure
binden. Generatoren und async/await-Coroutinen sind dafür nicht geeignet.
Zwei bei Bedarf gestartete Threads bearbeiten maximal 32 wartende Aufträge.
Insgesamt maximal 64 noch nicht zugestellte Jobs; volle Queues melden RuntimeError.
Dies eignet sich für Datei-/Netzwerk-I/O und native Funktionen, die den GIL
freigeben. Reine Python-Rechenarbeit teilt sich weiterhin den GIL mit dem Spiel.

`on_done(result)` und optional `on_error(details)` laufen nur bei aktivem Spiel
auf dem Spielthread, nach Framecallbacks und vor Timern. Bei Pause bleiben
Ergebnisse in der Queue. Maximal 32 Ergebnisse werden pro Frame verarbeitet;
neu in einem Frame angelegte Jobs liefern frühestens im nächsten Tick zurück.
Ohne Callback ist das Ergebnis nach Zustellung über `job.result` lesbar.

`done` bedeutet zugestellt, fehlgeschlagen oder abgebrochen; fertig gerechnete,
aber noch nicht zugestellte Jobs bleiben zunächst offen. `cancelled`, `owner`,
`result` und `error` sind lesbar. Fehler werden als Text mit Traceback protokolliert;
es werden keine Exception-/Traceback-Objekte im Handle gespeichert. Ein fehlerhafter
Worker oder Ergebnis-Callback stoppt andere Jobs nicht. Ergebnis-Callbacks ab
50 ms werden geloggt und müssen kurz bleiben.

`cancel()` ist wiederholbar und nur auf dem Spielthread erlaubt. Noch nicht
begonnene Arbeit wird übersprungen, spätere Ergebnisse werden verworfen. Bereits
laufender Code wird nicht unterbrochen und seine Datei-/Netzwerkaktionen werden
nicht rückgängig gemacht. Eigene I/O-Aufrufe brauchen daher passende Timeouts.
Abgebrochene Queueeinträge belegen bis zur Entnahme weiterhin ihren Platz.
Workers bleiben bis zum Prozessende erhalten; das Spiel wartet nicht auf ihre
Fertigstellung. Spielzugriffe und Eventregistrierungen aus Workern werden abgewiesen.

Erkannte Spieluhr-Resets und ein Ladefehler von main.py brechen alle offenen Jobs
einschließlich Ergebniszustellung ab. Eine vollständige Spielstand- oder Mod-
Lebensdauererkennung ist das weiterhin nicht.

Für das Beispiel in der eigenen `main.py` ergänzen:

```python
import example_background
```

O liest die Beispieldatei im Hintergrund; nach einer absichtlichen Wartezeit von
zwei Sekunden im Worker zeigt der Spielthread Zeilen-/Zeichenzahl im HUD an.
P bricht die Ergebniszustellung ab. ASI und Datenordner gemeinsam aus `Release`
aktualisieren. Spielabnahme offen: O drücken und weiterlaufen/fahren, Pause bis
nach Ende der Arbeit halten und beim Fortsetzen die Meldung prüfen. O und direkt
P darf keine spätere Ergebnismeldung liefern.
