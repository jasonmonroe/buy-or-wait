# tests/test_rules_engine.py
from datetime import date, timedelta

import pandas as pd
import pytest
from src import rules_engine
from src.rules_engine import Change, FinancialContext, RecurringSeries

from tests.factories import (
    empty_exchange_rates,
    empty_images,
    empty_messages,
    make_ctx,
    make_events_df,
    make_payment_options,
    make_resolved_events,
)


class FakeAgent:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_change_format_reduce_to():
    change = Change(kind="reduce_to", event_id="event_5", new_amount=42.5)
    assert change.format() == "reduce_to:event_5:42.50"


# --------------------------------------------------------------------------- #
# fmt_amount
# --------------------------------------------------------------------------- #


def test_fmt_amount_integer():
    assert rules_engine.fmt_amount(25256.0) == "25256"


def test_fmt_amount_decimal():
    assert rules_engine.fmt_amount(941.6) == "941.60"


def test_fmt_amount_zero():
    assert rules_engine.fmt_amount(0.0) == "0"


# --------------------------------------------------------------------------- #
# convert_amount / _find_rate
# --------------------------------------------------------------------------- #


def test_convert_amount_same_currency_is_noop():
    rates = empty_exchange_rates()
    assert rules_engine.convert_amount(100.0, "ZAR", "ZAR", date(2024, 1, 1), rates) == 100.0


def test_convert_amount_nan_passthrough():
    rates = empty_exchange_rates()
    result = rules_engine.convert_amount(float("nan"), "USD", "ZAR", date(2024, 1, 1), rates)
    assert pd.isna(result)


def test_convert_amount_direct_rate():
    rates = pd.DataFrame(
        [{"rate_date": date(2024, 1, 15), "from_currency": "USD", "to_currency": "ZAR", "rate": 18.0}]
    )
    result = rules_engine.convert_amount(10.0, "USD", "ZAR", date(2024, 1, 20), rates)
    assert result == 180.0


def test_convert_amount_uses_inverse_rate_when_only_that_direction_exists():
    rates = pd.DataFrame(
        [{"rate_date": date(2024, 1, 15), "from_currency": "ZAR", "to_currency": "USD", "rate": 0.05}]
    )
    result = rules_engine.convert_amount(100.0, "USD", "ZAR", date(2024, 1, 20), rates)
    assert result == pytest.approx(100.0 / 0.05)


def test_convert_amount_two_hop_chain():
    rates = pd.DataFrame(
        [
            {"rate_date": date(2024, 1, 15), "from_currency": "USD", "to_currency": "EUR", "rate": 0.9},
            {"rate_date": date(2024, 1, 15), "from_currency": "EUR", "to_currency": "ZAR", "rate": 20.0},
        ]
    )
    result = rules_engine.convert_amount(10.0, "USD", "ZAR", date(2024, 1, 20), rates)
    assert result == pytest.approx(10.0 * 0.9 * 20.0)


def test_convert_amount_two_hop_chain_using_inverse_rates_both_ways():
    # Only the reverse direction is stored for both hops.
    rates = pd.DataFrame(
        [
            {"rate_date": date(2024, 1, 15), "from_currency": "EUR", "to_currency": "USD", "rate": 1.1},
            {"rate_date": date(2024, 1, 15), "from_currency": "ZAR", "to_currency": "EUR", "rate": 0.05},
        ]
    )
    result = rules_engine.convert_amount(11.0, "USD", "ZAR", date(2024, 1, 20), rates)
    assert result == pytest.approx(11.0 / 1.1 / 0.05)


def test_convert_amount_no_path_raises():
    rates = pd.DataFrame(
        [{"rate_date": date(2024, 1, 15), "from_currency": "USD", "to_currency": "EUR", "rate": 0.9}]
    )
    with pytest.raises(ValueError):
        rules_engine.convert_amount(10.0, "USD", "INR", date(2024, 1, 20), rates)


def test_find_rate_uses_nearest_prior_date():
    rates = pd.DataFrame(
        [
            {"rate_date": date(2024, 1, 15), "from_currency": "USD", "to_currency": "ZAR", "rate": 18.0},
            {"rate_date": date(2024, 2, 15), "from_currency": "USD", "to_currency": "ZAR", "rate": 19.0},
        ]
    )
    rate = rules_engine._find_rate(rates, "USD", "ZAR", date(2024, 2, 1))
    assert rate == 18.0


def test_find_rate_falls_back_to_earliest_when_no_prior_date():
    rates = pd.DataFrame(
        [{"rate_date": date(2024, 6, 15), "from_currency": "USD", "to_currency": "ZAR", "rate": 20.0}]
    )
    rate = rules_engine._find_rate(rates, "USD", "ZAR", date(2023, 1, 1))
    assert rate == 20.0


