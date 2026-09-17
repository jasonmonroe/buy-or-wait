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

from evaluation.main import run_evaluation_pipeline
from pipelines.process_request import run_process_request_pipeline
from src.constants import APP_NAME, ARGS_LIST
from src.data_handler import DataHandler
from src.utils import gen_run_id, show_timer, start_timer


def run_main_pipeline(args: dict):
    m = inspect.currentframe().f_code.co_name.title().replace("_", " ").upper()
    print(f"🏃 {m}")

    print(args)

    # Data Handling
    data_handle = DataHandler(args)

    # Process Tickets
    output = run_process_request_pipeline(args, data_handle.__dict__)

    # Save Outputs
    # data_handle.save(output)

    # Evaluate
    if args.get("eval"):
        run_evaluation_pipeline()


def _parse_args(argv: list[str]) -> dict:
    """
    Parses CLI args against ARGS_LIST.

    A flag ending in ":" (e.g. "--id:") takes a value, passed as
    "--id:<value>" (no space). When present, its key is the whole
    "id:<value>" token and its value is True; when absent, the key falls
    back to the bare "id" and its value is False. Every other flag is a
    plain boolean, True if present in argv.
    """
    parsed = {}
    for arg in ARGS_LIST:
        if arg.endswith(":"):
            match = next((token for token in argv if token.startswith(arg)), None)
            if match is not None:
                parsed[match.strip("-")] = True
            else:
                parsed[arg.strip("-").rstrip(":")] = False
        else:
            key = arg.strip("-")
            parsed[key] = arg in argv

    return parsed


if __name__ == "__main__":
    warnings.filterwarnings("ignore")

    print(f"\n-----  🖥️ {APP_NAME} 🖥️  -----")

    prog_start_time = start_timer()
    run_id = gen_run_id()
    print(f"RUN ID: {run_id}")

    args = _parse_args(sys.argv[1:])
    run_main_pipeline(args)
    show_timer(prog_start_time)
