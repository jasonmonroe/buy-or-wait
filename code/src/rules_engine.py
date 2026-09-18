from __future__ import annotations

# src/rules_engine.py
# +---------------------------------------------------------------------------+
# |                       DETERMINISTIC RULES ENGINE                          |
# +---------------------------------------------------------------------------+
#
# Pure functions operating on a FinancialContext. No LLM calls happen here -
# this module is the deterministic layer described in AGENTS.md section 6.4
# ("keep behavior deterministic where possible") and problem_statement.md's
# 90-Day Safety Check / Choosing Between Safe Plans sections.
# Python Libraries
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

# Vendor Libraries
import pandas as pd

# Local Libraries
from src.constants import NONE_VAL
from src.enum import AffordabilityStatus, RecommendedPaymentMethod

FORECAST_DAYS = 90

# Rows in these states never represent real, countable cash flow.
_DROP_STATUSES = {"cancelled", "failed", "unrealized"}
_DROP_DIRECTIONS = {"non_cash"}
_FLEXIBLE_VALUES = {"stoppable", "reducible", "reducible_or_stoppable"}

# --------------------------------------------------------------------------- #
# Data Structures
# --------------------------------------------------------------------------- #


@dataclass
class RecurringSeries:
    category: str
    direction: str  # "credit" | "debit"
    avg_amount: float
    interval_days: int
    next_expected_date: date
    event_ids: list[str]
    flexibility: str


@dataclass
class Change:
    kind: str  # "stop" | "reduce_to"
    event_id: str
    new_amount: float | None = None

    def format(self) -> str:
        if self.kind == "stop":
            return f"stop:{self.event_id}"
        return f"reduce_to:{self.event_id}:{fmt_amount(self.new_amount)}"


@dataclass
class PlanCandidate:
    method: str
    status: str
    plan: list[tuple[date, float]]
    total_paid: float
    start: date
    n_payments: int
    option_id: str | None
    needs_changes: bool = False
    changes: list[Change] = field(default_factory=list)


@dataclass
class FinancialContext:
    request_id: str
    user_id: str
    request_date: date
    requested_amount: float
    desired_completion_date: date
    allows_partial_payment: bool
    home_currency: str

    current_available_balance: float
    minimum_balance_to_keep: float
    protected_categories: list[str]
    reducible_categories: list[str]
    stoppable_categories: list[str]
    payment_methods_allowed: list[str]
    max_installment_months: float | None

    raw_events: pd.DataFrame
    payment_options: pd.DataFrame
    exchange_rates: pd.DataFrame
    images: pd.DataFrame
    messages: pd.DataFrame

    resolved_events: pd.DataFrame = None
    recurring_series: list[RecurringSeries] = field(default_factory=list)
    variable_daily_rate: float = 0.0

    daily_balance: dict = None
    running_min_from: dict = None

    amount_safe_to_pay: float = None
    affordability_status: str = None
    recommended_payment_method: str = None
    payment_plan: str = None
    earliest_date_for_full_payment: str = None
    spending_changes_needed: str = None
    chosen_payment_option_id: str = None


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def compute(agent, filtered_data: dict, ocr_fn=None) -> FinancialContext:
    """Runs the full deterministic pipeline and returns the populated context."""
    ctx = build_context(agent, filtered_data)
    resolve_events(ctx, ocr_fn=ocr_fn)
    detect_recurring(ctx)
    estimate_variable_spending(ctx)
    build_forecast(ctx)
    select_plan(ctx)
    return ctx