def test_find_rate_returns_none_when_pair_missing():
    rates = empty_exchange_rates()
    assert rules_engine._find_rate(rates, "USD", "ZAR", date(2024, 1, 1)) is None


# --------------------------------------------------------------------------- #
# build_context
# --------------------------------------------------------------------------- #


def test_build_context_maps_profile_fields():
    agent = FakeAgent(
        request_id="request_1",
        user_id="user_1",
        request_date=date(2024, 1, 1),
        requested_amount=500,
        desired_completion_date=date(2024, 2, 1),
        allows_partial_payment=True,
    )
    profile = pd.DataFrame(
        [
            {
                "user_id": "user_1",
                "home_currency": "ZAR",
                "current_available_balance": 5000.0,
                "minimum_balance_to_keep": 1000.0,
                "expense_categories_to_protect": ("rent",),
                "expense_categories_user_is_willing_to_reduce": ("dining",),
                "expense_categories_user_is_willing_to_stop": ("streaming",),
                "payment_methods_user_will_consider": ("full_payment",),
                "max_installment_months": float("nan"),
            }
        ]
    )
    filtered_data = {
        "financial_profiles": profile,
        "financial_events": make_events_df([]),
        "request_payment_options": make_payment_options([]),
        "exchange_rates": empty_exchange_rates(),
        "images": empty_images(),
        "messages": empty_messages(),
    }

    ctx = rules_engine.build_context(agent, filtered_data)

    assert ctx.home_currency == "ZAR"
    assert ctx.current_available_balance == 5000.0
    assert ctx.max_installment_months is None  # NaN -> None, never 0


def test_build_context_raises_when_no_profile():
    agent = FakeAgent(user_id="user_missing")
    filtered_data = {"financial_profiles": pd.DataFrame()}
    with pytest.raises(ValueError):
        rules_engine.build_context(agent, filtered_data)


# --------------------------------------------------------------------------- #
# resolve_events
# --------------------------------------------------------------------------- #


def test_resolve_events_drops_uncountable_statuses_and_directions():
    ctx = make_ctx(
        raw_events=make_events_df(
            [
                {"status": "cancelled"},
                {"status": "failed"},
                {"status": "unrealized", "direction": "non_cash"},
                {"status": "settled"},
            ]
        )
    )
    rules_engine.resolve_events(ctx)
    assert len(ctx.resolved_events) == 1
    assert ctx.resolved_events.iloc[0]["status"] == "settled"


def test_resolve_events_fills_blank_amount_via_ocr_and_drops_unresolved():
    ctx = make_ctx(
        raw_events=make_events_df(
            [
                {"event_id": "event_blank_ok", "amount": None},
                {"event_id": "event_blank_fail", "amount": None},
            ]
        ),
        images=pd.DataFrame(
            [
                {"image_id": "image_1", "user_id": "user_1", "request_id": "request_1", "related_event_id": "event_blank_ok"},
            ]
        ),
    )
    # Rebuild raw_events with explicit event_id column since make_events_df
    # ignores explicit event_id after the positional default merge order.
    ctx.raw_events["event_id"] = ["event_blank_ok", "event_blank_fail"]

    def ocr_fn(images_df):
        return 250.0 if "event_blank_ok" in images_df["related_event_id"].values else None

    rules_engine.resolve_events(ctx, ocr_fn=ocr_fn)

    assert len(ctx.resolved_events) == 1
    assert ctx.resolved_events.iloc[0]["event_id"] == "event_blank_ok"
    assert ctx.resolved_events.iloc[0]["amount"] == 250.0


def test_resolve_events_dedups_exact_duplicates():
    ctx = make_ctx(
        raw_events=make_events_df(
            [
                {"category": "rent", "amount": 100.0, "event_date": date(2024, 1, 1)},
                {"category": "rent", "amount": 100.0, "event_date": date(2024, 1, 1)},
            ]
        )
    )
    rules_engine.resolve_events(ctx)
    assert len(ctx.resolved_events) == 1


def test_resolve_events_converts_currency_and_copies_payment_option_amounts():
    ctx = make_ctx(
        home_currency="ZAR",
        raw_events=make_events_df([{"amount": 10.0, "currency": "USD", "settlement_date": date(2024, 1, 20)}]),
        exchange_rates=pd.DataFrame(
            [{"rate_date": date(2024, 1, 15), "from_currency": "USD", "to_currency": "ZAR", "rate": 18.0}]
        ),
        payment_options=make_payment_options([{"payment_amount": 50.0, "total_payable_amount": 150.0}]),
    )
    rules_engine.resolve_events(ctx)

    assert ctx.resolved_events.iloc[0]["amount_home_ccy"] == 180.0
    assert ctx.payment_options.iloc[0]["payment_amount_home_ccy"] == 50.0
    assert ctx.payment_options.iloc[0]["total_payable_amount_home_ccy"] == 150.0


