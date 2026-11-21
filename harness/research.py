"""Public research planning, evidence checks, and a date-ordered alert replay."""

from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlsplit
import re

from toss_client import HarnessError
from workflows import ET, decimal_value, iso_time


ROLE_STAGES = (
    ("parallel", ("market", "fundamentals", "analyst-opinions")),
    ("parallel", ("valuation", "trade-timing")),
    ("review", ("risk-review",)),
)
ROLES = frozenset(role for _, roles in ROLE_STAGES for role in roles)
PUBLIC_QUOTE_SOURCE = "https://openapi.tossinvest.com/openapi-docs/latest/api-reference/Apis/MarketDataApi.md#getPrices"
PRIVATE_URL_KEYS = {"token", "access_token", "api_key", "apikey", "client_secret", "accountseq", "signature"}


def research_symbol(value):
    symbol = value.upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,14}", symbol):
        raise HarnessError("종목코드를 확인해 주세요.")
    return symbol


def research_plan(symbol, cutoff):
    return {
        "symbol": research_symbol(symbol),
        "asOfEt": cutoff.astimezone(ET).isoformat(timespec="seconds"),
        "dataScope": "public-market-and-filings",
        "stages": [{"mode": mode, "roles": list(roles)} for mode, roles in ROLE_STAGES],
        "reportGate": "research-check",
        "userOutput": "결론과 조건부터 짧게 전달",
    }


def market_packet(client, symbol):
    symbol = research_symbol(symbol)
    if not client.market_only:
        raise HarnessError("공개 시세 내보내기는 시장 조회 경로를 사용해야 합니다.")
    rows = [row for row in client.get("getPrices", symbols=symbol) if row.get("symbol") == symbol]
    if len(rows) != 1 or rows[0].get("currency") not in ("USD", "KRW"):
        raise HarnessError("공개 시세의 종목이나 통화를 확인하지 못했습니다.")
    quote = rows[0]
    observed = iso_time(quote["timestamp"])
    checked = datetime.now(timezone.utc)
    price = decimal_value(quote["lastPrice"], "시장 가격")
    if price == 0 or observed > checked + timedelta(seconds=10):
        raise HarnessError("공개 시세 가격이나 시각을 확인하지 못했습니다.")
    return {
        "dataScope": "public-market",
        "symbol": symbol,
        "currency": quote["currency"],
        "lastPrice": str(price),
        "observedAtEt": observed.astimezone(ET).isoformat(timespec="seconds"),
        "receivedAtEt": checked.astimezone(ET).isoformat(timespec="seconds"),
        "source": PUBLIC_QUOTE_SOURCE,
    }


def check_research_evidence(document):
    if set(document) != {"symbol", "asOfEt", "findings"}:
        raise HarnessError("공개 검증 자료는 symbol, asOfEt, findings 세 항목으로 작성해 주세요.")
    cutoff = iso_time(document["asOfEt"])
    if cutoff > datetime.now(timezone.utc):
        raise HarnessError("연구 기준 시각은 현재보다 앞서야 합니다.")
    seen = set()
    for entry in document["findings"]:
        if set(entry) != {"role", "source", "availableAt"} or entry["role"] not in ROLES:
            raise HarnessError("검증 자료에는 역할, 공개 출처와 공개 시각만 넣을 수 있습니다.")
        source = urlsplit(entry["source"])
        if (source.scheme != "https" or not source.hostname or source.username or source.password
                or any(key.lower() in PRIVATE_URL_KEYS for key, _ in parse_qsl(source.query))):
            raise HarnessError("검증 자료의 출처는 공개 HTTPS 주소여야 합니다.")
        if iso_time(entry["availableAt"]) > cutoff:
            raise HarnessError(f'{entry["role"]} 자료가 리포트 기준 시각보다 늦게 공개됐습니다.')
        seen.add(entry["role"])
    missing = sorted(ROLES - seen)
    return {
        "symbol": research_symbol(document["symbol"]),
        "ready": not missing,
        "missingRoles": missing,
        "confirmedRoles": sorted(seen),
    }


def replay_alert(rule, rows, through):
    previous = None
    streak = 0
    checked_count = 0
    signals = []
    for row in rows:
        if set(row) != {"date", "previousSessionDate", "close", "low", "complete"}:
            raise HarnessError("리플레이에는 날짜, 직전 거래일, 마감가, 최저가와 완료 여부가 필요합니다.")
        day = date.fromisoformat(row["date"])
        prior = date.fromisoformat(row["previousSessionDate"]) if row["previousSessionDate"] else None
        if (previous is not None and day <= previous) or (prior is not None and prior >= day):
            raise HarnessError("리플레이 거래일 순서를 확인해 주세요.")
        if day > through:
            previous = day
            continue
        if row["complete"] is True:
            close = decimal_value(row["close"], "정규장 마감가")
            low = decimal_value(row["low"], "정규장 최저가")
            if not 0 < low <= close:
                raise HarnessError("정규장 가격의 최저가와 마감가를 확인해 주세요.")
            checked_count += 1
            if close > rule["closeAbove"] and low >= rule["lowAtLeast"]:
                streak = streak + 1 if prior == previous else 1
            else:
                streak = 0
        else:
            streak = 0
        if streak == 2:
            signals.append(day.isoformat())
        previous = day
    return {
        "symbol": rule["symbol"],
        "through": through.isoformat(),
        "completeSessions": checked_count,
        "firstSignalDates": signals,
    }
