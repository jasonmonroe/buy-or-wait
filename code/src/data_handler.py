# src/data_handler.py
# +---------------------------------------------------------------------------+
# |                               DATA HANDLER                                |
# +---------------------------------------------------------------------------+

# Python Libraries

# Local Libraries
from code.src.constants import DATASET_DIR, DATASET_FILES
from code.src.utils import pretty_dict
from pathlib import Path

# Vendor Libraries
import pandas as pd


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

        if args.get("eda"):
            self._describe()

    def _load_data(self, use_sample: bool):

        for csv_file in DATASET_FILES:
            setattr(self, csv_file, self._path(csv_file))

        # Override request with sample request
        if use_sample:
            self.requests = self._path("sample_requests")

    def _path(self, csv_file: str) -> pd.DataFrame:
        filepath = f"{DATASET_DIR}/{csv_file}.csv"
        print(f"\n 📁 Loading {filepath}")
        return pd.read_csv(Path(filepath))

    def _load_images(self):
        image_path = Path(f"{DATASET_DIR}")
        if image_path.exists():
            pass

    def _describe(self):
        print("\n# --- 📚 Data Description 📚 --- #".upper())

        for csv_file in DATASET_FILES:
            print(f"Csv File: {csv_file}".upper())

            csv_df = getattr(self, csv_file)

            print(f"Number of rows: {len(csv_df)}")
            print(f"\n 🗂️ Number of columns: {len(csv_df.columns)}")
            print(f"\n 🗂️ Columns:\n{pretty_dict(csv_df.columns.tolist())}")
            print(f"\n 🗂️ Data types:\n{pretty_dict(csv_df.dtypes.to_dict())}")
            print(
                f"\n 🗂️ Missing values:\n{pretty_dict(csv_df.isnull().sum().to_dict())}"
            )
            print(f"\n 🗂️ Unique values:\n{pretty_dict(csv_df.nunique().to_dict())}")

            # Convert Tuples from value_counts() into string keys for JSON serialization
            val_counts_dict = {
                str(k): v for k, v in csv_df.value_counts().to_dict().items()
            }
            print(f"\n 🗂️ Value counts:\n{pretty_dict(val_counts_dict)}")

            print(
                f"\n 🗂️ Descriptive statistics:\n{pretty_dict(csv_df.describe(include='all').to_dict())}"
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