# --------------------------------------------------------------------------- #
# detect_recurring
# --------------------------------------------------------------------------- #


def test_detect_recurring_finds_clean_monthly_series():
    ctx = make_ctx(
        request_date=date(2024, 4, 1),
        resolved_events=make_resolved_events(
            [
                {"category": "rent", "direction": "debit", "amount": 100.0, "event_date": date(2024, 1, 1)},
                {"category": "rent", "direction": "debit", "amount": 100.0, "event_date": date(2024, 2, 1)},
                {"category": "rent", "direction": "debit", "amount": 100.0, "event_date": date(2024, 3, 1)},
            ]
        ),
    )
    rules_engine.detect_recurring(ctx)

    assert len(ctx.recurring_series) == 1
    series = ctx.recurring_series[0]
    assert series.category == "rent"
    assert series.avg_amount == 100.0
    # Jan (31 days) then Feb 2024 (leap year, 29 days) -> mean gap 30, not a
    # fixed "one month" constant.
    assert series.interval_days == 30


def test_detect_recurring_requires_at_least_two_points():
    ctx = make_ctx(
        resolved_events=make_resolved_events(
            [{"category": "rent", "direction": "debit", "amount": 100.0, "event_date": date(2024, 1, 1)}]
        )
    )
    rules_engine.detect_recurring(ctx)
    assert ctx.recurring_series == []


def test_detect_recurring_rejects_too_frequent_as_variable_spend():
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(4)]  # daily
    ctx = make_ctx(
        resolved_events=make_resolved_events(
            [{"category": "groceries", "direction": "debit", "amount": 20.0, "event_date": d} for d in dates]
        )
    )
    rules_engine.detect_recurring(ctx)
    assert ctx.recurring_series == []


def test_detect_recurring_rejects_inconsistent_gaps():
    dates = [date(2024, 1, 1), date(2024, 1, 10), date(2024, 3, 1)]  # 9 days, then 51 days
    ctx = make_ctx(
        resolved_events=make_resolved_events(
            [{"category": "rent", "direction": "debit", "amount": 100.0, "event_date": d} for d in dates]
        )
    )
    rules_engine.detect_recurring(ctx)
    assert ctx.recurring_series == []


def test_detect_recurring_rejects_wildly_inconsistent_amounts_with_3plus_points():
    dates = [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)]
    amounts = [100.0, 100.0, 1000.0]  # last one wildly different
    ctx = make_ctx(
        resolved_events=make_resolved_events(
            [
                {"category": "rent", "direction": "debit", "amount": a, "event_date": d}
                for d, a in zip(dates, amounts)
            ]
        )
    )
    rules_engine.detect_recurring(ctx)
    assert ctx.recurring_series == []


def test_detect_recurring_accepts_two_point_raise_and_projects_last_amount():
    ctx = make_ctx(
        request_date=date(2024, 3, 3),
        resolved_events=make_resolved_events(
            [
                {
                    "category": "salary",
                    "direction": "credit",
                    "amount": 12826.0,
                    "event_date": date(2024, 2, 15),
                    "settlement_date": date(2024, 2, 15),
                    "status": "settled",
                },
                {
                    "category": "salary",
                    "direction": "credit",
                    "amount": 23320.0,
                    "event_date": date(2024, 3, 15),
                    "settlement_date": date(2024, 3, 15),
                    "status": "scheduled",
                },
            ]
        ),
    )
    rules_engine.detect_recurring(ctx)

    assert len(ctx.recurring_series) == 1
    assert ctx.recurring_series[0].avg_amount == 23320.0  # last value, not the mean


def test_detect_recurring_accepts_semimonthly_pay_via_mean_gap():
    # Paid on the 7th and 20th of every month - gaps alternate 13/15/17/18
    # depending on month length, which the median would reject.
    dates = [
        date(2026, 2, 7), date(2026, 2, 20),
        date(2026, 3, 7), date(2026, 3, 20),
        date(2026, 4, 7), date(2026, 4, 20),
        date(2026, 5, 7), date(2026, 5, 20),
        date(2026, 6, 7), date(2026, 6, 20),
    ]
    amounts = [488.8, 514.25, 485.55, 527.63, 582.12, 355.99, 506.35, 441.96, 547.55, 361.45]
    ctx = make_ctx(
        request_date=date(2026, 7, 4),
        resolved_events=make_resolved_events(
            [
                {"category": "salary", "direction": "credit", "amount": a, "event_date": d}
                for d, a in zip(dates, amounts)
            ]
        ),
    )
    rules_engine.detect_recurring(ctx)

    assert len(ctx.recurring_series) == 1


