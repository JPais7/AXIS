# AXIS benchmarks

`PROTOCOL.md` freezes the intended comparison before results are collected.
The first local measurement is intentionally limited to the packaged synthetic
demo and cannot establish superiority over another tool.

Run ten repetitions from the repository root:

```shell
axis benchmark --repetitions 10 --warmups 1
```

The command writes an aggregate JSON report and a TSV file containing every
measured run. It reports environment, wall-clock time, Python allocation peak,
output size and check status. `tracemalloc` measures Python allocations rather
than total operating-system resident memory; the distinction is retained in
the outputs. `benchmark_demo.py` remains as a compatibility entry point and
uses the same implementation as the public command.

The first report produced by the public command is retained under
[`results/windows-v0.2.0-dev`](results/windows-v0.2.0-dev). It records ten
measured runs after one warmup on Windows; raw per-run timing values are kept
in TSV form alongside the aggregate JSON report.

The GitHub Actions matrix also runs the command on Ubuntu, Windows and macOS.
Successful workflow runs expose one 90-day artifact per operating system,
named `axis-benchmark-<os>-python-3.12`, containing only the aggregate report
and per-run TSV table.
