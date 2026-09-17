# pipelines/process_request.py
# +---------------------------------------------------------------------------+
# |                        PROCESS REQUESTS PIPELINE                          |
# +---------------------------------------------------------------------------+

import inspect

from agents.request_agent import RequestAgent
from models.llm_model import LlmModel


def run_process_request_pipeline(args: dict, dataset: dict) -> dict:
    m = inspect.currentframe().f_code.co_name.title().replace("_", " ").upper()
    print(f"🏃 {m}")

    # print(dataset)

    output_rows = []
    requests_df = dataset.get("requests")

    llm_model = LlmModel()
    agent = RequestAgent(llm_model)

    request_idx = _check_id(args)

    if request_idx:
        request_idx = int(request_idx)
        if request_idx > 0 and request_idx < len(requests_df):
            print(f"request_idx={request_idx}")
            row = requests_df.iloc[request_idx]
            output = agent.process_by_id(row)
            output_rows.append(output)
    else:
        for csv_request in requests_df:
            output = agent.process_by_id(csv_request)
            output_rows.append(output)

    return output_rows


def _check_id(args: dict) -> str | None:
    id_key = next((k for k in args if k.startswith("id:")), None)
    return id_key.split(":", 1)[1] if id_key else None
