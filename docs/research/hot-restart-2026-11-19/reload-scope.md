# Hot Restart und zustandserhaltender Hot Reload

Die drei öffentlichen Issues wurden um die Abgrenzung ergänzt. Grundlage
sind die vorhandenen Restart-Messungen und die Quellpfade, kein neuer
Hot-Reload-Benchmark und kein weiterer SDK-Build.

Hot Reload aktualisiert Code in der laufenden Anwendung. Vorhandene
Flutter-`State`-Objekte und ihre Werte bleiben erhalten; `main()` und
`initState()` dieser vorhandenen Objekte laufen nicht erneut.
Neu entstehende State-Objekte können natürlich `initState()` ausführen.

Hot Restart startet die Dart-Anwendung erneut, führt `main()` aus und
erstellt frischen Dart-Zustand. Die Browserseite bleibt dabei bestehen.
Browserobjekte, Event-Listener und CanvasKit müssen daher über explizite
Aufräumpfade berücksichtigt werden. Ein Browser-Refresh lädt eine neue
Seitenumgebung und ist ein anderer Vorgang.

| Issue | Bestätigter Auslöser | Abgrenzung |
| --- | --- | --- |
| CanvasKit 196967 | Wiederholte Hot Restarts | Normaler Hot Reload behält den Renderer. PR 196786 verbessert zusätzlich allgemeine Surface-Freigabe/Canvas-Ersetzung, etwa bei Resize-Recovery. |
| Dispatcher 196968 | Alter Dispatcher wird beim Restart beendet | Normaler Hot Reload behält den Dispatcher. PR 196787 repariert dessen `dispose()` auch für andere explizite Engine-Disposals; Widget-Disposal ist ein anderer Vorgang. |
| DDC 64979 | Canary-Hot-Restart ersetzt Runtime/Bibliotheksobjekte | Stateful Hot Reload verwendet die vorhandenen Bibliotheksobjekte weiter und ruft den neuen Native-Disposal nicht auf. Auch die Callback-Exception wurde nach Restart reproduziert. |

DWDS ruft beim Restart `ext.flutter.disassemble` auf. Der Hot-Reload-Pfad
verwendet `dartDevEmbedder.hotReload`; Flutter kann anschließend reassemble
ausführen. `LibraryManager.hotReloadEnd()` aktualisiert bestehende Bibliotheken;
`hotRestartEnd()` entfernt im geprüften Change native Erweiterungen und leert
die Bibliothekstabelle. Damit sind die betrachteten Vorgänge getrennt.

Ein möglicher anderer Speicherfehler bei Hot Reload wurde hier weder
nachgewiesen noch ausgeschlossen. Die numerischen Messungen gelten für
den ausdrücklich ausgelösten Full-Hot-Restart.

- https://github.com/flutter/flutter/issues/196967
- https://github.com/flutter/flutter/issues/196968
- https://github.com/dart-lang/sdk/issues/64979

Die genauen Quelllinks und öffentlich ergänzten Formulierungen stehen in
`reload-scope.json` und den synchronisierten `drafts/published-issue-*.md`.
