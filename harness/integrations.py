"""Opt-in adapters for public market research and offline paper simulation."""

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

from install_integrations import RUNTIME, clean_environment, is_installed, python_path, read_lock
from research import research_plan, research_symbol
from toss_client import HarnessError
from workflows import ET


TOOLS = ("tradingagents", "openbb", "ai-hedge-fund", "financial-services")
FINANCE_SKILLS = {
    "earnings": ("earnings-reviewer", ("earnings-preview", "earnings-analysis", "model-update")),
    "market": ("market-researcher", ("competitive-analysis", "comps-analysis", "sector-overview")),
    "valuation": ("valuation-reviewer", ("ic-memo", "returns-analysis", "portfolio-monitoring")),
    "model": ("financial-analysis", ("dcf-model", "comps-analysis")),
}
DEBATE_KEY = "STOCK_HARNESS_DEBATE_KEY"
PAPER_DEMO = {
    "dataScope": "synthetic-only",
    "currency": "USD",
    "startingCash": 10000,
    "trades": [
        {"day": "2024-01-02", "symbol": "DEMO", "side": "buy", "quantity": 10, "price": 100},
        {"day": "2024-01-05", "symbol": "DEMO", "side": "sell", "quantity": 4, "price": 110},
    ],
}

# Child programs receive fixed code, validated JSON, and an empty working
# directory. Any upstream logging stays off the harness output channel.
OPENBB_SETUP = """
import asyncio
from openbb_core.app import constants
from pathlib import Path
constants.OPENBB_DIRECTORY = Path.cwd() / ".openbb_platform"
constants.USER_SETTINGS_PATH = constants.OPENBB_DIRECTORY / "user_settings.json"
constants.SYSTEM_SETTINGS_PATH = constants.OPENBB_DIRECTORY / "system_settings.json"
constants.OPENBB_DIRECTORY.mkdir()
constants.USER_SETTINGS_PATH.write_text(json.dumps({"preferences": {
    "cache_directory": str(Path.cwd() / "cache"),
    "data_directory": str(Path.cwd()),
}}))
"""

OPENBB_PRICE = OPENBB_SETUP + """
from openbb_nasdaq.models.equity_historical import NasdaqEquityHistoricalFetcher

items = asyncio.run(NasdaqEquityHistoricalFetcher.fetch_data(
    {"symbol": payload["symbol"], "start_date": payload["start"], "end_date": payload["end"]}, {}
))
result = [
    {field: getattr(item, field) for field in ("date", "open", "high", "low", "close", "volume")}
    for item in items
]
"""

OPENBB_FILINGS = OPENBB_SETUP + """
from openbb_sec.models.company_filings import SecCompanyFilingsFetcher

items = asyncio.run(SecCompanyFilingsFetcher.fetch_data(
    {"symbol": payload["symbol"], "form_type": "10-K,10-Q,8-K",
     "limit": payload["limit"], "use_cache": False}, {}
))
result = [
    {field: getattr(item, field) for field in ("filing_date", "report_date",
        "report_type", "filing_detail_url", "report_url")}
    for item in items
]
"""

PAPER_RUN = """
from hedge_fund.brokers import Order, SimBroker, TradingCosts

book = SimBroker(cash=payload["startingCash"], costs=TradingCosts(
    spread_bps=0, commission_per_share=0, impact_coefficient=0, min_trade_pct=0
))
fills = []
for trade in payload["trades"]:
    fill = book.place_order(Order(
        ticker=trade["symbol"], side=trade["side"], quantity=trade["quantity"], price=trade["price"]
    ))
    fills.append({"day": trade["day"], **fill.model_dump(), "cashAfter": round(book.cash(), 2)})
result = {
    "fills": fills,
    "cash": round(book.cash(), 2),
    "positions": {symbol: position.shares for symbol, position in book.positions().items()},
}
"""