def build_context(agent, filtered_data: dict) -> FinancialContext:
    profile_df = filtered_data.get("financial_profiles")
    if profile_df is None or profile_df.empty:
        raise ValueError(f"No financial profile found for user_id={agent.user_id}")
    profile = profile_df.iloc[0]

    max_months = profile["max_installment_months"]

    return FinancialContext(
        request_id=agent.request_id,
        user_id=agent.user_id,
        request_date=agent.request_date,
        requested_amount=float(agent.requested_amount),
        desired_completion_date=agent.desired_completion_date,
        allows_partial_payment=bool(agent.allows_partial_payment),
        home_currency=profile["home_currency"],
        current_available_balance=float(profile["current_available_balance"]),
        minimum_balance_to_keep=float(profile["minimum_balance_to_keep"]),
        protected_categories=profile["expense_categories_to_protect"],
        reducible_categories=profile["expense_categories_user_is_willing_to_reduce"],
        stoppable_categories=profile["expense_categories_user_is_willing_to_stop"],
        payment_methods_allowed=profile["payment_methods_user_will_consider"],
        max_installment_months=None if pd.isna(max_months) else float(max_months),
        raw_events=filtered_data.get("financial_events").copy(),
        payment_options=filtered_data.get("request_payment_options").copy(),
        exchange_rates=filtered_data.get("exchange_rates"),
        images=filtered_data.get("images"),
        messages=filtered_data.get("messages"),
    )


# --------------------------------------------------------------------------- #
# Step 1: resolve events (currency conversion, blank-amount OCR fill, dedup)
# --------------------------------------------------------------------------- #


def resolve_events(ctx: FinancialContext, ocr_fn=None) -> None:
    events = ctx.raw_events.copy()

    events = events[~events["status"].isin(_DROP_STATUSES)]
    events = events[~events["direction"].isin(_DROP_DIRECTIONS)]

    blank_mask = events["amount"].isna()
    if blank_mask.any() and ocr_fn is not None:
        for event_id in events.loc[blank_mask, "event_id"].tolist():
            matching_images = ctx.images[ctx.images["related_event_id"] == event_id]
            if matching_images.empty:
                continue
            extracted = ocr_fn(matching_images)
            if extracted is not None:
                events.loc[events["event_id"] == event_id, "amount"] = extracted

    # A blank amount that couldn't be resolved must not be treated as zero -
    # drop it rather than let it silently zero out the forecast.
    events = events.dropna(subset=["amount"])

    dedup_cols = ["user_id", "category", "amount", "event_date", "direction"]
    events = events.drop_duplicates(subset=dedup_cols, keep="last")

    def _convert_row(row):
        on_date = (
            row["settlement_date"]
            if pd.notna(row["settlement_date"])
            else row["event_date"]
        )
        return convert_amount(
            row["amount"],
            row["currency"],
            ctx.home_currency,
            on_date,
            ctx.exchange_rates,
        )

    events["amount_home_ccy"] = events.apply(_convert_row, axis=1)

    ctx.resolved_events = events

    # request_payment_options.csv carries no currency column - per the dataset
    # contract, payment options are already stated in the user's home currency.
    ctx.payment_options["payment_amount_home_ccy"] = ctx.payment_options[
        "payment_amount"
    ]
    ctx.payment_options["total_payable_amount_home_ccy"] = ctx.payment_options[
        "total_payable_amount"
    ]


def convert_amount(
    amount: float,
    from_currency: str,
    to_currency: str,
    on_date: date,
    rates_df: pd.DataFrame,
) -> float:
    if pd.isna(amount) or from_currency == to_currency:
        return amount

    rate = _find_rate(rates_df, from_currency, to_currency, on_date)
    if rate is not None:
        return amount * rate

    inv_rate = _find_rate(rates_df, to_currency, from_currency, on_date)
    if inv_rate is not None:
        return amount / inv_rate

    # 2-hop chain through any intermediate currency present in the table
    # (e.g. USD -> EUR -> ZAR when no direct USD -> ZAR rate is stored).
    for mid in rates_df["from_currency"].unique():
        if mid in (from_currency, to_currency):
            continue
        r1 = _find_rate(rates_df, from_currency, mid, on_date)
        if r1 is None:
            inv = _find_rate(rates_df, mid, from_currency, on_date)
            r1 = (1 / inv) if inv else None
        r2 = _find_rate(rates_df, mid, to_currency, on_date)
        if r2 is None:
            inv = _find_rate(rates_df, to_currency, mid, on_date)
            r2 = (1 / inv) if inv else None
        if r1 and r2:
            return amount * r1 * r2

    raise ValueError(f"No FX path {from_currency}->{to_currency} on {on_date}")


