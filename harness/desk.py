"""Local research journal: report catalog, thesis log, decision scorecard and event calendar."""

import argparse
from datetime import date, datetime, timedelta
import json
import math
import os
from pathlib import Path
import re
import tempfile

from toss_client import HarnessError
from workflows import KST


ROOT = Path(__file__).resolve().parent.parent
JOURNAL = ROOT / ".local" / "desk" / "journal.json"
CATALOG = Path(__file__).with_name("report-catalog.json")
MARKETS = ("US", "KR", "FUTURES", "MACRO")
RATINGS = {
    "strong-buy": ("적극 매수 검토", 1), "buy": ("매수 검토", 1), "hold": ("관망", 0),
    "reduce": ("비중 축소 검토", -1), "sell": ("매도 검토", -1),
}
IMPACTS = ("strengthens", "weakens", "neutral")
EVENT_KINDS = ("earnings", "macro", "corporate", "expiry", "other")
LIMIT = 2000


def today():
    return datetime.now(KST).date()


def clean_symbol(value):
    symbol = str(value).upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.=^-]{0,14}", symbol):
        raise HarnessError("종목이나 지표 기호를 확인해 주세요. 예: NVDA, 005930, ES=F")
    return symbol


def clean_text(value, label, limit=400):
    text = " ".join(str(value).split())
    if not text or len(text) > limit:
        raise HarnessError(f"{label} 항목은 1~{limit}자로 입력해 주세요.")
    return text


def clean_number(value, label):
    if value is None:
        return None
    if not math.isfinite(value) or value <= 0:
        raise HarnessError(f"{label} 값은 0보다 큰 숫자로 입력해 주세요.")
    return value


def clean_day(value):
    if value is None:
        return today().isoformat()
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
            raise ValueError
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise HarnessError("날짜는 달력에 있는 날로 YYYY-MM-DD 형식으로 입력해 주세요.") from None


def load(path=JOURNAL):
    try:
        journal = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        journal = {}
    except (OSError, ValueError):
        raise HarnessError("리서치 기록 파일을 읽지 못했습니다. 파일을 확인해 주세요.") from None
    if not isinstance(journal, dict):
        raise HarnessError("리서치 기록 파일의 형식이 올바르지 않습니다.")
    for key in ("theses", "decisions", "events"):
        if not isinstance(journal.setdefault(key, []), list):
            raise HarnessError("리서치 기록 파일의 형식이 올바르지 않습니다.")
    return journal


def save(journal, path=JOURNAL):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".journal-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(journal, file, ensure_ascii=False, indent=2)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def reports():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def thesis_add(journal, symbol, market, statement, pillars, risks, target=None, stop=None, day=None):
    symbol = clean_symbol(symbol)
    if market not in MARKETS:
        raise HarnessError("시장은 US, KR, FUTURES, MACRO 중에서 골라 주세요.")
    if not 1 <= len(pillars) <= 5 or not 1 <= len(risks) <= 5:
        raise HarnessError("논지의 근거와 깨지는 조건은 각각 1~5개로 적어 주세요.")
    if any(item["symbol"] == symbol and item["status"] == "open" for item in journal["theses"]):
        raise HarnessError("이미 열려 있는 논지가 있습니다. thesis-update로 기록하거나 thesis-close로 닫아 주세요.")
    if len(journal["theses"]) >= LIMIT:
        raise HarnessError("기록이 너무 많습니다. 오래된 기록을 정리해 주세요.")
    entry = {
        "symbol": symbol, "market": market, "status": "open", "openedOn": clean_day(day),
        "statement": clean_text(statement, "논지"),
        "pillars": [clean_text(item, "근거") for item in pillars],
        "invalidators": [clean_text(item, "깨지는 조건") for item in risks],
        "target": clean_number(target, "목표 가격"), "stop": clean_number(stop, "손절 가격"),
        "updates": [],
    }
    journal["theses"].append(entry)
    return entry


def open_thesis(journal, symbol):
    symbol = clean_symbol(symbol)
    for item in journal["theses"]:
        if item["symbol"] == symbol and item["status"] == "open":
            return item
    raise HarnessError("열려 있는 논지가 없습니다. thesis-add로 먼저 기록해 주세요.")


