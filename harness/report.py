#!/usr/bin/env python3
"""One way to make every report file, so all of them share the same design.

`render` turns report JSON into HTML (and PDF) with the shared template.
`check` tells whether an HTML file came from that template or was written by hand.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SKILL = "skills/us-stock-research/scripts"
MARK = '<meta name="generator" content="stock-harness-report">'
# Files made with the shared template before the mark was added still carry its colour names.
EARLIER = ("--blue-ink:", "--fill:", ".metric-note")


class ReportError(Exception):
    pass


def scripts_folder(root=ROOT):
    for base in (".agents", "claude/us-stock-team"):
        folder = Path(root) / base / SKILL
        if (folder / "render_report.py").is_file():
            return folder
    raise ReportError("리포트 템플릿을 찾지 못했습니다. 패키지 루트에서 실행해 주세요.")


def execute(command):
    result = subprocess.run([str(part) for part in command], capture_output=True, text=True, check=False)
    if result.returncode:
        raise ReportError((result.stderr or result.stdout).strip()[-400:] or "리포트를 만들지 못했습니다.")


def render(source, output, *, pdf=False, overwrite=False, root=ROOT, run=execute):
    source, output = Path(source), Path(output)
    if source.suffix.lower() != ".json" or not source.is_file():
        raise ReportError("입력은 리포트 내용이 담긴 .json 파일이어야 합니다.")
    if output.suffix.lower() != ".html":
        raise ReportError("출력 파일 이름은 .html로 끝나야 합니다.")
    try:
        json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ReportError("입력 JSON을 읽지 못했습니다.") from None
    folder = scripts_folder(root)
    extra = ["--overwrite"] if overwrite else []
    run((sys.executable, folder / "render_report.py", source, output, *extra))
    made = {"html": str(output)}
    if pdf:
        run((sys.executable, folder / "render_pdf.py", output, output.with_suffix(".pdf"), *extra))
        made["pdf"] = str(output.with_suffix(".pdf"))
    made["standardDesign"] = not output.is_file() or check([output])["files"][0]["standardDesign"]
    return made


def check(paths):
    files = []
    for path in paths:
        path = Path(path)
        if path.suffix.lower() not in (".html", ".htm") or not path.is_file():
            raise ReportError(f"HTML 파일이 아닙니다: {path.name}")
        page = path.read_text(encoding="utf-8", errors="ignore")
        standard = MARK in page[:4000] or all(name in page for name in EARLIER)
        files.append({"file": str(path), "standardDesign": standard,
                      "fix": None if standard else "리포트 내용을 JSON으로 옮겨 report.py render로 다시 만들어 주세요."})
    return {"allStandard": all(item["standardDesign"] for item in files), "files": files}


def main():
    parser = argparse.ArgumentParser(description="모든 리포트를 같은 디자인으로 만든다")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("render", help="리포트 JSON을 표준 디자인의 HTML(과 PDF)로 만들기")
    make.add_argument("input")
    make.add_argument("output")
    make.add_argument("--pdf", action="store_true", help="같은 이름의 PDF도 만들기")
    make.add_argument("--overwrite", action="store_true")
    look = commands.add_parser("check", help="HTML 파일이 표준 디자인으로 만들어졌는지 확인")
    look.add_argument("files", nargs="+")
    args = parser.parse_args()
    try:
        result = render(args.input, args.output, pdf=args.pdf, overwrite=args.overwrite) if args.command == "render" else check(args.files)
    except ReportError as failure:
        print(f"리포트 작업 실패: {failure}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("allStandard", result.get("standardDesign", True)) else 1


if __name__ == "__main__":
    sys.exit(main())
