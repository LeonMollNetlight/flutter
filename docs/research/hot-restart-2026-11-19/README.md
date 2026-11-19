# Hot-Restart-Fixes außerhalb von DartPad: Desktop-Ergebnis

Stand: 19.11.2026. Alle drei Probleme lassen sich außerhalb von DartPad
reproduzieren. Die vollständige Kombination behebt die beobachteten
Flutter-Web-Retention-Pfade. Der DDC-Fix allein hat allerdings einen
zusätzlichen, auch in reinem Dart-Web reproduzierbaren Callback-Effekt:
Ein alter DOM-Listener wirft nach Hot Restart einen TypeError. Deshalb ist
der Dart-Change noch nicht als unabhängig sicherer Fix bestätigt.

## Welche Anwendungen sind betroffen?

| Verwendung | CanvasKit PR 196786 | Dispatcher PR 196787 | DDC CL 578301 |
| --- | --- | --- | --- |
| Normales Flutter-Web, DDC-Debug, CanvasKit, Hot Restart | Desktop reproduziert | Desktop reproduziert | Desktop reproduziert; zusammen getestet |
| Reines Dart-Web, DDC-Canary mit Library-Bundle-Loader | Keine Flutter-Engine | Kein Flutter-Dispatcher | Runtime-Leck und neuer Callback-TypeError reproduziert |
| Reines Dart-Web, traditioneller AMD/DDC-Loader | Keine Flutter-Engine | Kein Flutter-Dispatcher | Dieser neue Disposal-Pfad wird nicht verwendet; bestehender Runtime-Reset wird im Regressionstest geprüft |
| Reines Dart-Web mit `dart compile js` oder `dart compile wasm` | Keine Flutter-Engine | Kein Flutter-Dispatcher | Vorher/Nachher-Ausgaben der Test-App bytegleich |
| Flutter-Release mit CanvasKit | Gemeinsame Surface-Disposal-/Resize-Pfade ändern sich ebenfalls; hier nicht als Release-Benchmark untersucht | Gemeinsames Dispatcher-Disposal ändert sich; gewöhnlich kein Hot Restart | Kein DDC-Anwendungs-Runtime |
| Flutter-Wasm mit Skwasm | Andere Renderer-Implementierung | Gemeinsamer Dispatcher-Code; hier nicht gemessen | Kein DDC-Anwendungs-Runtime |
| DartPad-Console / Flutter-Sandbox | Bei CanvasKit | Bei Flutter | Canary-DDC betroffen; Aufrufpfad durch Quellprüfung und frühere separate DartPad-Messungen belegt |

„Dart-Web“ allein bezeichnet daher keine einheitliche Laufzeit. Der
reproduzierte Dart-SDK-Effekt betrifft den Canary-DDC-Hot-Restart, nicht
automatisch jede Webdev-Konfiguration oder einen JavaScript-/Wasm-Release.
Die Standard-Builder-Optionen und Aufrufpfade stehen im
[Quellenbericht](source-analysis.md).

## Neue Messungen

Apple M4 Pro, macOS 27.2, Chrome **157.0.8103.80**. Normales
`flutter run -d web-server`, Chrome, DDC-Debug und ein animierter
`CustomPaint` mit 300 Kreisen und 4 MiB Anwendungsdaten. Der Flutter-
Maschinen-Protocol-Aufruf `app.restart(fullRestart: true)` löst die
Restarts aus. DartPad wird in diesem Test nicht geladen.

Die acht Fix-Kombinationen wurden jeweils dreimal in neuen Testseiten
gemessen, mit 15 Restarts pro Durchlauf: **24 Durchläufe / 384 Samples**.
Die Tabellenwerte sind Mediane. Die Baseline wurde dreimal separat zuerst
gemessen; die übrigen Varianten wechseln ihre Reihenfolge zwischen den
Durchläufen. Es ist kein vollständig randomisierter Versuch.

