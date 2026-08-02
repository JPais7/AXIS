# AXIS benchmarks

`PROTOCOL.md` freezes the intended comparison before results are collected.
The first local measurement is intentionally limited to the packaged synthetic
demo and cannot establish superiority over another tool.

Run ten repetitions from the repository root:

```shell
python benchmarks/benchmark_demo.py --repetitions 10
```

The JSON result reports environment, wall-clock time, Python allocation peak,
output size and check status. `tracemalloc` measures Python allocations rather
than total operating-system resident memory; the distinction is retained in
the output.