def thesis_update(journal, symbol, note, impact, conviction, day=None):
    entry = open_thesis(journal, symbol)
    if impact not in IMPACTS or not 1 <= conviction <= 5:
        raise HarnessError("영향은 strengthens·weakens·neutral, 확신도는 1~5로 입력해 주세요.")
    if len(entry["updates"]) >= 500:
        raise HarnessError("이 논지의 기록이 너무 많습니다. 닫고 새로 열어 주세요.")
    entry["updates"].append({"date": clean_day(day), "note": clean_text(note, "메모"),
                             "impact": impact, "conviction": conviction})
    return entry


def thesis_close(journal, symbol, reason, day=None):
    entry = open_thesis(journal, symbol)
    entry.update(status="closed", closedOn=clean_day(day), closeReason=clean_text(reason, "닫는 이유"))
    return entry


def decision_log(journal, symbol, market, rating, price, benchmark, benchmark_level, day=None):
    if rating not in RATINGS or market not in MARKETS:
        raise HarnessError("의견은 strong-buy·buy·hold·reduce·sell, 시장은 US·KR·FUTURES·MACRO 중에서 골라 주세요.")
    if len(journal["decisions"]) >= LIMIT:
        raise HarnessError("기록이 너무 많습니다. 오래된 기록을 정리해 주세요.")
    entry = {
        "id": len(journal["decisions"]) + 1, "symbol": clean_symbol(symbol), "market": market,
        "rating": rating, "ratingLabel": RATINGS[rating][0], "date": clean_day(day),
        "price": clean_number(price, "기준 가격"), "benchmark": clean_symbol(benchmark),
        "benchmarkLevel": clean_number(benchmark_level, "기준 지수"), "settled": None,
    }
    journal["decisions"].append(entry)
    return entry


def decision_score(journal, decision_id, price, benchmark_level, day=None):
    entry = next((item for item in journal["decisions"] if item["id"] == decision_id), None)
    if entry is None:
        raise HarnessError("해당 번호의 의견 기록이 없습니다. scorecard로 번호를 확인해 주세요.")
    settled_on = clean_day(day)
    if settled_on < entry["date"]:
        raise HarnessError("정산일은 의견을 낸 날 이후여야 합니다.")
    gain = clean_number(price, "현재 가격") / entry["price"] - 1
    base = clean_number(benchmark_level, "현재 지수") / entry["benchmarkLevel"] - 1
    direction = RATINGS[entry["rating"]][1]
    alpha = gain - base
    entry["settled"] = {
        "date": settled_on, "returnPct": round(gain * 100, 2), "benchmarkReturnPct": round(base * 100, 2),
        "alphaPct": round(alpha * 100, 2), "hit": None if direction == 0 else (alpha * direction > 0),
    }
    return entry


def scorecard(journal):
    settled = [item for item in journal["decisions"] if item["settled"]]
    by_rating = {}
    for item in settled:
        row = by_rating.setdefault(item["rating"], {"label": item["ratingLabel"], "count": 0, "alphaSum": 0.0})
        row["count"] += 1
        row["alphaSum"] += item["settled"]["alphaPct"]
    judged = [item for item in settled if item["settled"]["hit"] is not None]
    return {
        "dataScope": "local-journal", "decisions": len(journal["decisions"]), "settled": len(settled),
        "hitRatePct": round(sum(item["settled"]["hit"] for item in judged) / len(judged) * 100, 1) if judged else None,
        "byRating": {rating: {"label": row["label"], "count": row["count"],
                              "meanAlphaPct": round(row["alphaSum"] / row["count"], 2)}
                     for rating, row in by_rating.items()},
        "open": [{key: item[key] for key in ("id", "symbol", "ratingLabel", "date", "price", "benchmark")}
                 for item in journal["decisions"] if not item["settled"]],
        "note": "표본이 20건보다 적으면 우연과 실력을 구분하기 어렵습니다." if len(judged) < 20 else None,
    }


def event_add(journal, day, title, kind="other", impact="M", symbol=None):
    if kind not in EVENT_KINDS or impact not in ("H", "M", "L"):
        raise HarnessError("종류는 earnings·macro·corporate·expiry·other, 영향은 H·M·L로 입력해 주세요.")
    if len(journal["events"]) >= LIMIT:
        raise HarnessError("기록이 너무 많습니다. 오래된 일정을 정리해 주세요.")
    entry = {"date": clean_day(day), "title": clean_text(title, "일정 이름", 200), "kind": kind,
             "impact": impact, "symbol": clean_symbol(symbol) if symbol else None}
    journal["events"].append(entry)
    journal["events"].sort(key=lambda item: item["date"])
    return entry


