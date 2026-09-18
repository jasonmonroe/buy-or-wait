# tests/factories.py
# +---------------------------------------------------------------------------+
# |                    TEST DATA FACTORIES (not a test module)                |
# +---------------------------------------------------------------------------+
#
# Small builders for the DataFrames/dataclasses rules_engine.py and
# request_agent.py operate on, so individual tests only specify the fields
# that matter for that test rather than the full CSV schema every time.

# python -m pytest code/tests/ --cov=code --cov-report=`term-missing` or `html`
# open htmlcov/index.html

from datetime import date

import pandas as pd
from src.rules_engine import FinancialContext

EVENT_DEFAULTS = {
    "user_id": "user_1",
    "event_type": "expense",
    "description": "",
    "category": "rent",
    "direction": "debit",
    "amount": 100.0,
    "currency": "ZAR",
    "event_date": date(2024, 1, 1),
    "settlement_date": date(2024, 1, 1),
    "status": "settled",
    "linked_event_id": None,
    "flexibility": "fixed",
    "minimum_allowed_amount": None,
}

EVENT_COLUMNS = [
    "event_id",
    "user_id",
    "event_type",
    "description",
    "category",
    "direction",
    "amount",
    "currency",
    "event_date",
    "settlement_date",
    "status",
    "linked_event_id",
    "flexibility",
    "minimum_allowed_amount",
]


def make_events_df(rows: list[dict]) -> pd.DataFrame:
    """Builds a financial_events-shaped DataFrame. Each row may omit any
    column - EVENT_DEFAULTS fills it in - except event_id, which defaults to
    a positional event_0, event_1, ... unless given explicitly."""
    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    filled = []
    for i, row in enumerate(rows):
        merged = {"event_id": f"event_{i}", **EVENT_DEFAULTS, **row}
        filled.append(merged)
    return pd.DataFrame(filled, columns=EVENT_COLUMNS)


def make_resolved_events(rows: list[dict]) -> pd.DataFrame:
    """Like make_events_df, but also stamps amount_home_ccy (defaulting to
    amount) - i.e. what ctx.resolved_events looks like after resolve_events()
    has run, for tests that start downstream of currency conversion."""
    df = make_events_df(rows)
    df["amount_home_ccy"] = [
        r.get("amount_home_ccy", r.get("amount", EVENT_DEFAULTS["amount"]))
        for r in rows
    ]
    return df


PAYMENT_OPTION_DEFAULTS = {
    "request_id": "request_1",
    "payment_method": "installments",
    "payment_amount": 100.0,
    "number_of_payments": 3,
    "first_payment_date": date(2024, 1, 1),
    "payment_frequency_days": 30,
    "financing_fee": 0.0,
    "total_payable_amount": 300.0,
}

PAYMENT_OPTION_COLUMNS = ["payment_option_id"] + list(PAYMENT_OPTION_DEFAULTS.keys())


def make_payment_options(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        df = pd.DataFrame(columns=PAYMENT_OPTION_COLUMNS)
    else:
        filled = []
        for i, row in enumerate(rows):
            merged = {
                "payment_option_id": f"payment_option_{i:02d}",
                **PAYMENT_OPTION_DEFAULTS,
                **row,
            }
            filled.append(merged)
        df = pd.DataFrame(filled, columns=PAYMENT_OPTION_COLUMNS)

    df["payment_amount_home_ccy"] = df["payment_amount"] if len(df) else []
    df["total_payable_amount_home_ccy"] = df["total_payable_amount"] if len(df) else []
    return df


def empty_exchange_rates() -> pd.DataFrame:
    return pd.DataFrame(columns=["rate_date", "from_currency", "to_currency", "rate"])


def empty_images() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["image_id", "user_id", "request_id", "related_event_id"]
    )


def empty_messages() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "message_id",
            "user_id",
            "request_id",
            "related_event_id",
            "sent_at",
            "source_type",
            "message_text",
        ]
    )


def make_ctx(**overrides) -> FinancialContext:
    """A FinancialContext with sane defaults for a solvent, no-history user.
    Override only the fields a given test cares about."""
    defaults = dict(
        request_id="request_1",
        user_id="user_1",
        request_date=date(2024, 1, 1),
        requested_amount=1000.0,
        desired_completion_date=date(2024, 2, 1),
        allows_partial_payment=True,
        home_currency="ZAR",
        current_available_balance=5000.0,
        minimum_balance_to_keep=1000.0,
        protected_categories=("rent",),
        reducible_categories=("dining",),
        stoppable_categories=("streaming",),
        payment_methods_allowed=("full_payment", "partial_payment", "installments"),
        max_installment_months=12.0,
        raw_events=make_events_df([]),
        payment_options=make_payment_options([]),
        exchange_rates=empty_exchange_rates(),
        images=empty_images(),
        messages=empty_messages(),
    )
    defaults.update(overrides)
    return FinancialContext(**defaults)
