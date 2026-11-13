"""The coverage badge of the README (.github/scripts/coverage_badge.py, run by the CI)."""

import importlib.util
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "coverage_badge.py"


def load_script():
    """The script is not in a package (.github has no __init__.py): load it by its path."""
    spec = importlib.util.spec_from_file_location("coverage_badge", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


badge = load_script()


@pytest.mark.parametrize(
    ("percent", "colour"),
    [
        (100, "#4c1"),
        (90, "#4c1"),
        (89.99, "#97ca00"),
        (70, "#dfb317"),
        (65, "#fe7d37"),
        (12, "#e05d44"),
        (0, "#e05d44"),
        (-1, "#e05d44"),
    ],
)
def test_colour_depends_on_the_percent(percent, colour):
    assert badge.colour_for(percent) == colour


@pytest.mark.parametrize(("percent", "text"), [(98.43, "98%"), (98.5, "99%"), (100, "100%")])
def test_badge_is_valid_svg_with_the_rounded_percent(percent, text):
    svg = badge.badge_svg(percent)

    root = ElementTree.fromstring(svg)  # raises on broken XML
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.get("aria-label") == f"coverage: {text}"
    # The value part is wide enough for its text ("100%" is wider than "98%")
    assert int(root.get("width")) == (len("coverage") + len(text)) * 7 + 40


def test_main_writes_the_file(tmp_path, capsys):
    output = tmp_path / "coverage.svg"

    assert badge.main(["98.43", str(output)]) == 0

    assert "coverage: 98%" in output.read_text(encoding="utf-8")
    assert "coverage 98.43%" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["98"], ["ninety", "coverage.svg"]])
def test_main_rejects_wrong_arguments(argv, tmp_path, capsys):
    assert badge.main(argv) == 2
    assert capsys.readouterr().err
    assert not list(tmp_path.iterdir())
