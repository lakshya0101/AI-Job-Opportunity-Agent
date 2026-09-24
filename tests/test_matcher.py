from src.matching.matcher import normalize_text


def test_normalize_text():
    result = normalize_text(
        "Machine-Learning / Engineer"
    )

    assert result == (
        "machine learning engineer"
    )