def _find_rate(
    rates_df: pd.DataFrame, frm: str, to: str, on_date: date
) -> float | None:
    subset = rates_df[
        (rates_df["from_currency"] == frm) & (rates_df["to_currency"] == to)
    ]
    if subset.empty:
        return None

    # exchange_rates.csv is a sparse monthly grid, so an exact settlement-date
    # match will rarely exist - use the nearest rate on or before that date,
    # falling back to the earliest available rate if none is prior.
    prior = subset[subset["rate_date"] <= on_date]
    row = (
        prior.sort_values("rate_date").iloc[-1]
        if not prior.empty
        else subset.sort_values("rate_date").iloc[0]
    )
    return float(row["rate"])


# --------------------------------------------------------------------------- #
# Step 2: Recurrence Detection
# --------------------------------------------------------------------------- #


def detect_recurring(ctx: FinancialContext) -> None:
    # Use every known occurrence (settled history plus any already-confirmed
    # scheduled/pending row) to detect the pattern - a single settled salary
    # payment plus next month's already-scheduled one is exactly the
    # "confirmed salary" evidence AGENTS.md describes, and rejecting it for
    # having only one *settled* data point would understate future income.
    history = ctx.resolved_events[
        ctx.resolved_events["event_date"]
        <= ctx.request_date + timedelta(days=FORECAST_DAYS)
    ]

    series: list[RecurringSeries] = []
    for (category, direction), group in history.groupby(["category", "direction"]):
        group = group.sort_values("event_date")
        dates = group["event_date"].tolist()
        amounts = group["amount_home_ccy"].tolist()

        if len(dates) < 2:
            continue

        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        mean_gap = statistics.mean(gaps)
        if mean_gap < 5:
            continue  # too frequent to be a periodic bill, treat as variable spend
        # Reference the MEAN, not the median: a common real-world pattern is
        # pay on fixed calendar days (e.g. the 7th and 20th of every month),
        # which alternates between two gap lengths (13, 15, 17, 18, ...)
        # depending on month length. The median sits at one extreme of that
        # alternation and would wrongly reject the whole series as
        # inconsistent; the mean sits between the two clusters.
        if not all(abs(g - mean_gap) <= max(4, 0.3 * mean_gap) for g in gaps):
            continue

        avg_amount = statistics.mean(amounts)
        # With only 2 historical points, a single jump (e.g. a raise) can't be
        # distinguished from noise - trust the interval and project forward
        # using the most recent amount instead of rejecting the series.
        # Threshold is deliberately loose (80% of the mean): a tight, exact
        # interval (e.g. groceries every 10 days like clockwork) is already
        # strong evidence of a recurring pattern, and normal per-trip amount
        # variation (different amounts each grocery run) shouldn't disqualify
        # it - only genuine noise (amounts varying wildly) should.
        if (
            len(amounts) >= 3
            and avg_amount
            and (max(amounts) - min(amounts)) > 0.8 * avg_amount
        ):
            continue

        next_expected = dates[-1] + timedelta(days=round(mean_gap))
        # A per-occurrence-volatile category (groceries, ad hoc transport)
        # with enough history is better represented by its historical mean
        # than by one noisy last data point. Only fall back to the last
        # observed amount when there's too little history to average (a
        # step change like a raise, with just 2 points, should carry
        # forward rather than get averaged down/up).
        projected_amount = amounts[-1] if len(amounts) <= 2 else avg_amount
        series.append(
            RecurringSeries(
                category=category,
                direction=direction,
                avg_amount=projected_amount,
                interval_days=round(mean_gap),
                next_expected_date=next_expected,
                event_ids=group["event_id"].tolist(),
                flexibility=group["flexibility"].iloc[-1],
            )
        )

    ctx.recurring_series = series