def test_detect_recurring_projects_mean_for_3plus_volatile_points():
    dates = [date(2024, 1, 1) + timedelta(days=10 * i) for i in range(4)]
    amounts = [100.0, 150.0, 120.0, 130.0]
    ctx = make_ctx(
        request_date=date(2024, 5, 1),
        resolved_events=make_resolved_events(
            [
                {"category": "groceries", "direction": "debit", "amount": a, "event_date": d}
                for d, a in zip(dates, amounts)
            ]
        ),
    )
    rules_engine.detect_recurring(ctx)

    assert len(ctx.recurring_series) == 1
    assert ctx.recurring_series[0].avg_amount == pytest.approx(sum(amounts) / len(amounts))


# --------------------------------------------------------------------------- #
# estimate_variable_spending
# --------------------------------------------------------------------------- #


def test_estimate_variable_spending_includes_essential_irregular_category():
    ctx = make_ctx(
        request_date=date(2024, 4, 1),
        resolved_events=make_resolved_events(
            [
                {"category": "groceries", "direction": "debit", "amount": 100.0, "event_date": date(2024, 3, 1)},
                {"category": "groceries", "direction": "debit", "amount": 200.0, "event_date": date(2024, 3, 15)},
            ]
        ),
    )
    rules_engine.estimate_variable_spending(ctx)
    assert ctx.variable_daily_rate == pytest.approx(300.0 / rules_engine.VARIABLE_LOOKBACK_DAYS)


def test_estimate_variable_spending_skips_categories_already_recurring():
    ctx = make_ctx(
        request_date=date(2024, 4, 1),
        recurring_series=[
            RecurringSeries(
                category="groceries",
                direction="debit",
                avg_amount=150.0,
                interval_days=14,
                next_expected_date=date(2024, 4, 5),
                event_ids=["event_0", "event_1"],
                flexibility="fixed",
            )
        ],
        resolved_events=make_resolved_events(
            [
                {"category": "groceries", "direction": "debit", "amount": 100.0, "event_date": date(2024, 3, 1)},
                {"category": "groceries", "direction": "debit", "amount": 200.0, "event_date": date(2024, 3, 15)},
            ]
        ),
    )
    rules_engine.estimate_variable_spending(ctx)
    assert ctx.variable_daily_rate == 0.0


def test_estimate_variable_spending_ignores_non_essential_category():
    ctx = make_ctx(
        request_date=date(2024, 4, 1),
        resolved_events=make_resolved_events(
            [
                {"category": "shopping", "direction": "debit", "amount": 100.0, "event_date": date(2024, 3, 1)},
                {"category": "shopping", "direction": "debit", "amount": 200.0, "event_date": date(2024, 3, 15)},
            ]
        ),
    )
    rules_engine.estimate_variable_spending(ctx)
    assert ctx.variable_daily_rate == 0.0


def test_estimate_variable_spending_requires_min_occurrences():
    ctx = make_ctx(
        request_date=date(2024, 4, 1),
        resolved_events=make_resolved_events(
            [{"category": "groceries", "direction": "debit", "amount": 100.0, "event_date": date(2024, 3, 1)}]
        ),
    )
    rules_engine.estimate_variable_spending(ctx)
    assert ctx.variable_daily_rate == 0.0


# --------------------------------------------------------------------------- #
# build_forecast / suffix-min / amount_safe_to_pay / earliest_date
# --------------------------------------------------------------------------- #


def test_build_forecast_flat_balance_with_no_events():
    ctx = make_ctx(current_available_balance=5000.0, resolved_events=make_resolved_events([]))
    rules_engine.build_forecast(ctx)

    assert ctx.daily_balance[ctx.request_date] == 5000.0
    assert ctx.running_min_from[ctx.request_date] == 5000.0


def test_build_forecast_applies_future_debit_and_ignores_pending_credit():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        current_available_balance=1000.0,
        resolved_events=make_resolved_events(
            [
                {
                    "category": "rent", "direction": "debit", "amount": 300.0,
                    "settlement_date": date(2024, 1, 10), "status": "scheduled",
                },
                {
                    "category": "bonus", "direction": "credit", "amount": 5000.0,
                    "settlement_date": date(2024, 1, 5), "status": "pending",
                },
            ]
        ),
    )
    rules_engine.build_forecast(ctx)

    assert ctx.daily_balance[date(2024, 1, 4)] == 1000.0  # pending credit not counted
    assert ctx.daily_balance[date(2024, 1, 10)] == 700.0  # scheduled debit applied
    assert ctx.running_min_from[ctx.request_date] == 700.0


