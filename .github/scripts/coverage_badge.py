"""Draws the coverage badge (an SVG picture) for the README.

    python .github/scripts/coverage_badge.py 98.43 coverage.svg

The CI (.github/workflows/django.yml) runs it after the tests and pushes the
picture to the "badges" branch; the README shows it from there. Our own
badge instead of a service like Codecov: no account, no token, no data of
the project leaves GitHub.

The look is the "flat" style of shields.io: grey "coverage" on the left,
the percent on the right, coloured by how good it is.
"""

import sys
from pathlib import Path

# (lowest percent, colour), from the best one down; the colours of shields.io
COLOURS = (
    (90, "#4c1"),  # bright green
    (80, "#97ca00"),  # green
    (70, "#dfb317"),  # yellow: 70% is the minimum of the homework (pytest.ini)
    (60, "#fe7d37"),  # orange
    (0, "#e05d44"),  # red
)

LABEL = "coverage"
# Width of one character of Verdana 11px, about; plus 10px of padding on
# both sides of a text. Enough for "coverage" and "100%", no font needed.
CHAR_WIDTH = 7
PADDING = 10

TEMPLATE = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" \
aria-label="{label}: {value}">
<title>{label}: {value}</title>
<linearGradient id="s" x2="0" y2="100%">
<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
<stop offset="1" stop-opacity=".1"/>
</linearGradient>
<clipPath id="r"><rect width="{width}" height="20" rx="3" fill="#fff"/></clipPath>
<g clip-path="url(#r)">
<rect width="{label_width}" height="20" fill="#555"/>
<rect x="{label_width}" width="{value_width}" height="20" fill="{colour}"/>
<rect width="{width}" height="20" fill="url(#s)"/>
</g>
<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" \
font-size="11">
<text x="{label_x}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
<text x="{label_x}" y="14">{label}</text>
<text x="{value_x}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
<text x="{value_x}" y="14">{value}</text>
</g>
</svg>
"""


def colour_for(percent):
    """98.43 -> "#4c1". The first colour whose minimum the percent reaches."""
    for minimum, colour in COLOURS:
        if percent >= minimum:
            return colour
    return COLOURS[-1][1]  # below 0: can't happen, but never fail on it


def badge_svg(percent):
    """The SVG text of the badge. The percent is rounded to a whole number:
    "98%" reads better on a badge than "98.43%"; int(... + 0.5) instead of
    round(): round(98.5) is 98 in Python (to the even number)."""
    value = f"{int(percent + 0.5)}%"
    label_width = len(LABEL) * CHAR_WIDTH + 2 * PADDING
    value_width = len(value) * CHAR_WIDTH + 2 * PADDING
    return TEMPLATE.format(
        label=LABEL,
        value=value,
        colour=colour_for(percent),
        width=label_width + value_width,
        label_width=label_width,
        value_width=value_width,
        label_x=label_width / 2,
        value_x=label_width + value_width / 2,
    )


def main(argv):
    """argv: [percent, output file]. Returns the exit code."""
    if len(argv) != 2:
        print("Usage: coverage_badge.py <percent> <output.svg>", file=sys.stderr)
        return 2
    try:
        percent = float(argv[0])
    except ValueError:
        print(f"Not a number: {argv[0]!r}", file=sys.stderr)
        return 2
    Path(argv[1]).write_text(badge_svg(percent), encoding="utf-8")
    print(f"{argv[1]}: {LABEL} {percent}%")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