VARIABLE_LOOKBACK_DAYS = 90
MIN_VARIABLE_OCCURRENCES = 2

# Cost-of-living categories that are genuinely ongoing/essential even when
# their timing and amount are too irregular to pass the strict periodic
# recurring test. Deliberately excludes discretionary/one-off categories
# (shopping, entertainment, family_support, investment, ...) - AGENTS.md 6.3
# calls for distinguishing recurring essentials from one-time purchases, and
# auto-applying a perpetual burn rate to a one-off category would be inventing
# spending, not forecasting it conservatively.
_ESSENTIAL_VARIABLE_CATEGORIES = {"groceries", "transport", "dining", "healthcare"}


def estimate_variable_spending(ctx: FinancialContext) -> None:
    """Essential-but-irregular debit categories (groceries, transport, ad hoc
    dining, ...) often fail the strict periodic recurring test - real-world
    spending in these categories isn't evenly spaced or a fixed amount. Per
    AGENTS.md 6.3 ("forecast essential variable spending conservatively"),
    such a category must still be projected forward as a smoothed daily
    burn rate rather than dropped from the forecast entirely."""
    recurring_debit_categories = {
        s.category for s in ctx.recurring_series if s.direction == "debit"
    }
    lookback_start = ctx.request_date - timedelta(days=VARIABLE_LOOKBACK_DAYS)

    history = ctx.resolved_events[
        (ctx.resolved_events["direction"] == "debit")
        & (ctx.resolved_events["category"].isin(_ESSENTIAL_VARIABLE_CATEGORIES))
        & (ctx.resolved_events["event_date"] >= lookback_start)
        & (ctx.resolved_events["event_date"] < ctx.request_date)
    ]

    total_daily_rate = 0.0
    for category, group in history.groupby("category"):
        if (
            category in recurring_debit_categories
            or len(group) < MIN_VARIABLE_OCCURRENCES
        ):
            continue
        total_daily_rate += group["amount_home_ccy"].sum() / VARIABLE_LOOKBACK_DAYS

    ctx.variable_daily_rate = total_daily_rate


# --------------------------------------------------------------------------- #
# Step 3: 90-day forecast
# --------------------------------------------------------------------------- #


def build_forecast(ctx: FinancialContext) -> None:
    start = ctx.request_date
    end = start + timedelta(days=FORECAST_DAYS)

    cash_events: list[tuple[date, float]] = []
    covered_by_series: dict[tuple[str, str], set[date]] = {}

    future = ctx.resolved_events[
        ctx.resolved_events["settlement_date"].notna()
        & (ctx.resolved_events["settlement_date"] >= start)
        & (ctx.resolved_events["settlement_date"] <= end)
    ]

    for _, ev in future.iterrows():
        if ev["status"] == "pending" and ev["direction"] == "credit":
            continue  # ignore pending credits/bonuses/refunds until settled

        sign = 1 if ev["direction"] == "credit" else -1
        d = ev["settlement_date"]
        cash_events.append((d, sign * ev["amount_home_ccy"]))
        covered_by_series.setdefault((ev["category"], ev["direction"]), set()).add(d)

    for s in ctx.recurring_series:
        covered = covered_by_series.get((s.category, s.direction), set())
        next_date = s.next_expected_date
        while next_date <= end:
            if next_date >= start and next_date not in covered:
                sign = 1 if s.direction == "credit" else -1
                cash_events.append((next_date, sign * s.avg_amount))
            next_date += timedelta(days=s.interval_days)

    cash_events.sort(key=lambda t: t[0])

    daily: dict[date, float] = {}
    running = ctx.current_available_balance
    idx, n = 0, len(cash_events)
    d = start
    while d <= end:
        while idx < n and cash_events[idx][0] == d:
            running += cash_events[idx][1]
            idx += 1
        running -= ctx.variable_daily_rate
        daily[d] = running
        d += timedelta(days=1)

    ctx.daily_balance = daily
    ctx.running_min_from = _suffix_min(daily, start, end)


