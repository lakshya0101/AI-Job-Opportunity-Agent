from src.collectors.official_careers import (
    collect_company,
)


def test_unsupported_platform_returns_empty():

    company = {
        "name": "Test Company",
        "platform": "unknown",
        "identifier": "test",
    }

    result = collect_company(
        company
    )

    assert result == []


def test_missing_identifier_returns_empty():

    company = {
        "name": "Test Company",
        "platform": "greenhouse",
    }

    result = collect_company(
        company
    )

    assert result == []
