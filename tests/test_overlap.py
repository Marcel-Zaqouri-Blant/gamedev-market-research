"""Sanity checks for the overlap math on synthetic data with a known answer.

Run: python tests/test_overlap.py
"""
import importlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
ov = importlib.import_module("07_audience_overlap")

rng = np.random.default_rng(0)
POP = 200_000


def sample(n, pool=None):
    pool = np.arange(POP, dtype=np.uint32) if pool is None else pool
    return np.unique(rng.choice(pool, size=n, replace=False)).astype(np.uint32)


def build(boost):
    """Every game draws reviewers at random; game a1 draws `boost`x more from B's audience."""
    sets = {f"r{i}": sample(3000) for i in range(30)}       # other segments
    sets.update({f"b{i}": sample(3000) for i in range(5)})   # segment B
    b_aud = ov.union([sets[f"b{i}"] for i in range(5)])
    share = len(b_aud) / POP                                  # random chance to be in B
    k = int(3000 * min(1.0, share * boost))
    not_b = np.setdiff1d(np.arange(POP, dtype=np.uint32), b_aud)
    sets["a1"] = np.unique(np.concatenate([sample(k, b_aud), sample(3000 - k, not_b)])).astype(np.uint32)
    sets["a2"] = sample(3000)
    names = ["dog", "hunting", "friendslop", "horror", "roguelite", "extraction"]
    members = {s: set() for s in names}
    members["dog"] = {"a1", "a2"}
    members["hunting"] = {f"b{i}" for i in range(5)}
    members["friendslop"] = {f"r{i}" for i in range(30)}
    return sets, members


def lift_dog_hunting(boost):
    sets, members = build(boost)
    p = ov.pair_overlaps(sets, members)
    row = p[(p.segment_a == "dog") & (p.segment_b == "hunting")].iloc[0]
    return row.lift_a_to_b


# no planted affinity -> lift ~1; planted 3x on half of segment A -> lift ~2
l1, l3 = lift_dog_hunting(1.0), lift_dog_hunting(3.0)
print(f"random lift={l1:.2f} (expect ~1.0)   planted lift={l3:.2f} (expect ~2.0)")
assert 0.85 < l1 < 1.15, l1
assert 1.7 < l3 < 2.3, l3

# a game that has both elements must not create overlap by itself
sets, members = build(1.0)
sets["hybrid"] = sample(5000)
members["dog"].add("hybrid"); members["hunting"].add("hybrid")
p = ov.pair_overlaps(sets, members)
assert 0.85 < p[(p.segment_a == "dog") & (p.segment_b == "hunting")].iloc[0].lift_a_to_b < 1.15

# count_in matches a plain set intersection
a, b = sample(5000), sample(7000)
assert ov.count_in(a, b) == len(set(a.tolist()) & set(b.tolist()))
assert ov.count_in(np.empty(0, np.uint32), b) == 0
print("all checks passed")
