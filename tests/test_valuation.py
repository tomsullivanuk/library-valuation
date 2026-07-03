from valuation.rps import calculate_rps, empty_rps_breakdown
from valuation.workbook import build_valuation_rows, valuation_fieldnames


def test_calculate_rps_uses_default_weights_and_missing_signals_as_zero():
    score = calculate_rps({"publisher_tier": 1.0, "subject_signal": 0.5})

    assert score == 0.5


def test_calculate_rps_accepts_custom_weights():
    score = calculate_rps({"signal": 0.25}, {"signal": 2.0})

    assert score == 0.5


def test_empty_rps_breakdown_exposes_stable_shape():
    assert empty_rps_breakdown() == {"score": 0.0, "signals": {}}


def test_valuation_fieldnames_returns_copy():
    fields = valuation_fieldnames()
    fields.append("mutated")

    assert "mutated" not in valuation_fieldnames()


def test_build_valuation_rows_maps_catalog_fields_without_scoring():
    rows = build_valuation_rows(
        [
            {
                "isbn13": "9780198786221",
                "title": "Cognitive neuroscience",
                "authors": "Richard Passingham",
                "lcc": "QP360.5",
                "subjects": "Neuroscience",
            }
        ]
    )

    assert rows == [
        {
            "isbn13": "9780198786221",
            "title": "Cognitive neuroscience",
            "authors": "Richard Passingham",
            "publishers": "",
            "lcc": "QP360.5",
            "subjects": "Neuroscience",
            "rps_score": "",
            "valuation_notes": "",
        }
    ]
