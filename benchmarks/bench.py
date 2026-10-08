"""Benchmark lca_algebraic on a synthetic background.

Usage: python bench.py SIZE MODE [REPS] [OUT_JSON]
  MODE = all      : fresh copy of $BENCH_DATA/bwSIZE, build foreground, run all timings
  MODE = diskwarm : reuse project from a previous 'all' run (disk caches present), time first calls
  MODE = profile:<name> : run one workload under cProfile, dump stats to $BENCH_OUT/prof/<name>-SIZE.prof

$BENCH_DATA holds the projects build_bg.py made; run.sh sets it and $BENCH_OUT.
"""

import json
import os
import shutil
import statistics
import sys
import tempfile
import time

SIZE = int(sys.argv[1])
MODE = sys.argv[2]
REPS = int(sys.argv[3]) if len(sys.argv) > 3 else 5
OUT = sys.argv[4] if len(sys.argv) > 4 else None

DATA = os.environ.get("BENCH_DATA", os.path.join(os.path.dirname(__file__), "data"))
OUT_DIR = os.environ.get("BENCH_OUT", DATA)
# Each run works on a copy, so the built project stays untouched between runs.
PROJ_DIR = os.path.join(os.environ.get("BENCH_SCRATCH", tempfile.gettempdir()), f"lca-bench-{SIZE}")
if MODE != "diskwarm" or not os.path.exists(PROJ_DIR):
    shutil.rmtree(PROJ_DIR, ignore_errors=True)
    shutil.copytree(os.path.join(DATA, f"bw{SIZE}"), PROJ_DIR)
os.environ["BRIGHTWAY2_DIR"] = PROJ_DIR

import contextlib  # noqa: E402
import io  # noqa: E402
import logging  # noqa: E402

import numpy as np  # noqa: E402

import lca_algebraic as agb  # noqa: E402
from lca_algebraic import stats as st  # noqa: E402
from lca_algebraic.bw_wrapper import projects  # noqa: E402
from lca_algebraic.cache import clear_caches  # noqa: E402
from lca_algebraic.lca import _preMultiLCAAlgebric  # noqa: E402
from lca_algebraic.params import DistributionType as D  # noqa: E402

logging.getLogger("lca_algebraic").setLevel(logging.ERROR)
projects.set_current("perf")
METHODS = [("perf", f"method{m}", "total") for m in range(5)]
USER_DB = "fg"


def build_foreground():
    rng = np.random.default_rng(7)
    agb.resetDb(USER_DB, foreground=True)
    agb.resetParams()
    params = []
    for i in range(20):
        kind = i % 4
        if kind == 0:
            p = agb.newFloatParam(f"p{i}", 1.0 + i, min=0.5 + i, max=2.0 + i, distrib=D.LINEAR, group="lin")
        elif kind == 1:
            p = agb.newFloatParam(f"p{i}", 1.0, min=0.2, max=3.0, distrib=D.TRIANGLE, group="tri")
        elif kind == 2:
            p = agb.newFloatParam(f"p{i}", 2.0, min=1.0, max=3.0, std=0.3, distrib=D.NORMAL, group="norm")
        else:
            p = agb.newFloatParam(f"p{i}", 0.5, std=0.4, distrib=D.LOGNORMAL, group="lognorm")
        params.append(p)
    mix = agb.newEnumParam("mix", default="eu", values={"eu": 2, "fr": 1, "cn": 1})

    bg = [agb.getActByCode("bg", f"a{j}") for j in rng.choice(SIZE, 60, replace=False)]
    bio = [agb.getActByCode("biosphere3", f"flow{k}") for k in (1, 2)]

    def p(k):
        return params[k % len(params)]

    # Leaves: 8 sub-assemblies with formula amounts on background
    leaves = []
    for a in range(8):
        exch = {}
        for b in range(5):
            act = bg[(a * 5 + b) % len(bg)]
            if b == 0:
                exch[act] = 0.3  # static amount
            else:
                exch[act] = p(a + b) * 0.1 + p(a * 3 + b) * p(b) * 0.01
        if a == 0:
            exch[bio[0]] = p(4) * 0.02
        leaf = agb.newActivity(USER_DB, f"leaf{a}", "unit", exch)
        leaf.updateMeta(phase=["manufacturing", "use", "eol"][a % 3])
        leaves.append(leaf)

    elec = agb.newActivity(
        USER_DB,
        "elec",
        "kWh",
        {bg[40]: mix.symbol("eu"), bg[41]: mix.symbol("fr"), bg[42]: mix.symbol("cn")},
    )
    elec.updateMeta(phase="use")
    use = agb.newActivity(USER_DB, "use", "unit", {elec: p(1) * p(2) * 100, bio[1]: p(3) * 0.5})
    use.updateMeta(phase="use")
    exch = {leaf: 1.0 + p(i) * 0.1 for i, leaf in enumerate(leaves)}
    exch[use] = p(5) * p(6)
    for j in range(43, 60):
        exch[bg[j]] = p(j) * 0.05
    model = agb.newActivity(USER_DB, "model", "unit", exch)
    return model


