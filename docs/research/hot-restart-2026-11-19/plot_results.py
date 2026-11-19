"""Produce publication images, CSV raw samples, and a compact HTML view."""
import csv
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
MIB = 1024 * 1024
LABELS = {
    'baseline': 'Before fixes', 'context': 'CanvasKit only',
    'listener': 'Listener only', 'both': 'CanvasKit + listener',
    'ddc': 'Experimental DDC (callback errors)', 'context-ddc': 'CanvasKit + experimental DDC',
    'listener-ddc': 'Listener + experimental DDC',
    'all': 'Both Flutter PRs + experimental DDC', 'fixed': 'Experimental DDC cleanup',
}
COLORS = {'baseline': '#c24b40', 'context': '#1f77b4', 'listener': '#a36ea6',
          'both': '#ba890b', 'ddc': '#777777', 'context-ddc': '#7250a2',
          'listener-ddc': '#d58443', 'all': '#187d62', 'fixed': '#187d62'}
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                     'svg.fonttype': 'none', 'figure.dpi': 150})


def series(rows, condition, metric, subtract=False):
    groups = {}
    for row in rows:
        if row['condition'] != condition:
            continue
        value = row[metric]
        if subtract:
            start = next(r[metric] for r in rows if r['condition'] == condition
                         and r['repetition'] == row['repetition'] and r['restart'] == 2)
            value -= start
        groups.setdefault(row['restart'], []).append(value)
    indices = sorted(groups)
    scale = MIB if metric.endswith('Size') or metric == 'wasmMemoryBytes' else 1
    return indices, *[[function(groups[i]) / scale for i in indices]
                      for function in [statistics.median, min, max]]


def chart(rows, metrics, conditions, title, filename, labels, subtract=False):
    fig, axes = plt.subplots(1, len(metrics), figsize=(7.8 * len(metrics), 4.5), squeeze=False)
    for axis, metric, ylabel in zip(axes[0], metrics, labels):
        for condition in conditions:
            x, median, low, high = series(rows, condition, metric, subtract=subtract)
            if not x:
                continue
            if subtract:
                valid = [i for i, index in enumerate(x) if index >= 2]
                x, median, low, high = [[values[i] for i in valid] for values in [x, median, low, high]]
            axis.plot(x, median, color=COLORS[condition], label=LABELS[condition], marker='.', lw=1.8)
            axis.fill_between(x, low, high, color=COLORS[condition], alpha=.12)
        axis.set(xlabel='Hot restarts', ylabel=ylabel, xticks=range(0, 16, 3))
        axis.grid(axis='y', alpha=.2)
        axis.legend(loc='best', frameon=False, fontsize=9)
    fig.suptitle(title, fontsize=13)
    note = 'Apple M4 Pro · Chrome 157 · DDC debug · median of 3 runs; shading = full observed range'
    if any(metric == 'rafFps' for metric in metrics):
        note += '\nrAF measures main-thread cadence, not compositor presentation; 300 animated circles'
        if 'ddc' in conditions:
            note += '\nDDC-only runs throw from retired callbacks despite their steady cadence'
    elif any(metric.endswith('Size') for metric in metrics):
        note += '\nForced GC before each sample; JS heap excludes workers and GPU memory'
    experimental = any(condition in {'ddc', 'context-ddc', 'listener-ddc', 'all', 'fixed'}
                       for condition in conditions)
    if experimental:
        note += '\nExperimental DDC = CL 578301/3; known stale-callback regression, not merge-ready'
    fig.text(.5, .015, note, ha='center', fontsize=8, color='#555555')
    fig.tight_layout(rect=(0, .18 if 'ddc' in conditions else .14 if experimental else .09, 1, .94))
    for extension in ['png', 'svg']:
        fig.savefig(ROOT / f'{filename}.{extension}', dpi=240)
    plt.close(fig)


