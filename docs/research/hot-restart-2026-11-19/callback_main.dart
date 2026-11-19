import 'dart:js_interop';

@JS('document.addEventListener')
external void addListener(JSString type, JSFunction callback);

@JS('__reportNumber')
external void reportNumber(JSNumber value);

void main() {
  final value = int.parse('42');
  addListener(
    'probe'.toJS,
    ((JSAny? event) {
      reportNumber(value.toDouble().toJS);
    }).toJS,
  );
}
