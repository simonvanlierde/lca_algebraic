#!/usr/bin/env bash
# Benchmark lca_algebraic on synthetic ecoinvent-sized backgrounds; see benchmarks/README.md.
set -euo pipefail
cd "$(dirname "$0")/.."

SIZES=${SIZES:-"2000 20000"}
REPS=${REPS:-5}
export BENCH_DATA=${BENCH_DATA:-$PWD/benchmarks/data/${BW:-bw25}}
export BENCH_OUT=${BENCH_OUT:-$PWD/benchmarks/results/$(hostname -s)-$(date +%Y%m%dT%H%M)}
PROFILES=${PROFILES:-"cold_fixed_m5 vec10k_m5 stochastics_n1024_m5 sobol_simplify_n512_m1"}

command -v uv >/dev/null || { echo "uv not found: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2; exit 1; }
# bw25 by default. bw2data 3.x (the bw2 extra) still calls np.NaN, gone in numpy 2 (#61).
BW=${BW:-bw25}
uv venv -q --allow-existing -p 3.12 "benchmarks/.venv-$BW"
if [ "$BW" = bw2 ]; then
  VIRTUAL_ENV="benchmarks/.venv-$BW" uv pip install -q -e ".[bw2]" "numpy<2"
else
  VIRTUAL_ENV="benchmarks/.venv-$BW" uv pip install -q -e ".[$BW]"
fi
PY=$PWD/benchmarks/.venv-$BW/bin/python
mkdir -p "$BENCH_DATA" "$BENCH_OUT/prof"

{
  echo "date: $(date -Is)"
  echo "host: $(hostname)"
  echo "commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "cpu: $(lscpu 2>/dev/null | sed -n 's/^Model name: *//p')"
  echo "cores: $(nproc)"
  echo "threads: OMP=${OMP_NUM_THREADS:-unset} MKL=${MKL_NUM_THREADS:-unset} OPENBLAS=${OPENBLAS_NUM_THREADS:-unset}"
  echo "backend: $BW  sizes: $SIZES  reps: $REPS"
  VIRTUAL_ENV="benchmarks/.venv-$BW" uv pip list 2>/dev/null | grep -Ei '^(numpy|scipy|sympy|pandas|bw2|bw-|brightway|lca.algebraic|salib)'
} > "$BENCH_OUT/env.txt"
cat "$BENCH_OUT/env.txt"

for n in $SIZES; do
  # The build is the slow part at 20k and is reused across runs. It writes to a
  # .partial directory first, so an interrupted build is never mistaken for a done one.
  if [ ! -d "$BENCH_DATA/bw$n" ]; then
    rm -rf "$BENCH_DATA/bw$n.partial" && mkdir -p "$BENCH_DATA/bw$n.partial"
    BRIGHTWAY2_DIR="$BENCH_DATA/bw$n.partial" "$PY" benchmarks/build_bg.py "$n" | tee -a "$BENCH_OUT/build.txt"
    mv "$BENCH_DATA/bw$n.partial" "$BENCH_DATA/bw$n"
  fi
  "$PY" benchmarks/bench.py "$n" all "$REPS" "$BENCH_OUT/all-$n.json" | tee "$BENCH_OUT/all-$n.txt"
  for w in $PROFILES; do
    "$PY" benchmarks/bench.py "$n" "profile:$w" >/dev/null || echo "profile $w failed at $n" >&2
  done
done

# Readable top-30 tables, so the .prof files are optional to inspect.
for f in "$BENCH_OUT"/prof/*.prof; do
  "$PY" -c "import pstats,sys; pstats.Stats(sys.argv[1]).sort_stats('cumulative').print_stats(30)" "$f" > "${f%.prof}.txt"
done
echo "results in $BENCH_OUT"