def event_list(journal, days=30, start=None):
    if not 1 <= days <= 400:
        raise HarnessError("조회 기간은 1~400일로 입력해 주세요.")
    first = date.fromisoformat(clean_day(start))
    last = first + timedelta(days=days)
    return {"dataScope": "local-journal", "from": first.isoformat(), "to": last.isoformat(),
            "events": [item for item in journal["events"] if first.isoformat() <= item["date"] <= last.isoformat()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("reports", help="리포트 종류와 담당 스킬")

    add = commands.add_parser("thesis-add", help="투자 논지 기록")
    add.add_argument("symbol")
    add.add_argument("--market", required=True, help="US, KR, FUTURES, MACRO")
    add.add_argument("--statement", required=True)
    add.add_argument("--pillar", action="append", default=[], help="논지를 받치는 근거 (여러 번)")
    add.add_argument("--risk", action="append", default=[], help="논지가 깨지는 조건 (여러 번)")
    add.add_argument("--target", type=float)
    add.add_argument("--stop", type=float)
    update = commands.add_parser("thesis-update", help="논지에 새 사실 기록")
    update.add_argument("symbol")
    update.add_argument("--note", required=True)
    update.add_argument("--impact", required=True, help="strengthens, weakens, neutral")
    update.add_argument("--conviction", type=int, required=True)
    close = commands.add_parser("thesis-close", help="논지 닫기")
    close.add_argument("symbol")
    close.add_argument("--reason", required=True)
    commands.add_parser("thesis-list", help="논지 목록").add_argument("symbol", nargs="?")

    log = commands.add_parser("decision-log", help="의견을 기준 가격과 함께 기록")
    log.add_argument("symbol")
    log.add_argument("--market", required=True, help="US, KR, FUTURES, MACRO")
    log.add_argument("--rating", required=True, help="strong-buy, buy, hold, reduce, sell")
    log.add_argument("--price", type=float, required=True)
    log.add_argument("--benchmark", required=True, help="비교 지수 기호. 예: SPX, KOSPI, KOSDAQ")
    log.add_argument("--benchmark-level", type=float, required=True)
    score = commands.add_parser("decision-score", help="의견을 지수 대비로 정산")
    score.add_argument("id", type=int)
    score.add_argument("--price", type=float, required=True)
    score.add_argument("--benchmark-level", type=float, required=True)
    commands.add_parser("scorecard", help="의견 적중률과 초과수익")

    event = commands.add_parser("event-add", help="일정 기록")
    event.add_argument("date")
    event.add_argument("title")
    event.add_argument("--kind", default="other", help="earnings, macro, corporate, expiry, other")
    event.add_argument("--impact", default="M", help="H, M, L")
    event.add_argument("--symbol")
    listing = commands.add_parser("event-list", help="다가오는 일정")
    listing.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    try:
        if args.command == "reports":
            result = reports()
        else:
            journal = load()
            writes = True
            if args.command == "thesis-add":
                result = thesis_add(journal, args.symbol, args.market, args.statement, args.pillar, args.risk,
                                    args.target, args.stop)
            elif args.command == "thesis-update":
                result = thesis_update(journal, args.symbol, args.note, args.impact, args.conviction)
            elif args.command == "thesis-close":
                result = thesis_close(journal, args.symbol, args.reason)
            elif args.command == "decision-log":
                result = decision_log(journal, args.symbol, args.market, args.rating, args.price,
                                      args.benchmark, args.benchmark_level)
            elif args.command == "decision-score":
                result = decision_score(journal, args.id, args.price, args.benchmark_level)
            elif args.command == "event-add":
                result = event_add(journal, args.date, args.title, args.kind, args.impact, args.symbol)
            else:
                writes = False
                if args.command == "thesis-list":
                    wanted = clean_symbol(args.symbol) if args.symbol else None
                    result = {"dataScope": "local-journal",
                              "theses": [item for item in journal["theses"] if wanted in (None, item["symbol"])]}
                elif args.command == "scorecard":
                    result = scorecard(journal)
                else:
                    result = event_list(journal, args.days)
            if writes:
                save(journal)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except HarnessError as exc:
        parser.exit(1, f"{exc}\n")
    except (OSError, ValueError):
        parser.exit(1, "입력값과 기록 파일을 확인해 주세요.\n")


if __name__ == "__main__":
    main()