def write_csv(rows, name):
    keys = sorted({key for row in rows for key in row if not isinstance(row[key], (list, dict))})
    with (ROOT / name).open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    summary = {}
    for condition in dict.fromkeys(r['condition'] for r in rows):
        measurements = []
        for repetition in sorted({r['repetition'] for r in rows if r['condition'] == condition}):
            selected = [r for r in rows if r['condition'] == condition and r['repetition'] == repetition]
            warm = next(r for r in selected if r['restart'] == 2)
            final = next(r for r in selected if r['restart'] == 15)
            late = next(r for r in selected if r['restart'] == 10)
            measurements.append({
                'repetition': repetition, 'heapWarmMiB': warm['usedSize'] / MIB,
                'heapFinalMiB': final['usedSize'] / MIB,
                'heapGrowthAfterWarmupMiB': (final['usedSize'] - warm['usedSize']) / MIB,
                'heapGrowthLastFiveMiB': (final['usedSize'] - late['usedSize']) / MIB,
                'symbolsFinal': final['symbols'],
                **({key: final[key] for key in ['activeContexts', 'contextsCreated', 'retiredRenderersAlive',
                                               'retiredDispatchersAlive', 'clickAdded', 'clickRemoved', 'rafFps', 'rafP95Ms']}
                   if 'rafFps' in final else {}),
            })
        summary[condition] = {'runs': measurements, 'median': {key: statistics.median(r[key] for r in measurements)
                                                             for key in measurements[0] if key != 'repetition'}}
    return summary


def main():
    plain = json.loads((ROOT / 'plain-results.json').read_text())['rows']
    flutter = json.loads((ROOT / 'flutter-results.json').read_text())['rows']
    write_csv(plain, 'plain-samples.csv')
    write_csv(flutter, 'flutter-samples.csv')
    summary = {'plain': summarize(plain), 'flutter': summarize(flutter)}
    (ROOT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    chart(plain, ['usedSize', 'symbols'], ['baseline', 'fixed'],
          'Plain Dart web: DDC runtime retention across hot restarts', 'plain-dart',
          ['Post-GC JavaScript heap (MiB)', 'Symbols on native Function constructor'])
    chart(flutter, ['rafFps'], ['baseline', 'context', 'ddc', 'all'],
          'Normal Flutter web: CanvasKit cleanup prevents cadence collapse', 'flutter-cadence',
          ['requestAnimationFrame calls / second'])
    chart(flutter, ['activeContexts', 'contextsCreated'], ['baseline', 'context', 'all'],
          'Normal Flutter web: retained contexts trigger repeated context creation', 'flutter-contexts',
          ['Active tracked WebGL contexts', 'Cumulative WebGL contexts created'])
    chart(flutter, ['usedSize'], ['context', 'both', 'context-ddc', 'all'],
          'Normal Flutter web: memory retention with CanvasKit cleanup held constant', 'flutter-memory',
          ['Post-GC JavaScript heap growth after restart 2 (MiB)'], subtract=True)
    chart(flutter, ['retiredDispatchersAlive', 'retiredRenderersAlive'], ['context', 'both', 'context-ddc', 'all'],
          'Normal Flutter web: retired engine objects remain reachable through separate roots', 'flutter-retention',
          ['Live retired dispatchers after GC', 'Live retired CanvasKit renderers after GC'])
    pictures = [('flutter-cadence', 'Normal Flutter web: Taktung'),
                ('flutter-memory', 'Normal Flutter web: JavaScript-Heap'),
                ('flutter-contexts', 'WebGL-Kontexte'), ('plain-dart', 'Reines Dart-Web mit DDC')]
    sections = ''.join(f'<section><h3>{title}</h3><img src="{ROOT}/{name}.png" alt="{title}"></section>' for name, title in pictures)
    html = f'''<!doctype html><meta charset="utf-8"><style>
    :root {{font-family:var(--font-sans);color:var(--foreground)}}
    h3 {{font-size:15px;margin:12px 0 6px}} img {{display:block;width:100%;height:auto}}
    p {{font-size:13px;color:var(--muted-foreground)}}
    section {{margin-bottom:18px}} details {{margin-top:12px}}
    </style><p>Desktop-Messung vom 19.11.2026 · Apple M4 Pro · Chrome 157 · drei Durchläufe pro Variante.
    Die rAF-Kurve zeigt die Taktung des Hauptthreads. Heap-Werte wurden nach erzwungener GC gemessen.</p>
    <p>DDC-Kurven zeigen einen experimentellen Patch mit bekannter Callback-Regression,
    keinen merge-fertigen Fix. Der getestete Patch und die Rohdaten bleiben archiviert.</p>
    {sections}'''
    (ROOT / 'charts.html').write_text(html)


if __name__ == '__main__':
    main()
