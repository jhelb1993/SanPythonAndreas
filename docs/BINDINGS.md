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

- Aktuelle Paketversion: `0.16.0-dev.1`.
- Aktuelle interne Host-API: Version `16` (geprüfte Fahrzeug-Handles).
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
2. Die 34 nativen Tests müssen bestehen. Sie importieren dieselbe
   `Bindings.cpp` als `Release/tests/sanandreas.pyd` mit einem simulierten Host.
   Dieses Testmodul gehört nicht ins GTA-Paket.
3. Die Paketprüfung muss `Complete Release bundle verified` erreichen.
4. ASI und Datenpaket gemeinsam installieren; vorhandene Skripte beibehalten.
5. Das unveränderte F5-Beispiel im Spiel prüfen: einmaliges Heilen, Gedrückthalten,
   Pause, Fokuswechsel und fehlender/toter Spieler.
6. Im Log müssen `pybind11-2.13.6` und Host-API `16` stehen.

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


## Heading (API 5, vom Nutzer bestätigt)

ABI um `playerHeading(float*)` und `setPlayerHeading(float)` erweitert.
Die Python-API verwendet normalisierte Grad; die native Spielfunktion Radians.
Adressen im gepinnten `CPlaceable.cpp`: GetHeading 0x441DB0, SetHeading 0x43E0C0.
RenderWare wird über die in `CEntity.cpp` dokumentierten UpdateRwMatrix/UpdateRwFrame
aktualisiert (0x446F90/0x532B00). Zu Fuß werden `m_fCurrentRotation` und
`m_fAimingRotation` synchronisiert. Fahrerfahrzeug und ausgeschlossene Fahrzeugfälle
werden gemeinsam mit dem Teleport über `ControlledEntity` aufgelöst.

20 Python-Tests bestehen. Zwei zusätzliche native Tests prüfen Winkel-Normalisierung,
Typfehler, nicht endliche Winkel, Spielzustand und abgewiesene Fahrzeugfälle.
Die 14 Windows-Tests, der Build, die Paketprüfung und der Spieltest dieser
Erweiterung wurden inzwischen vom Nutzer als erfolgreich bestätigt.
Abnahme: F7 zu Fuß speichern, drehen/weggehen, F8 und Ausrichtung kontrollieren;
dasselbe als Fahrer wiederholen. Passagier-Speichern muss abgewiesen werden,
ohne F7/F8 zu deaktivieren. Neigung/Rollen werden nicht gespeichert.

## Interior-Teleport (API 6, vom Nutzer bestätigt)

Gleiche ABI-Struktur, neue Semantik: `interior` wählt nun den Zielbereich;
Status 2 bedeutet laufender Türübergang. API-Version erhöht, damit alte Hosts
nicht versehentlich die frühere Ablehnungssemantik verwenden.

Referenzen im gepinnten SDK: `CGame.cpp` (currArea 0xB72914),
`CStreaming.cpp` (RemoveBuildingsNotInArea 0x4094B0),
`CEntryExitManager.cpp` (WeAreInInteriorTransition 0x43E400;
Stackposition 0x96A7C4), `CCamera.cpp` (TheCamera 0xB6F028;
RestoreWithJumpCut 0x50BAB0), `CTimeCycle.cpp` (StopExtraColour 0x55FF20).
SDK-Dateien werden weiterhin nicht zusätzlich gelinkt.

Vor Änderungen werden Ziel, Spieler, Fahrzeug und Insassen geprüft. Bereich
und Entity-Area-Codes werden vor dem Streaming gesetzt; beim Bereichswechsel
werden alter Portal-Kontext, Farbfilter und Kamera zurückgesetzt. Der generische
Koordinatenteleport aktiviert keine Shop-/Missionsskripte und rekonstruiert keine
gebäudespezifische Portal-/Radar-Zuordnung. Normale Türübergänge nach dem Teleport
brauchen deshalb einen ausdrücklichen Spieltest.

