"""The README's architecture picture, in the design system's colours, light and dark.

Reads the colours from docs/design-system/tokens.css, so the picture follows the system, and
writes docs/images/architecture-light.svg and -dark.svg. The README shows the one that matches
the reader's theme (`<picture>`). Run from a checkout: `python3 tools/architecture_svg.py`.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "docs" / "design-system" / "tokens.css"
OUT = ROOT / "docs" / "images"
NAMES = ("surface-0", "surface-1", "text-1", "text-2", "text-3", "border", "border-strong", "accent")
FONT = "Geist, system-ui, -apple-system, Segoe UI, sans-serif"
MONO = "Geist Mono, ui-monospace, SFMono-Regular, Menlo, monospace"
W, H = 760, 444


def colours(theme: str) -> dict[str, str]:
    """The tokens of one theme: `:root` for light, `:root[data-theme="dark"]` for dark."""
    css = TOKENS.read_text(encoding="utf-8")
    head = r'^:root\[data-theme="dark"\]\s*\{' if theme == "dark" else r'^:root\s*\{'
    blocks = re.findall(head + r"([^}]*)\}", css, re.M)  # top-level blocks only
    assert blocks, f"no {theme} block in {TOKENS}"
    found = dict(re.findall(r"--([\w-]+):\s*([^;]+);", "".join(blocks)))
    return {name: found[name].strip() for name in NAMES}


def box(c, x, y, w, h, title, lines, strong=False):
    edge = c["accent"] if strong else c["border-strong"]
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{c["surface-1"]}" '
           f'stroke="{edge}" stroke-width="{1.5 if strong else 1}"/>',
           f'<text x="{x + w / 2}" y="{y + 28 if lines else y + h / 2 + 5}" text-anchor="middle" font-weight="600" '
           f'font-size="15" fill="{c["text-1"]}">{escape(title)}</text>']
    for i, line in enumerate(lines):
        family = f' font-family="{MONO}"' if line.startswith("$ ") else ""
        out.append(f'<text x="{x + w / 2}" y="{y + 50 + 19 * i}" text-anchor="middle" '
                   f'font-size="13"{family} fill="{c["text-2"]}">{escape(line.removeprefix("$ "))}</text>')
    return out


def arrow(c, x1, y1, x2, y2, label, lx, anchor="start"):
    return [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c["accent"]}" '
            f'stroke-width="1.5" marker-end="url(#head)"/>',
            f'<text x="{lx}" y="{(y1 + y2) / 2 + 4}" text-anchor="{anchor}" font-size="12.5" '
            f'fill="{c["text-2"]}">{escape(label)}</text>']


def picture(theme: str) -> str:
    c = colours(theme)
    parts = [
        f'<rect width="{W}" height="{H}" rx="8" fill="{c["surface-0"]}" stroke="{c["border"]}"/>',
        *box(c, 230, 24, 300, 86, "Dev machine (laptop or PC)", ["you and your agents run", "$ mulebox check"]),
        *arrow(c, 380, 110, 380, 186, "ssh: a job goes in, its output and exit code come back", 392),
        f'<rect x="24" y="166" width="{W - 48}" height="{H - 180}" rx="8" fill="none" '
        f'stroke="{c["border-strong"]}" stroke-dasharray="4 4"/>',
        f'<text x="40" y="190" font-size="12.5" fill="{c["text-3"]}">Nodes: Linux machines on your LAN</text>',
        *box(c, 200, 200, 360, 88, "Node 1: coordinator + worker",
             ["one line of jobs, history, the dashboard", "and slots that run jobs"], strong=True),
        *box(c, 70, 350, 250, 60, "Node 2: worker", []),
        *box(c, 440, 350, 250, 60, "Node 3: worker", []),
        *arrow(c, 300, 288, 210, 350, "a job, when it asks over ssh", 248, "end"),
        *arrow(c, 460, 288, 550, 350, "a job, when it asks over ssh", 512),
    ]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            f'font-family="{FONT}" role="img" aria-label="The dev machine sends jobs over ssh to the '
            f'coordinator node, which hands them to worker nodes">\n'
            f'<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{c["accent"]}"/></marker></defs>\n'
            + "\n".join(parts) + "\n</svg>\n")


if __name__ == "__main__":
    for theme in ("light", "dark"):
        path = OUT / f"architecture-{theme}.svg"
        path.write_text(picture(theme), encoding="utf-8")
        print(path.relative_to(ROOT))
