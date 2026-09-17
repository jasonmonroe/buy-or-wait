# agents/request_agent.py
# +---------------------------------------------------------------------------+
# |                             AGENT: REQUEST                                |
# +---------------------------------------------------------------------------+

# Python Libraries
import sys
from datetime import datetime
from pathlib import Path

import easyocr

# from numpy.random import f
import pandas as pd
import pytesseract
from PIL import Image
from src.constants import IMAGE_DIR

# Local Libraries
from src.enum import AffordabilityStatus, RecommendedPaymentMethod, RequestType
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
        self.amount_safe_to_pay = None
        self.affordability_status = None
        self.recommended_payment_method = None
        self.payment_plan = None
        self.earliest_date_for_full_payment = None
        self.spending_changes_needed = None
        self.decision_explanation = None

        self._data = data.copy()

    def _set_attrs(self, df: pd.Series):
        for key, value in df.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def process_by_id(self, df: dict):
        # self.data = data
        self._set_attrs(df)
        print(self.__dict__)

        # Update Filtered Data
        filtered_dataset = self.filter()
        filtered_with_rules_dataset = self.apply_rules(filtered_dataset)

        sys.exit(0)

        prompt_dataset = filtered_dataset | filtered_with_rules_dataset

        self.check_rules()

        # Now that you have all the prelimanary data build the final prompt.
        builder = PromptBuilder(prompt_dataset)

        return self.model.get_response(builder.prompt)

    def filter(self) -> dict:
        exchange_rates = self._data.get("exchange_rates")
        financial_events = self._data.get("financial_events")
        financial_profiles = self._data.get("financial_profiles")
        images = self._data.get("images")
        messages = self._data.get("messages")
        request_payment_options = self._data.get("request_payment_options")

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

        if not messages.empty:
            event_ids = messages["related_event_id"].dropna()
            event_ids = event_ids[event_ids != ""].tolist()

            if event_ids:
                financial_events = financial_events[
                    financial_events["event_id"].isin(event_ids)
                ]
                images = images[images["related_event_id"].isin(event_ids)]

        return {
            "exchange_rates": exchange_rates,
            "financial_events": financial_events,
            "financial_profiles": financial_profiles,
            "images": images,
            "messages": messages,
            "request_payment_options": request_payment_options,
        }

    def apply_rules(self, filtered_data: dict):
        """
        Applies business logic to populate all required attributes with
        accurate data from the filtered request and user profile before passing
        them to the Prompt Builder.
        """

        exchange_rates = filtered_data.get("exchange_rates")
        financial_events = filtered_data.get("financial_events")
        financial_profiles = filtered_data.get("financial_profiles")
        images = filtered_data.get("images")
        messages = filtered_data.get("messages")
        request_payment_options = filtered_data.get("request_payment_options")

        """
        'request_id': 'request_01',
        'user_id': 'user_01',
        'request_date': '2024-03-03',
        'request_type': 'purchase',
        'requested_amount': np.float64(25256.0),
        'desired_completion_date': '2024-03-20',
        'allows_partial_payment': np.True_,
        'request_text': "Would paying for the laptop today leave enough for my 
            regular expenses? The laptop I'm looking at is ZAR 25,256.",
        
        ----

        'amount_safe_to_pay': np.float64(25256.0),
        'affordability_status': 'affordable_now',
        'recommended_payment_method': 'full_payment',
        'payment_plan': '2024-03-03:25256',
        'earliest_date_for_full_payment': '2024-03-03',
        'spending_changes_needed': 'none',
        'decision_explanation': 'Pay ZAR 25,256 today. This leaves at least ZAR 
            18,000 available over the next 90 days.'
        """

        # When a financial event has a blank amount use its event_id to find
        # related event id in images, then extract that amount from that image.

        financial_event_date = financial_events["event_date"]

        financial_event_amount = self.get_amount(filtered_data)

        to_currency = self.calc_currency(
            financial_events["currency"], financial_event_date, exchange_rates
        )

        # Rules for output columns

    def get_amount_safe_to_pay(self) -> float:
        # The maximum amount theuser can safely pay today.

        self.amount_safe_to_pay = None

    def get_affordability_status(self) -> str:
        """
        Whether the reqeust is affordable now, affordable with a plan,
        affordable later, or not affordable.
        """
        self.affordability_status = None

    def get_recommended_payment_method(self) -> str:
        """
        The safest way to proceed.  Uses Enum value determined by logic.
        """
        self.recommended_payment_method = None

    def get_payment_plan(self) -> datetime:

        payment_plan = None

        self.payment_plan = None

    def get_earliest_date_for_full_payment(self) -> str:
        """The earliest safe date for pyaing the full amount."""
        self.earliest_date_for_full_payment = None

    def get_spending_changes_needed(self) -> str:
        """Flexible expenses that must be stopped or reduced."""
        self.spending_changes_needed = None

    def get_decision_explanation(self) -> str:
        """A short explanation supporting the recommendation."""
        self.decision_explanation = None

    def get_amount(self, data) -> float:
        # Get Financial Event amount

        financial_events = data.get("financial_events")
        amount = financial_events["amount"].item()

        if not amount:
            image_data = None
            images = data.get("images")

            if not images.empty:
                image_text = self.extract_from_image(images)

            # Get amount

        return amount

    def get_output() -> dict:

        return {}

    def check_rules(self) -> bool:
        """Check rules of each attribute to see if the data is correct."""

        for key, value in self.__dict__:
            if key == "_data":
                continue
            if not value:
                return False

        return True

    def is_of_request_type(self, request_type: str) -> bool:
        return request_type in [item.value for item in RequestType]

    def is_of_affordability_status(self, status: str) -> bool:
        return status in [item.value for item in AffordabilityStatus]

    def is_of_recommended_payment_method(self, pay_method: str) -> bool:
        return pay_method in [item.value for item in RecommendedPaymentMethod]

    def calc_currency(
        self, home_currency: str, event_date: str, exchange_rates
    ) -> float:
        rates = exchange_rates[
            (exchange_rates["from_currency"] == home_currency)
            & (exchange_rates["event_date"] == event_date)
        ]

        return rates["to_currency"].items()

    def extract_from_image(self, images):
        image_id = images["image_id"].iloc[0]
        image_path = Path(f"{IMAGE_DIR}{image_id}")
        # Open and load the image
        # img = Image.open(image_path)

        # Show image details
        # print(img.format, img.size, img.mode)

        # Display the image
        # img.show()

        # i  # mg_path = Path("document.jpg")

        # Extract text directly from the image
        reader = easyocr.Reader(["en"])
        results = reader.readtext(str(image_path))
        text = pytesseract.image_to_string(Image.open(image_path))

        return text