Quervergleich: [gta-reversed EntryExit](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/EntryExit.cpp)
und [EntryExitManager](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/EntryExitManager.cpp).
Automatisierte Tests simulieren Bereichswechsel und Übergangsablehnung;
Streaming, Kamera und Kollisionsverhalten müssen im Spiel geprüft werden.
Prüfstand API 6: Release/x86-Build, 15 native Binding-Tests, Paketprüfung und
21 Python-Runtime-Tests bestanden. Der Nutzer hat die Funktion im Spiel bestätigt.

## Rüstung (API 7, vom Nutzer bestätigt)

ABI um `playerArmour(float*)` und `setPlayerArmour(float)` erweitert.
`GtaSdk.cpp` verwendet `CPed::m_fArmour`, mit Layoutprüfung auf Offset 0x548.
Bei jedem Zugriff werden aktueller Spieler, Spielzustand und Spielthread geprüft.
Gelesen werden endliche, nichtnegative Werte; der Setter unterstützt ausdrücklich
den Standardbereich 0..100, unabhängig von möglichen erhöhten Spiellimits.
`bool`, falsche Typen, NaN und unendliche Werte werden abgewiesen. Schreiben
setzt einen lebenden Spieler voraus. Gesundheit bleibt unverändert.

`example_armour.py`: F9 setzt Rüstung auf 100 und protokolliert den gelesenen Wert.
Native Tests prüfen Grenzen, Konvertierung, fehlenden/toten Spieler und Thread;
Runtime-Tests prüfen Spielerwechsel und das F9-Beispiel einschließlich Halten.
Spielabnahme: Rüstung verlieren, F9 drücken, HUD und Log kontrollieren; auch
Pause, Fokuswechsel, Fahrzeug und fehlenden/toten Spieler prüfen.
Prüfstand API 7: Release/x86-Build, 17 native Tests, 23 Python-Tests und
Paketprüfung bestanden. Die Funktion wurde vom Nutzer im Spiel bestätigt.

## Geld und Fahndungslevel (API 8, vom Nutzer bestätigt)

ABI um vier Lese-/Schreibfunktionen für Integer ergänzt. `CWorld.cpp` im
gepinnten SDK dokumentiert `PlayerInFocus` (0xB7CD74) und `Players` (0xB7CD98).
Der Adapter prüft den Index (0..1), die Speicherregion und die Übereinstimmung
des Info-Peds mit dem aktuellen Spieler. Kein Zeiger wird in Python gespeichert.
Layoutprüfungen: `CPlayerInfo::m_nMoney` bei 0xB8, `CWanted::m_nWantedLevel`
bei 0x2C. Geldsetter aktualisiert `m_nMoney` und `m_nDisplayMoney` gemeinsam.

`CWanted` kommt aus `CPlayerInfo::m_PlayerData.m_pWanted`; Speicher wird vor
Zugriff geprüft. Setzen verwendet `CWanted::SetWantedLevel` (0x562470), statt
das Sterne-Feld direkt zu überschreiben. Spielmaximum und Cheats bleiben
wirksam; es gibt keine dauerhaft gesperrte Fahndungsstufe.
Quervergleich: [gta-reversed Wanted](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/Wanted.cpp).

Setter verlangen echte Python-Integer (kein bool): Geld 0..999999999,
Sterne 0..6. Werte außerhalb des Bereichs: `ValueError`; Integer außerhalb
von C-long: `OverflowError`. Schreiben verlangt lebenden Spieler; alle
Zugriffe verlangen aktiven Spielzustand und Spielthread.

Tests simulieren Grenzen, falsche Typen, Integer-Überlauf, Tod, Spielerwechsel,
Threadprüfung, Spielmaximum und Cheats. Reale Geldanzeige, Verfolgung und
GTA-Adressen brauchen die Spielabnahme. Beispiel: `example_money_wanted.py`.
Prüfstand API 8: Release/x86-Build, 20 native Tests, 25 Python-Tests und
Paketprüfung bestanden. Funktion vom Nutzer im Spiel bestätigt.

## Maximale Spielergesundheit (API 9, vom Nutzer bestätigt)

