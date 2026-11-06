from pathlib import Path

from cv_generator.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DATA = ROOT / "examples" / "cv.example.yml"


def test_generates_tex(tmp_path):
    out = tmp_path / "cv.tex"

    assert (
        main(
            [
                "--data",
                str(EXAMPLE_DATA),
                "--content-dir",
                str(ROOT),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    text = out.read_text(encoding="utf-8")
    assert "Ada Example" in text
    assert "Example Fintech" in text
    assert "Ingeniera de Calidad (SDET)" in text


def test_filters_by_tag_and_language(tmp_path):
    out = tmp_path / "cv.tex"

    assert (
        main(
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
        )
        == 0
    )

    text = out.read_text(encoding="utf-8")
    assert "Software Quality Engineer (SDET)" in text
    assert "Front-end and API test automation" in text
    assert "MSc in Computer Science" not in text
    assert "Built REST services in Python and Java." not in text
    assert "Pandas" not in text
