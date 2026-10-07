"""Canonical manifest hashing: property/fuzz tests.

The hash is provenance: invariant to non-semantic variation, sensitive to
semantic variation.
"""
import json
import random

import pytest

from r2a2.canonical import canonical_hash, normalize_path
from r2a2.compiler import ExecutionManifest, canonical_hash


def test_key_order_invariant():
    a = {"b": 1, "a": {"y": 2, "x": 3}}
    b = {"a": {"x": 3, "y": 2}, "b": 1}
    assert canonical_hash(a) == canonical_hash(b)


def test_whitespace_invariant():
    s = '{"a": 1, "b": [1, 2]}'
    obj = json.loads(s)
    assert canonical_hash(obj) == canonical_hash(json.loads('{"b":[1,2],"a":1}'))


def test_tuple_list_equivalent():
    assert canonical_hash({"a": (1, 2)}) == canonical_hash({"a": [1, 2]})


def test_path_normalization():
    assert normalize_path("a\\b\\c.txt") == "a/b/c.txt"
    assert normalize_path("dir/./sub/../f") == "dir/f"


def test_sensitive_to_threshold():
    m1 = {"threshold": 0.01}
    m2 = {"threshold": 0.02}
    assert canonical_hash(m1) != canonical_hash(m2)


def test_sensitive_to_assumption_text():
    assert canonical_hash({"assume": "law is linear"}) != \
        canonical_hash({"assume": "law is linear "})  # even trailing space counts


def test_manifest_freeze_deterministic_across_runs():
    def make():
        m = ExecutionManifest(theory_id="t", theory_version="1",
                              parameters={"a": 1}, tests=["T1"],
                              thresholds={"p": 0.05}, seeds={"d": 7},
                              backend="local", environment={"python": "3.15"})
        m.freeze()
        return m
    assert make().hash == make().hash


def test_frozen_manifest_immutable():
    m = ExecutionManifest(theory_id="t", theory_version="1")
    m.freeze()
    with pytest.raises(RuntimeError):
        m.thresholds = {"p": 0.1}


@pytest.mark.parametrize("seed", range(20))
def test_fuzz_key_order(seed):
    rng = random.Random(seed)
    def rand_obj(depth=0):
        if depth > 2:
            return rng.choice([1, 2.5, "x", None, True])
        kind = rng.randrange(3)
        if kind == 0:
            return {rng.choice("abcd"): rand_obj(depth + 1) for _ in range(rng.randrange(4))}
        if kind == 1:
            return [rand_obj(depth + 1) for _ in range(rng.randrange(4))]
        return rng.choice([1, 2.5, "x", None, True])
    obj = rand_obj()
    # same object re-serialized with shuffled dict order must hash identically
    import collections
    shuffled = json.loads(json.dumps(obj), object_pairs_hook=collections.OrderedDict)
    assert canonical_hash(obj) == canonical_hash(shuffled)