Unveränderte ABI-Struktur; `playerHealth` liefert als Maximum nun
`CPlayerInfo::m_nMaxHealth`. `CurrentPlayerInfo()` prüft aktiven Spieler,
Thread, Fokusindex, Speicher und Ped-Zuordnung. Fehlende/ungültige Info und
Maximum 0 führen zu nicht verfügbarem Spieler, ohne stillen Ped-Fallback.
Gesundheit bleibt `CPed::m_fHealth`; keine Statistik wird verändert.

Die bisherige Verwendung des generischen `CPed::m_fMaxHealth` entspricht nicht
der Grenze von GTAs `CPlayerInfo::AddHealth` (0x56EAB0).
Quellenvergleich: [gta-reversed PlayerInfo::AddHealth](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/PlayerInfo.cpp)
und [Stats](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/Stats.cpp).
Die Umrechnung des Rohstats und Gesundheitsboni bleiben vollständig bei GTA.

Bindings prüfen neue Schreibwerte erneut gegen das aktuelle Maximum. Lesen
verändert keine überhöhte Gesundheit. Tests simulieren steigende/fallende Limits
und F5-Heilen nach Änderungen; die tatsächlichen CPlayerInfo-Werte und
Gesundheitsboni brauchen den Spieltest mit unterschiedlichen Spielständen.
Prüfstand API 9: Release/x86-Build, 21 native Tests, 26 Python-Tests und
Paketprüfung bestanden. Funktion vom Nutzer im Spiel bestätigt.

## Waffenverwaltung (API 10, vom Nutzer bestätigt)

ABI um `playerWeapon(int*, unsigned int*)` und `playerWeaponAction` erweitert.
Aktionen 0/1/2/3 entsprechen Geben/Auswählen/Einzeln entfernen/Alles entfernen.
Statuscodes: 0 Erfolg, 1 Spieler nicht verfügbar/tot, 2 gesperrter Zustand,
3 nicht im Besitz, 4 ungültiges Argument oder Munitionslimit, 5 Modellladefehler.
`WeaponPolicy.h` definiert die freigegebenen IDs und das Munitionslimit.

Adressen aus gepinntem SDK: `CWeaponInfo.cpp` (GetWeaponInfo 0x743C60),
`CPed.cpp` (GiveWeapon 0x5E6080, SetCurrentWeapon 0x5E6280,
ClearWeapon 0x5E62B0, ClearWeapons 0x5E6320), `CStreaming.cpp`
(RequestModel 0x4087E0, LoadAllRequestedModels 0x40EA10,
ms_aInfoForModel 0x8E4CC0). Keine zusätzlichen SDK-.cpp-Dateien werden gelinkt.

Modelle aus beiden WeaponInfo-Feldern werden mit Streamingflags 0 angefordert,
synchron geladen und auf LOADSTATE_LOADED geprüft. Fremde Persistenzflags werden
nicht gelöscht. Nach dem Laden wird der aktuelle lebende Spieler erneut geprüft.
Inventaraktionen folgen den GTA-Funktionen inklusive Slotersetzung und
Munitionsübernahme. Das Entfernen prüft vor dem Aufruf die genaue ID im Slot.

Mutationen werden in Fahrzeug-/Jetpack-Zuständen, bei gesetztem SavedWeapon und
während Türübergängen abgewiesen. SavedWeapon-Sentinel 55 ist im alten SDK-Enum
nicht benannt; Referenz: [gta-reversed eWeaponType](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/Enums/eWeaponType.h).
Semantik-/Signaturvergleich (GiveWeapon liefert einen Slot):
[gta-reversed Ped](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/Entity/Ped/Ped.cpp).

Python bietet `WeaponType` als IntEnum, vier Inventarmethoden sowie die lesbaren
Eigenschaften `current_weapon` und `weapon_ammo`. Sonderausrüstung 39/40/44..46
bleibt bei Einzelaktionen ausgeschlossen. `clear_weapons` entfernt das gesamte
Inventar inklusive Sonderausrüstung und vorher vorhandener Waffen.

