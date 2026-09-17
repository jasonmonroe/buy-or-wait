# agents/request_agent.py
# +---------------------------------------------------------------------------+
# |                             AGENT: REQUEST                                |
# +---------------------------------------------------------------------------+


class RequestAgent:
    def __init__(self, model):
        self.model = model

        self.request_id = None
        self.user_id = None
        self.request_date = None
        self.request_type = None
        self.requested_amount = None
        self.desired_completion_date = None
        self.allows_partial_payment = None
        self.request_text = None

    def _set_attrs(self, df):
        for key, value in df.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def process_by_id(self, df: dict):
        self._set_attrs(df)
        print(self.__dict__)

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
