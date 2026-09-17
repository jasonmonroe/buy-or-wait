# evaluation/main.py
# +---------------------------------------------------------------------------+
# |                          EVALUTATION PIPELINE                             |
# +---------------------------------------------------------------------------+

import inspect


def run_evaluation_pipeline():
    m = inspect.currentframe().f_code.co_name.title().replace("_", " ").upper()
    print(f"🏃 {m}")