def test_build_forecast_projects_recurring_series_without_double_counting_explicit_row():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        current_available_balance=1000.0,
        resolved_events=make_resolved_events(
            [
                {
                    "category": "salary", "direction": "credit", "amount": 500.0,
                    "settlement_date": date(2024, 1, 15), "status": "scheduled",
                },
            ]
        ),
        recurring_series=[
            RecurringSeries(
                category="salary", direction="credit", avg_amount=500.0, interval_days=30,
                next_expected_date=date(2024, 1, 15),  # same date as the explicit row above
                event_ids=["event_hist"], flexibility="fixed",
            )
        ],
    )
    rules_engine.build_forecast(ctx)

    # Only ONE +500 should land on 2024-01-15 (the explicit row), not two.
    assert ctx.daily_balance[date(2024, 1, 15)] == 1500.0
    # The series' next occurrence (2024-02-14) should still be projected.
    assert ctx.daily_balance[date(2024, 2, 14)] == 2000.0


def test_compute_amount_safe_to_pay_capped_at_requested_amount():
    ctx = make_ctx(requested_amount=100.0, minimum_balance_to_keep=1000.0, resolved_events=make_resolved_events([]))
    ctx.current_available_balance = 5000.0
    rules_engine.build_forecast(ctx)
    assert rules_engine.compute_amount_safe_to_pay(ctx) == 100.0


def test_compute_amount_safe_to_pay_floors_at_zero():
    ctx = make_ctx(
        requested_amount=100.0,
        minimum_balance_to_keep=1000.0,
        current_available_balance=500.0,
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    assert rules_engine.compute_amount_safe_to_pay(ctx) == 0.0


def test_compute_earliest_date_for_full_payment_finds_future_safe_date():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        requested_amount=1000.0,
        minimum_balance_to_keep=500.0,
        current_available_balance=500.0,
        resolved_events=make_resolved_events(
            [
                {
                    "category": "salary", "direction": "credit", "amount": 1200.0,
                    "settlement_date": date(2024, 1, 20), "status": "scheduled",
                }
            ]
        ),
    )
    rules_engine.build_forecast(ctx)
    assert rules_engine.compute_earliest_date_for_full_payment(ctx) == date(2024, 1, 20)


def test_compute_earliest_date_for_full_payment_none_when_never_safe():
    ctx = make_ctx(
        requested_amount=100000.0,
        minimum_balance_to_keep=1000.0,
        current_available_balance=2000.0,
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    assert rules_engine.compute_earliest_date_for_full_payment(ctx) is None


# --------------------------------------------------------------------------- #
# _amount_safe_to_pay_with_changes
# --------------------------------------------------------------------------- #


def test_amount_safe_to_pay_with_changes_stop_frees_full_amount():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        requested_amount=400.0,
        minimum_balance_to_keep=500.0,
        current_available_balance=1000.0,
        resolved_events=make_resolved_events(
            [
                {
                    "event_id": "event_0", "category": "streaming", "direction": "debit", "amount": 300.0,
                    "settlement_date": date(2024, 1, 2), "flexibility": "stoppable",
                }
            ]
        ),
    )
    ctx.resolved_events["event_id"] = ["event_0"]
    rules_engine.build_forecast(ctx)
    ctx.amount_safe_to_pay = rules_engine.compute_amount_safe_to_pay(ctx)

    result = rules_engine._amount_safe_to_pay_with_changes(
        ctx, [Change(kind="stop", event_id="event_0")]
    )
    assert result == 400.0  # fully restored: 1000 - 500 = 500 headroom, capped at requested


def test_amount_safe_to_pay_with_changes_ignores_unknown_event_id():
    ctx = make_ctx(
        requested_amount=100.0,
        minimum_balance_to_keep=1000.0,
        current_available_balance=1500.0,
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    result = rules_engine._amount_safe_to_pay_with_changes(
        ctx, [Change(kind="stop", event_id="does_not_exist")]
    )
    assert result == 100.0


# --------------------------------------------------------------------------- #
# propose_spending_changes
# --------------------------------------------------------------------------- #


def test_propose_spending_changes_no_shortfall_returns_empty():
    ctx = make_ctx(resolved_events=make_resolved_events([]))
    ctx.amount_safe_to_pay = ctx.requested_amount
    assert rules_engine.propose_spending_changes(ctx) == []


def test_propose_spending_changes_prefers_stop_over_reduce():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        requested_amount=350.0,
        minimum_balance_to_keep=500.0,
        current_available_balance=1000.0,
        stoppable_categories=("streaming",),
        reducible_categories=("streaming",),
        resolved_events=make_resolved_events(
            [
                {
                    "event_id": "event_0", "category": "streaming", "direction": "debit", "amount": 300.0,
                    "settlement_date": date(2024, 1, 2), "flexibility": "reducible_or_stoppable",
                }
            ]
        ),
    )
    ctx.resolved_events["event_id"] = ["event_0"]
    rules_engine.build_forecast(ctx)
    ctx.amount_safe_to_pay = rules_engine.compute_amount_safe_to_pay(ctx)

    changes = rules_engine.propose_spending_changes(ctx)
    assert len(changes) == 1
    assert changes[0].kind == "stop"


