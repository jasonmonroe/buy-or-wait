# src/prompt_builder.py
# +---------------------------------------------------------------------------+
# |                            PROMPT BUILDER                                 |
# +---------------------------------------------------------------------------+

import json

from src.constants import USER_PROMPT


class PromptBuilder:
    """Builds the LLM prompt from the already-computed decision payload
    (see rules_engine.py). The LLM never receives raw filtered DataFrames -
    only the small set of final numbers/dates it needs to phrase
    `decision_explanation` around."""

    def __init__(self, payload: dict):
        self.prompt = self._build(payload)

    def _build(self, payload: dict) -> str:
        request_json = json.dumps(payload, indent=2, default=str)
        return USER_PROMPT.format(request_json=request_json)
