# agents/request_agent.py
# +---------------------------------------------------------------------------+
# |                             AGENT: REQUEST                                |
# +---------------------------------------------------------------------------+

import sys

import pandas as pd

# Local Libraries
from src.prompt_builder import PromptBuilder


class RequestAgent:
    def __init__(self, model, data):
        self.model = model

        self.request_id = None
        self.user_id = None
        self.request_date = None
        self.request_type = None
        self.requested_amount = None
        self.desired_completion_date = None
        self.allows_partial_payment = None
        self.request_text = None
        self.data = data

    def _set_attrs(self, df: pd.Series):
        for key, value in df.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def process_by_id(self, df: dict):
        # self.data = data
        self._set_attrs(df)
        print(self.__dict__)

        # Update Filtered Data
        self.data = self.filter()
        print(self.data)
        sys.exit(0)

        prompt_dataset = {}

        # Now that you have all the prelimanary data build the final prompt.
        builder = PromptBuilder(prompt_dataset)

        return self.model.get_response(builder.prompt)

    def filter(self) -> dict:
        exchange_rates = self.data.get("exchange_rates")
        financial_events = self.data.get("financial_events")
        financial_profiles = self.data.get("financial_profiles")
        images = self.data.get("images")
        messages = self.data.get("messages")
        request_payment_options = self.data.get("request_payment_options")

        # Filter the rows by request id
        images = images[images["request_id"] == self.request_id]
        messages = messages[messages["request_id"] == self.request_id]
        request_payment_options = request_payment_options[
            request_payment_options["request_id"] == self.request_id
        ]

        # Next, filter the rows by user_id
        # exchange_rates = exchange_rates[exchange_rates["user_id"] == self.user_id]
        financial_events = financial_events[financial_events["user_id"] == self.user_id]
        financial_profiles = financial_profiles[
            financial_profiles["user_id"] == self.user_id
        ]
        messages = messages[messages["user_id"] == self.user_id]

        # Next filter by events
        event_id = messages["related_event_id"].item()
        financial_events = financial_events[financial_events["event_id"] == event_id]
        images = images[images["related_event_id"] == event_id]

        return {
            "exchange_rates": exchange_rates,
            "financial_events": financial_events,
            "financial_profiles": financial_profiles,
            "images": images,
            "messages": messages,
            "request_payment_options": request_payment_options,
        }

    def apply_rules(self):

        # Rules for

        # Rules for output columns

        pass

    def get_output() -> dict:

        return {}

    def check_rules(self) -> bool:
        pass

    def is_of_request_type(self) -> bool:
        pass

    def is_of_affordability_status(self) -> bool:
        pass

    def is_of_recommended_payment_method(self) -> bool:
        pass

    def filter_by_rates(self, home_currency: str):
        pass