def test_propose_spending_changes_reduce_respects_floor():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        requested_amount=350.0,
        minimum_balance_to_keep=500.0,
        current_available_balance=1000.0,
        reducible_categories=("dining",),
        resolved_events=make_resolved_events(
            [
                {
                    "event_id": "event_0", "category": "dining", "direction": "debit", "amount": 200.0,
                    "settlement_date": date(2024, 1, 2), "flexibility": "reducible",
                    "minimum_allowed_amount": 150.0,
                }
            ]
        ),
    )
    ctx.resolved_events["event_id"] = ["event_0"]
    rules_engine.build_forecast(ctx)
    ctx.amount_safe_to_pay = rules_engine.compute_amount_safe_to_pay(ctx)  # 300; shortfall 50, exactly the floor's headroom

    changes = rules_engine.propose_spending_changes(ctx)
    assert len(changes) == 1
    assert changes[0].kind == "reduce_to"
    assert changes[0].new_amount == 150.0


def test_propose_spending_changes_excludes_protected_category():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        requested_amount=400.0,
        protected_categories=("groceries",),
        stoppable_categories=("groceries",),
        resolved_events=make_resolved_events(
            [
                {
                    "event_id": "event_0", "category": "groceries", "direction": "debit", "amount": 300.0,
                    "settlement_date": date(2024, 1, 5), "flexibility": "stoppable",
                }
            ]
        ),
    )
    ctx.amount_safe_to_pay = 100.0
    assert rules_engine.propose_spending_changes(ctx) == []


def test_propose_spending_changes_caps_at_three():
    # 5 eligible events, strictly decreasing amounts so sort order is
    # deterministic. Requested (450) needs more than any 2 (390) but is
    # covered by the top 3 (570 freed, once the other two events' permanent
    # drag is accounted for) - the 4th and 5th must never be touched.
    amounts = [200.0, 190.0, 180.0, 170.0, 160.0]
    rows = [
        {
            "event_id": f"event_{i}", "category": "streaming", "direction": "debit", "amount": amt,
            "settlement_date": date(2024, 1, 5 + i), "flexibility": "stoppable",
        }
        for i, amt in enumerate(amounts)
    ]
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        requested_amount=450.0,
        minimum_balance_to_keep=200.0,
        current_available_balance=1000.0,
        stoppable_categories=("streaming",),
        resolved_events=make_resolved_events(rows),
    )
    ctx.resolved_events["event_id"] = [r["event_id"] for r in rows]
    rules_engine.build_forecast(ctx)
    ctx.amount_safe_to_pay = rules_engine.compute_amount_safe_to_pay(ctx)

    changes = rules_engine.propose_spending_changes(ctx)
    assert len(changes) == 3
    assert {c.event_id for c in changes} == {"event_0", "event_1", "event_2"}


def test_propose_spending_changes_skips_event_permitted_for_neither_action():
    # flexibility is "stoppable" (passes the initial filter) but the
    # category isn't in the user's stoppable OR reducible lists, so neither
    # _can_stop nor _can_reduce applies - _freed() must return 0 for it.
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        requested_amount=400.0,
        stoppable_categories=(),
        reducible_categories=(),
        resolved_events=make_resolved_events(
            [
                {
                    "event_id": "event_0", "category": "gym", "direction": "debit", "amount": 300.0,
                    "settlement_date": date(2024, 1, 5), "flexibility": "stoppable",
                }
            ]
        ),
    )
    ctx.amount_safe_to_pay = 100.0
    assert rules_engine.propose_spending_changes(ctx) == []


def test_propose_spending_changes_returns_empty_when_still_insufficient():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        requested_amount=100000.0,
        minimum_balance_to_keep=1000.0,
        current_available_balance=2000.0,
        stoppable_categories=("streaming",),
        resolved_events=make_resolved_events(
            [
                {
                    "event_id": "event_0", "category": "streaming", "direction": "debit", "amount": 50.0,
                    "settlement_date": date(2024, 1, 5), "flexibility": "stoppable",
                }
            ]
        ),
    )
    ctx.resolved_events["event_id"] = ["event_0"]
    rules_engine.build_forecast(ctx)
    ctx.amount_safe_to_pay = rules_engine.compute_amount_safe_to_pay(ctx)

    assert rules_engine.propose_spending_changes(ctx) == []


# --------------------------------------------------------------------------- #
# _installment_schedule / _schedule_is_safe
# --------------------------------------------------------------------------- #


def test_installment_schedule_builds_expected_dates_and_amounts():
    opt = pd.Series(
        {
            "number_of_payments": 3,
            "payment_amount_home_ccy": 100.0,
            "payment_frequency_days": 30,
            "first_payment_date": date(2024, 1, 1),
        }
    )
    schedule = rules_engine._installment_schedule(opt)
    assert schedule == [
        (date(2024, 1, 1), 100.0),
        (date(2024, 1, 31), 100.0),
        (date(2024, 3, 1), 100.0),
    ]


