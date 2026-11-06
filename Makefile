.PHONY: help examples test build clean

help:
	@echo "make examples  Regenerate the example CVs (ES/EN, TeX + PDF)"
	@echo "make test      Run the test suite"
	@echo "make build     Build the wheel and sdist"
	@echo "make clean     Remove build artifacts"

examples:
	@mkdir -p examples/output
	uv run cv-generator --data examples/cv.example.yml --out examples/output/cv-example-es.tex --lang es --pdf
	uv run cv-generator --data examples/cv.example.yml --out examples/output/cv-example-en.tex --lang en --pdf --public
	@rm -f examples/output/*.aux examples/output/*.bbl examples/output/*.bcf \
		examples/output/*.blg examples/output/*.log examples/output/*.out \
		examples/output/*.run.xml

test:
	uv run pytest

build:
	uv build

clean:
	rm -rf build dist .pytest_cache