| Variante | rAF/s nach 15 Restarts | Aktive WebGL-Kontexte | Alte Renderer / Dispatcher nach GC | JS-Heap-Zuwachs in den letzten 5 Restarts |
| --- | ---: | ---: | ---: | ---: |
| Ohne Fix | 9,41 | 16 | 15 / 15 | 56,64 MiB |
| Nur CanvasKit | 59,93 | 2 | 15 / 15 | 54,96 MiB |
| Nur Click-Listener | 9,85 | 16 | 15 / 15 | 56,77 MiB |
| CanvasKit + Click-Listener | 59,48 | 2 | 15 / 15 | 54,96 MiB |
| Nur DDC | 59,88¹ | 15 | 15 / 15 | 49,78 MiB |
| CanvasKit + DDC | 59,75 | 2 | 15 / 15 | 49,80 MiB |
| Click-Listener + DDC | 59,56¹ | 15 | 15 / 15 | 49,68 MiB |
| Alle drei | 59,86 | 2 | 0 / 0 | 0,13 MiB |

¹ Diese Varianten werfen Fehler in alten CanvasKit-Callbacks. Ihre gute
Taktung ist kein erfolgreicher Korrektheitsnachweis.

Ohne Fix entstehen im Median **3.344 WebGL-Kontexte** über den Durchlauf,
mit CanvasKit-Cleanup 49. Diese 49 umfassen die reguläre Kontext-Erzeugung
der 16 Anwendungs-Generationen sowie initiale Probe-/Erkennungs-Kontexte;
die kumulative Erzeugungszahl ist nicht die Zahl gleichzeitig aktiver
Kontexte. CanvasKit und seine Wasm-Instanz werden bei den Restarts behalten.

Auch der PC zeigt also einen deutlichen Einbruch. `requestAnimationFrame`
misst hier die Taktung des Hauptthreads, **nicht** vom Compositor tatsächlich
präsentierte Frames. Ein Handy war dafür nicht erforderlich.

Die separate, tatsächlich mit DDC kompilierte reine Dart-App liefert:

| Variante | Native `Function`-Symbole nach 15 Restarts | JS-Heap nach 15 Restarts | Zuwachs in den letzten 5 Restarts |
| --- | ---: | ---: | ---: |
| Ohne DDC-Fix | 96, ausgehend von 6 | 97,25 MiB | 24,21 MiB |
| Mit DDC-Fix | 6 | 30,57 MiB | 0,001 MiB |

Die reine Dart-Messung enthält drei Vorher/Nachher-Durchläufe, insgesamt
96 Samples. Die JS-Interop-Payload-Probe bleibt in beiden Varianten bei
einem lebenden JS-Typed-Array. Der belegte Befund ist hier das Retention-
Wachstum des Runtimes/der Metadaten; die Probe beweist keine Retention
jeder Art von Dart-Anwendungsdaten.

## Zusammenhang und neu gefundener Callback-Effekt

Die Ressourcen bilden mehrere getrennte Wurzeln:

1. Native JS-Konstruktoren/-Prototypen behalten alte DDC-Metadaten und
   Runtimes. CL 578301 entfernt die installierten Schlüssel und setzt
   ausgehenden statischen Runtime-Zustand zurück.
2. Der Document-Click-Listener behält den alten Dispatcher. PR 196787
   entfernt genau diesen Callback mit demselben Capture-Flag.
3. CanvasKit/WebGL-Kontexte und Kontextverlust-Listener überleben den
   alten Renderer. PR 196786 registriert Renderer-Disposal beim Hot Restart
   und gibt Listener, Skia-/WebGL-Ressourcen und Context-Table-Einträge frei.

Die isolierten Kombinationen zeigen, warum eine einzelne entfernte Wurzel
für GC nicht reicht. Erst die vollständige Kombination macht in dieser
Flutter-App alle beobachteten alten Renderer und Dispatcher unerreichbar.

Der DDC-Fix entfernt aber auch Methoden-Schlüssel, die alte Callbacks noch
verwenden. Ohne CanvasKit-Cleanup erzeugt das in den Flutter-Versuchen
16–17 ungefangene Fehler pro Durchlauf:

```text
TypeError: _engine.webGLVersion[$toDouble] is not a function
  at CkOffscreenSurface._createGrContext
  at CkOffscreenSurface.recreateContextForCanvas
  at CkOffscreenSurface.onContextLost
```

