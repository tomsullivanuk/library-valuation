from pathlib import Path

from valuation.research_signals import (
    ResearchSignalConfig,
    generate_research_signals,
    load_research_signal_config,
)


def signal_by_code(signals):
    return {signal.signal_code: signal for signal in signals}


def test_generate_research_signals_uses_configured_old_publication_year_threshold():
    config = ResearchSignalConfig(weights={"old_publication_year": 12}, old_publication_year_threshold=1940)

    signals = generate_research_signals(
        {
            "catalog_item_id": "BK000001",
            "publication_year": "1931",
            "lcc": "B123 .A1",
            "oclc": "12345",
            "resolution_confidence": "high",
        },
        config=config,
    )

    old_year = signal_by_code(signals)["old_publication_year"]
    assert old_year.points == 12
    assert old_year.evidence_field == "publication_year"
    assert old_year.evidence_value == "1931"
    assert old_year.explanation == "Published before 1940."


def test_generate_research_signals_detects_missing_metadata():
    config = ResearchSignalConfig(weights={"missing_lcc": 8, "missing_oclc": 5})

    signals = signal_by_code(
        generate_research_signals(
            {
                "catalog_item_id": "BK000001",
                "publication_year": "2020",
                "publisher": "Modern Books",
                "resolution_confidence": "high",
            },
            config=config,
        )
    )

    assert signals["missing_lcc"].points == 8
    assert signals["missing_lcc"].explanation.startswith("LC classification is missing")
    assert signals["missing_oclc"].points == 5
    assert signals["missing_oclc"].explanation.startswith("OCLC identifier is missing")


def test_generate_research_signals_detects_publisher_tier():
    config = ResearchSignalConfig(
        weights={"university_press": 15, "specialist_publisher": 10},
        publisher_tiers={
            "university_press": ["Oxford University Press"],
            "specialist_trade": ["Routledge"],
        },
    )

    university_signals = signal_by_code(
        generate_research_signals(
            {"catalog_item_id": "BK000001", "publisher": "Oxford University Press", "lcc": "B1", "oclc": "1"},
            config=config,
        )
    )
    specialist_signals = signal_by_code(
        generate_research_signals(
            {"catalog_item_id": "BK000002", "publisher": "Routledge", "lcc": "B1", "oclc": "1"},
            config=config,
        )
    )

    assert university_signals["university_press"].points == 15
    assert university_signals["university_press"].explanation == "Published by a university press."
    assert specialist_signals["specialist_publisher"].points == 10
    assert specialist_signals["specialist_publisher"].explanation == "Published by a specialist or scholarly publisher."


def test_generate_research_signals_detects_scholarly_lc_subject_and_multiple_acquisitions():
    config = ResearchSignalConfig(
        weights={"scholarly_lc_subject": 10, "multiple_acquisitions": 6},
        scholarly_lc_classes={"B": "Philosophy, Psychology, Religion"},
    )

    signals = signal_by_code(
        generate_research_signals(
            {
                "catalog_item_id": "BK000001",
                "publication_year": "2020",
                "publisher": "Modern Books",
                "lcc": "B123 .A1",
                "oclc": "1",
            },
            acquisitions=[
                {"catalog_item_id": "BK000001", "acquisition_id": "A1"},
                {"catalog_item_id": "BK000001", "acquisition_id": "A2"},
            ],
            config=config,
        )
    )

    assert signals["scholarly_lc_subject"].evidence_value == "B123 .A1"
    assert signals["multiple_acquisitions"].evidence_value == "2"


def test_generate_research_signals_detects_low_metadata_confidence():
    config = ResearchSignalConfig(weights={"low_metadata_confidence": 6})

    signals = signal_by_code(
        generate_research_signals(
            {
                "catalog_item_id": "BK000001",
                "publication_year": "2020",
                "publisher": "Modern Books",
                "lcc": "B1",
                "oclc": "1",
                "resolution_source": "manual_review",
                "resolution_confidence": "low",
            },
            config=config,
        )
    )

    assert signals["low_metadata_confidence"].points == 6
    assert signals["low_metadata_confidence"].evidence_value == "low"


def test_generate_research_signals_returns_empty_list_when_no_signal_applies():
    signals = generate_research_signals(
        {
            "catalog_item_id": "BK000001",
            "publication_year": "2020",
            "publisher": "Modern Books",
            "lcc": "Z123 .A1",
            "oclc": "1",
            "resolution_confidence": "high",
            "openlibrary_status": "matched",
        },
        config=ResearchSignalConfig(weights={}),
    )

    assert signals == []


def test_research_signal_as_dict_uses_stable_string_shape():
    signal = generate_research_signals(
        {"catalog_item_id": "BK000001", "publication_year": "1931", "lcc": "Z1", "oclc": "1"},
        config=ResearchSignalConfig(weights={"old_publication_year": 12}, old_publication_year_threshold=1945),
    )[0]

    assert signal.as_dict() == {
        "signal_code": "old_publication_year",
        "signal_label": "Older publication",
        "points": "12",
        "evidence_field": "publication_year",
        "evidence_value": "1931",
        "explanation": "Published before 1945.",
    }


def test_load_research_signal_config_reads_weights_threshold_publishers_and_subjects(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "research_signals.yml").write_text(
        "old_publication_year_threshold: 1940\nweights:\n  old_publication_year: 9\nbands:\n  high: 25\n",
        encoding="utf-8",
    )
    (config_dir / "publisher_tiers.yml").write_text(
        "tiers:\n  university_press:\n    examples:\n      - Oxford University Press\n",
        encoding="utf-8",
    )
    (config_dir / "lc_subjects.yml").write_text(
        "subjects:\n  B:\n    label: Philosophy\n",
        encoding="utf-8",
    )

    config = load_research_signal_config(Path(config_dir))

    assert config.old_publication_year_threshold == 1940
    assert config.points("old_publication_year") == 9
    assert config.band_threshold("high") == 25
    assert config.publisher_tiers == {"university_press": ["Oxford University Press"]}
    assert config.scholarly_lc_classes == {"B": "Philosophy"}
