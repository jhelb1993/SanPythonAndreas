# SDK- und Binding-Schicht

SDK-Basis (API 2): 15 Python-Tests sowie Windows-Release/x86-Build, alle
sieben nativen Binding-Tests und die Paketprüfung bestanden. Die Windows-Prüfung
ist durch die vom Nutzer gezeigte Build-Ausgabe bestätigt. Auch der erneute
F5-Spieltest der SDK-/pybind11-Anbindung wurde vom Nutzer als erfolgreich bestätigt.

## Architektur

- `GameBridge.cpp`: bestehender Spielcallback, Threadprüfung und Laden der Runtime.
- `GtaSdk.cpp`: GTA-1.0-US-Adapter mit Plugin-SDK-Typen (`CPed`, `CHud`) und
  Layoutprüfungen. Gesundheit wird über benannte SDK-Felder gelesen/geschrieben.
  Ein SDK-Call-Helper findet den Spieler; die HUD-Funktion verwendet den SDK-Funktionstyp.
- `RuntimeApi.h`: kleine C-Schnittstelle zwischen ASI und Runtime, mit Größe und
  ausdrücklicher API-Version. Keine STL-/Python-Objekte über diese DLL-Grenze.
- `Bindings.cpp`: pybind11-Modul für die bisherige Python-API.
- `PythonRuntime.cpp`: einziger Besitzer des Interpreters. Registrierung erfolgt
  ausdrücklich vor `pybind11::initialize_interpreter`, außerhalb von `DllMain`.
- `_spa_runtime.py`: bestehende Ereignisse und Spieleransicht; prüft API-Kompatibilität.

Es wird zunächst die benötigte Header-/Call-Helper-Schicht des SDKs integriert,
nicht die komplette SDK-Bibliothek und auch kein zweiter Event-Hook. Die wenigen
verwendeten Spieladressen bleiben im versionsspezifischen Adapter. Ein vollständiger
SDK-Aufbau und die Bindung weiterer Funktionen sind spätere Erweiterungen.

## Abhängigkeiten

`bindings-dependencies.json` fixiert pybind11 auf `v2.13.6` und Plugin-SDK auf
Commit `62a1080902627b3edec0124acf02127ba8c0dcdb`. Dieser SDK-Snapshot wird zunächst
für die bestehenden Gesundheits-/HUD-Typen verwendet; es wird kein veränderliches
`master` beim Build gezogen.

`tools/Setup-Bindings.ps1` lädt die Archive über HTTPS, entpackt sie unter
`dependencies`, vermerkt Revision und tatsächlich geladenen SHA256-Archivhash und
verwendet sie bei Folgebuilds wieder. Die SHA256-Datei ist eine Bestandsaufnahme,
keine gegen einen extern festgelegten Hash verifizierte Signatur.

Der Build übernimmt die mitgelieferten Upstream-Lizenz-/Hinweisdateien ins
Datenpaket unter `licenses`. Die SDK-Header bleiben unverändert. Der SDK-Adapter
nutzt zusätzlich den Include-Pfad `shared/game` und aktiviert
`_CRT_SECURE_NO_WARNINGS` nur für diese Übersetzungseinheit, weil der gepinnte
Injector alte CRT-Aufrufe enthält. Die SDK-Dateien bleiben unverändert. Er
wird separat mit C++17 übersetzt; die übrige Runtime nutzt weiterhin C++20.

## Paketvertrag und Kompatibilität

- Aktuelle Paketversion: `0.5.0-dev.1`.
- Aktuelle interne Host-API: Version `3` (zusätzliche Positionsabfrage).
- Python: `sanandreas.__version__`.
- Diagnoseattribute: `_host_api_version`, `_binding_backend`, `_sdk_revision`.
- ASI/Runtime-Abweichungen werden einmal sichtbar gemeldet.
- Ein veralteter Bootstrap oder Python 3.8 wird ausdrücklich abgewiesen.
- Bestehende Skriptaufrufe wie `sa.player()`, `player.health`, `sa.show_text()` und
  `@sa.on_key_down("F5")` behalten ihre bisherigen Namen und Semantik.
- Eigene `main.py` wird weiterhin nicht überschrieben.

Bei einem Update ASI, Runtime-DLL und Bootstrap zusammen ersetzen. Alle Benutzer-
und Spielkonfigurationen sowie vorhandene Skripte bleiben beim Build erhalten;
nur interne Runtime-Dateien, Typdefinitionen und benannte Beispiele werden erneuert.

## Abnahme unter Windows

1. `Build-Release.cmd` ausführen; es baut Host, Runtime und ein Testmodul neu.
2. Die 14 nativen Tests müssen bestehen. Sie importieren dieselbe
   `Bindings.cpp` als `Release/tests/sanandreas.pyd` mit einem simulierten Host.
   Dieses Testmodul gehört nicht ins GTA-Paket.