def _suffix_min(daily: dict[date, float], start: date, end: date) -> dict[date, float]:
    result: dict[date, float] = {}
    running_min = None
    d = end
    while d >= start:
        val = daily[d]
        running_min = val if running_min is None else min(running_min, val)
        result[d] = running_min
        d -= timedelta(days=1)
    return result


def compute_amount_safe_to_pay(ctx: FinancialContext) -> float:
    headroom = ctx.running_min_from[ctx.request_date] - ctx.minimum_balance_to_keep
    return max(0.0, min(ctx.requested_amount, headroom))


def compute_earliest_date_for_full_payment(ctx: FinancialContext) -> date | None:
    end = ctx.request_date + timedelta(days=FORECAST_DAYS)
    d = ctx.request_date
    while d <= end:
        headroom = ctx.running_min_from[d] - ctx.minimum_balance_to_keep
        if headroom >= ctx.requested_amount:
            return d
        d += timedelta(days=1)
    return None


def _amount_safe_to_pay_with_changes(
    ctx: FinancialContext, changes: list[Change]
) -> float:
    """Recomputes headroom as if the proposed changes had freed up cash from
    their event's settlement date onward, without mutating the base forecast."""
    end = ctx.request_date + timedelta(days=FORECAST_DAYS)
    freed_by_date: dict[date, float] = {}

    for ch in changes:
        row = ctx.resolved_events[ctx.resolved_events["event_id"] == ch.event_id]
        if row.empty:
            continue
        row = row.iloc[0]
        d = row["settlement_date"]
        freed = (
            row["amount_home_ccy"]
            if ch.kind == "stop"
            else row["amount_home_ccy"] - ch.new_amount
        )
        freed_by_date[d] = freed_by_date.get(d, 0.0) + freed

    adjusted_daily: dict[date, float] = {}
    running_add = 0.0
    d = ctx.request_date
    while d <= end:
        running_add += freed_by_date.get(d, 0.0)
        adjusted_daily[d] = ctx.daily_balance[d] + running_add
        d += timedelta(days=1)

    adjusted_min = _suffix_min(adjusted_daily, ctx.request_date, end)
    headroom = adjusted_min[ctx.request_date] - ctx.minimum_balance_to_keep
    return max(0.0, min(ctx.requested_amount, headroom))


# --------------------------------------------------------------------------- #
# Step 4: Spending-changes proposal (last resort, only tried when no
# change-free plan is safe - see select_plan)
# --------------------------------------------------------------------------- #


