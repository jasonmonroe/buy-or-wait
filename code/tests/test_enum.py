# tests/test_enum.py
from src.enum import AffordabilityStatus, RecommendedPaymentMethod, RequestType


def test_affordability_status_values_match_spec():
    assert {s.value for s in AffordabilityStatus} == {
        "affordable_now",
        "affordable_with_plan",
        "affordable_later",
        "not_affordable",
    }


def test_recommended_payment_method_values_match_spec():
    assert {m.value for m in RecommendedPaymentMethod} == {
        "full_payment",
        "partial_payment",
        "installments",
        "wait",
        "not_recommended",
    }


def test_request_type_values_match_spec():
    assert {t.value for t in RequestType} == {
        "purchase",
        "travel",
        "education",
        "family_transfer",
        "debt_repayment",
        "investment",
        "housing",
        "emergency_expense",
        "other",
    }


def test_strenum_compares_equal_to_plain_string():
    assert AffordabilityStatus.AFFORDABLE_NOW == "affordable_now"
    assert str(AffordabilityStatus.AFFORDABLE_NOW) == "affordable_now"
