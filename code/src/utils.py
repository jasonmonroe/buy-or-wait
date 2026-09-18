# src/utils.py
# +---------------------------------------------------------------------------+
# |                              UTILITIES                                    |
# +---------------------------------------------------------------------------+

import json
import time
import uuid
from enum import Enum

from src.constants import MSEC, SECS_IN_MIN


def gen_run_id() -> str:
    """Generates a unique ID for the current run."""
    return uuid.uuid4().hex[:5].upper()


def start_timer() -> float:
    """
    Start a timer
    """
    return time.time()


def get_time(start_time_float: float, end_time_float: float | None = None) -> str:

    if end_time_float is None:
        end_time_float = time.time()

    diff = abs(end_time_float - start_time_float)
    _, remainder = divmod(diff, SECS_IN_MIN * SECS_IN_MIN)
    minutes, seconds = divmod(remainder, SECS_IN_MIN)
    fractional_seconds = seconds - int(seconds)

    ms = fractional_seconds * MSEC
    return f"{int(minutes)}m {int(seconds)}s {int(ms)}ms"


def show_timer(start_time_int: float) -> None:
    print(f"⏱ Run Time: {get_time(start_time_int)}")


def get_progress_bar(idx: int, total: int) -> str:
    """
    Displays progress of claim analysis.

    :param idx:
    :param total:
    :return:
    """
    print()

    i_empty, i_full = "☑️ ", "✅️ "
    completion_pct = ((idx + 1) / total) * 100

    graphic = ""
    for i in range(total):
        graphic += i_full if i <= idx else i_empty

    return graphic + f"\t{completion_pct:.1f}%"


def pretty_dict(d: dict, indent: int = 4, stage: str = "") -> str:
    """Converts a dictionary into a pretty-printed, indented JSON string.

    Handles custom types like Enums safely.
    """
    pretty = json.dumps(
        d,
        indent=indent,
        default=lambda o: o.value if isinstance(o, Enum) else str(o),
    )

    return pretty


def format_date(date_str: str) -> str:
    return str(date_str.strftime("%Y-%m-%d"))