def test_schedule_is_safe_true_when_headroom_holds():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        minimum_balance_to_keep=1000.0,
        current_available_balance=6000.0,
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    schedule = [(date(2024, 1, 1), 1000.0), (date(2024, 1, 31), 1000.0), (date(2024, 3, 1), 1000.0)]
    assert rules_engine._schedule_is_safe(ctx, schedule) is True


def test_schedule_is_safe_false_when_cumulative_breaches_minimum():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        minimum_balance_to_keep=1000.0,
        current_available_balance=2000.0,
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    schedule = [(date(2024, 1, 1), 1000.0), (date(2024, 1, 31), 1000.0)]
    assert rules_engine._schedule_is_safe(ctx, schedule) is False


# --------------------------------------------------------------------------- #
# select_plan (end-to-end scenarios)
# --------------------------------------------------------------------------- #


def test_select_plan_affordable_now_full_payment():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        desired_completion_date=date(2024, 2, 1),
        requested_amount=1000.0,
        current_available_balance=5000.0,
        minimum_balance_to_keep=1000.0,
        payment_methods_allowed=("full_payment",),
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.amount_safe_to_pay == 1000.0
    assert ctx.affordability_status == "affordable_now"
    assert ctx.recommended_payment_method == "full_payment"
    assert ctx.payment_plan == "2024-01-01:1000"
    assert ctx.earliest_date_for_full_payment == "2024-01-01"
    assert ctx.spending_changes_needed == "none"


def test_select_plan_not_affordable_when_flat_and_insufficient():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        requested_amount=500.0,
        current_available_balance=1000.0,
        minimum_balance_to_keep=1000.0,
        payment_methods_allowed=("full_payment",),
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.affordability_status == "not_affordable"
    assert ctx.recommended_payment_method == "not_recommended"
    assert ctx.payment_plan == "none"
    assert ctx.spending_changes_needed == "none"
    assert ctx.earliest_date_for_full_payment == ""


def test_select_plan_wait_when_full_payment_becomes_safe_later():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        desired_completion_date=date(2024, 2, 1),
        requested_amount=500.0,
        current_available_balance=1000.0,
        minimum_balance_to_keep=1000.0,
        payment_methods_allowed=("full_payment",),
        resolved_events=make_resolved_events(
            [
                {
                    "category": "salary", "direction": "credit", "amount": 2000.0,
                    "settlement_date": date(2024, 1, 10), "status": "scheduled",
                }
            ]
        ),
    )
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.affordability_status == "affordable_later"
    assert ctx.recommended_payment_method == "wait"
    assert ctx.payment_plan == "2024-01-10:500"


def test_select_plan_partial_payment():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        desired_completion_date=date(2024, 2, 1),
        requested_amount=1000.0,
        allows_partial_payment=True,
        current_available_balance=1500.0,
        minimum_balance_to_keep=1000.0,
        payment_methods_allowed=("partial_payment",),
        resolved_events=make_resolved_events(
            [
                {
                    "category": "salary", "direction": "credit", "amount": 1000.0,
                    "settlement_date": date(2024, 1, 6), "status": "scheduled",
                }
            ]
        ),
    )
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.affordability_status == "affordable_with_plan"
    assert ctx.recommended_payment_method == "partial_payment"
    assert ctx.payment_plan == "2024-01-01:500|2024-01-06:500"


def test_select_plan_installments_within_max_months():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        desired_completion_date=date(2024, 6, 1),
        requested_amount=3000.0,
        current_available_balance=6000.0,
        minimum_balance_to_keep=1000.0,
        payment_methods_allowed=("installments",),
        max_installment_months=12.0,
        payment_options=make_payment_options(
            [{"payment_method": "installments", "payment_amount": 1000.0, "number_of_payments": 3,
              "payment_frequency_days": 30, "first_payment_date": date(2024, 1, 1),
              "total_payable_amount": 3000.0}]
        ),
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.recommended_payment_method == "installments"
    assert ctx.affordability_status == "affordable_with_plan"
    assert ctx.chosen_payment_option_id == "payment_option_00"


def test_select_plan_installments_excluded_when_schedule_is_unsafe():
    # Within max_installment_months, but the balance can't actually sustain it.
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        desired_completion_date=date(2024, 6, 1),
        requested_amount=3000.0,
        current_available_balance=1500.0,
        minimum_balance_to_keep=1000.0,
        payment_methods_allowed=("installments",),
        max_installment_months=12.0,
        payment_options=make_payment_options(
            [{"payment_method": "installments", "payment_amount": 1000.0, "number_of_payments": 3,
              "payment_frequency_days": 30, "first_payment_date": date(2024, 1, 1),
              "total_payable_amount": 3000.0}]
        ),
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.recommended_payment_method == "not_recommended"


