"""Tests for src.refs.conference_db (adapted from TestJacoWConnector)."""

import pytest

from src.refs.conference_db import FieldCompletion, JacoWConnector


def test_lookup_ipac2023(connector: JacoWConnector):
    m = connector.lookup("IPAC", "2023")
    assert m is not None
    assert m["city"] == "Venice"
    assert m["country"] == "Italy"
    assert m["month"] == "May"


def test_lookup_linac2024(connector: JacoWConnector):
    m = connector.lookup("LINAC", "2024")
    assert m is not None
    assert m["city"] == "Chicago"
    assert m["country"] == "USA"


def test_lookup_srf2023(connector: JacoWConnector):
    m = connector.lookup("SRF", "2023")
    assert m is not None
    assert m["city"] == "Grand Rapids"


def test_lookup_ibic2022(connector: JacoWConnector):
    m = connector.lookup("IBIC", "2022")
    assert m is not None
    assert m["city"] == "Kraków"


def test_lookup_case_insensitive(connector: JacoWConnector):
    assert connector.lookup("ipac", "2023") == connector.lookup("IPAC", "2023")


def test_lookup_with_year_suffix_in_acronym(connector: JacoWConnector):
    """``IPAC2023`` (no space) should also resolve."""
    m = connector.lookup("IPAC2023", "2023")
    assert m is not None


def test_lookup_unknown_returns_none(connector: JacoWConnector):
    assert connector.lookup("UNKNOWN", "2099") is None


def test_lookup_unknown_year_returns_none(connector: JacoWConnector):
    assert connector.lookup("IPAC", "1899") is None


def test_is_jacow_series_known(connector: JacoWConnector):
    assert connector.is_jacow_series("IPAC") is True
    assert connector.is_jacow_series("LINAC") is True
    assert connector.is_jacow_series("FEL") is True


def test_is_jacow_series_unknown(connector: JacoWConnector):
    assert connector.is_jacow_series("TOTALLY_FAKE_CONF") is False


def test_complete_record_fills_location(connector: JacoWConnector):
    rec = {"conference": "IPAC", "year": "2023"}
    fl: list[FieldCompletion] = []
    rec = connector.complete_record(rec, fl, "2024-01-01T00:00:00Z")
    assert rec["city"] == "Venice"
    assert rec["country"] == "Italy"
    assert rec["month"] == "May"


def test_complete_record_logs_fields(connector: JacoWConnector):
    rec = {"conference": "IPAC", "year": "2023"}
    fl: list[FieldCompletion] = []
    connector.complete_record(rec, fl, "2024-01-01T00:00:00Z")
    assert len(fl) >= 2
    field_names = {fc.field for fc in fl}
    assert "city" in field_names
    assert "country" in field_names


def test_complete_record_confidence_is_one(connector: JacoWConnector):
    rec = {"conference": "IPAC", "year": "2023"}
    fl: list[FieldCompletion] = []
    connector.complete_record(rec, fl, "2024-01-01T00:00:00Z")
    assert all(fc.confidence == 1.0 for fc in fl)


def test_complete_record_source_is_jacow_db(connector: JacoWConnector):
    rec = {"conference": "IPAC", "year": "2023"}
    fl: list[FieldCompletion] = []
    connector.complete_record(rec, fl, "2024-01-01T00:00:00Z")
    assert all(fc.source == "JACoW-DB" for fc in fl)


def test_complete_record_does_not_overwrite_existing(connector: JacoWConnector):
    rec = {"conference": "IPAC", "year": "2023", "city": "MyCity"}
    fl: list[FieldCompletion] = []
    rec = connector.complete_record(rec, fl, "2024-01-01T00:00:00Z")
    assert rec["city"] == "MyCity"


def test_complete_record_unknown_conf_no_crash(connector: JacoWConnector):
    rec = {"conference": "UNKNOWN", "year": "2099"}
    fl: list[FieldCompletion] = []
    result = connector.complete_record(rec, fl, "2024-01-01T00:00:00Z")
    assert result == rec
    assert fl == []


def test_field_log_timestamp_format(connector: JacoWConnector):
    import re

    rec = {"conference": "IPAC", "year": "2023"}
    fl: list[FieldCompletion] = []
    connector.complete_record(rec, fl, "2024-06-01T12:00:00Z")
    iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    for fc in fl:
        assert iso_re.match(fc.timestamp), (
            f"Timestamp {fc.timestamp!r} is not ISO-8601 UTC"
        )


def test_field_completion_vars_has_all_keys():
    fc = FieldCompletion(field="f", value="v", source="s", timestamp="t")
    d = vars(fc)
    for k in ("field", "value", "source", "timestamp", "cached", "confidence"):
        assert k in d


def test_field_completion_defaults():
    fc = FieldCompletion(
        field="city", value="Venice", source="JACoW-DB",
        timestamp="2024-01-01T00:00:00Z",
    )
    assert fc.confidence == 1.0
    assert fc.cached is False


def test_complete_record_no_conference_no_change(connector: JacoWConnector):
    rec = {"year": "2023"}
    fl: list[FieldCompletion] = []
    result = connector.complete_record(rec, fl, "2024-01-01T00:00:00Z")
    assert result == rec
    assert fl == []


def test_complete_record_default_timestamp(connector: JacoWConnector):
    """When ts is omitted, an ISO-8601 UTC stamp is auto-generated."""
    import re

    rec = {"conference": "IPAC", "year": "2023"}
    fl: list[FieldCompletion] = []
    connector.complete_record(rec, fl)
    assert fl, "expected at least one filled field"
    iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    assert iso_re.match(fl[0].timestamp)