def propose_spending_changes(ctx: FinancialContext) -> list[Change]:
    shortfall = ctx.requested_amount - ctx.amount_safe_to_pay
    if shortfall <= 0:
        return []

    window_end = ctx.request_date + timedelta(days=FORECAST_DAYS)
    events = ctx.resolved_events
    eligible = events[
        events["settlement_date"].notna()
        & (events["settlement_date"] >= ctx.request_date)
        & (events["settlement_date"] <= window_end)
        & (events["direction"] == "debit")
        & (~events["category"].isin(ctx.protected_categories))
        & (events["flexibility"].isin(_FLEXIBLE_VALUES))
    ].copy()

    if eligible.empty:
        return []

    def _can_stop(row) -> bool:
        return row["category"] in ctx.stoppable_categories and row["flexibility"] in (
            "stoppable",
            "reducible_or_stoppable",
        )

    def _can_reduce(row) -> bool:
        return row["category"] in ctx.reducible_categories and row["flexibility"] in (
            "reducible",
            "reducible_or_stoppable",
        )

    def _freed(row) -> float:
        if _can_stop(row):
            return row["amount_home_ccy"]
        if _can_reduce(row):
            floor = (
                row["minimum_allowed_amount"]
                if pd.notna(row["minimum_allowed_amount"])
                else 0.0
            )
            return max(0.0, row["amount_home_ccy"] - floor)
        return 0.0

    eligible["freed"] = eligible.apply(_freed, axis=1)
    eligible = eligible[eligible["freed"] > 0].sort_values("freed", ascending=False)

    chosen: list[Change] = []
    covered = 0.0
    for _, ev in eligible.iterrows():
        if len(chosen) >= 3 or covered >= shortfall:
            break
        # stop is preferred over reduce when both are legal on the same event -
        # it fully frees the amount in one action, using fewer of the 3 slots.
        if _can_stop(ev):
            chosen.append(Change(kind="stop", event_id=ev["event_id"]))
            covered += ev["amount_home_ccy"]
        elif _can_reduce(ev):
            floor = (
                ev["minimum_allowed_amount"]
                if pd.notna(ev["minimum_allowed_amount"])
                else 0.0
            )
            new_amount = max(floor, ev["amount_home_ccy"] - (shortfall - covered))
            if new_amount < ev["amount_home_ccy"]:
                chosen.append(
                    Change(
                        kind="reduce_to", event_id=ev["event_id"], new_amount=new_amount
                    )
                )
                covered += ev["amount_home_ccy"] - new_amount

    if not chosen:
        return []

    if _amount_safe_to_pay_with_changes(ctx, chosen) < ctx.requested_amount:
        return []  # even the max allowed changes aren't enough - not affordable

    return chosen


# --------------------------------------------------------------------------- #
# Step 5: Plan selection / ranking
# --------------------------------------------------------------------------- #


def _installment_schedule(opt) -> list[tuple[date, float]]:
    n = int(opt["number_of_payments"])
    amount = float(opt["payment_amount_home_ccy"])
    freq = (
        int(opt["payment_frequency_days"])
        if pd.notna(opt["payment_frequency_days"])
        else 0
    )
    first = opt["first_payment_date"]
    return [(first + timedelta(days=freq * i), amount) for i in range(n)]


def _schedule_is_safe(
    ctx: FinancialContext, schedule: list[tuple[date, float]]
) -> bool:
    window_end = ctx.request_date + timedelta(days=FORECAST_DAYS)
    for check_date, _ in schedule:
        lookup_date = min(check_date, window_end)
        cumulative = sum(amt for d, amt in schedule if d <= check_date)
        headroom = ctx.running_min_from[lookup_date] - cumulative
        if headroom < ctx.minimum_balance_to_keep:
            return False
    return True