def test_select_plan_installments_excluded_when_exceeding_max_months():
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        desired_completion_date=date(2030, 1, 1),
        requested_amount=3000.0,
        current_available_balance=60000.0,
        minimum_balance_to_keep=1000.0,
        payment_methods_allowed=("installments",),
        max_installment_months=2.0,  # too short for an 18-month plan
        payment_options=make_payment_options(
            [{"payment_method": "installments", "payment_amount": 200.0, "number_of_payments": 18,
              "payment_frequency_days": 31, "first_payment_date": date(2024, 1, 1),
              "total_payable_amount": 3600.0}]
        ),
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.recommended_payment_method == "not_recommended"


def test_select_plan_installments_ineligible_when_max_months_is_none():
    ctx = make_ctx(
        requested_amount=3000.0,
        current_available_balance=6000.0,
        minimum_balance_to_keep=1000.0,
        payment_methods_allowed=("installments",),
        max_installment_months=None,
        payment_options=make_payment_options(
            [{"payment_method": "installments", "payment_amount": 1000.0, "number_of_payments": 3}]
        ),
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.recommended_payment_method == "not_recommended"


def test_select_plan_ranks_lower_total_paid_over_more_payments():
    # Two safe installment options; the cheaper one (lower total_paid) must win.
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        desired_completion_date=date(2024, 6, 1),
        requested_amount=3000.0,
        current_available_balance=20000.0,
        minimum_balance_to_keep=1000.0,
        payment_methods_allowed=("installments",),
        max_installment_months=12.0,
        payment_options=make_payment_options(
            [
                {"payment_method": "installments", "payment_amount": 1000.0, "number_of_payments": 3,
                 "payment_frequency_days": 30, "first_payment_date": date(2024, 1, 1),
                 "total_payable_amount": 3000.0},
                {"payment_method": "installments", "payment_amount": 700.0, "number_of_payments": 5,
                 "payment_frequency_days": 30, "first_payment_date": date(2024, 1, 1),
                 "total_payable_amount": 3500.0},
            ]
        ),
        resolved_events=make_resolved_events([]),
    )
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.chosen_payment_option_id == "payment_option_00"


def test_select_plan_uses_spending_changes_as_last_resort():
    # Baseline headroom (with the streaming debit applied) is only 200, not
    # enough for the 350 request - but stopping the streaming debit frees an
    # extra 300, which is enough.
    ctx = make_ctx(
        request_date=date(2024, 1, 1),
        desired_completion_date=date(2024, 2, 1),
        requested_amount=350.0,
        current_available_balance=1000.0,
        minimum_balance_to_keep=500.0,
        payment_methods_allowed=("full_payment",),
        stoppable_categories=("streaming",),
        resolved_events=make_resolved_events(
            [
                {
                    "event_id": "event_0", "category": "streaming", "direction": "debit", "amount": 300.0,
                    "settlement_date": date(2024, 1, 2), "flexibility": "stoppable",
                }
            ]
        ),
    )
    ctx.resolved_events["event_id"] = ["event_0"]
    rules_engine.build_forecast(ctx)
    rules_engine.select_plan(ctx)

    assert ctx.recommended_payment_method == "full_payment"
    assert ctx.affordability_status == "affordable_with_plan"
    assert ctx.spending_changes_needed == "stop:event_0"
    assert ctx.payment_plan == "2024-01-01:350"


# --------------------------------------------------------------------------- #
# compute() orchestration
# --------------------------------------------------------------------------- #


def test_compute_runs_full_pipeline_end_to_end():
    agent = FakeAgent(
        request_id="request_1",
        user_id="user_1",
        request_date=date(2024, 1, 1),
        requested_amount=1000.0,
        desired_completion_date=date(2024, 2, 1),
        allows_partial_payment=False,
    )
    profile = pd.DataFrame(
        [
            {
                "user_id": "user_1",
                "home_currency": "ZAR",
                "current_available_balance": 5000.0,
                "minimum_balance_to_keep": 1000.0,
                "expense_categories_to_protect": (),
                "expense_categories_user_is_willing_to_reduce": (),
                "expense_categories_user_is_willing_to_stop": (),
                "payment_methods_user_will_consider": ("full_payment",),
                "max_installment_months": float("nan"),
            }
        ]
    )
    filtered_data = {
        "financial_profiles": profile,
        "financial_events": make_events_df([]),
        "request_payment_options": make_payment_options([]),
        "exchange_rates": empty_exchange_rates(),
        "images": empty_images(),
        "messages": empty_messages(),
    }

    ctx = rules_engine.compute(agent, filtered_data)

    assert ctx.affordability_status == "affordable_now"
    assert ctx.amount_safe_to_pay == 1000.0
