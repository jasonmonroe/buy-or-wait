# agents/request_agent.py
# +---------------------------------------------------------------------------+
# |                             AGENT: REQUEST                                |
# +---------------------------------------------------------------------------+

# Python Libraries
import re
from pathlib import Path

# Vendor Libraries
import pandas as pd
import pytesseract
from PIL import Image

# Local Libraries
from src import rules_engine
from src.constants import IMAGE_DIR, MODEL_API_KEY
from src.enum import AffordabilityStatus, RecommendedPaymentMethod
from src.prompt_builder import PromptBuilder

_AMOUNT_PATTERN = re.compile(r"[\d][\d,]*\.?\d*")


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

        self._ctx = None
        self._data = data.copy()

    def _set_attrs(self, df: pd.Series):
        for key, value in df.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def process_by_id(self, df: pd.Series) -> dict:
        self._set_attrs(df)

        filtered_dataset = self.filter()
        self.apply_rules(filtered_dataset)
        self.get_decision_explanation()

        if not self.check_rules():
            print(f"⚠️  check_rules() failed for {self.request_id}")

        return self.get_output()

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

        # Next, filter the rows by user_id. `financial_events` keeps the
        # user's FULL history (not just events a message happens to
        # reference) - the 90-day forecast and recurrence detection need the
        # whole picture. `related_event_id` is only used to attach message
        # evidence to a specific event later, never to narrow the working
        # event set.
        financial_events = financial_events[financial_events["user_id"] == self.user_id]
        financial_profiles = financial_profiles[
            financial_profiles["user_id"] == self.user_id
        ]
        messages = messages[messages["user_id"] == self.user_id]

        return {
            "exchange_rates": exchange_rates,
            "financial_events": financial_events,
            "financial_profiles": financial_profiles,
            "images": images,
            "messages": messages,
            "request_payment_options": request_payment_options,
        }

    def apply_rules(self, filtered_data: dict) -> dict:
        """
        Runs the deterministic rules engine (src/rules_engine.py) to compute
        all financial-decision attributes from the filtered request and user
        profile. The LLM is never asked to do this arithmetic - it only
        phrases `decision_explanation` afterward, in get_decision_explanation().
        """
        self._ctx = rules_engine.compute(
            self, filtered_data, ocr_fn=self.get_amount_from_image
        )

        self.get_amount_safe_to_pay()
        self.get_affordability_status()
        self.get_recommended_payment_method()
        self.get_payment_plan()
        self.get_earliest_date_for_full_payment()
        self.get_spending_changes_needed()

        return {
            "amount_safe_to_pay": self.amount_safe_to_pay,
            "affordability_status": self.affordability_status,
            "recommended_payment_method": self.recommended_payment_method,
            "payment_plan": self.payment_plan,
            "earliest_date_for_full_payment": self.earliest_date_for_full_payment,
            "spending_changes_needed": self.spending_changes_needed,
        }

    def get_amount_safe_to_pay(self) -> float:
        self.amount_safe_to_pay = self._ctx.amount_safe_to_pay
        return self.amount_safe_to_pay

    def get_affordability_status(self) -> str:
        self.affordability_status = self._ctx.affordability_status
        return self.affordability_status

    def get_recommended_payment_method(self) -> str:
        self.recommended_payment_method = self._ctx.recommended_payment_method
        return self.recommended_payment_method

    def get_payment_plan(self) -> str:
        self.payment_plan = self._ctx.payment_plan
        return self.payment_plan

    def get_earliest_date_for_full_payment(self) -> str:
        self.earliest_date_for_full_payment = self._ctx.earliest_date_for_full_payment
        return self.earliest_date_for_full_payment

    def get_spending_changes_needed(self) -> str:
        self.spending_changes_needed = self._ctx.spending_changes_needed
        return self.spending_changes_needed

    def get_decision_explanation(self) -> str:
        """The one place the LLM is used: phrasing a short explanation around
        the already-computed numbers. Falls back to a Python template if no
        model API key is configured, so the engine stays testable offline."""
        if not MODEL_API_KEY:
            self.decision_explanation = self._fallback_explanation()
            return self.decision_explanation

        builder = PromptBuilder(self._build_explanation_payload())
        response = self.model.get_response(builder.prompt) or {}
        explanation = (
            response.get("decision_explanation") if isinstance(response, dict) else None
        )

        self.decision_explanation = explanation or self._fallback_explanation()
        return self.decision_explanation

    def _build_explanation_payload(self) -> dict:
        return {
            "request_id": self.request_id,
            "home_currency": self._ctx.home_currency,
            "requested_amount": self.requested_amount,
            "minimum_balance_to_keep": self._ctx.minimum_balance_to_keep,
            "amount_safe_to_pay": self.amount_safe_to_pay,
            "affordability_status": self.affordability_status,
            "recommended_payment_method": self.recommended_payment_method,
            "payment_plan": self.payment_plan,
            "earliest_date_for_full_payment": self.earliest_date_for_full_payment,
            "spending_changes_needed": self.spending_changes_needed,
        }

    def _fallback_explanation(self) -> str:
        currency = self._ctx.home_currency
        minimum = self._ctx.minimum_balance_to_keep

        if self.recommended_payment_method == RecommendedPaymentMethod.NOT_RECOMMENDED:
            return (
                f"Do not proceed with this request. None of the available options "
                f"keeps the {currency} {minimum:,.0f} minimum protected."
            )

        return (
            f"{self.recommended_payment_method.replace('_', ' ').title()}: "
            f"{self.payment_plan}. Keeps at least {currency} {minimum:,.0f} available."
        )

    def get_output(self) -> dict:
        return {
            "request_id": self.request_id,
            "amount_safe_to_pay": self.amount_safe_to_pay,
            "affordability_status": self.affordability_status,
            "recommended_payment_method": self.recommended_payment_method,
            "payment_plan": self.payment_plan,
            "earliest_date_for_full_payment": self.earliest_date_for_full_payment,
            "spending_changes_needed": self.spending_changes_needed,
            "decision_explanation": self.decision_explanation,
        }

    def check_rules(self) -> bool:
        """Check rules of each attribute to see if the data is correct."""
        skip_keys = {"_data", "_ctx", "earliest_date_for_full_payment"}

        for key, value in self.__dict__.items():
            if key in skip_keys:
                continue
            if value is None:
                return False

        if not (0 <= self.amount_safe_to_pay <= self.requested_amount):
            return False

        # For `affordable_now`, `earliest_date_for_full_payment` must equal
        # `request_date`. Leave it empty when the full amount is not
        # expected to become safe within the forecast period.
        if (
            self.affordability_status == AffordabilityStatus.AFFORDABLE_NOW
            and self.earliest_date_for_full_payment != self.request_date.isoformat()
        ):
            return False

        return True

    def get_amount_from_image(self, images: pd.DataFrame) -> float | None:
        """Used by rules_engine.resolve_events() to fill a blank financial-
        event amount by OCR'ing its linked image (never treat blank as 0)."""
        if images.empty:
            return None

        text = self.extract_from_image(images)
        return self._parse_amount_from_text(text)

    def extract_from_image(self, images: pd.DataFrame) -> str:
        image_id = images["image_id"].iloc[0]
        image_path = Path(f"{IMAGE_DIR}{image_id}.png")

        if not image_path.exists():
            return ""

        return pytesseract.image_to_string(Image.open(image_path))

    def _parse_amount_from_text(self, text: str) -> float | None:
        candidates = []
        for match in _AMOUNT_PATTERN.finditer(text or ""):
            raw = match.group().replace(",", "")
            try:
                value = float(raw)
            except ValueError:
                continue
            if value > 0:
                candidates.append(value)

        return max(candidates) if candidates else None