TRADING_DEBATE = """
from pathlib import Path
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = dict(DEFAULT_CONFIG, llm_provider="openai", deep_think_llm=payload["model"],
    quick_think_llm=payload["model"], deep_think_provider="openai",
    quick_think_provider="openai", results_dir="results", data_cache_dir="cache",
    memory_log_path=str(Path.cwd() / "memory.md"), checkpoint_enabled=False,
    max_debate_rounds=1, max_risk_discuss_rounds=1, output_language="Korean")
graph = TradingAgentsGraph(config=config)
state, _ = graph.propagate(payload["symbol"], payload["date"])
debate = state["investment_debate_state"]
risk = state["risk_debate_state"]
result = {
    "bull": debate["bull_history"],
    "bear": debate["bear_history"],
    "risk": {key: risk[key] for key in ("aggressive_history", "conservative_history", "neutral_history")},
    "decision": state["final_trade_decision"],
}
"""


def run_adapter(name, code, payload, *, timeout=60, debate_key=None):
    if not is_installed(name, read_lock()[name], RUNTIME):
        raise HarnessError(f"{name} 설치가 필요합니다. python3 harness/install_integrations.py")
    environment = clean_environment()
    if debate_key is not None:
        environment["OPENAI_API_KEY"] = debate_key
    script = (
        "import json, sys\nfrom pathlib import Path\npayload = json.load(sys.stdin)\n"
        + code + "\nPath('result.json').write_text(json.dumps(result, default=str, allow_nan=False))\n"
    )
    try:
        with tempfile.TemporaryDirectory(prefix="stock-harness-") as work:
            subprocess.run(
                [str(python_path(RUNTIME / name)), "-I", "-c", script],
                input=json.dumps(payload, allow_nan=False), text=True, cwd=work, env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=timeout,
            )
            return json.loads((Path(work) / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, subprocess.SubprocessError):
        raise HarnessError(f"{name} 실행 결과를 받아오지 못했습니다. 설치 상태와 데이터 제공처를 확인해 주세요.") from None


def doctor():
    entries = read_lock()
    return {
        name: {"installed": is_installed(name, entries[name], RUNTIME), "commit": entries[name]["commit"]}
        for name in TOOLS
    }


def plan(symbol):
    result = research_plan(symbol, datetime.now(timezone.utc))
    result["tools"] = {
        "publicData": {"name": "openbb", "providers": ["Nasdaq", "SEC EDGAR"]},
        "debate": {"name": "tradingagents", "mode": "optional-public-only-model-run"},
        "earningsAndValuation": {"name": "financial-services", "mode": "local-skills"},
        "simulation": {"name": "ai-hedge-fund", "mode": "offline-paper"},
    }
    return result


def parse_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise HarnessError("날짜는 YYYY-MM-DD 형식으로 입력해 주세요.")
    return date.fromisoformat(value)


def price(symbol, start, end):
    symbol = research_symbol(symbol)
    first, last = parse_day(start), parse_day(end)
    if not first <= last < datetime.now(ET).date() or last - first > timedelta(days=366):
        raise HarnessError("미국 동부 기준 어제까지 최대 1년 범위로 입력해 주세요.")
    rows = run_adapter("openbb", OPENBB_PRICE, {"symbol": symbol, "start": start, "end": end})
    rows = sorted((row for row in rows if start <= row["date"] <= end), key=lambda row: row["date"])
    if not rows:
        raise HarnessError("Nasdaq에서 지정한 구간의 일봉을 받지 못했습니다.")
    return {
        "dataScope": "public-market", "symbol": symbol,
        "source": "https://www.nasdaq.com/market-activity/stocks",
        "provider": "Nasdaq via OpenBB", "interval": "1d", "currency": "USD",
        "retrievedAtEt": datetime.now(ET).isoformat(timespec="seconds"), "bars": rows,
    }


def filings(symbol, limit):
    symbol = research_symbol(symbol)
    if not 1 <= limit <= 25:
        raise HarnessError("조회할 공시 개수는 1~25건으로 입력해 주세요.")
    rows = run_adapter("openbb", OPENBB_FILINGS, {"symbol": symbol, "limit": limit})
    if not rows:
        raise HarnessError("SEC에서 해당 공시를 받지 못했습니다.")
    for row in rows:
        for key in ("filing_detail_url", "report_url"):
            url = urlsplit(row[key] or "")
            if url.scheme != "https" or url.netloc not in ("www.sec.gov", "sec.gov"):
                raise HarnessError("SEC 공식 공시 주소를 확인할 수 없습니다.")
    return {
        "dataScope": "public-filings", "symbol": symbol,
        "source": "https://www.sec.gov/edgar/search/",
        "provider": "SEC EDGAR via OpenBB",
        "retrievedAtEt": datetime.now(ET).isoformat(timespec="seconds"), "filings": rows[:limit],
    }


def financial_skills(topic):
    name = "financial-services"
    entry = read_lock()[name]
    if not is_installed(name, entry, RUNTIME):
        raise HarnessError(f"{name} 설치가 필요합니다. python3 harness/install_integrations.py")
    plugin, skills = FINANCE_SKILLS[topic]
    directory = RUNTIME / name / "plugins" / plugin
    paths = [directory / "skills" / skill / "SKILL.md" for skill in skills]
    if not all(path.is_file() for path in paths):
        raise HarnessError("설치한 금융 스킬 목록이 고정 버전과 일치하지 않습니다.")
    return {
        "dataScope": "public-research", "topic": topic, "plugin": str(directory),
        "skills": [str(path) for path in paths],
        "source": f"https://github.com/{entry['repository']}/tree/{entry['commit']}",
    }


def dollars(value):
    try:
        if type(value) not in (int, float, str) or len(str(value)) > 20:
            raise InvalidOperation
        amount = Decimal(str(value))
        if not amount.is_finite() or not (0 < amount <= Decimal("1000000000")):
            raise InvalidOperation
        if amount != amount.quantize(Decimal("0.01")):
            raise InvalidOperation
        return amount
    except InvalidOperation:
        raise HarnessError("USD 금액은 0보다 크고 소수점 두 자리 이내여야 합니다.") from None


def paper_payload(document):
    if (not isinstance(document, dict) or set(document) != set(PAPER_DEMO)
            or document["dataScope"] != "synthetic-only" or document["currency"] != "USD"):
        raise HarnessError("가상 USD 시나리오에는 dataScope, currency, startingCash, trades만 입력해 주세요.")
    trades = document["trades"]
    if not isinstance(trades, list) or not 1 <= len(trades) <= 1000:
        raise HarnessError("모의 체결 행은 1개에서 1,000개까지 입력할 수 있습니다.")

    cash = starting_cash = dollars(document["startingCash"])
    positions = {}
    clean_trades = []
    previous = date.min
    for trade in trades:
        if not isinstance(trade, dict) or set(trade) != {"day", "symbol", "side", "quantity", "price"}:
            raise HarnessError("모의 체결 행에는 day, symbol, side, quantity, price가 필요합니다.")
        day = parse_day(trade["day"])
        if day < previous:
            raise HarnessError("모의 체결 행을 날짜순으로 정렬해 주세요.")
        previous = day
        if not isinstance(trade["symbol"], str):
            raise HarnessError("종목코드를 확인해 주세요.")
        symbol = research_symbol(trade["symbol"])
        side, quantity = trade["side"], trade["quantity"]
        if side not in ("buy", "sell") or type(quantity) is not int or not 1 <= quantity <= 1000000:
            raise HarnessError("모의 체결 방향은 buy 또는 sell이며 수량은 1~1,000,000 사이의 정수입니다.")
        mark = dollars(trade["price"])
        direction = 1 if side == "buy" else -1
        positions[symbol] = positions.get(symbol, 0) + quantity * direction
        cash -= mark * quantity * direction
        if cash < 0 or positions[symbol] < 0:
            raise HarnessError("가상 현금이나 보유 수량을 초과하는 체결이 있습니다.")
        clean_trades.append({**trade, "symbol": symbol, "price": float(mark)})
    return {**document, "startingCash": float(starting_cash), "trades": clean_trades}


def paper(document):
    payload = paper_payload(document)
    result = run_adapter("ai-hedge-fund", PAPER_RUN, payload)
    return {"dataScope": "synthetic-only", "mode": "paper", "currency": "USD",
            "startingCash": payload["startingCash"], "costModel": "zero", **result}


def debate(symbol, day, model):
    symbol = research_symbol(symbol)
    if parse_day(day) != datetime.now(ET).date():
        raise HarnessError("외부 토론은 오늘 미국 동부 날짜만 지원합니다. 과거 검증에는 research-check와 replay-alert를 사용해 주세요.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", model):
        raise HarnessError("사용할 모델 ID를 확인해 주세요.")
    key = os.environ.get(DEBATE_KEY)
    if not key:
        raise HarnessError(f"요청을 보내려면 전용 OpenAI 키를 {DEBATE_KEY}로 지정해 주세요.")
    result = run_adapter(
        "tradingagents", TRADING_DEBATE, {"symbol": symbol, "date": day, "model": model},
        timeout=900, debate_key=key,
    )
    return {"dataScope": "public-research", "mode": "model-opinions", "symbol": symbol,
            "dateEt": day, "model": model, "evidenceCheck": "required", **result}


def read_scenario(path):
    with Path(path).open("rb") as source:
        contents = source.read(2_000_001)
    if len(contents) > 2_000_000:
        raise HarnessError("모의 시나리오 JSON은 2MB 이하로 입력해 주세요.")
    return json.loads(contents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check pinned installs")
    commands.add_parser("plan", help="route public research").add_argument("symbol")
    price_cmd = commands.add_parser("price", help="fetch public Nasdaq bars via OpenBB")
    price_cmd.add_argument("symbol")
    price_cmd.add_argument("--start", required=True)
    price_cmd.add_argument("--end", required=True)
    filings_cmd = commands.add_parser("filings", help="fetch public SEC 10-K, 10-Q and 8-K filings via OpenBB")
    filings_cmd.add_argument("symbol")
    filings_cmd.add_argument("--limit", type=int, default=5)
    commands.add_parser("financial-skills", help="locate installed Anthropic skills").add_argument(
        "topic", choices=FINANCE_SKILLS
    )
    commands.add_parser("paper-demo", help="simulate two offline fills")
    commands.add_parser("paper", help="simulate a synthetic USD scenario").add_argument("scenario")
    debate_cmd = commands.add_parser("debate", help="run opt-in model debate on a public ticker")
    debate_cmd.add_argument("symbol")
    debate_cmd.add_argument("--date", required=True)
    debate_cmd.add_argument("--model", required=True)
    args = parser.parse_args()
    actions = {
        "doctor": doctor,
        "plan": lambda: plan(args.symbol),
        "price": lambda: price(args.symbol, args.start, args.end),
        "filings": lambda: filings(args.symbol, args.limit),
        "financial-skills": lambda: financial_skills(args.topic),
        "paper-demo": lambda: paper(PAPER_DEMO),
        "paper": lambda: paper(read_scenario(args.scenario)),
        "debate": lambda: debate(args.symbol, args.date, args.model),
    }
    try:
        print(json.dumps(actions[args.command](), ensure_ascii=False, indent=2, allow_nan=False))
    except HarnessError as exc:
        parser.exit(1, f"{exc}\n")
    except (OSError, ValueError):
        parser.exit(1, "파일, 날짜 또는 결과 형식을 확인해 주세요.\n")


if __name__ == "__main__":
    main()