Der neue Minimaltest [callback_main.dart](callback_main.dart) benötigt nur
Dart und einen DOM-Listener. Er erfasst einen Integer und ruft im Callback
`value.toDouble()` auf. Nach einem Restart bleiben alter und neuer Listener
registriert. Ohne Fix berichten beide 42; mit Fix berichtet nur der neue
Listener 42 und der alte wirft:

```text
Uncaught TypeError: value[$toDouble] is not a function
```

Das Weiterleben des alten Listeners ist ein bestehendes Problem. Die neue
Native-Cleanup-Änderung verwandelt den bisherigen veralteten Aufruf in
eine neue ungefangene Exception. Die zwölfteilige Metadaten-Regression
deckt dieses Verhalten nicht ab.

Die bisherige Formulierung „either change can land first“ ist deshalb
**keine ausreichende Rollout-Aussage**. Loader und generierter DDC-SDK-
Runtime müssen ohnehin gemeinsam ausgeliefert werden. Für Flutter darf
die DDC-Änderung nicht ohne CanvasKit-Cleanup als sicher bestätigt werden.
Für reines Dart-Web muss zusätzlich der Vertrag für alte JS-Interop-
Callbacks geklärt werden; eine allgemeine Generation-Guard-Lösung wurde
hier weder implementiert noch getestet. Das überschneidet sich mit
[Dart issue 56127](https://github.com/dart-lang/sdk/issues/56127), ohne
dessen breiteren Scope vollständig zu lösen.

## Builds und Validierung

Die betroffenen DDC- und Flutter-Web-SDK-Artefakte wurden neu aus Dart-
Quellen kompiliert. Compiler/VM-Binaries und CanvasKit-Wasm wurden als
Prebuilts verwendet; an diesen nativen Komponenten ändern die PRs nichts.
Es wurde kein vollständiger Dart-VM-/C++-/Skia-Neubau durchgeführt.

- Flutter-Quellbasis: `22e676c57e1e6d04c2289a47368ea4093bbc3c18`.
- PR 196786: `3e25df705b11935d0a4a5750e6b8bc26460877b1`.
- PR 196787: `b8bbc80b12474d54da242a2e150c6fd6d8dbde9c`.
- Dart-Compiler: `3.15.0-edge.e1671c00019972a92e16247dc254ad3eaa48c2b6`.
- Lokale Dart-Change-Quelle: `cca4921c970dd56bece3f0ecadf6825e9fc2f090`;
  die Produktionsänderungen entsprechen Gerrit Patchset 3, dessen Commit-
  Nachricht inzwischen geändert wurde. Unmodifizierte `classes.dart` und
  Loader stimmen byteweise mit dem verwendeten Compiler-Archiv überein.
- Aktuelle CanvasKit-Prebuilts: Flutter-Engine-Content-Hash
  `69353cb5ad9bde13f9f47df42fb0fc74b936ff17`.

Die eingereichten Engine-Regressionen schlagen auf der Quellbasis fehl:
keine zehn Listener-Removals, Kontextverlust-Listener bleibt registriert,
GL-Handle bleibt gültig, alte Kontexte werden nicht freigegeben. Mit beiden
Flutter-Änderungen bestehen die gezielten Suites: **113 Tests bestanden,
4 übersprungen**, auf Chromium- und Full-CanvasKit-Varianten. Die zwei
vorhandenen Kontextfehler-Tests sind je Variante übersprungen; die übrigen
Context-Loss-/Surface-/Renderer-/Rasterizer-/Dispatcher-Tests laufen.

Der aktuelle DDC-Runtime besteht die bestehende Chrome-Regression mit
12 Restarts, beiden APIs, statischem Reset, Cross-Frame-Cleanup,
unveränderten fremden JS-Properties, Legacy-Reset und GC eines abgetrennten
Frames. Mit originalem Loader schlägt sie nach dem ersten Restart fehl:
`12 !== 6` native Konstruktor-Symbole.

Die Release-Kontrolle kompiliert dieselbe Dart-App vor und nach dem Runtime-
Patch mit `dart compile js -O2 --no-source-maps` und
`dart compile wasm --no-source-maps`: beide Paare sind bytegleich
([Hashes](release-controls.json)). Das ist ein Kontrollversuch für diese
App, kein Benchmark jeder denkbaren Release-Anwendung.

## Messgrenzen

Heap-Werte werden nach erzwungener GC gemessen. Das ist ein definierter
Messpunkt, kein Vorschlag, GC in DartPad zu erzwingen. Die Werte schließen
Compiler-/Analyzer-Worker, Gesamtprozess-PSS und GPU-Speicher nicht ein.
Wasm-Memory-Größen und Backing-Storage wurden separat roh erfasst.

Auch mit allen Fixes wächst der Heap früh noch: von Restart 2 bis 15 um
24,03 MiB. Es gibt einen deutlichen Stufensprung ungefähr bei Restart 8;
danach plateauiert er. Seine Ursache wurde nicht profiliert. Die letzten
fünf Restarts und die WeakRefs belegen das Entfernen der beobachteten
linearen Retention, nicht vollständige Speicher-Konstanz ab dem Start.

Die früheren DartPad-/Samsung-Werte wurden hier nicht neu gemessen und
werden nicht mit dieser Desktop-Matrix vermischt. Es wurde weder ein
Handy noch ein Simulator verwendet. Die gewöhnlichen Benutzer-Browser-
Sitzungen blieben unangetastet.

## Dateien und erneuter Lauf

- [Alle Graphen](charts.html), jeweils als PNG und SVG: [Taktung](flutter-cadence.png),
  [Heap](flutter-memory.png), [Kontexte](flutter-contexts.png),
  [Objekt-Retention](flutter-retention.png), [reines Dart](plain-dart.png).
- Rohdaten: [Flutter JSON](flutter-results.json), [Flutter CSV](flutter-samples.csv),
  [Dart JSON](plain-results.json), [Dart CSV](plain-samples.csv).
- [Zusammenfassung](summary.json), [Build-Hashes](build-manifest.json),
  [Engine-Tests](engine-validation.json), [Suite-Zahlen](engine-suite-summary.json),
  [DOM-Callback-Test](stale-callback-results.json).
- [Issue-/PR-Veröffentlichungsplan](drafts/publication-plan.md) und die
  einzelnen sachlichen Entwürfe im selben Verzeichnis. Sie wurden nicht
  veröffentlicht und enthalten noch keine öffentlichen Evidence-/Issue-URLs.

Große SDK-/Compiler-Artefakte stehen lokal unter
`.dart_tool/hot-restart-analysis`; die eigenen bestehenden SDK-Checkouts
wurden nicht verändert. `build_web_sdks.py` kompiliert die Varianten und
`prepare_flutter_run.py` erstellt die benötigten Outline-/Loader-Artefakte
für den normalen Flutter-Befehl. Beide Skripte beschreiben die verwendeten
lokalen Eingaben; das archivierte SDK muss zur Version/den Hashes passen.

Aus dem DartPad-Repository-Root, mit einem separaten Chrome-Testprofil und
Debugging-Port 9433:

```sh
node docs/research/hot-restart-2026-11-19/measure_plain.mjs
node docs/research/hot-restart-2026-11-19/measure_flutter.mjs
python3 docs/research/hot-restart-2026-11-19/validate_engine.py
python3 docs/research/hot-restart-2026-11-19/release_controls.py
```

`measure_flutter.mjs` setzt eine vorhandene Ergebnisdatei fort und
überspringt vollständige Durchläufe. Für neue unabhängige Messungen die
alte Datei zuerst archivieren. Engine-Tests und Builds nach den Performance-
Messungen ausführen, um die Rechnerlast nicht in die rAF-Kurven einzutragen.
Während des ersten Baseline-Durchlaufs wurden zusätzliche SDK-Varianten
kompiliert; die beiden anschließenden Baselines reproduzieren den Einbruch
ohne diese Build-Last.

Die Quellenprüfung nennt weitere Versionen/Builder-Konfigurationen und
die drei ursprünglichen Änderungen:
[Flutter PR 196786](https://github.com/flutter/flutter/pull/196786),
[Dart CL 578301](https://dart-review.googlesource.com/c/sdk/+/578301),
[Flutter PR 196787](https://github.com/flutter/flutter/pull/196787).
Alle drei waren beim Prüfen noch ungemergt. GitHub-API-Aufrufe wurden mit
dem Token von `LeonMollNetlight` ausgeführt; `mollle` blieb aktiver
CLI-Account.
