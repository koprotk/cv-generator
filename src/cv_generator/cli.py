#!/usr/bin/env python3
"""Generate a LaTeX CV from a YAML data file using a Jinja2 template.

Features:
 - tag-based filtering for education/experience
 - public mode to omit confidential docs
 - optional bibkey filtering: writes a filtered .bib next to output .tex
 - Spanish/English language variants
 - optional PDF compilation (pdflatex + biber)

Usage:
  cv-generator --data data/cv.yml --out build/cv.tex --tags qa,it --public --pdf
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    import bibtexparser
    import yaml
    from jinja2 import Environment, FileSystemLoader
except Exception as exc:  # pragma: no cover - import error path
    print("Missing dependency:", exc)
    print("Install with: pip install pyyaml jinja2 bibtexparser")
    raise

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_DIR = PACKAGE_DIR / "templates"
DEFAULT_STYLE_DIR = PACKAGE_DIR / "styles"

HEADERS = {
    "es": {
        "education": "Educación",
        "experience": "Experiencia",
        "courses": "Certificaciones",
        "languages": "Idiomas",
        "skills": "Habilidades",
        "references": "Referencias",
        "publications": "Publicaciones",
        "summary": "Perfil",
    },
    "en": {
        "education": "Education",
        "experience": "Experience",
        "courses": "Certifications",
        "languages": "Languages",
        "skills": "Skills",
        "references": "References",
        "publications": "Publications",
        "summary": "Profile",
    },
}

TRANSLATABLE = {
    "education": ["title", "note", "location"],
    "experience": ["role", "desc", "location"],
    "skills": ["category", "items"],
    "courses": ["title", "org", "desc"],
    "languages": ["name", "level", "note"],
    "references": ["relation"],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a LaTeX CV from a YAML single source."
    )
    parser.add_argument(
        "--data",
        default="data/cv.yml",
        help="CV YAML file, relative to --content-dir (default: data/cv.yml)",
    )
    parser.add_argument(
        "--content-dir",
        default=".",
        help="Directory used to resolve --data and relative asset/bib paths "
        "(default: current directory)",
    )
    parser.add_argument(
        "--out",
        default="build/cv.tex",
        help="Output .tex path, relative to the current directory (default: build/cv.tex)",
    )
    parser.add_argument(
        "--tags", default="", help="Comma-separated tags to include"
    )
    parser.add_argument(
        "--public", action="store_true", help="Omit confidential links"
    )
    parser.add_argument(
        "--no-references", action="store_true", help="Omit the references section"
    )
    parser.add_argument(
        "--no-publications", action="store_true", help="Omit the publications section"
    )
    parser.add_argument(
        "--bibkeys",
        default="",
        help="Comma-separated bibtex keys to include in a filtered .bib",
    )
    parser.add_argument(
        "--lang",
        default="es",
        choices=["es", "en"],
        help="Language: es (Spanish) or en (English)",
    )
    parser.add_argument(
        "--pdf", action="store_true", help="Compile to PDF after generating .tex"
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        help="Template directory (default: bundled template)",
    )
    parser.add_argument(
        "--styles",
        type=Path,
        default=None,
        help="LaTeX style directory (default: bundled styles)",
    )
    return parser


def filter_by_tags(items: list[dict], selected_tags: set[str]) -> list[dict]:
    if not selected_tags:
        return items
    out = []
    for item in items:
        item_tags = set(item.get("tags", []))
        if not item_tags or (item_tags & selected_tags):
            out.append(item)
    return out


def resolve_lang(items: list[dict], lang: str, fields: list[str]) -> list[dict]:
    """For each item, if `field_lang` exists use it, else fall back to `field`."""
    result = []
    for item in items:
        translated = dict(item)
        for field in fields:
            lang_key = f"{field}_{lang}"
            if lang_key in item:
                translated[field] = item[lang_key]
        result.append(translated)
    return result


def escape_latex(text: str) -> str:
    """Escape LaTeX special characters in a string."""
    if not isinstance(text, str):
        return text
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def escape_context(obj):
    """Recursively escape LaTeX specials in strings within dicts/lists."""
    if isinstance(obj, str):
        return escape_latex(obj)
    if isinstance(obj, dict):
        return {key: escape_context(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [escape_context(item) for item in obj]
    return obj


def prepare_context(
    data: dict,
    lang: str,
    selected_tags: set[str],
    public: bool,
    show_references: bool,
    show_publications: bool,
) -> dict:
    personal = data.get("personal", {}).copy()
    orcid_full = personal.get("orcid", "")
    if orcid_full.startswith("0000-000"):
        personal["orcid"] = orcid_full[len("0000-000") :]

    if f"summary_{lang}" in personal:
        personal["summary"] = escape_latex(personal[f"summary_{lang}"])
    elif "summary" in personal:
        personal["summary"] = escape_latex(personal["summary"])

    context: dict = {
        "personal": personal,
        "config": data.get("config", {}).copy(),
        "headers": HEADERS[lang],
        "show_references": show_references,
        "show_publications": show_publications,
    }

    for section in ("education", "experience", "skills", "courses", "languages"):
        items = filter_by_tags(data.get(section, []), selected_tags)
        items = resolve_lang(items, lang, TRANSLATABLE[section])
        context[section] = escape_context(items)

    references = resolve_lang(data.get("references", []), lang, TRANSLATABLE["references"])
    context["references"] = escape_context(references)

    documents = data.get("documents", [])
    if public:
        documents = [doc for doc in documents if not doc.get("confidential")]
    context["documents"] = escape_context(documents)

    return context


def handle_bibliography(
    context: dict,
    content_dir: Path,
    out_path: Path,
    selected_bibkeys: list[str],
) -> None:
    """Point the template at the bibliography and optionally filter it."""
    bibpath = context["config"].get("bibpath", "biblio/cv_ref.bib")
    orig_bibpath = Path(bibpath)
    if not orig_bibpath.is_absolute():
        orig_bibpath = content_dir / orig_bibpath
    orig_bibpath = orig_bibpath.resolve()

    if not orig_bibpath.exists():
        print("Warning: bibliography not found at", orig_bibpath)
        context["config"]["bibpath"] = str(orig_bibpath)
        return

    if selected_bibkeys:
        with open(orig_bibpath, "r", encoding="utf-8") as bib_file:
            bibdb = bibtexparser.load(bib_file)
        filtered = [
            entry for entry in bibdb.entries if entry.get("ID") in selected_bibkeys
        ]
        new_bib = bibtexparser.bibdatabase.BibDatabase()
        new_bib.entries = filtered
        writer = bibtexparser.bwriter.BibTexWriter()
        filtered_bib_path = out_path.parent / "refs_filtered.bib"
        with open(filtered_bib_path, "w", encoding="utf-8") as out_file:
            out_file.write(writer.write(new_bib))
        context["config"]["bibpath"] = filtered_bib_path.name
        print(
            "Wrote filtered .bib with",
            len(filtered),
            "entries ->",
            filtered_bib_path,
        )
        return

    # Relative paths in \addbibresource are resolved from the .bcf in the
    # output directory, so compute the path from there.
    try:
        context["config"]["bibpath"] = os.path.relpath(
            orig_bibpath, start=out_path.parent
        )
    except ValueError:
        context["config"]["bibpath"] = str(orig_bibpath)


def compile_pdf(out_path: Path, content_dir: Path, styles_dir: Path) -> bool:
    env = os.environ.copy()
    env["TEXINPUTS"] = f".:{styles_dir}:"
    latex_flags = [
        "-interaction=nonstopmode",
        f"-output-directory={out_path.parent}",
    ]
    tex_file = str(out_path)
    jobname = str(out_path.with_suffix(""))

    print("\nCompiling PDF...")
    steps = [
        (["pdflatex"] + latex_flags + [tex_file], "pdflatex (1/3)"),
        (["biber", jobname], "biber"),
        (["pdflatex"] + latex_flags + [tex_file], "pdflatex (2/3)"),
        (["pdflatex"] + latex_flags + [tex_file], "pdflatex (3/3)"),
    ]
    for step, label in steps:
        print(f"  {label}...", end=" ", flush=True)
        try:
            result = subprocess.run(
                step, capture_output=True, text=True, cwd=content_dir, env=env
            )
        except FileNotFoundError as exc:
            print("FAILED")
            print(f"  Missing executable: {exc.filename}")
            return False
        if result.returncode != 0:
            print("FAILED")
            print("--- stderr ---")
            print(result.stderr.strip() or "(empty)")
            print("--- stdout ---")
            print(result.stdout.strip() or "(empty)")
            return False
        print("OK")

    print(f"\nDone: {out_path.with_suffix('.pdf')}")
    return True


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    content_dir = Path(args.content_dir).expanduser().resolve()
    if not content_dir.is_dir():
        print(f"Error: content directory not found: {content_dir}", file=sys.stderr)
        return 1

    data_path = Path(args.data).expanduser()
    if not data_path.is_absolute():
        data_path = content_dir / data_path
    data_path = data_path.resolve()
    if not data_path.is_file():
        print(f"Error: CV data file not found: {data_path}", file=sys.stderr)
        return 1

    selected_tags = {tag.strip() for tag in args.tags.split(",") if tag.strip()}
    selected_bibkeys = [key.strip() for key in args.bibkeys.split(",") if key.strip()]

    with open(data_path, "r", encoding="utf-8") as data_file:
        data = yaml.safe_load(data_file) or {}

    context = prepare_context(
        data,
        args.lang,
        selected_tags,
        args.public,
        show_references=not args.no_references,
        show_publications=not args.no_publications,
    )

    out_path = Path(args.out).expanduser()
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    handle_bibliography(context, content_dir, out_path, selected_bibkeys)

    template_dir = Path(args.templates).resolve() if args.templates else DEFAULT_TEMPLATE_DIR
    styles_dir = Path(args.styles).resolve() if args.styles else DEFAULT_STYLE_DIR

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        trim_blocks=True,
        lstrip_blocks=True,
        variable_start_string="<<",
        variable_end_string=">>",
    )
    template = env.get_template("harvard.tex.jinja2")
    rendered = template.render(**context)

    out_path.write_text(rendered, encoding="utf-8")
    print("Wrote", out_path)

    if args.pdf:
        if not compile_pdf(out_path, content_dir, styles_dir):
            return 1
    else:
        print("\nNext: compile with pdflatex + biber. Example:")
        print(
            "  pdflatex -interaction=nonstopmode "
            f"-output-directory={out_path.parent} {out_path}"
        )
        print("  biber " + str(out_path.with_suffix("")))
        print(
            "  pdflatex -interaction=nonstopmode "
            f"-output-directory={out_path.parent} {out_path}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
