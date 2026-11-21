"""Render a self-contained Korean stock research report from JSON."""

import argparse
from html import escape
import json
from pathlib import Path
import re
from string import Template
from urllib.parse import urlsplit


TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "report.html"
NUMBER = r"[+-]?\d[\d,]*(?:\.\d+)?"
MEASURE = re.compile(
    rf"(\${NUMBER}(?: *(?:~|–|→) *\${NUMBER})?"
    rf"|{NUMBER}(?:[~–]{NUMBER})? *(?:[억조만] *달러|달러|%|배)"
    r"|\d{1,2}월 \d{1,2}일)"
)


def readable_text(value):
    parts = MEASURE.split(value)
    return "".join(
        f'<span class="measure">{escape(part)}</span>' if index % 2 else escape(part)
        for index, part in enumerate(parts)
    )


def render_paragraphs(value, tail=""):
    paragraphs = [value] if isinstance(value, str) else list(value)
    return "".join(
        f"<p>{readable_text(paragraph)}{tail if index == len(paragraphs) - 1 else ''}</p>"
        for index, paragraph in enumerate(paragraphs)
    )


def render_table(table):
    caption = escape(table["caption"])
    header = "".join(f'<th scope="col">{escape(column)}</th>' for column in table["columns"])
    rows = []
    for row in table["rows"]:
        if not row or len(row) != len(table["columns"]):
            raise ValueError("Each table row must match the number of columns.")
        cells = "".join(f"<td>{readable_text(cell)}</td>" for cell in row[1:])
        rows.append(f'<tr><th scope="row">{readable_text(row[0])}</th>{cells}</tr>')
    return (
        f'<div class="table-wrap" role="region" aria-label="{caption}" tabindex="0">'
        f"<table><caption>{caption}</caption><thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_report(data):
    source_items = []
    for number, source in enumerate(data.get("sources", []), start=1):
        url = urlsplit(source["url"])
        if url.scheme not in ("https", "http") or not url.hostname:
            raise ValueError(f"Source {number} must be an HTTP or HTTPS URL.")
        source_items.append(
            f'<li id="source-{number}"><a href="{escape(source["url"])}">'
            f'{escape(source["label"])}</a></li>'
        )

    def references(numbers):
        if not numbers:
            return ""
        links = []
        for number in dict.fromkeys(numbers):
            if type(number) is not int or not 1 <= number <= len(source_items):
                raise ValueError(f"Source reference {number!r} does not exist.")
            links.append(f'<a href="#source-{number}" aria-label="출처 {number}">[{number}]</a>')
        return f'<span class="refs">{"".join(links)}</span>'

    metrics = []
    for item in data.get("metrics", []):
        note = readable_text(item.get("note", "")) + references(item.get("refs"))
        metrics.append(
            f'<div class="metric"><dt>{escape(item["label"])}</dt>'
            f'<dd class="metric-value">{readable_text(item["value"])}</dd>'
            f'<dd class="metric-note">{note}</dd></div>'
        )

    timing_items = []
    for item in data.get("timing", []):
        timing_items.append(
            f'<li><h3>{escape(item["label"])}</h3><div>'
            f'<p class="timing-trigger">{readable_text(item["trigger"])}</p>'
            f'{render_paragraphs(item["action"], references(item.get("refs")))}</div></li>'
        )
    timing_note = data.get("timing_note")
    timing = ""
    if timing_items:
        note = f'<div class="timing-note">{render_paragraphs(timing_note)}</div>' if timing_note else ""
        timing = (
            '<section class="timing" aria-labelledby="timing-title">'
            '<h2 id="timing-title">언제 사고, 언제 팔지</h2>'
            f'<ul>{"".join(timing_items)}</ul>{note}</section>'
        )

    sections = []
    for section in data["sections"]:
        paragraphs = render_paragraphs(section.get("paragraphs", []))
        table = render_table(section["table"]) if section.get("table") else ""
        refs = references(section.get("refs"))
        evidence = f'<div class="evidence">근거{refs}</div>' if refs else ""
        sections.append(
            f'<section class="section"><h2>{readable_text(section["title"])}</h2>'
            f"{paragraphs}{table}{evidence}</section>"
        )

    watch_items = []
    for item in data.get("watch", []):
        refs = references(item.get("refs"))
        watch_items.append(f'<li><h3>{escape(item["label"])}</h3><p>{escape(item["text"])}{refs}</p></li>')

    terms = [
        f'<div><dt>{escape(item["term"])}</dt><dd>{escape(item["definition"])}</dd></div>'
        for item in data.get("terms", [])
    ]
    panels = []
    if watch_items:
        panels.append(f'<section class="panel"><h2>다음에 볼 것</h2><ul>{"".join(watch_items)}</ul></section>')
    if terms:
        panels.append(f'<section class="panel"><h2>용어 풀이</h2><dl>{"".join(terms)}</dl></section>')

    team_items = [
        f'<div><dt>{escape(item["role"])}</dt><dd>{escape(item["contribution"])}</dd></div>'
        for item in data.get("team", [])
    ]

    values = {key: readable_text(data[key]) for key in ("as_of", "headline")}
    values.update(
        kind=escape(data["kind"]),
        title=escape(data["title"]),
        summary=render_paragraphs(data["summary"], references(data.get("summary_refs"))),
        metrics=f'<dl class="metrics">{"".join(metrics)}</dl>' if metrics else "",
        timing=timing,
        report_class=" has-timing" if timing else "",
        column_class="" if panels else " single",
        sections="\n          ".join(sections),
        aside=f'<aside aria-label="리포트 참고 사항">{"".join(panels)}</aside>' if panels else "",
        team=(
            '<section class="team"><h2>분석팀이 확인한 것</h2>'
            f'<dl>{"".join(team_items)}</dl></section>' if team_items else ""
        ),
        sources=(
            f'<footer class="sources"><h2>출처</h2><ol>{"".join(source_items)}</ol></footer>'
            if source_items else ""
        ),
    )
    return Template(TEMPLATE.read_text(encoding="utf-8")).substitute(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output file.")
    args = parser.parse_args()
    try:
        report = render_report(json.loads(args.input.read_text(encoding="utf-8")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w" if args.overwrite else "x", encoding="utf-8") as output:
            output.write(report)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
