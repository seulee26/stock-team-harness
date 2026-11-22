"""Research wiki where the user chooses: this PC, a synced Google Drive folder, or a Drive or Notion connector."""

import argparse
from datetime import date, datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil

from toss_client import HarnessError
from workflows import KST


ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".local" / "wiki" / "config.json"
MODES = ("local", "drive-folder", "drive-connector", "notion-connector")
CONNECTORS = {"drive-connector": "Google Drive", "notion-connector": "Notion"}
KINDS = {
    "company": "기업", "sector": "산업", "macro": "매크로", "market": "시황",
    "strategy": "전략", "thesis": "투자 논지", "quant": "퀀트", "other": "기타",
}
SOURCE_TYPES = (".html", ".pdf", ".md")
MAX_SOURCE_BYTES = 30_000_000
HOLDINGS = re.compile(r"계좌번호|보유 ?수량|평가 ?금액|매수 ?가능 ?금액|accountNumber|cashBuyingPower", re.I)
LAYOUT = (
    "pages/<종류>/<대상>.md  대상마다 한 장. 새 리포트가 나올 때마다 날짜별 기록이 쌓입니다.",
    "sources/<연도>/         리포트 원본(HTML, PDF, MD)",
    "index.md               전체 목차 (자동 생성)",
    "log.md                 언제 무엇을 넣었는지 기록",
)


def today():
    return datetime.now(KST).date().isoformat()


def clean_day(value):
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
            raise ValueError
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise HarnessError("날짜는 달력에 있는 날로 YYYY-MM-DD 형식으로 입력해 주세요.") from None


def slug(value):
    text = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", str(value).strip()).strip("-.")
    if not text or len(text) > 60:
        raise HarnessError("대상 이름은 한글, 영문, 숫자로 1~60자 안에서 입력해 주세요. 예: NVDA, 005930, 반도체")
    return text


def line(value, label, limit):
    text = " ".join(str(value).split())
    if not text or len(text) > limit:
        raise HarnessError(f"{label} 항목은 1~{limit}자로 입력해 주세요.")
    return text


def load_config(path=CONFIG):
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HarnessError("위키를 아직 만들지 않았습니다. wiki.py init으로 저장 위치를 먼저 정해 주세요.") from None
    except (OSError, ValueError):
        raise HarnessError("위키 설정 파일을 읽지 못했습니다.") from None
    if not isinstance(config, dict) or config.get("mode") not in MODES:
        raise HarnessError("위키 설정 파일의 형식이 올바르지 않습니다.")
    return config


def wiki_root(config):
    if config["mode"] in CONNECTORS:
        raise HarnessError(f"이 위키는 {CONNECTORS[config['mode']]} 커넥터로 관리하도록 설정돼 있습니다. 파일 작업은 커넥터 도구로 합니다.")
    root = Path(config["path"])
    if not (root / "index.md").is_file():
        raise HarnessError("위키 폴더를 찾지 못했습니다. 폴더가 옮겨졌다면 wiki.py init으로 다시 지정해 주세요.")
    return root


def init(mode, path=None, *, switch=False, config_path=CONFIG):
    if mode not in MODES:
        raise HarnessError("저장 방식은 " + ", ".join(MODES) + " 중에서 골라 주세요.")
    try:
        previous = load_config(config_path)
    except HarnessError:
        previous = None
    target = None if mode in CONNECTORS or not path else str(Path(path).expanduser().resolve())
    if previous and (previous["mode"], previous.get("path")) != (mode, target) and not switch:
        where = previous.get("path") or CONNECTORS.get(previous["mode"], "") + " 커넥터"
        raise HarnessError(f"이미 위키가 있습니다({previous['mode']}: {where}). 저장 위치를 바꾸려면 --switch를 붙여 주세요. "
                           "기존 문서는 지워지지 않지만 새 위치로 옮겨지지도 않습니다.")
    config = {"mode": mode, "createdOn": today()}
    if mode in CONNECTORS:
        config["path"] = None
    else:
        if not path:
            raise HarnessError("위키를 둘 폴더를 --path로 지정해 주세요.")
        root = Path(path).expanduser().resolve()
        if root == ROOT or ROOT in root.parents and ".local" not in root.parts and root.name != "wiki":
            raise HarnessError("하네스 폴더 안에 둘 때는 폴더 이름을 wiki로 해 주세요. 예: --path ./wiki")
        for folder in ("pages", "sources"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        if not (root / "log.md").exists():
            (root / "log.md").write_text("# 기록\n\n", encoding="utf-8")
        config["path"] = str(root)
        rebuild_index(root)
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"dataScope": "local-wiki", **config, "layout": list(LAYOUT),
            "next": ("커넥터 도구로 Drive에 같은 구조의 폴더를 만듭니다." if mode == "drive-connector"
                     else "wiki.py notion-entry로 넣을 내용을 만들고 Notion 커넥터 도구로 데이터베이스에 넣습니다." if mode == "notion-connector"
                     else "리포트를 만들 때마다 wiki.py add로 넣습니다.")}


