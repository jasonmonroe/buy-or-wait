# src/constants.py
# +---------------------------------------------------------------------------+
# |                               CONSTANTS                                   |
# +---------------------------------------------------------------------------+

import os

APP_NAME = os.environ("APP_NAME", None)
MODEL_NAME = os.environ("MODEL_NAME")
MODEL_API_KEY = os.environ("MODEL_API_KEY")
MODEL_API_URL = os.environ("MODEL_API_URL")

ARGS_LIST = [
    "--eda",
    "--eval",
    "--sample",
    "--id:",  # request id
]

SECS_IN_MIN = 60
MSEC = 1000

DATASET_DIR = "dataset/"


# Fields

NONE_VAL = "none"

DATASET_FILES = [
    "exchange_rates",
    "financial_events",
    "financial_profiles",
    # "images",
    "messages",
    "output",
    "request_payment_options",
    "requests",
]

IMAGE_DIR = f"{DATASET_DIR}/media/"

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