def get_model():
    return agb.getActByCode(USER_DB, "model")


def vec_params(n, seed=0):
    params, _ = st._generate_random_params(n, sample_method=st.StochasticMethod.RAND, seed=seed)
    return params


def timeit(fn, reps, setup=None):
    out = []
    for _ in range(reps):
        if setup:
            setup()
        t = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t)
    return out


def quiet(fn):
    def w():
        with contextlib.redirect_stdout(io.StringIO()):
            return fn()

    return w


def summary(ts):
    return {"median": statistics.median(ts), "min": min(ts), "max": max(ts), "n": len(ts), "all": ts}


def cold():
    clear_caches()


WORKLOADS = {}


def workloads(model):
    p1k = vec_params(1000)
    p10k = vec_params(10000)
    m1, m5 = METHODS[:1], METHODS
    lambdas5 = _preMultiLCAAlgebric(model, m5)
    var_params = st._extract_var_params(lambdas5)
    return {
        "fixed_m1": lambda: agb.compute_impacts(model, m1),
        "fixed_m5": lambda: agb.compute_impacts(model, m5),
        "vec1k_m1": lambda: agb.compute_impacts(model, m1, **p1k),
        "vec1k_m5": lambda: agb.compute_impacts(model, m5, **p1k),
        "vec10k_m1": lambda: agb.compute_impacts(model, m1, **p10k),
        "vec10k_m5": lambda: agb.compute_impacts(model, m5, **p10k),
        "axis_m5": lambda: agb.compute_impacts(model, m5, axis="phase"),
        # Monte Carlo core of incer_stochastic_matrix / violin, without the plots
        "stochastics_n1024_m5": quiet(lambda: st._stochastics(lambdas5, m5, 1024, var_params)),
        "stoch_sobols_n1024_m5": quiet(lambda: st._sobols(m5, *st._stochastics(lambdas5, m5, 1024, var_params)[0::2])),
        "sobol_simplify_n512_m1": quiet(lambda: st.sobol_simplify_model(model, m1, n=512)),
    }


def main():
    results = {}
    if MODE == "all":
        t = time.perf_counter()
        model = build_foreground()
        results["build_foreground"] = time.perf_counter() - t
        # Cold: in-memory and disk caches cleared before each run
        results["cold_fixed_m1"] = summary(timeit(lambda: agb.compute_impacts(model, METHODS[:1]), REPS, cold))
        results["cold_fixed_m5"] = summary(timeit(lambda: agb.compute_impacts(model, METHODS), REPS, cold))
        results["cold_axis_m5"] = summary(timeit(lambda: agb.compute_impacts(model, METHODS, axis="phase"), REPS, cold))
        # Warm
        agb.compute_impacts(model, METHODS)
        agb.compute_impacts(model, METHODS, axis="phase")
        for name, fn in workloads(model).items():
            reps = 3 if name.startswith("sobol_simplify") else REPS
            fn()  # warm-up
            results["warm_" + name] = summary(timeit(fn, reps))
    elif MODE == "diskwarm":
        model = get_model()
        from lca_algebraic.cache import _Caches

        _Caches.caches.clear()
        t = time.perf_counter()
        agb.compute_impacts(model, METHODS)
        results["diskwarm_first_fixed_m5"] = time.perf_counter() - t
    elif MODE.startswith("profile:"):
        import cProfile

        name = MODE.split(":", 1)[1]
        model = build_foreground()
        os.makedirs(os.path.join(OUT_DIR, "prof"), exist_ok=True)
        if name.startswith("cold_"):
            target = {
                "cold_fixed_m1": lambda: agb.compute_impacts(model, METHODS[:1]),
                "cold_fixed_m5": lambda: agb.compute_impacts(model, METHODS),
                "cold_axis_m5": lambda: agb.compute_impacts(model, METHODS, axis="phase"),
            }[name]
            agb.compute_impacts(model, METHODS[:1])  # creates proxies once
            cold()
        else:
            agb.compute_impacts(model, METHODS)
            agb.compute_impacts(model, METHODS, axis="phase")
            target = workloads(model)[name]
            target()
        prof = cProfile.Profile()
        prof.enable()
        target()
        prof.disable()
        prof.dump_stats(os.path.join(OUT_DIR, "prof", f"{name}-{SIZE}.prof"))
    for k, v in results.items():
        if isinstance(v, dict):
            print(f"{k:32s} median {v['median']:.4f}  min {v['min']:.4f}  max {v['max']:.4f}  n={v['n']}")
        else:
            print(f"{k:32s} {v:.4f}")
    if OUT:
        with open(OUT, "w") as f:
            json.dump(results, f, indent=1)


main()
