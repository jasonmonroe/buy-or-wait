# tests/test_data_handler.py
from datetime import date

import pandas as pd
import src.data_handler as data_handler_module
from src.data_handler import DataHandler


def make_handler() -> DataHandler:
    """A DataHandler instance without running __init__ (which hits disk) -
    _coerce/save/_describe don't depend on __init__ having run."""
    return DataHandler.__new__(DataHandler)


# --------------------------------------------------------------------------- #
# _coerce
# --------------------------------------------------------------------------- #


def test_coerce_parses_date_columns():
    handler = make_handler()
    df = pd.DataFrame({"request_date": ["2024-01-15"], "desired_completion_date": ["2024-02-01"]})
    result = handler._coerce(df, "requests")
    assert result["request_date"].iloc[0] == date(2024, 1, 15)


def test_coerce_parses_datetime_columns():
    handler = make_handler()
    df = pd.DataFrame({"sent_at": ["2025-07-29T09:30:00Z"]})
    result = handler._coerce(df, "messages")
    assert result["sent_at"].iloc[0].year == 2025


def test_coerce_parses_numeric_columns():
    handler = make_handler()
    df = pd.DataFrame({"requested_amount": ["100.5"]})
    result = handler._coerce(df, "requests")
    assert result["requested_amount"].iloc[0] == 100.5


def test_coerce_numeric_blank_becomes_nan_not_zero():
    handler = make_handler()
    df = pd.DataFrame({"max_installment_months": [""]})
    result = handler._coerce(df, "financial_profiles")
    assert pd.isna(result["max_installment_months"].iloc[0])


def test_coerce_bool_column():
    handler = make_handler()
    df = pd.DataFrame({"allows_partial_payment": [True, False]})
    result = handler._coerce(df, "requests")
    assert result["allows_partial_payment"].tolist() == [True, False]


def test_coerce_list_columns_split_on_pipe_as_tuples():
    handler = make_handler()
    df = pd.DataFrame({"payment_methods_user_will_consider": ["full_payment|installments"]})
    result = handler._coerce(df, "financial_profiles")
    value = result["payment_methods_user_will_consider"].iloc[0]
    assert value == ("full_payment", "installments")
    assert isinstance(value, tuple)  # hashable - see test_describe below


def test_coerce_list_column_blank_becomes_empty_tuple():
    handler = make_handler()
    df = pd.DataFrame({"payment_methods_user_will_consider": [None]})
    result = handler._coerce(df, "financial_profiles")
    assert result["payment_methods_user_will_consider"].iloc[0] == ()


def test_coerce_ignores_columns_not_in_the_csv():
    handler = make_handler()
    df = pd.DataFrame({"unrelated_column": [1, 2]})
    result = handler._coerce(df, "requests")
    assert result["unrelated_column"].tolist() == [1, 2]


def test_coerce_ignores_unknown_csv_file():
    handler = make_handler()
    df = pd.DataFrame({"request_date": ["2024-01-01"]})
    result = handler._coerce(df, "not_a_known_file")
    assert result["request_date"].iloc[0] == "2024-01-01"  # left untouched


# --------------------------------------------------------------------------- #
# save
# --------------------------------------------------------------------------- #


def test_save_writes_list_of_dicts_to_csv(tmp_path, monkeypatch):
    handler = make_handler()
    output_file = tmp_path / "output.csv"
    monkeypatch.setattr(data_handler_module, "OUTPUT_FILE", str(output_file))

    handler.save([{"request_id": "request_1", "amount_safe_to_pay": 100.0}])

    written = pd.read_csv(output_file)
    assert written.iloc[0]["request_id"] == "request_1"
    assert written.iloc[0]["amount_safe_to_pay"] == 100.0


def test_save_accepts_a_dataframe_directly(tmp_path, monkeypatch):
    handler = make_handler()
    output_file = tmp_path / "output.csv"
    monkeypatch.setattr(data_handler_module, "OUTPUT_FILE", str(output_file))

    handler.save(pd.DataFrame([{"request_id": "request_2"}]))

    written = pd.read_csv(output_file)
    assert written.iloc[0]["request_id"] == "request_2"


# --------------------------------------------------------------------------- #
# load_image / _describe
# --------------------------------------------------------------------------- #