def read_pages(root):
    pages = []
    for path in sorted((root / "pages").glob("*/*.md")):
        text = path.read_text(encoding="utf-8")
        entries = re.findall(r"^### (\d{4}-\d{2}-\d{2}) · (.+)$", text, re.M)
        pages.append({"kind": path.parent.name, "subject": path.stem, "path": path,
                      "entries": entries, "text": text})
    return pages


def rebuild_index(root):
    pages = read_pages(root)
    lines = ["# 리서치 위키", "", f"마지막 정리: {today()} · 문서 {len(pages)}장", ""]
    for kind, label in KINDS.items():
        group = [page for page in pages if page["kind"] == kind]
        if not group:
            continue
        lines += [f"## {label}", ""]
        for page in group:
            latest = max(page["entries"])[0] if page["entries"] else "기록 없음"
            lines.append(f"- [{page['subject']}](pages/{kind}/{page['subject']}.md) · 기록 {len(page['entries'])}건 · 최근 {latest}")
        lines.append("")
    (root / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return len(pages)


def add(config, source, kind, subject, title, summary, day=None, tags=(), allow_holdings=False):
    root = wiki_root(config)
    if kind not in KINDS:
        raise HarnessError("종류는 " + ", ".join(KINDS) + " 중에서 골라 주세요.")
    source = Path(source)
    if source.suffix.lower() not in SOURCE_TYPES or source.is_symlink() or not source.is_file():
        raise HarnessError("넣을 파일은 .html, .pdf, .md 중 하나여야 합니다.")
    body = source.read_bytes()
    if not body or len(body) > MAX_SOURCE_BYTES:
        raise HarnessError("넣을 파일은 비어 있지 않고 30MB 이하여야 합니다.")
    holds = source.suffix.lower() != ".pdf" and HOLDINGS.search(body.decode("utf-8", "ignore"))
    if holds and not (allow_holdings and config["mode"] == "local"):
        raise HarnessError("보유 수량이나 계좌 정보가 들어 있는 파일입니다. Drive 위키에는 넣지 않습니다. "
                           "내 PC 위키에만 --allow-holdings로 넣을 수 있습니다.")
    day, name = clean_day(day or today()), slug(subject)
    title, summary = line(title, "제목", 120), line(summary, "요약", 1500)
    tags = [slug(tag) for tag in tags][:8]
    target = root / "sources" / day[:4] / f"{day}-{kind}-{name}{source.suffix.lower()}"
    if target.exists():
        raise HarnessError("같은 날짜, 같은 종류, 같은 대상의 원본이 이미 있습니다. 날짜나 대상을 바꿔 주세요.")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    page = root / "pages" / kind / f"{name}.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    if not page.exists():
        page.write_text(f"# {name}\n\n- 종류: {KINDS[kind]}\n\n## 기록\n", encoding="utf-8")
    relative = Path("..") / ".." / target.relative_to(root)
    entry = f"\n### {day} · {title}\n\n{summary}\n\n- 원본: [{target.name}]({relative.as_posix()})\n"
    if tags:
        entry += "- 태그: " + ", ".join(tags) + "\n"
    with page.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    with (root / "log.md").open("a", encoding="utf-8") as handle:
        handle.write(f"- {today()} · 추가 · {KINDS[kind]} · {name} · {title}\n")
    count = rebuild_index(root)
    return {"dataScope": "local-wiki", "page": str(page), "source": str(target), "pages": count}


def search(config, query, limit=20):
    root = wiki_root(config)
    needle = line(query, "검색어", 80).lower()
    hits = []
    for page in read_pages(root):
        if needle in page["subject"].lower() and needle not in page["text"].lower():
            hits.append({"page": f"pages/{page['kind']}/{page['subject']}.md", "line": 1, "text": page["subject"]})
        for number, text in enumerate(page["text"].splitlines(), 1):
            if needle in text.lower():
                hits.append({"page": f"pages/{page['kind']}/{page['subject']}.md", "line": number, "text": text.strip()[:200]})
                if len(hits) >= limit:
                    return {"dataScope": "local-wiki", "query": query, "hits": hits, "truncated": True}
    return {"dataScope": "local-wiki", "query": query, "hits": hits, "truncated": False}


def lint(config, stale_days=90):
    root = wiki_root(config)
    if not 1 <= stale_days <= 3650:
        raise HarnessError("오래된 기준은 1~3650일로 입력해 주세요.")
    now = date.fromisoformat(today())
    stale, empty, broken = [], [], []
    for page in read_pages(root):
        name = f"pages/{page['kind']}/{page['subject']}.md"
        if not page["entries"]:
            empty.append(name)
        elif (now - date.fromisoformat(max(page["entries"])[0])).days > stale_days:
            stale.append({"page": name, "latest": max(page["entries"])[0]})
        for link in re.findall(r"\]\((\.\./\.\./sources/[^)]+)\)", page["text"]):
            if not (page["path"].parent / link).resolve().is_file():
                broken.append({"page": name, "link": link})
    linked = {(page["path"].parent / link).resolve() for page in read_pages(root)
              for link in re.findall(r"\]\((\.\./\.\./sources/[^)]+)\)", page["text"])}
    orphans = [path.relative_to(root).as_posix() for path in sorted((root / "sources").glob("*/*"))
               if path.is_file() and path.resolve() not in linked]
    return {"dataScope": "local-wiki", "staleDays": stale_days, "stale": stale, "empty": empty,
            "brokenLinks": broken, "unlinkedSources": orphans,
            "clean": not (stale or empty or broken or orphans)}


class Outline(HTMLParser):
    """Collect the report title and section headings without keeping the body."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tag, self.title, self.headings = None, "", []

    def handle_starttag(self, tag, attrs):
        if tag in ("title", "h1", "h2"):
            self.tag = tag
            if tag == "h2":
                self.headings.append("")

    def handle_endtag(self, tag):
        if tag == self.tag:
            self.tag = None

    def handle_data(self, data):
        if self.tag == "h2":
            self.headings[-1] += data
        elif self.tag and not (self.tag == "title" and self.title):
            self.title = (self.title + data) if self.tag == "h1" else data


def notion_entry(source, kind, subject, title, summary, day=None, tags=(), link=None):
    """Build a short Notion database row from a report on this PC. Nothing is sent anywhere."""
    if kind not in KINDS:
        raise HarnessError("종류는 " + ", ".join(KINDS) + " 중에서 골라 주세요.")
    source = Path(source)
    if source.suffix.lower() not in SOURCE_TYPES or source.is_symlink() or not source.is_file():
        raise HarnessError("넣을 파일은 .html, .pdf, .md 중 하나여야 합니다.")
    body = source.read_bytes()
    if not body or len(body) > MAX_SOURCE_BYTES:
        raise HarnessError("넣을 파일은 비어 있지 않고 30MB 이하여야 합니다.")
    text = "" if source.suffix.lower() == ".pdf" else body.decode("utf-8", "ignore")
    if HOLDINGS.search(text):
        raise HarnessError("보유 수량이나 계좌 정보가 들어 있는 파일입니다. Notion 위키에는 넣지 않습니다. 내 PC 위키를 써 주세요.")
    if link is not None and not re.fullmatch(r"https://[^\s<>\"']{4,500}", link):
        raise HarnessError("원본 링크는 https:// 로 시작하는 주소여야 합니다.")
    day, name = clean_day(day or today()), slug(subject)
    title, summary = line(title, "제목", 120), line(summary, "요약", 1500)
    tags = [slug(tag) for tag in tags][:8]
    outline = Outline()
    if source.suffix.lower() == ".html":
        outline.feed(text)
    elif source.suffix.lower() == ".md":
        outline.headings = [row[3:] for row in text.splitlines() if row.startswith("## ")]
    headings = [" ".join(item.split())[:80] for item in outline.headings if item.strip()][:14]
    content = f"## 결론\n\n{summary}\n"
    if headings:
        content += "\n## 리포트 목차\n\n" + "".join(f"- {item}\n" for item in headings)
    content += f"\n## 원본\n\n- 파일: {source.name} ({len(body) // 1024:,}KB)\n"
    content += f"- 링크: {link}\n" if link else "- 원본 파일은 내 PC나 드라이브에 있습니다. Notion에는 요약만 넣었습니다.\n"
    content += "\n조사 기록이며 투자 조언이나 권유가 아닙니다.\n"
    fields = [
        {"name": "대상", "type": "title", "value": name},
        {"name": "종류", "type": "select", "value": KINDS[kind], "options": list(KINDS.values())},
        {"name": "기준일", "type": "date", "value": day},
        {"name": "제목", "type": "text", "value": title},
        {"name": "결론", "type": "text", "value": summary},
        {"name": "태그", "type": "multi_select", "value": tags},
        {"name": "원본", "type": "url", "value": link},
    ]
    return {
        "dataScope": "notion-payload", "database": "리서치 위키", "fields": fields, "content": content,
        "sizes": {"reportChars": len(text) or None, "payloadChars": len(content) + sum(len(str(item["value"] or "")) for item in fields)},
        "next": "Notion 커넥터의 데이터베이스 '리서치 위키'에 fields를 속성으로, content를 본문으로 한 행을 만듭니다. "
                "데이터베이스가 없으면 fields의 name과 type으로 먼저 만들고, 어디에 만들지 사용자에게 확인받습니다.",
    }


def status(config):
    if config["mode"] in CONNECTORS:
        name = CONNECTORS[config["mode"]]
        return {"dataScope": "local-wiki", **config, "note": f"{name} 커넥터로 관리합니다. 문서 수는 {name}에서 확인합니다."}
    root = wiki_root(config)
    pages = read_pages(root)
    return {"dataScope": "local-wiki", **config, "pages": len(pages),
            "entries": sum(len(page["entries"]) for page in pages),
            "sources": sum(1 for path in (root / "sources").glob("*/*") if path.is_file())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("init", help="저장 위치를 정하고 위키 폴더를 만듭니다")
    start.add_argument("--mode", required=True, help=", ".join(MODES))
    start.add_argument("--path", help="위키 폴더. drive-folder는 PC에 동기화된 Google Drive 폴더 안의 경로")
    start.add_argument("--switch", action="store_true", help="이미 있는 위키의 저장 위치를 바꿉니다")
    put = commands.add_parser("add", help="리포트를 위키에 넣습니다")
    put.add_argument("file")
    put.add_argument("--kind", required=True, help=", ".join(KINDS))
    put.add_argument("--subject", required=True, help="대상. 예: NVDA, 005930, 반도체")
    put.add_argument("--title", required=True)
    put.add_argument("--summary", required=True, help="결론 두세 줄")
    put.add_argument("--date", help="리포트 기준일 (기본: 오늘)")
    put.add_argument("--tag", action="append", default=[])
    put.add_argument("--allow-holdings", action="store_true", help="보유 내역이 든 파일을 내 PC 위키에 넣습니다")
    note = commands.add_parser("notion-entry", help="Notion 데이터베이스에 넣을 짧은 기록을 만듭니다 (전송하지 않음)")
    note.add_argument("file")
    note.add_argument("--kind", required=True, help=", ".join(KINDS))
    note.add_argument("--subject", required=True)
    note.add_argument("--title", required=True)
    note.add_argument("--summary", required=True, help="결론 두세 줄")
    note.add_argument("--date", help="리포트 기준일 (기본: 오늘)")
    note.add_argument("--tag", action="append", default=[])
    note.add_argument("--link", help="원본을 볼 수 있는 https 주소 (예: 드라이브 링크)")
    commands.add_parser("index", help="목차를 다시 만듭니다")
    find = commands.add_parser("search", help="위키에서 찾습니다")
    find.add_argument("query")
    check = commands.add_parser("lint", help="오래된 문서, 빈 문서, 끊어진 링크를 찾습니다")
    check.add_argument("--stale-days", type=int, default=90)
    commands.add_parser("status", help="위키 위치와 문서 수")
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = init(args.mode, args.path, switch=args.switch)
        elif args.command == "notion-entry":
            result = notion_entry(args.file, args.kind, args.subject, args.title, args.summary, args.date, args.tag, args.link)
        else:
            config = load_config()
            if args.command == "add":
                result = add(config, args.file, args.kind, args.subject, args.title, args.summary,
                             args.date, args.tag, args.allow_holdings)
            elif args.command == "index":
                result = {"dataScope": "local-wiki", "pages": rebuild_index(wiki_root(config))}
            elif args.command == "search":
                result = search(config, args.query)
            elif args.command == "lint":
                result = lint(config, args.stale_days)
            else:
                result = status(config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except HarnessError as exc:
        parser.exit(1, f"{exc}\n")
    except (OSError, ValueError):
        parser.exit(1, "입력값과 폴더 권한을 확인해 주세요.\n")


if __name__ == "__main__":
    main()
