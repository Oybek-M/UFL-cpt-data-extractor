from ufl.stats.budget import compute_budget, total_budget


def test_compute_budget_matches_target_with_collected():
    targets = {"books": 120_000_000, "education": 180_000_000}
    collected = {"books": 30_000_000}

    budgets = compute_budget(targets, collected)

    by_category = {b.category: b for b in budgets}
    assert by_category["books"].collected_tokens == 30_000_000
    assert by_category["books"].target_tokens == 120_000_000
    assert by_category["education"].collected_tokens == 0  # hali yig'ilmagan


def test_progress_pct_computed_correctly():
    targets = {"books": 100}
    collected = {"books": 25}

    budgets = compute_budget(targets, collected)

    assert budgets[0].progress_pct == 25.0


def test_progress_pct_caps_at_100():
    targets = {"books": 100}
    collected = {"books": 500}

    budgets = compute_budget(targets, collected)

    assert budgets[0].progress_pct == 100.0


def test_progress_pct_zero_target_does_not_divide_by_zero():
    targets = {"misc": 0}
    collected = {"misc": 10}

    budgets = compute_budget(targets, collected)

    assert budgets[0].progress_pct == 0.0


def test_total_budget_sums_all_categories():
    targets = {"books": 120, "education": 180}
    collected = {"books": 30, "education": 90}

    budgets = compute_budget(targets, collected)
    total = total_budget(budgets)

    assert total.category == "JAMI"
    assert total.target_tokens == 300
    assert total.collected_tokens == 120