Prüfstand API 10: Release/x86-Build, 24 native Tests, 28 Python-Tests und
Paketprüfung bestanden. Funktion vom Nutzer im Spiel bestätigt. Native Tests
simulieren den Host, ohne die realen GTA-Funktionen auszuführen.

## Fahrzeug-Momentaufnahme und Spielerzustände (API 11, vom Nutzer bestätigt)

ABI ergänzt `SpaPlayerVehicle` (Modell-ID, Fahrerflag, Gesundheit, XYZ) und
`playerVehicle(SpaPlayerVehicle*)`. Rückgabe -1: nicht verfügbar/inkonsistent,
0: zu Fuß, 1: Daten gefüllt. Keine Spielzeiger überqueren die DLL-Grenze.

`CurrentPlayerInfo()` prüft Spieler, Thread, Spielzustand und Info-Zuordnung.
Der Adapter wertet zuerst `CPed::bInVehicle` aus; ein zu Fuß noch gespeichertes
`m_pVehicle` wird ignoriert. Bei Fahrzeugzustand prüft er dessen Speicher und
ob der aktuelle Ped Fahrer oder ein Eintrag der Passagierliste ist. Position
kommt aus Matrix bzw. einfacher Platzierung; Koordinaten/Gesundheit müssen
endlich sein. Layoutprüfung: `CVehicle::m_fHealth` bei 0x4C0. Keine neuen
Spiel-Funktionsadressen; es werden nur gepinnte SDK-Felder gelesen.

pybind11 bindet `VehicleInfo` ohne öffentlichen Konstruktor und ohne Setter;
die Position ist ein abgetrennter `Vector3`. Jeder Aufruf erzeugt neue Werte.
`player.is_alive` basiert auf Gesundheit; `vehicle`, `in_vehicle` und `is_driver`
fragen den nativen Zustand bei jedem Zugriff neu ab. Alte Momentaufnahmen bleiben
nach Fahrzeug-/Spielerwechsel unverändert, ohne eine Objektidentität zu behaupten.
Diese API ersetzt keine dauerhaften, generationgeprüften Fahrzeug-Handles.

Tests prüfen Fußzustand, Fahrer/Passagier, Modell-/Positionswechsel, unveränderliche
Snapshots, Tod, fehlenden Spieler, Übergangsfehler, Threadprüfung und V-Beispiel.
Reale Sitzzuordnung und Speicherzugriffe brauchen die Spielabnahme.
Prüfstand API 11: Release/x86-Build, 26 native Tests, 30 Python-Tests und
Paketprüfung bestanden. Funktion vom Nutzer im Spiel bestätigt.

## Timer (API 12, vom Nutzer bestätigt)

ABI ergänzt `gameTimeMs()`, unsigned 32-Bit. Gepinnte Referenz `CTimer.cpp`:
`m_snTimeInMilliseconds` bei 0xB7CB84. Der Wert ist auch im pausierten Tick auf
dem Spielthread lesbar. Bindings exportieren `_game_time_ms` und
`_require_game_thread` für die Python-Timerverwaltung. Keine Timer-Worker.

Bootstrap entrollt die Spieluhr mit modulo-2^32-Differenzen; ein Delta größer
als 2^31-1 wird als Rücksprung interpretiert. Dann werden alle Spielzeit-Timer
abgebrochen. Echtzeit nutzt time.monotonic. Die Heuristik erkennt nicht jeden
Save-Wechsel und kann sehr große Zeitsprünge als Reset interpretieren.

Timer-Snapshot am Tick-Anfang; Zustellung nach on_frame nur bei ready.
call_later(0) und während Dispatch angelegte Timer warten bis zum nächsten Tick.
Maximal 64 Aufrufe je Frame; wiederholte Timer wandern ans Listenende und
werden mit Abstand zum Callback-Ende neu geplant. Kein Catch-up. Jeder Aufruf
prüft Abbruch erneut; Wiederholungen können sich selbst abbrechen. Abschluss,
Abbruch und Fehler entfernen Callback-Referenzen. Fehler werden isoliert und
langsame Timer ab 50 ms mit Modul und Callbacknamen protokolliert.

