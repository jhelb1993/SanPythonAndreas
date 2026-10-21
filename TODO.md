# SanPythonAndreas – Gesamt-TODO

Ziel: Python-Mods für das klassische GTA: San Andreas schreiben, mit einer gut
dokumentierten `sanandreas`-API und einem vollständig mitgelieferten x86-Python.

Wir arbeiten die Meilensteine der Reihe nach ab. Ein Haken bedeutet umgesetzt
und geprüft; geschriebener Code allein gilt noch nicht als bestandener Spieltest.
Die breite GTA-API entsteht schrittweise. Plugin-SDK lässt sich nicht vollständig
und ohne Anpassungen automatisch in Python importieren.

## 0. Bereits vorhanden

- [x] ASI und separate native Runtime-DLL.
- [x] Python 3.11.9 x86 mit lokalem Embeddable-Paket und automatischem Download.
- [x] Vollständiger Release-Build mit Paketprüfung über `Build-Release.cmd`.
- [x] Python-Ausführung auf dem Spielthread und dauerhafter Interpreter.
- [x] `import sanandreas as sa` in den Skripten.
- [x] Ereignisse `on_game_ready`, `on_frame` und `on_key_down`.
- [x] Tastendruckerkennung mit Behandlung von Pause und Fokuswechsel.
- [x] Spielerzugriff: `player()`, `health` und `max_health`.
- [x] HUD-Hilfetext über `show_text()`.
- [x] F5-Heilungsbeispiel; Funktion im Spiel vom Nutzer bestätigt.
- [x] Python-Logging, sichtbare Ladefehler und separate API-Diagnose.
- [x] Erste `.pyi`-Typdefinitionen und automatisierte Python-Tests.

## 1. Funktionierende Basis absichern

- [x] Funktionierenden Stand als lokales Release-Archiv mit Hashmanifest sichern.
- [ ] Optional Git-Tag setzen (`.git` ist hier schreibgeschützt).
- [x] GTA-Version und beobachtete Testumgebung dokumentieren; Loader-Version noch zu bestätigen.
- [ ] Reproduzierbare Anleitung für einen frischen Checkout ohne installiertes Python prüfen.
- [ ] Paketversion und ausdrückliche Versionsnummer der ASI/Runtime-Schnittstelle einführen.
- [ ] Bei gemischten ASI-/Runtime-/Bootstrap-Versionen verständlich abbrechen.
- [ ] Geladene Modulpfade, Python-Version und Plugin-Version beim Start protokollieren.
- [ ] Festlegen, welche Skript-/Konfigurationsdateien ein Update überschreiben darf.

Abnahme: Ein frischer Release-Build funktioniert im Spiel; ein absichtlich
vermischtes Paket meldet den Versionskonflikt eindeutig.

## 2. Plugin-SDK und pybind11 integrieren – abgeschlossen

Implementierung liegt vor: gepinnte Abhängigkeiten, SDK-Adapter, pybind11-Modul,
API-Version 2 und sieben native Tests im Windows-Build. Windows-Release/x86-Build,
alle sieben nativen Tests und die Paketprüfung sind bestanden (Nutzernachweis).
**Abnahme bestanden:** Das F5-Beispiel funktioniert laut Nutzerbestätigung auch
im Spiel mit der SDK-/pybind11-Anbindung. Details: `docs/BINDINGS.md`.

- [x] Abhängigkeiten mit festen Versionen/Commits ins Buildsystem aufnehmen.
- [x] Benötigte Lizenzen im Paket mitliefern.
- [x] SDK-Anbindung an die unterstützte GTA-Version kapseln.
- [x] Eindeutigen Besitzer für Initialisierung und Lebensdauer des Python-Interpreters behalten.
- [x] Ein kleines pybind11-Modul in der bestehenden Runtime-DLL erproben.
- [x] Spieler-Gesundheit und HUD-Ausgabe über die neue Binding-Schicht bereitstellen.
- [x] Bestehende Python-API und Skripte bei der Umstellung kompatibel halten.
- [x] Alte manuelle Bindings nach erfolgreicher Umstellung entfernen.

Abnahme: Das bestehende F5-Beispiel funktioniert unverändert mit der neuen
Anbindung. Release-Build, Paketprüfung und bisherige Tests bestehen.

## 3. Grundlage für Spielobjekte

