"""
code/main.py

+-----------------------------------------------------------------------------+
|                                 MAIN PIPELINE                               |
+-----------------------------------------------------------------------------+

+-------------------------------- BUY OR WAIT? -------------------------------+

Build an AI-powered financial agent that decides whether a user can safely
afford a requested expense.

A user may ask: "Can I afford this laptop?"

Answering well takes more than the current balance. The agent must account for
recurring expenses, pending payments, essential spending, confirmed income,
available payment options, and relevant details buried in messages and images.

For every request, the agent decides whether the user should pay in full, pay
partially, use installments, wait, or not proceed. The recommendation must be
personalized: two users with the same balance can deserve different answers
based on their commitments, priorities, payment preferences, and willingness to
adjust flexible expenses.

A recommendation is safe only if the user can complete the full payment plan,
cover essential expenses, and stay above their preferred minimum balance
throughout the forecast period.
"""

__author__ = "Jason Monroe (jason@jasonmonroe.com)"
__copyright__ = "Copyright © 2011-2026 Monroe Labs Co"
__date__ = "2026-09-17"
__version__ = "1.0.0"

import inspect
import sys
import warnings
from code.evaluation.main import run_evaluation_pipeline
from code.pipelines.process_request import run_process_request_pipeline
from code.src.constants import APP_NAME, ARGS_LIST
from code.src.data_handler import DataHandler
from code.src.utils import gen_run_id, show_timer, start_timer


def run_main_pipeline(args: dict):
    m = inspect.f_code.co_name.title().replace("_", " ").upper()
    print(f"🏃 {m}")

    # Data Handling
    data_handle = DataHandler(args)

    # Process Tickets
    output = run_process_request_pipeline(args, data_handle.__dict__)

    # Save Outputs

    # Evaluate
    if args.get("eval"):
        run_evaluation_pipeline()


def _parse_args(command_line_str: str) -> dict:
    return {arg.strip("--"): (arg in command_line_str) for arg in ARGS_LIST}


if __name__ == "__main__":
    warnings.filterwarnings("ignore")

    print(f"\n-----  🖥️ {APP_NAME} 🖥️  -----")

    prog_start_time = start_timer()
    run_id = gen_run_id()
    print(f"RUN ID: {run_id}")

    args = _parse_args(sys.argv[1:])
    run_main_pipeline(args)
    show_timer(prog_start_time)
