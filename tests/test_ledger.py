"""Tests for the epistemic ledger: dependency graph is canonical."""
import pytest

from r2a2.ledger import Ledger


def test_cone_and_descendants():
    led = Ledger()
    led.add("src", "source")
    led.add("param", "parameter", deps=["src"])
    led.add("claim", "claim", deps=["param"])
    assert led.ancestors("claim") == {"src", "param"}
    assert led.descendants("src") == {"param", "claim"}


def test_cycle_detection():
    led = Ledger()
    led.add("a", "claim")
    led.add("b", "claim", deps=["a"])
    led.nodes["a"].deps.add("b")
    assert led.find_cycles()


def test_topological_order_rejects_cycle():
    led = Ledger()
    led.add("a", "claim")
    led.add("b", "claim", deps=["a"])
    led.nodes["a"].deps.add("b")
    with pytest.raises(ValueError):
        led.topological_order()


def test_debt_is_labelled_not_blind():
    led = Ledger()
    led.add("x", "claim", debt_kinds=None)
    led.add_debt("x", "commitment", 2)
    led.add_debt("x", "fitted-parameter", 1)
    totals = led.total_debt()
    assert totals == {"commitment": 2, "fitted-parameter": 1}
    # unknown kind rejected
    with pytest.raises(ValueError):
        led.add_debt("x", "made-up")


def test_double_count_is_visible():
    """The scenario the old blind sum could not detect: one source feeding two
    claims that present themselves as independent."""
    led = Ledger()
    led.add("s", "source")
    led.add("c1", "claim", deps=["s"])
    led.add("c2", "claim", deps=["s"])
    feeds = [n.id for n in led.nodes.values() if "s" in n.deps]
    assert len(feeds) == 2  # the audit layer flags this; the graph makes it visible