`Vector3` ist implementiert und als C++-Werttyp getestet; der Nutzer hat
das funktionierende F6-Beispiel im Spiel bestätigt. Die weiteren Handle-/Lebensdaueraufgaben folgen
separat. Die aktuelle Spieleransicht bleibt vorerst ein Zugriff auf den jeweils
aktuellen Spieler.

- [x] `Vector3` mit `x`, `y`, `z` und grundlegenden Rechenoperationen anbieten.
- [ ] Geprüfte Handles für Peds, Fahrzeuge und Objekte einführen.
- [ ] Objektgültigkeit bei jedem nativen Zugriff prüfen; keine frei verfügbaren Rohzeiger.
- [ ] Verhalten bei gelöschten Objekten, Tod, neuem Spiel und Spielstandwechsel festlegen.
- [ ] Aktuelle Spieleransicht klar von einem Handle für einen bestimmten Ped unterscheiden.
- [ ] Einheitliche Python-Ausnahmen für ungültige Objekte und falsche Threads definieren.
- [ ] Besitz und Aufräumen von durch Skripte erzeugten Objekten festlegen.

Abnahme: Ein Handle auf ein entferntes Objekt erzeugt eine verständliche
Python-Ausnahme; es greift nicht auf einen inzwischen wiederverwendeten Slot zu.

## 4. Spieler-API und Position

Lesbare `player.position` und ein separat ladbares `example_position.py` für F6
sind implementiert (API 3). Python-Tests bestanden; Funktion im Spiel vom Nutzer
bestätigt. API 4 ergänzt Teleportieren im aktuellen Interior; Funktion vom Nutzer bestätigt.
API 5 ergänzt Heading; Build, native Tests, Paketprüfung und Spieltest wurden vom Nutzer bestätigt.
API 6 ergänzt Interior-Wechsel beim Teleportieren; vom Nutzer im Spiel bestätigt.
API 7 ergänzt Rüstung; vom Nutzer im Spiel bestätigt.
API 8 ergänzt Geld und Fahndungslevel; vom Nutzer im Spiel bestätigt.
API 9 verwendet das spielerspezifische Gesundheitslimit; vom Nutzer im Spiel bestätigt.
API 10 ergänzt Waffenverwaltung zu Fuß; vom Nutzer im Spiel bestätigt.
API 11 ergänzt Spielerzustände und eine Fahrzeug-Momentaufnahme; Spielabnahme steht noch aus.

- [x] Spielerposition lesen; F6-Beispiel zeigt Koordinaten an.
- [x] Position setzen und Teleportieren im aktuellen Interior (vom Nutzer bestätigt).
- [x] Richtung/Heading lesen und setzen: API 5 vom Nutzer im Spiel bestätigt.
- [x] Interior lesen und versehentlichen Wechsel beim Teleportieren verhindern.
- [x] Interior-Wechsel mit Weltbereich, Streaming und Kamera: API 6 vom Nutzer im Spiel bestätigt. Shop-/Missionsaktivierung und Portalzuordnung bleiben separat.
- [x] Rüstung lesen und setzen: API 7 vom Nutzer im Spiel bestätigt.
- [x] Geld und Fahndungslevel lesen und verändern: API 8 vom Nutzer im Spiel bestätigt.
- [x] Maximale Gesundheit mit den Spielerstatistiken abgleichen: API 9 vom Nutzer im Spiel bestätigt.
- [x] Waffen geben, auswählen und entfernen: API 10 vom Nutzer im Spiel bestätigt (zu Fuß, IDs 1..18/22..38/41..43). Sonderausrüstung folgt separat.
- [ ] Aktuelles Fahrzeug und Spielerzustände abfragen: API 11 implementiert (unveränderliche Fahrzeugdaten, is_alive/in_vehicle/is_driver), Spielabnahme offen. Dauerhafte Fahrzeug-Handles folgen in der Objektgrundlage.

Abnahme: F5 heilt, F6 zeigt die Position, ein weiteres Beispiel teleportiert
kontrolliert zwischen zwei bekannten Positionen.

## 5. Timer, Tasks und asynchrones Laden

- [ ] Verzögerte und wiederholte Aufrufe anbieten.
- [ ] Kooperatives Warten ermöglichen, ohne den Spielthread zu blockieren.
- [ ] Spielzeit und Echtzeit sowie Verhalten während Pause ausdrücklich festlegen.
- [ ] Tasks abbrechen und dem verursachenden Skript zuordnen können.
- [ ] Modellanforderung mit Bereitschaftsprüfung, Timeout und Freigabe kapseln.
- [ ] Hintergrundarbeit mit einer Queue für Rückgaben auf den Spielthread ermöglichen.
- [ ] Task-Fehler isolieren und langsame Callbacks protokollieren.