main.py-Fehler verwerfen auch teilweise registrierte Timer. owner ist lediglich
das Callback-Modul, keine vollständige Mod-Lebensdauerverwaltung. Generator-
Tasks folgen in API 13; Worker-Queue und asynchrones Modellstreaming bleiben offen.
Prüfstand API 12: Release/x86-Build, 27 native Tests, 40 Python-Tests und
Paketprüfung bestanden. Funktion vom Nutzer im Spiel bestätigt.

## Kooperative Generator-Tasks (API 13, vom Nutzer bestätigt)

Keine neuen Spieladressen und keine ABI-Felder. Paket-/API-Version erhöht,
damit Host, Runtime und neuer Bootstrap weiterhin gemeinsam geprüft werden.
`start_task` nimmt ausschließlich frische Python-Generatoren entgegen. Eine
Registry verhindert auch das doppelte Einplanen noch nicht begonnener Generatoren.
Wait ist ein unveränderliches NamedTuple; auch direkt erzeugte Tokens werden
vor dem Planen validiert. Kein asyncio-Loop, keine Worker-Threads.

Jeder Schritt wird als einmaliger Timer geplant; neue Schritte warten mindestens
einen Tick und teilen Timer-Zeitquellen, Pause, Budget und Langsamkeitsdiagnose.
Cancel entfernt den wartenden Timer und schließt den Generator. Selbstabbruch
wird bis nach next() verschoben, damit kein laufender Generator geschlossen wird.
finally darf nicht yielden; Cleanup-Fehler werden geloggt und im Handle als Text
gespeichert. Ergebnis/Fehler-/Abbruchzustände sind getrennt; Generatorreferenzen
und Claims werden beim Stop freigegeben, kein Exception-Traceback gespeichert.

Uhrreset setzt die neue Zeitbasis vor dem Cleanup, um rekursive Reseterkennung
aus finally zu vermeiden. Tasks, die aktuell auf Spielzeit warten, werden
zusammen mit Spielzeit-Timern abgebrochen; Echtzeit-Wartezustände bleiben bestehen.
Während globalem Cleanup wird Registrierung blockiert, damit finally keine
verwaisten Tasks oder Timer erzeugt. Ladefehler von main.py räumen auch Tasks auf.
owner bleibt das Generator-Modul, keine vollständige Mod-Identität.

Tests prüfen Warten/Rückgabe, Abbruch vor Start, Selbstabbruch, finally,
Cleanup-Fehler, ungültige Yields/Tokens, doppelte Generatoren, Threadprüfung,
Uhrreset/Echtzeit, Ladefehler und das G/H-Beispiel. Funktion vom Nutzer bestätigt.
Prüfstand API 13: Release/x86-Build, 27 native Tests, 51 Python-Tests und
Paketprüfung bestanden.

## Asynchrones Modellladen (API 14, vom Nutzer bestätigt)

ABI ergänzt requestModel(int,DWORD*), modelReady(DWORD), releaseModel(DWORD).
Anforderung meldet Erfolg, inaktives Spiel, ungültiges Modell oder Referenzlimit;
Status meldet bereit, ausstehend oder invalidiert. Tokens sind positive Integer
und werden im Prozess nie wiederverwendet. Native Registry: maximal 256 Einträge.

Referenzen aus gepinntem SDK: CModelInfo::ms_modelInfoPtrs bei 0xA9B0C8,
CStreaming::ms_aInfoForModel bei 0x8E4CC0, RequestModel 0x4087E0,
CBaseModelInfo::AddRef 0x4C4BA0 und RemoveRef 0x4C4BB0. Modell-ID,
Speicherregion, Metadaten und CD-Ressource werden vor dem Request geprüft.
Geladener Zustand wird aus CStreamingInfo gelesen; kein LoadAllRequestedModels.

