"""Build a synthetic ecoinvent-like background project.

Usage: python build_bg.py N_ACTS  (BRIGHTWAY2_DIR must be set)
Creates project "perf" with databases biosphere3 (2000 flows), bg (N_ACTS processes)
and 5 impact methods.
"""

import sys
import time

import numpy as np

N = int(sys.argv[1])
N_BIO = 2000
N_TECH_EXC = 10
N_BIO_EXC = 20
N_METHODS = 5

import bw2data as bd  # noqa: E402

rng = np.random.default_rng(42)
t0 = time.perf_counter()
bd.projects.set_current("perf")

bio = {
    ("biosphere3", f"flow{i}"): {
        "name": f"flow {i}",
        "unit": "kilogram",
        "type": "emission",
        "categories": ("air",),
    }
    for i in range(N_BIO)
}
bd.Database("biosphere3").write(bio)

bg = {}
for i in range(N):
    exc = [{"input": ("bg", f"a{i}"), "amount": 1.0, "type": "production"}]
    for j in rng.choice(N, N_TECH_EXC, replace=False):
        if j == i:
            continue
        # Sum of inputs < 0.5 -> diagonally dominant, invertible
        exc.append({"input": ("bg", f"a{j}"), "amount": float(rng.uniform(0, 0.05)), "type": "technosphere"})
    for k in rng.choice(N_BIO, N_BIO_EXC, replace=False):
        exc.append({"input": ("biosphere3", f"flow{k}"), "amount": float(rng.lognormal(-3, 2)), "type": "biosphere"})
    bg[("bg", f"a{i}")] = {
        "name": f"activity {i}",
        "unit": "kilogram",
        "location": "GLO",
        "reference product": f"product {i}",
        "type": "process",
        "exchanges": exc,
    }
bd.Database("bg").write(bg)

for m in range(N_METHODS):
    flows = rng.choice(N_BIO, 500, replace=False)
    meth = bd.Method(("perf", f"method{m}", "total"))
    meth.register(unit="kg eq")
    meth.write([(("biosphere3", f"flow{k}"), float(rng.uniform(0.1, 10))) for k in flows])

print(f"built N={N} in {time.perf_counter() - t0:.1f}s")
