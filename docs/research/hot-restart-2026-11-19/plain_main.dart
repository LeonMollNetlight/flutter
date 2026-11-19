import 'dart:js_interop';
import 'dart:typed_data';

@JS('__publishPayload')
external void publishPayload(JSUint8Array payload);

class Application {
  final Uint8List payload = Uint8List(4 * 1024 * 1024);
}

Application? application;

void main() {
  application = Application();
  application!.payload[0] = 42;
  publishPayload(application!.payload.toJS);
}
