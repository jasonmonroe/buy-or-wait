# src/constants.py
# +---------------------------------------------------------------------------+
# |                               CONSTANTS                                   |
# +---------------------------------------------------------------------------+

import os

APP_NAME = os.environ.get("APP_NAME", None)
MODEL_NAME = os.environ.get("MODEL_NAME")
MODEL_API_KEY = os.environ.get("MODEL_API_KEY")
MODEL_API_URL = os.environ.get("MODEL_API_URL")

ARGS_LIST = [
    "--eda",
    "--eval",
    "--sample",
    "--id:",  # request id
]

PAUSE_TIMER = 1.5
RATE_LIMIT_PAUSE_TIMER = 30
RATE_LIMIT_RETRIES = 3

MAX_TOKENS = 4096
MSEC = 1000
SECS_IN_MIN = 60

DATASET_DIR = "dataset/"
OUTPUT_FILE = f"{DATASET_DIR}output.csv"


CSV_FILENAMES = [
    "exchange_rates",
    "financial_events",
    "financial_profiles",
    "images",
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
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
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

NONE_VAL = "none"

# Prompts
SYS_INSTR_PROMPT = (
    "You are a Machine Learning expert with extensive knowledge in multimodal ",
    "prompts for an AI-powered system that decides whether a user can sarely ",
    "afford a requested expense.\n",
    "For every request, you must decide whether the user should pay in full, ",
    "pay partially, use installments, wait, or not proceed.\n\n",
    "## CRITICAL EXECUTION RULES: \n",
    "1. The data is provided in XML. It consists of ",
    f"{''.join(', ', CSV_FILENAMES)}  and media attachments (if available) ",
    "together to make a financial determination.\n",
)


USER_PROMPT = """

## </> XML REQUEST DATA

{request_xml}

## TASK INSTRUCTIONS
 


### CRITICAL OUTPUT REQUIREMENT:
Return your response as a valid JSON object wrapped inside a markdown code block (```json ... ```). 

**The JSON structure below is a template/blueprint.** Do not use the sample IDs or values from it. Populate all keys using the *actual data, IDs, and decisions* derived from the prompt context above:
{{
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
}}

**IMPORTANT RULES:**
1. JSON object keys must be in the exact order shown above. Do not deviate!
2. Replace all placeholder values with real data from the current context.

""".strip()
