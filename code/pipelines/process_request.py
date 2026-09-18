# pipelines/process_request.py
# +---------------------------------------------------------------------------+
# |                        PROCESS REQUESTS PIPELINE                          |
# +---------------------------------------------------------------------------+


# Python Libraries
import inspect

# Local Libraries
from agents.request_agent import RequestAgent
from models.llm_model import LlmModel
from src.usage_tracker import UsageTracker
from src.utils import get_progress_bar, show_timer, start_timer


def run_process_request_pipeline(
    args: dict, dataset: dict
) -> tuple[list, UsageTracker]:
    m = inspect.currentframe().f_code.co_name.title().replace("_", " ").upper()
    print(f"\n🏃 {m}")

    llm_model = LlmModel()
    agent = RequestAgent(llm_model, dataset)

    output_rows = []
    requests_df = dataset.get("requests")
    total_requests = len(requests_df)

    print(f"# --- Processing {total_requests} requests --- #")

    request_idx = _check_id(args)

    if request_idx is not None:
        if request_idx >= 0 and request_idx < total_requests:
            output = agent.process_by_id(requests_df.iloc[request_idx])
            output_rows.append(output)
    else:
        for idx, csv_request in requests_df.iterrows():
            print(f"Row: {idx} ")
            start_time = start_timer()
            output = agent.process_by_id(csv_request)
            output_rows.append(output)
            print(get_progress_bar(idx, total_requests))
            show_timer(start_time)

    return output_rows, llm_model.usage


def _check_id(args: dict) -> int | None:
    id_key = next((k for k in args if k.startswith("id:")), None)
    return int(id_key.split(":", 1)[1]) if id_key else None
