# pipelines/process_request.py
# +---------------------------------------------------------------------------+
# |                        PROCESS REQUESTS PIPELINE                          |
# +---------------------------------------------------------------------------+

import inspect


def run_process_request_pipeline(args: dict, dataset: dict) -> dict:
    m = inspect.f_code.co_name.title().replace("_", " ").upper()
    print(f"🏃 {m}")
