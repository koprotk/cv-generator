from pathlib import Path

from cv_generator.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DATA = ROOT / "examples" / "cv.example.yml"


def test_generates_tex(tmp_path):
    out = tmp_path / "cv.tex"

    assert main(["--data", str(EXAMPLE_DATA), "--content-dir", str(ROOT), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Ada Example" in text
    assert "Example Corp" in text


def test_filters_by_tag_and_language(tmp_path):
    out = tmp_path / "cv.tex"

    assert main(
        [
            "--data",
            str(EXAMPLE_DATA),
            "--content-dir",
            str(ROOT),
            "--out",
            str(out),
            "--tags",
            "qa",
            "--lang",
            "en",
        ]
    ) == 0

    text = out.read_text(encoding="utf-8")
    assert "QA Automation Program" in text
    assert "MSc in Examples (EN)" not in text
    assert "Automated front-end and API tests." in text
    assert "Taught introductory programming." not in text
