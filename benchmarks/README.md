# Benchmarks

Times `compute_impacts`, Monte Carlo and Sobol on synthetic background databases the
size of ecoinvent, and profiles the slowest workloads. The data is generated, so no
ecoinvent licence is needed.

```sh
benchmarks/run.sh                          # sizes 2000 and 20000, 5 repetitions
SIZES=2000 REPS=3 benchmarks/run.sh        # quick check
BW=bw2 benchmarks/run.sh                   # the Brightway 2 backend (pins numpy<2)
```

Needs `uv` and Python 3.12 (uv fetches it). The first run builds the background
projects under `benchmarks/data/` and reuses them afterwards. Each run writes to
`benchmarks/results/<host>-<timestamp>/`:

- `env.txt`: CPU, cores, thread settings and package versions
- `all-<size>.json` and `.txt`: median, min and max per workload, cold and warm cache
- `prof/<workload>-<size>.prof` and `.txt`: cProfile output and its top 30 by cumulative time

The background has 2,000 biosphere flows, about 10 technosphere and 20 biosphere
exchanges per activity, and 5 impact methods. The foreground model has 20 float
parameters (linear, triangle, normal, lognormal), one enum parameter, and formula
amounts on 60 background activities.
