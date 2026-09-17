# src/constants.py

import os

APP_NAME = os.environ("APP_NAME", None)
MODEL_NAME = os.environ("MODEL_NAME")
MODEL_API_KEY = os.environ("MODEL_API_KEY")
MODEL_API_URL = os.environ("MODEL_API_URL")

DATASET_DIR = "dataset"


# Fields


NONE_VAL = "none"


INPUT_COLS = [
    "request_id",
    "user_id",
    "request_date",
    "request_type",
    "requested_amount",
    "desired_completion_date",
    "allows_partial_payment",
    "request_text",
]

OUTPUT_COLS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]

AFFORDABILITY_STATUSES = [
    "affordable_now",
    "affordable_with_plan",
    "affordable_later",
    "not_affordable",
]

RECOMMENDED_PAYMENT_METHODS = [
    "full_payment",
    "partial_payment",
    "installments",
    "wait",
    "not_recommended",
]

REQUEST_TYPES = [
    "purchase",
    "travel",
    "education",
    "family_transfer",
    "debt_repayment",
    "investment",
    "housing",
    "emergency_expense",
    "other",
]
