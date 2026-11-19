import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/widgets.dart';

void main() => runApp(const Probe());

class Probe extends StatefulWidget {
  const Probe({super.key});

  @override
  State<Probe> createState() => _ProbeState();
}

class _ProbeState extends State<Probe> with SingleTickerProviderStateMixin {
  final payload = Uint8List(4 * 1024 * 1024);
  late final AnimationController animation = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 4),
  )..repeat();

  @override
  void dispose() {
    animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Directionality(
    textDirection: TextDirection.ltr,
    child: ColoredBox(
      color: const Color(0xff14202e),
      child: CustomPaint(painter: ProbePainter(animation, payload)),
    ),
  );
}

class ProbePainter extends CustomPainter {
  ProbePainter(this.animation, this.payload) : super(repaint: animation);
  final Animation<double> animation;
  final Uint8List payload;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = const Color(0xff5fd7ba);
    final phase = animation.value * 2 * math.pi;
    for (var i = 0; i < 300; i++) {
      final angle = i * 2.39996323 + phase;
      final radius = math.sqrt(i / 300) * size.shortestSide * .43;
      canvas.drawCircle(
        Offset(
          size.width / 2 + math.cos(angle) * radius,
          size.height / 2 + math.sin(angle) * radius,
        ),
        4,
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(ProbePainter oldDelegate) => true;
}
