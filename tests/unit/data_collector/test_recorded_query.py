from __future__ import annotations

import json

from xtr_orm.data_collector import RecordedQuery


def test_a_query_is_kept_as_a_mapping_of_every_field() -> None:
    query = RecordedQuery(
        connection="default",
        statement="select 1",
        parameters={"kind": "mapping", "type": "dict", "items": [], "truncated": 0},
        executemany=False,
        duration_ms=1.5,
        row_count=None,
        error="OperationalError: locked",
    )

    assert query.to_data() == {
        "connection": "default",
        "statement": "select 1",
        "parameters": {"kind": "mapping", "type": "dict", "items": [], "truncated": 0},
        "executemany": False,
        "duration_ms": 1.5,
        "row_count": None,
        "error": "OperationalError: locked",
    }


def test_the_mapping_is_json_safe() -> None:
    query = RecordedQuery("default", "select 1", {}, executemany=True, duration_ms=0.0, row_count=3)

    assert json.loads(json.dumps(query.to_data())) == query.to_data()