def _write_minimal_dataset(dataset_dir):
    """Writes a one-row CSV for every CSV_FILENAMES entry, just enough for
    DataHandler.__init__ to load without error."""
    dataset_dir.mkdir(parents=True, exist_ok=True)
    minimal_columns = {
        "exchange_rates": "rate_date,from_currency,to_currency,rate\n2024-01-01,USD,ZAR,18.0\n",
        "financial_events": (
            "event_id,user_id,event_type,description,category,direction,amount,currency,"
            "event_date,settlement_date,status,linked_event_id,flexibility,minimum_allowed_amount\n"
            "event_1,user_1,expense,,rent,debit,100,ZAR,2024-01-01,2024-01-01,settled,,fixed,\n"
        ),
        "financial_profiles": (
            "user_id,home_currency,current_available_balance,minimum_balance_to_keep,"
            "financial_priorities,expense_categories_to_protect,"
            "expense_categories_user_is_willing_to_reduce,expense_categories_user_is_willing_to_stop,"
            "payment_methods_user_will_consider,max_installment_months\n"
            "user_1,ZAR,1000,500,,,,,full_payment,\n"
        ),
        "images": "image_id,user_id,request_id,related_event_id\n",
        "messages": "message_id,user_id,request_id,related_event_id,sent_at,source_type,message_text\n",
        "output": "request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation\n",
        "request_payment_options": (
            "payment_option_id,request_id,payment_method,payment_amount,number_of_payments,"
            "first_payment_date,payment_frequency_days,financing_fee,total_payable_amount\n"
        ),
        "requests": (
            "request_id,user_id,request_date,request_type,requested_amount,desired_completion_date,"
            "allows_partial_payment,request_text\n"
            "request_1,user_1,2024-01-01,purchase,100,2024-02-01,True,Can I afford this?\n"
        ),
        "sample_requests": (
            "request_id,user_id,request_date,request_type,requested_amount,desired_completion_date,"
            "allows_partial_payment,request_text,amount_safe_to_pay,affordability_status,"
            "recommended_payment_method,payment_plan,earliest_date_for_full_payment,"
            "spending_changes_needed,decision_explanation\n"
        ),
    }
    for name, content in minimal_columns.items():
        (dataset_dir / f"{name}.csv").write_text(content)


def test_data_handler_init_loads_all_csvs(tmp_path, monkeypatch):
    dataset_dir = tmp_path / "dataset"
    _write_minimal_dataset(dataset_dir)
    monkeypatch.setattr(data_handler_module, "DATASET_DIR", str(dataset_dir) + "/")

    handler = DataHandler({})

    assert len(handler.requests) == 1
    assert handler.requests.iloc[0]["request_date"] == date(2024, 1, 1)
    assert handler.financial_profiles.iloc[0]["payment_methods_user_will_consider"] == ("full_payment",)


def test_data_handler_init_with_sample_flag_overrides_requests(tmp_path, monkeypatch):
    dataset_dir = tmp_path / "dataset"
    _write_minimal_dataset(dataset_dir)
    (dataset_dir / "sample_requests.csv").write_text(
        (dataset_dir / "sample_requests.csv").read_text()
        + "request_2,user_1,2024-01-01,purchase,50,2024-02-01,True,text,50,affordable_now,full_payment,2024-01-01:50,2024-01-01,none,ok\n"
    )
    monkeypatch.setattr(data_handler_module, "DATASET_DIR", str(dataset_dir) + "/")

    handler = DataHandler({"sample": True})

    assert handler.requests.iloc[0]["request_id"] == "request_2"


def test_data_handler_init_with_eda_flag_runs_describe(tmp_path, monkeypatch, capsys):
    dataset_dir = tmp_path / "dataset"
    _write_minimal_dataset(dataset_dir)
    monkeypatch.setattr(data_handler_module, "DATASET_DIR", str(dataset_dir) + "/")

    DataHandler({"eda": True})

    assert "DATA DESCRIPTION" in capsys.readouterr().out


def test_load_image_is_a_noop():
    handler = make_handler()
    assert handler.load_image() is None


def test_describe_handles_tuple_columns_without_crashing(monkeypatch, capsys):
    # Regression test: nunique()/value_counts() choke on unhashable `list`
    # columns - LIST_COLUMNS coercion must produce hashable tuples so --eda
    # doesn't crash on financial_profiles.
    handler = make_handler()
    monkeypatch.setattr(data_handler_module, "CSV_FILENAMES", ["financial_profiles"])
    handler.financial_profiles = pd.DataFrame(
        {
            "user_id": ["user_1", "user_2"],
            "payment_methods_user_will_consider": [("full_payment",), ("installments", "partial_payment")],
        }
    )

    handler._describe()  # must not raise

    assert "FINANCIAL_PROFILES" in capsys.readouterr().out.upper()