Abnahme: Ein Countdown und eine Modellanforderung laufen ohne Ruckeln durch
blockierende Warteschleifen; Abbruch und Timeout funktionieren.

## 6. Fahrzeug-API

- [ ] Modelle über Namen und IDs auflösen und vor dem Erzeugen laden.
- [ ] Fahrzeuge erzeugen und eindeutig als skripteigene Objekte verwalten.
- [ ] Fahrzeuge gültig entfernen und angeforderte Ressourcen freigeben.
- [ ] Position, Heading und Geschwindigkeit lesen/setzten.
- [ ] Gesundheit, Reparatur, Farben, Türen und Motorzustand anbieten.
- [ ] Spieler/Peds in passende Sitzplätze setzen und aussteigen lassen.
- [ ] Fahrzeuge in einem Umkreis suchen.
- [ ] Fahrzeugverlust und Zerstörung über Handles korrekt behandeln.

Abnahme: Ein Beispiel erzeugt einen Infernus, setzt den Spieler hinein und
entfernt das erzeugte Fahrzeug auf ausdrücklichen Aufruf wieder.

## 7. Peds, Objekte und Welt

- [ ] Peds mit Modell laden, erzeugen und entfernen.
- [ ] Ped-Zustände und grundlegende Aufgaben/Animationen anbieten.
- [ ] Weltobjekte erzeugen, drehen, bewegen und entfernen.
- [ ] Modelle und Animationen nach Ende ihrer Verwendung freigeben.
- [ ] Uhrzeit und Wetter lesen/setzten.
- [ ] Bodenhöhe, Entfernung und einfache Weltabfragen anbieten.
- [ ] Marker, Blips und Checkpoints verwalten.
- [ ] Raycasts und Entitätssuche ergänzen.

Abnahme: Ein Beispiel erzeugt einen NPC und ein Objekt mit Kartenmarkierung;
beim Beenden werden nur seine eigenen Ressourcen aufgeräumt.

## 8. Ereignisse und Eingaben ausbauen

- [ ] Registrierungen als abmeldbare Verbindungen zurückgeben.
- [ ] `on_key_up`, gehaltene Tasten und Tastenkombinationen ergänzen.
- [ ] Controller-/Spielaktionen als Alternative zu Windows-Tastencodes prüfen.
- [ ] Ereignisse für Spielstandwechsel, Spieler-Tod und Respawn ergänzen.
- [ ] Fahrzeug-Ein-/Ausstieg und Zerstörung anbieten.
- [ ] Zustellreihenfolge, Argumente und einmalige Handler dokumentieren.
- [ ] Fehler einzelner Handler von anderen Skripten isolieren.

Abnahme: Registrieren, Abmelden und mehrfaches Laden hinterlassen keine
doppelten Handler. Fokuswechsel lösen keine ungewollten Tastenevents aus.

## 9. Mehrere Skripte und Mod-Verwaltung

- [ ] Skriptmanager mit eigener Identität und Status pro Skript/Mod einführen.
- [ ] Ein einfaches Mod-Verzeichnislayout und optionales Manifest festlegen.
- [ ] Einstiegspunkt, Imports und Ladereihenfolge definieren.
- [ ] Ereignisse, Tasks und erzeugte Objekte ihrem Skript zuordnen.
- [ ] `on_load`/`on_unload` und zentralen Cleanup anbieten.
- [ ] Einzelne Mods aktivieren/deaktivieren können.
- [ ] Fehler einer Mod dürfen andere Mods nicht stoppen.
- [ ] Konfiguration pro Mod unterstützen.

Abnahme: Zwei unabhängige Mods laufen gleichzeitig; eine lässt sich einschließlich
ihrer Ressourcen stoppen, ohne die andere zu beeinträchtigen.

## 10. Hot Reload und Entwicklungskomfort

- [ ] Manuelles Neuladen einer einzelnen Mod anbieten.
- [ ] Vor dem Neuladen ihre Handler, Tasks und Ressourcen aufräumen.
- [ ] Umgang mit importierten Untermodulen ausdrücklich definieren.
- [ ] Fehler beim Neuladen mit verständlichem Skriptstatus anzeigen.
- [ ] Optionalen Dateiwächter mit Änderungen gebündelt verarbeiten.
- [ ] Optionale Zustandsübergabe zwischen zwei Skriptversionen anbieten.
- [ ] Eine kleine Debug-Konsole für Status, Reload und Diagnose ergänzen.