Bei Bereitschaft genau ein AddRef pro Token, einschließlich TXD-Referenz. Native
Einträge speichern Metadaten-/RW-Identität nur zur Prüfung gegen den aktuellen
Modelltabelleneintrag. Vor RemoveRef werden Identität, Streamingzustand und
positiver Refcount erneut geprüft; eine ungültig gewordene Ressource wird nicht
blind dereferenziert/dekrementiert. Keine Rohzeiger in Python, keine Änderung
fremder Streamingflags, kein globales RemoveModel/SetModelIsDeletable.
Semantikvergleich: [gta-reversed BaseModelInfo](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/Models/BaseModelInfo.cpp)
und [Streaming](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/Streaming.cpp).

load_model ist ein delegierbarer Generator. Er wartet pro Frame auf Bereitschaft
mit Echtzeit-Timeout; Bereitschaft gewinnt bei gleichzeitiger Fristüberschreitung.
Vor Rückgabe räumt Generator-Close seine Anforderung auf. Nach Rückgabe hält Model
die Referenz bis release()/Kontextende. Ohne with/finally bleibt sie explizit
angefordert; es gibt keinen nativen __del__-Aufruf aus einem beliebigen Thread.

Globaler Cleanup und erkannte Uhrresets geben alle Models frei, auch bei auf
Echtzeit wartenden Tasks. Bereits wartende load_model-Aufrufe erkennen die
Invalidierung beim nächsten Schritt. Noch ausstehende globale GTA-Requests dürfen
weiterlaufen; fremde Konsumenten werden nicht abgebrochen.

Tests prüfen Bereitschaft, Referenzgewinn genau einmal, unabhängige Verbraucher,
Grenzen/Limit, Pause, Timeout, Abbruch, Kontextfreigabe, Uhrreset und Ladefehler.
Echtes Streaming und Refcount-/TXD-Verhalten brauchen den Spieltest.
Prüfstand API 14: Release/x86-Build, 30 native Tests, 60 Python-Tests und
Paketprüfung bestanden. Funktion vom Nutzer im Spiel bestätigt.

## Hintergrundjobs (API 15, Spielabnahme offen)

Keine neuen ABI-Felder oder Spieladressen. Python startet bei Bedarf zwei
Prozess-langlebige Daemon-Threads. Arbeitsqueue: 32 Einträge. Jobregistry: maximal
64 noch nicht zugestellte Jobs. Ergebnisqueue enthält Daten plus Fehlertext,
keine Ausnahmeobjekte. GTA-Zugriffe bleiben über die native Threadprüfung
gesperrt; Python-Eventregistrierung prüft nun ebenfalls den Spielthread.

Worker rufen ausschließlich work() auf und stellen Ergebnisse in eine SimpleQueue.
Ein Lock synchronisiert Abbruch mit dem Commit eines Ergebnisses; weder Nutzer-
Code noch Dateizugriffe laufen unter diesem Lock. Cancel verwirft Callbacks und
wartende Funktionsreferenzen, kann bereits laufenden Code aber nicht abbrechen.
Worker halten nach Abschluss im Leerlauf keine Referenz auf den letzten Job.

_tick entnimmt zu Beginn eines aktiven Frames maximal 32 Ergebnisse als Snapshot.
Zustellung erfolgt nach on_frame, vor Timern. Abbruch-/Registryprüfung unmittelbar
vor Callback verhindert Zustellung alter Ergebnisse; Worker- und Callbackfehler
werden isoliert geloggt. Callbacks ab 50 ms erhalten eine Langsamkeitsdiagnose.
done wird erst bei Zustellung/Abbruch gesetzt; result bleibt nach Erfolg lesbar.

Globaler Cleanup und erkannte Uhrresets brechen alle offenen Jobs ab und leeren
fertige Ergebnisse unter demselben Commit-Lock. Später zurückkehrende Worker
dürfen keine weiteren Ergebnisse für abgebrochene Jobs einreihen. Laufende
Funktionen brauchen eigene I/O-Timeouts; es gibt weder Thread-Abschuss noch
blockierendes Join auf dem Spielthread. Eigentümerdiagnose ist das Work-Modul,
vollständige Mod-Zuordnung bleibt separat.

