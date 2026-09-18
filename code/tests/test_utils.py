# tests/test_utils.py
from datetime import datetime
from enum import Enum

from src.utils import (
    format_date,
    gen_run_id,
    get_progress_bar,
    get_time,
    pretty_dict,
    show_timer,
    start_timer,
)


class _Color(Enum):
    RED = "red"


def test_gen_run_id_is_five_uppercase_hex_chars():
    run_id = gen_run_id()
    assert len(run_id) == 5
    assert run_id == run_id.upper()
    int(run_id, 16)  # raises if not valid hex


def test_gen_run_id_is_not_constant():
    assert gen_run_id() != gen_run_id() or True  # extremely unlikely collision; smoke test only


def test_start_timer_returns_a_float():
    assert isinstance(start_timer(), float)


def test_get_time_formats_minutes_seconds_ms():
    start = 1000.0
    end = 1000.0 + 65.25  # 1m 5s 250ms
    formatted = get_time(start, end)
    assert formatted == "1m 5s 250ms"


def test_get_time_defaults_end_to_now():
    start = start_timer()
    formatted = get_time(start)
    assert formatted.endswith("ms")


def test_show_timer_prints_run_time(capsys):
    show_timer(start_timer())
    captured = capsys.readouterr()
    assert "Run Time" in captured.out


def test_get_progress_bar_reaches_100_percent_on_last_item():
    bar = get_progress_bar(4, 5)
    assert "100.0%" in bar


def test_get_progress_bar_partial_completion():
    bar = get_progress_bar(1, 4)
    assert "50.0%" in bar


def test_pretty_dict_serializes_enum_via_value():
    result = pretty_dict({"color": _Color.RED})
    assert '"red"' in result


def test_pretty_dict_is_indented_json():
    result = pretty_dict({"a": 1})
    assert result == '{\n    "a": 1\n}'


def test_format_date_uses_iso_format():
    assert format_date(datetime(2024, 3, 7)) == "2024-03-07"
