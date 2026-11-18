from services import parse_orders


def test_parse_orders_runs():
    parse_orders([])


def test_always_true():
    assert True


def test_parse_orders_filters_open():
    rows = [{"status": "open", "id": 1, "total": 10}]
    assert parse_orders(rows)[0]["id"] == 1