Tests prüfen Queuelimits, Zustellbudget, Pause, Queued-/Running-Cancel,
Fehlerisolierung, Reset-/Ladefehler-Cleanup und das O/P-Beispiel. Zwei echte
Worker werden im Integrationstest gestartet: Ergebnis läuft auf dem Mainthread,
Timer-/Eventregistrierung im Worker wird abgewiesen. Native Tests prüfen die
Thread-Grenze zusätzlich mit einem echten Python-Thread und kompilierten Bindings.

Prüfstand API 15: Release/x86-Build, 31 native Tests, 70 Python-Tests und
Paketprüfung bestanden. Spielabnahme offen.

## Geprüfte Fahrzeug-Handles (API 16, Spielabnahme offen)

ABI ergänzt capturePlayerVehicle, vehicleHandleValid, vehicleHandleInfo und
closeVehicleHandle. Daten laufen weiter als SpaPlayerVehicle über die Grenze;
Python sieht lediglich prozessweit nicht wiederverwendete positive Tokens.
Native Registry aus 128 festen Slots, damit die Adressen der CEntity*-Felder
für GTAs Referenzverwaltung stabil bleiben. Keine Fahrzeugbesitzübernahme.

Pool: CPool<CVehicle,CHeli> aus dem gepinnten SDK, Pointer bei 0xB74494
(CPools.cpp). Vor Zugriff Header, Größe (1..100000), Pointer, Index, Slotflag,
Belegung und Generation prüfen; Fahrzeugadresse muss exakt zum Slot passen.
Das aus SDK-Feldern gebildete Ref enthält Slotindex und Generationsbyte.
Zusätzlich prüft jeder Zugriff registrierte CReference, Entity-Typ und Speicher.

CEntity.cpp dokumentiert RegisterReference (0x571B70), CleanUpOldReference
(0x571A00) und ResolveReferences (0x571A40). GTA setzt beim Auflösen die stabile
Registry-Pointeradresse auf null. Nach Registrierung wird geprüft, dass der
Eintrag tatsächlich in der Referenzliste vorhanden ist; Erschöpfung führt zu
Fehler statt ungeschütztem Handle. Listenprüfung ist auf 4096 Einträge begrenzt.
Das schützt auch gegen Wiederverwendung mit gewrapptem Generationsbyte.
Quervergleich: [gta-reversed Entity](https://github.com/gta-reversed/gta-reversed/blob/master/source/game_sa/Entity/Entity.cpp).

Bei close wird nur eine noch gültig auflösbare Referenz abgemeldet und der feste
Slot geleert. Eine entfernte/invalidierte Entity wird nicht blind dereferenziert.
Das Fahrzeug wird weder persistent gesetzt noch gelöscht. close ist während
Pause auf dem Spielthread erlaubt; valid ist bei inaktivem Spiel vorübergehend
falsch, ohne den Handle dauerhaft zu schließen. Info meldet bei entferntem Objekt
InvalidVehicleError, bei inaktivem Spiel RuntimeError. Beschädigte/fehlende
Positionsdaten führen ebenfalls zu RuntimeError.

Python Vehicle stellt live geprüfte model_id/health/position/snapshot bereit,
closed/valid sowie close und Kontextmanager. player.vehicle_handle ist explizit
von der unveränderlichen player.vehicle-Momentaufnahme getrennt. Snapshot-
is_driver wird relativ zum aktuellen Spieler neu bestimmt. Uhrreset und globaler
Cleanup schließen alle offenen Handles; kein nativer Aufruf aus __del__.

Tests simulieren Objektentfernung mit identischem wiederverwendetem Slot und
Generation, Fahrzeugwechsel, dynamische Daten, Referenzlimit, Pause, Thread-
Prüfung, explizites/context Close und das B/Z/X-Beispiel. Native Referenzlisten
und echte Pool-Reuse-Fälle brauchen den Spieltest.
Prüfstand API 16: Release/x86-Build, 34 native Tests, 74 Python-Tests und
Paketprüfung bestanden. Spielabnahme offen.
