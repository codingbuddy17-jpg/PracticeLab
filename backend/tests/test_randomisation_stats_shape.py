"""
Stored randomisation stats reach the UI as an object, whatever the DB returns.

The model declares Column(JSON) but the migration created the column as TEXT,
so Postgres hands the value back as a JSON string while SQLite deserialises it.
The endpoint tests therefore could not see the fault — it only appeared in
production, where the card read `.avg_uniqueness_pct` off a string, got
undefined, and rendered a dash with an empty per-coder table. That reads as
"no overlap" rather than "no data", so the sessions screen and the generate
screen disagreed about the same assessment.
"""
import json

from services.randomisation_stats import parse_stats

SAMPLE = {
    "avg_uniqueness_pct": 73.3,
    "pool_utilisation_pct": 35.6,
    "total_pool": 73,
    "coder_count": 3,
    "per_coder": [{"name": "Alice", "uniqueness_pct": 60.0, "shared_items": [1, 2]}],
}


def test_a_json_string_is_parsed():
    """What Postgres actually returns for this column."""
    assert parse_stats(json.dumps(SAMPLE)) == SAMPLE


def test_a_dict_passes_through():
    """What SQLite returns, and what the POST responses already carry."""
    assert parse_stats(SAMPLE) == SAMPLE


def test_none_stays_none():
    assert parse_stats(None) is None


def test_unparseable_text_becomes_none_not_a_string():
    """
    None renders as "not measured". A string renders as a dash that looks like
    a measurement of zero overlap, which is the failure being fixed.
    """
    assert parse_stats("not json at all") is None


def test_a_json_scalar_is_not_treated_as_stats():
    assert parse_stats("42") is None
    assert parse_stats('"a string"') is None


def test_the_parsed_shape_is_what_the_card_reads(client, db):
    """Guards the fields the UI dereferences, not just that it is a dict."""
    parsed = parse_stats(json.dumps(SAMPLE))
    assert parsed["avg_uniqueness_pct"] == 73.3
    assert parsed["per_coder"][0]["name"] == "Alice"
