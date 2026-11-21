"""Portfolio reads, sale-cost calculations, and regular-session alert rules."""

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from toss_client import HarnessError, PATH_VALUE


ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")
MINUTE = timedelta(minutes=1)
CLOSE_GRACE = timedelta(minutes=5)
FEE_BASIS_DATE = "2026-11-20"


def decimal_value(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HarnessError(f"{label} 값이 숫자가 아닙니다.") from None
    if not result.is_finite() or result < 0:
        raise HarnessError(f"{label} 값이 유효하지 않습니다.")
    return result


def iso_time(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is not None:
            return result
    except (TypeError, ValueError, AttributeError):
        pass
    raise HarnessError("토스에서 받은 시각에 시간대 정보가 없습니다.")


def portfolio(client, account):
    account = client.resolve_account(account)
    holding = client.get("getHoldings", account=account)
    buying_power = {
        currency: client.get("getBuyingPower", account=account, currency=currency)["cashBuyingPower"]
        for currency in ("KRW", "USD")
    }
    items = [{
        "symbol": item["symbol"],
        "name": item["name"],
        "currency": item["currency"],
        "quantity": item["quantity"],
        "averagePurchasePrice": item["averagePurchasePrice"],
        "marketValue": item["marketValue"]["amount"],
        "profitLoss": item["profitLoss"]["amount"],
        "returnPct": str(Decimal(item["profitLoss"]["rate"]) * 100),
    } for item in holding["items"]]
    return {
        "checkedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "items": items,
        "marketValue": holding["marketValue"]["amount"],
        "cashBuyingPower": buying_power,
    }


def sale_fee(client, market, amount, account):
    if amount <= 0:
        raise HarnessError("매도 금액을 0보다 크게 입력해 주세요.")
    account = client.resolve_account(account)
    market_country = "US" if market == "US" else "KR"
    today = datetime.now(KST).date().isoformat()
    rates = client.get("getCommissions", account=account)
    available = [
        row for row in rates
        if row["marketCountry"] == market_country
        and (not row.get("startDate") or row["startDate"] <= today)
        and (not row.get("endDate") or row["endDate"] >= today)
    ]
    if len(available) != 1:
        raise HarnessError("현재 계좌의 적용 수수료율을 하나로 확인하지 못했습니다.")
    commission_rate = decimal_value(available[0]["commissionRate"], "계좌 수수료율")
    tick = Decimal("0.01") if market == "US" else Decimal("1")
    commission = (
        Decimal(0) if market == "US" and amount <= 10 else amount * commission_rate
    ).quantize(tick, rounding=ROUND_HALF_UP)
    charge = (
        max(Decimal("0.01"), amount * Decimal("0.0000206"))
        if market == "US" else amount * Decimal("0.002")
    ).quantize(tick, rounding=ROUND_HALF_UP)
    return {
        "market": market,
        "currency": "USD" if market == "US" else "KRW",
        "gross": str(amount),
        "commissionRate": str(commission_rate),
        "commission": str(commission),
        "secFee" if market == "US" else "saleTax": str(charge),
        "total": str(commission + charge),
        "net": str(amount - commission - charge),
        "taxAndSecFeeBasisDate": FEE_BASIS_DATE,
    }


def read_rule(path):
    values = json.loads(path.read_text(encoding="utf-8"))
    symbol = values.get("symbol", "").upper()
    if not PATH_VALUE.fullmatch(symbol) or symbol in (".", ".."):
        raise HarnessError("알림 규칙의 종목코드를 확인해 주세요.")
    rule = {
        "symbol": symbol,
        "name": values.get("name") or symbol,
        "closeAbove": decimal_value(values.get("closeAbove"), "마감 기준"),
        "lowAtLeast": decimal_value(values.get("lowAtLeast"), "장중 최저가 기준"),
        "reviewUpTo": decimal_value(values.get("reviewUpTo"), "매수 검토 상한"),
    }
    if not 0 < rule["lowAtLeast"] <= rule["closeAbove"] < rule["reviewUpTo"]:
        raise HarnessError("최저가, 마감가, 매수 검토 상한을 확인해 주세요.")
    return rule


def rule_key(rule):
    body = json.dumps(rule, default=str, sort_keys=True).encode()
    return sha256(body).hexdigest()[:20]


def latest_completed_sessions(client, now):
    candidate = now.astimezone(ET).date()
    result = {}
    for _ in range(8):
        calendar = client.get("getUsMarketCalendar", date=candidate.isoformat())
        for item in calendar.values():
            market = item and item.get("regularMarket")
            if not market:
                continue
            start, end = iso_time(market["startTime"]), iso_time(market["endTime"])
            if end + CLOSE_GRACE <= now and start < end:
                result[item["date"]] = (item["date"], start, end)
        if len(result) >= 2:
            return sorted(result.values())[-2:]
        candidate -= timedelta(days=1)
    raise HarnessError("완료된 미국 정규장 두 거래일을 찾지 못했습니다.")


def session_prices(client, symbol, session):
    date, opened, closed = session
    cursor = closed.isoformat()
    bars = {}
    for _ in range(8):
        page = client.get("getCandles", symbol=symbol, interval="1m", count=200, before=cursor, adjusted="false")
        seen = []
        for bar in page.get("candles", []):
            ended = iso_time(bar["timestamp"])
            seen.append(ended)
            # The official 1m timestamp denotes the end, so [open, close) uses (open, close].
            if opened < ended <= closed:
                if bar.get("currency") != "USD":
                    raise HarnessError("미국주식 분봉의 통화가 USD가 아닙니다.")
                bars[ended] = bar
        next_cursor = page.get("nextBefore")
        if not seen or min(seen) <= opened + MINUTE or not next_cursor:
            break
        if iso_time(next_cursor) >= iso_time(cursor):
            raise HarnessError("분봉 페이지가 이전 시각으로 이동하지 않았습니다.")
        cursor = next_cursor
    expected = int((closed - opened) / MINUTE)
    expected_times = {opened + i * MINUTE for i in range(1, expected + 1)}
    record = {"date": date, "bars": len(bars), "expectedBars": expected}
    if not expected or set(bars) != expected_times:
        return {**record, "complete": False}
    return {
        **record,
        "complete": True,
        "close": decimal_value(bars[closed]["closePrice"], "정규장 마감가"),
        "low": min(decimal_value(bar["lowPrice"], "정규장 최저가") for bar in bars.values()),
    }


def evaluate_alert(client, rule, sessions):
    prices = [session_prices(client, rule["symbol"], session) for session in sessions]
    complete = all(item["complete"] for item in prices)
    passed = complete and all(
        item["close"] > rule["closeAbove"] and item["low"] >= rule["lowAtLeast"] for item in prices
    )
    status = "satisfied" if passed else "waiting" if complete else "insufficient-data"
    return {"status": status, "symbol": rule["symbol"], "sessions": prices}


def alert_message(rule, status):
    if status == "satisfied":
        return f'{rule["name"]} 매수 검토 조건 충족. {rule["closeAbove"]}달러 초과~{rule["reviewUpTo"]}달러에서 검토.'
    if status == "insufficient-data":
        return f'{rule["name"]} 정규장 분봉이 부족해 매수 조건을 확인할 수 없습니다.'
    return f'{rule["name"]} 매수 대기. 이틀 연속 정규장 가격 조건을 기다립니다.'