3. Die Paketprüfung muss `Complete Release bundle verified` erreichen.
4. ASI und Datenpaket gemeinsam installieren; vorhandene Skripte beibehalten.
5. Das unveränderte F5-Beispiel im Spiel prüfen: einmaliges Heilen, Gedrückthalten,
   Pause, Fokuswechsel und fehlender/toter Spieler.
6. Im Log müssen `pybind11-2.13.6` und Host-API `5` stehen.

Die nativen Tests prüfen Argumentkonvertierungen, Exceptions und Threadprüfungen;
sie führen keine GTA-Speicherzugriffe aus. Layoutprüfungen laufen beim x86-Build.
Die tatsächlichen Spieladressen und das Verhalten der SDK-Felder brauchen den
zusätzlichen Spieltest.

## Erweiterung: Vector3 und Spielerposition (API 3)

`Vector3.h` enthält einen unabhängigen unveränderlichen Werttyp. Die Bindings
stellen ihn als `sanandreas.Vector3` bereit. `GtaSdk::ReadPlayerPosition` liest
wahlweise Matrixposition oder einfache Platzierung über die SDK-Felder, nach
Speicher- und Threadprüfung. Die DLL-Schnittstelle überträgt nur drei floats;
der Python-Vektor speichert eine unabhängige Kopie. `Player.position` war in API 3 nur lesbar.

Aktueller Prüfstand: 17 Python-Tests und der eigenständige C++-Vektortest bestanden.
Der Nutzer hat den erfolgreichen F6-Spieltest dieser Erweiterung bestätigt.
Eine separate Ausgabe der zehn nativen Windows-Tests wurde für API 3 nicht
protokolliert. Frühere erfolgreiche API-2-Spieltests gelten weiterhin als Baseline und
sind keine Abnahme der neuen Positionserweiterung.


## Teleportieren (API 4, vom Nutzer bestätigt)

ABI um `playerInterior` und `teleportPlayer` erweitert. Fehlercodes werden in den
Bindings in Python-Ausnahmen übersetzt. Der Host löst den aktuellen Spieler und
gegebenenfalls sein Fahrerfahrzeug bei jedem Aufruf neu auf. Es werden keine
Spielzeiger in Python gespeichert. SDK-Referenzen im gepinnten Quellstand:
`CEntity.cpp` (Teleport, VTable-Slot 14), `CStreaming.cpp` (LoadScene 0x40EB70,
LoadSceneCollision 0x40ED80), `CPed.h` und `CVehicle.h` (Fahrer/Fahrzeugzuordnung).
Es werden keine zusätzlichen SDK-.cpp-Dateien gelinkt.

Interior bleibt erhalten; abweichende Ziel-Interiors werden vor Änderungen
abgewiesen. Keine Bodensuche, keine Hindernisprüfung, kein asynchrones Streaming.
Nach dem Teleport werden lineare und Winkelgeschwindigkeit gelöscht.
`example_teleport.py` fängt erwartete Laufzeitfehler, sodass F8 weiter nutzbar bleibt.

18 Python-Tests erfolgreich. Zwei neue native Tests prüfen Argumente, Statuscodes,
Interior-Ablehnung und Positionsübertragung am simulierten Host. Diese zwölf Tests
müssen unter Windows noch ausgeführt werden; virtuelle GTA-Aufrufe und Streaming
lassen sich damit nicht prüfen. Spielabnahme zu Fuß/Fahrer/Passagier/Interior offen.


## Heading (API 5, Spielabnahme offen)

ABI um `playerHeading(float*)` und `setPlayerHeading(float)` erweitert.
Die Python-API verwendet normalisierte Grad; die native Spielfunktion Radians.
Adressen im gepinnten `CPlaceable.cpp`: GetHeading 0x441DB0, SetHeading 0x43E0C0.
RenderWare wird über die in `CEntity.cpp` dokumentierten UpdateRwMatrix/UpdateRwFrame
aktualisiert (0x446F90/0x532B00). Zu Fuß werden `m_fCurrentRotation` und
`m_fAimingRotation` synchronisiert. Fahrerfahrzeug und ausgeschlossene Fahrzeugfälle
werden gemeinsam mit dem Teleport über `ControlledEntity` aufgelöst.

20 Python-Tests bestehen. Zwei zusätzliche native Tests prüfen Winkel-Normalisierung,
Typfehler, nicht endliche Winkel, Spielzustand und abgewiesene Fahrzeugfälle.
Die 14 Windows-Tests und der Spieltest dieser Erweiterung sind noch offen.
Abnahme: F7 zu Fuß speichern, drehen/weggehen, F8 und Ausrichtung kontrollieren;
dasselbe als Fahrer wiederholen. Passagier-Speichern muss abgewiesen werden,
ohne F7/F8 zu deaktivieren. Neigung/Rollen werden nicht gespeichert.