def _build_candidates(
    ctx: FinancialContext, earliest: date | None, changes: list[Change] | None
) -> list[PlanCandidate]:
    candidates: list[PlanCandidate] = []
    methods = set(ctx.payment_methods_allowed)
    needs_changes = bool(changes)
    safe_amount = (
        _amount_safe_to_pay_with_changes(ctx, changes)
        if needs_changes
        else ctx.amount_safe_to_pay
    )

    if "full_payment" in methods:
        if safe_amount >= ctx.requested_amount:
            candidates.append(
                PlanCandidate(
                    method=RecommendedPaymentMethod.FULL_PAYMENT,
                    status=(
                        AffordabilityStatus.AFFORDABLE_WITH_PLAN
                        if needs_changes
                        else AffordabilityStatus.AFFORDABLE_NOW
                    ),
                    plan=[(ctx.request_date, ctx.requested_amount)],
                    total_paid=ctx.requested_amount,
                    start=ctx.request_date,
                    n_payments=1,
                    option_id=None,
                    needs_changes=needs_changes,
                    changes=changes or [],
                )
            )
        elif not needs_changes and earliest and earliest <= ctx.desired_completion_date:
            candidates.append(
                PlanCandidate(
                    method=RecommendedPaymentMethod.WAIT,
                    status=AffordabilityStatus.AFFORDABLE_LATER,
                    plan=[(earliest, ctx.requested_amount)],
                    total_paid=ctx.requested_amount,
                    start=earliest,
                    n_payments=1,
                    option_id=None,
                )
            )

    if (
        not needs_changes
        and "partial_payment" in methods
        and ctx.allows_partial_payment
        and 0 < safe_amount < ctx.requested_amount
        and earliest
        and earliest <= ctx.desired_completion_date
    ):
        remainder = ctx.requested_amount - safe_amount
        candidates.append(
            PlanCandidate(
                method=RecommendedPaymentMethod.PARTIAL_PAYMENT,
                status=AffordabilityStatus.AFFORDABLE_WITH_PLAN,
                plan=[(ctx.request_date, safe_amount), (earliest, remainder)],
                total_paid=ctx.requested_amount,
                start=ctx.request_date,
                n_payments=2,
                option_id=None,
            )
        )

    if (
        not needs_changes
        and "installments" in methods
        and ctx.max_installment_months is not None
    ):
        options = ctx.payment_options[
            ctx.payment_options["payment_method"] == "installments"
        ]
        for _, opt in options.iterrows():
            freq = (
                opt["payment_frequency_days"]
                if pd.notna(opt["payment_frequency_days"])
                else 0
            )
            months = math.ceil((opt["number_of_payments"] * freq) / 30) if freq else 1
            if months > ctx.max_installment_months:
                continue

            schedule = _installment_schedule(opt)
            if not _schedule_is_safe(ctx, schedule):
                continue

            candidates.append(
                PlanCandidate(
                    method=RecommendedPaymentMethod.INSTALLMENTS,
                    status=AffordabilityStatus.AFFORDABLE_WITH_PLAN,
                    plan=schedule,
                    total_paid=float(opt["total_payable_amount_home_ccy"]),
                    start=schedule[0][0],
                    n_payments=len(schedule),
                    option_id=opt["payment_option_id"],
                )
            )

    return candidates


def _sort_key(ctx: FinancialContext):
    def key(c: PlanCandidate):
        completes_by_deadline = 0 if c.plan[-1][0] <= ctx.desired_completion_date else 1
        needs_changes = 1 if c.needs_changes else 0
        return (
            completes_by_deadline,
            needs_changes,
            c.total_paid,
            c.start,
            c.n_payments,
            c.option_id or "",
        )

    return key


def select_plan(ctx: FinancialContext) -> None:
    ctx.amount_safe_to_pay = compute_amount_safe_to_pay(ctx)
    earliest = compute_earliest_date_for_full_payment(ctx)
    ctx.earliest_date_for_full_payment = earliest.isoformat() if earliest else ""

    candidates = _build_candidates(ctx, earliest, changes=None)

    if not candidates:
        changes = propose_spending_changes(ctx)
        if changes:
            candidates = _build_candidates(ctx, earliest, changes=changes)

    if not candidates:
        ctx.affordability_status = AffordabilityStatus.NOT_AFFORDABLE
        ctx.recommended_payment_method = RecommendedPaymentMethod.NOT_RECOMMENDED
        ctx.payment_plan = NONE_VAL
        ctx.spending_changes_needed = NONE_VAL
        ctx.chosen_payment_option_id = None
        return

    best = min(candidates, key=_sort_key(ctx))
    ctx.recommended_payment_method = best.method
    ctx.affordability_status = best.status
    ctx.payment_plan = "|".join(
        f"{d.isoformat()}:{fmt_amount(a)}" for d, a in best.plan
    )
    ctx.spending_changes_needed = (
        "|".join(c.format() for c in best.changes)
        if best.needs_changes and best.changes
        else NONE_VAL
    )
    ctx.chosen_payment_option_id = best.option_id


def fmt_amount(amount: float) -> str:
    if float(amount).is_integer():
        return str(int(round(amount)))
    return f"{amount:.2f}"
