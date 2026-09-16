from main import DAILY_STEPS, SINGLE_MODES, WEEKLY_STEPS, get_steps


def test_modes_resolve_to_explicit_steps():
    assert get_steps("daily") is DAILY_STEPS
    assert get_steps("weekly") is WEEKLY_STEPS
    for mode, step in SINGLE_MODES.items():
        assert get_steps(mode) == (step,)


def test_weekly_steps_do_not_repeat_work():
    names = [step.name for step in WEEKLY_STEPS]
    assert len(names) == len(set(names))
    assert "EDGAR filings (chunked, 60 days)" not in names
    assert "Product Hunt (last 2 days)" not in names
    assert "TechCrunch (last 2 days)" not in names
    assert "Signalbase (last 2 days)" not in names
