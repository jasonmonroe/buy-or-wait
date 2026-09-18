# src/data_handler.py
# +---------------------------------------------------------------------------+
# |                               DATA HANDLER                                |
# +---------------------------------------------------------------------------+

# Python Libraries

# Local Libraries
from pathlib import Path

# Vendor Libraries
import pandas as pd
from src.constants import CSV_FILENAMES, DATASET_DIR, OUTPUT_FILE
from src.utils import pretty_dict

DATE_COLUMNS = {
    "requests": ["request_date", "desired_completion_date"],
    "sample_requests": ["request_date", "desired_completion_date"],
    "financial_events": ["event_date", "settlement_date"],
    "exchange_rates": ["rate_date"],
    "request_payment_options": ["first_payment_date"],
}

NUMERIC_COLUMNS = {
    "requests": ["requested_amount"],
    "sample_requests": ["requested_amount", "amount_safe_to_pay"],
    "financial_events": ["amount", "minimum_allowed_amount"],
    "exchange_rates": ["rate"],
    "request_payment_options": [
        "payment_amount",
        "number_of_payments",
        "payment_frequency_days",
        "financing_fee",
        "total_payable_amount",
    ],
    "financial_profiles": [
        "current_available_balance",
        "minimum_balance_to_keep",
        "max_installment_months",
    ],
}

BOOL_COLUMNS = {
    "requests": ["allows_partial_payment"],
    "sample_requests": ["allows_partial_payment"],
}

DATETIME_COLUMNS = {
    "messages": ["sent_at"],
}

LIST_COLUMNS = {
    "financial_profiles": [
        "financial_priorities",
        "expense_categories_to_protect",
        "expense_categories_user_is_willing_to_reduce",
        "expense_categories_user_is_willing_to_stop",
        "payment_methods_user_will_consider",
    ],
}


class DataHandler:
    def __init__(self, args: dict):
        self.exchange_rates = None
        self.financial_events = None
        self.financial_profiles = None
        self.images = None
        self.messages = None
        self.output = None
        self.request_payment_options = None
        self.requests = None

        self._load_data(args.get("sample"))
        # self._load_images()

        if args.get("eda"):
            self._describe()

    def _load_data(self, use_sample: bool):

        for csv_file in CSV_FILENAMES:
            setattr(self, csv_file, self._path(csv_file))

        # Override request with sample request
        if use_sample:
            print("\nOverriding requests...")
            self.requests = self._path("sample_requests")

    def _path(self, csv_file: str) -> pd.DataFrame:
        filepath = f"{DATASET_DIR}{csv_file}.csv"
        print(f"📁 Loading {filepath}")
        df = pd.read_csv(Path(filepath))
        return self._coerce(df, csv_file)

    def _coerce(self, df: pd.DataFrame, csv_file: str) -> pd.DataFrame:
        """Parses dates/numbers/lists once at load time so downstream code
        works with real `date`/`float`/`list` values instead of raw strings."""

        for col in DATE_COLUMNS.get(csv_file, []):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

        for col in DATETIME_COLUMNS.get(csv_file, []):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        for col in NUMERIC_COLUMNS.get(csv_file, []):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        for col in BOOL_COLUMNS.get(csv_file, []):
            if col in df.columns:
                df[col] = df[col].astype(bool)

        for col in LIST_COLUMNS.get(csv_file, []):
            if col in df.columns:
                # Tuples, not lists: hashable, so nunique()/value_counts() in
                # _describe() (--eda) don't choke on them, and every downstream
                # use (membership checks, set(), .isin()) works identically.
                df[col] = df[col].apply(
                    lambda v: tuple(v.split("|")) if isinstance(v, str) and v else ()
                )

        return df

    def load_image(self):
        pass

    def save(self, output_rows: dict):
        df = pd.DataFrame(output_rows) if isinstance(output_rows, list) else output_rows

        # Now call .to_csv() on the DataFrame
        output_file = Path(OUTPUT_FILE)
        print(f"Saving Data to {output_file}")

        df.to_csv(output_file, index=False)

    def _describe(self):
        print("\n# --- 📚 Data Description 📚 --- #".upper())

        for csv_file in CSV_FILENAMES:
            print(f"Csv File: {csv_file}".upper())

            csv_df = getattr(self, csv_file)

            print(f"🗂️ Row Count: {len(csv_df)}")
            print(f"\n🗂️ Column Count: {len(csv_df.columns)}")
            print(f"\n🗂️ Columns:\n{pretty_dict(csv_df.columns.tolist())}")
            print(f"\n🗂️ Data Types:\n{pretty_dict(csv_df.dtypes.to_dict())}")
            print(
                f"\n🗂️ Missing Values:\n{pretty_dict(csv_df.isnull().sum().to_dict())}"
            )
            print(f"\n🗂️ Unique Values:\n{pretty_dict(csv_df.nunique().to_dict())}")

            # Convert Tuples from value_counts() into string keys for JSON serialization
            val_counts_dict = {
                str(k): v for k, v in csv_df.value_counts().to_dict().items()
            }
            print(f"\n🗂️ Value Counts:\n{pretty_dict(val_counts_dict)}")

            print(
                f"\n🗂️ Descriptive statistics:\n{pretty_dict(csv_df.describe(include='all').to_dict())}"
            )

            print("\n# --- Data Head --- #")
            print(csv_df.head())

            print("\n# --- Data Info --- #")
            print(csv_df.info())

            print("\n# --- Data Describe --- #")
            print(csv_df.describe(include="all"))

            print("\n# --- Data Columns --- #")
            print(csv_df.columns.tolist())

            print("\n# --- Data Index --- #")
            print(csv_df.index)

            print("\n# --- Data Values --- #")
            print(csv_df.values)

            print("\n# --- Data Shape --- #")
            print(csv_df.shape)

            print("\n# --- Data Dtypes --- #")
            print(csv_df.dtypes)
