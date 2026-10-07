"""The starter benchmark runs, is deterministic, and gets the clear cases right."""
from claimcheck.bench.starter import SCENARIOS, run
from claimcheck.check.stats import SUPPORTED


def test_the_clearest_scenario_is_supported():
    assert run(SCENARIOS[0], seed=5) == SUPPORTED


def test_a_run_is_reproducible(tmp_path):
    a = run(SCENARIOS[0], seed=3, workdir=tmp_path / "a")
    b = run(SCENARIOS[0], seed=3, workdir=tmp_path / "b")
    assert a == b
