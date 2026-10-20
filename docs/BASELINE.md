# Funktionierender Ausgangsstand

Vor der Umstellung auf Plugin-SDK/pybind11 wurde der vom Nutzer im Spiel
bestätigte Python-3.11-/F5-Stand gesichert.

- Quellcommit: `5a2df0a1c295762e6f85ed2e92d84ec03c4a9f62`.
- Lokales Archiv: `backups/baseline-python311-f5.zip`.
- Inhalt: Quellstand einschließlich damaliger Arbeitsdateien, Release-Paket und
  eingebetteter Python-Runtime. Das Archiv enthält `BASELINE-SHA256.json`.
- Artefakt- und Spiel-Hashes: `docs/BASELINE.json`.
- Ein Git-Tag war wegen des schreibgeschützten `.git`-Ordners nicht möglich.

## Beobachtete Testumgebung

- Windows 11 (vom Nutzer gezeigte Oberfläche; genaue Buildnummer nicht erhoben).
- Klassisches GTA SA, 1.0 US/Hoodlum-Erkennung: Signatur `0x16197BE9` bei RVA `0x1000`.
- Python 3.11.9, Windows x86, offizielles Embeddable-Paket.
- ASI-Laden und F5-Heilen vom Nutzer bestätigt.
- `vorbisFile.dll` liegt als möglicher Proxy-Loader im Spielverzeichnis; die genaue
  Loader-Version ist nicht bestätigt. Der Dateihash steht in `BASELINE.json`.
- Mitinstallierte Mods: unter anderem CLEO, SilentPatch, GInput und Modloader.

## Rückkehr zur gesicherten Version

GTA vollständig beenden. Aus dem Archiv `Release/SanPythonAndreas.asi` und den
kompletten Ordner `Release/SanPythonAndreas` gemeinsam zurückkopieren. Eigene
inzwischen geänderte Skripte vorher separat sichern. Einzelne DLLs verschiedener
Paketversionen dürfen nicht vermischt werden.

Das Archiv ist eine lokale Rückfallversion und wird nicht in Git eingecheckt.
Der erfolgreiche Ausgangsstand bedeutet nicht, dass der neue SDK-/pybind11-Build
bereits im Spiel geprüft wurde.