Abnahme: Mehrfaches Ändern und Neuladen erzeugt keine doppelten Events,
verwaisten Tasks oder immer weiter anwachsenden Objektbestand.

## 11. HUD, Zeichnen, Kamera und Audio

- [ ] Eigene Texte mit Dauer, Farbe und Position anbieten.
- [ ] Einfache 2D-Elemente und Welt-zu-Bildschirm-Projektion ergänzen.
- [ ] Rendering ausschließlich in passenden Rendercallbacks ausführen.
- [ ] Texturen und Renderressourcen bei Geräteverlust/-wiederherstellung behandeln.
- [ ] Kamera lesen und kontrollierte Kamerasequenzen ermöglichen.
- [ ] Kamera beim Stoppen einer Mod zuverlässig zurückgeben.
- [ ] Soundeffekte und grundlegende Audiosteuerung anbieten.

Abnahme: Ein HUD- und ein Kamerabeispiel überstehen Pause, Alt-Tab und Mod-Unload.

## 12. API-Abdeckung systematisch erweitern

- [ ] Gewünschte API-Bereiche und unterstützte GTA-Versionen als Abdeckungsliste pflegen.
- [ ] Ein einheitliches Binding-Schema mit Typen, Threadvorgaben und Lebensdauerregeln festlegen.
- [ ] Wiederkehrende Bindings und Typdefinitionen nach Möglichkeit generieren.
- [ ] Generierte Bindings auf Zeiger, Überladungen und Besitzverhältnisse prüfen.
- [ ] Optional eine geprüfte SCM-/Opcode-Brücke für zusätzliche Skriptbefehle untersuchen.
- [ ] API-Versionierung und Regeln für inkompatible Änderungen festlegen.
- [ ] Weitere Spielversionen erst mit eigenem Erkennungs- und Testpfad ergänzen.

Abnahme: Neue Funktionen folgen demselben Schema; Dokumentation und
Typdefinitionen stimmen mit dem tatsächlich importierbaren Modul überein.

## 13. Dokumentation, Beispiele und Auslieferung

- [ ] Einstieg: Installation, erstes Skript und Fehlerdiagnose dokumentieren.
- [ ] API-Referenz und `.pyi`-Dateien mit jeder Erweiterung aktualisieren.
- [ ] Beispiele für Spieler, Teleport, Fahrzeuge, Tasks und Mod-Unload liefern.
- [ ] Einrichtung für VS Code und Visual Studio beschreiben.
- [ ] Unterstützte Python-Pakete und Installation passender x86-Abhängigkeiten erklären.
- [ ] Ein Release-ZIP mit ASI, Datenordner, Lizenzen und Versionsinformationen erzeugen.
- [ ] Ein Updateschema entwickeln, das eigene Skripte und Konfigurationen erhält.
- [ ] Vorgehen für Aktualisierungen der gebündelten Python-Runtime festlegen.

Abnahme: Ein Nutzer kann das Paket ohne Entwicklerwerkzeuge installieren und
mit der Anleitung seine erste Mod schreiben.

## Prüfung bei jedem Meilenstein

- [ ] Passende automatisierte Tests für neue Zustände und Fehlerfälle bestehen.
- [ ] Release/x86-Build und Paketprüfung bestehen.
- [ ] Funktioniert im Spiel mit unterstützter GTA-Version.
- [ ] Relevante Fälle geprüft: kein Spieler, Pause, Alt-Tab, Tod oder gelöschtes Objekt.
- [ ] Skriptfehler und falsche Argumente führen zu nachvollziehbaren Meldungen.
- [ ] Bestehende Beispiele funktionieren weiterhin.
- [ ] README, Typdefinitionen und diese Liste sind aktualisiert.

## Unmittelbar als Nächstes

1. Funktionierenden Stand und Testumgebung festhalten (Meilenstein 1).
2. Plugin-SDK und pybind11 anbinden, ohne das F5-Beispiel zu verändern (Meilenstein 2).
3. Geprüfte Objektgrundlage und `Vector3` schaffen (Meilenstein 3).
4. Spielerposition lesen und F6-Koordinatenbeispiel liefern (Beginn Meilenstein 4).
