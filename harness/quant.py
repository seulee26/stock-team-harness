"""Offline daily-bar backtests and position sizing for research. No order is ever sent."""

import argparse
import csv
from datetime import date
import json
import math
from pathlib import Path

from toss_client import HarnessError


STRATEGIES = ("buy-hold", "sma-cross", "momentum", "breakout")
MAX_BARS = 20000
MAX_FILE_BYTES = 5_000_000
TRADING_DAYS = 252


def read_bars(path):
    """Read a CSV with `date` and `close` columns, oldest row first."""
    with Path(path).open("rb") as source:
        raw = source.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise HarnessError("일봉 CSV는 5MB 이하로 입력해 주세요.")
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    if not rows or not {"date", "close"} <= {name.strip().lower() for name in rows[0] if name}:
        raise HarnessError("일봉 CSV에는 date와 close 열이 필요합니다.")
    bars = []
    for row in rows:
        row = {key.strip().lower(): (value or "").strip() for key, value in row.items() if key}
        try:
            bars.append((date.fromisoformat(row["date"]), float(row["close"])))
        except ValueError:
            raise HarnessError("일봉 CSV의 날짜(YYYY-MM-DD)와 종가를 확인해 주세요.") from None
    return validate_bars(bars)


def validate_bars(bars):
    if not 30 <= len(bars) <= MAX_BARS:
        raise HarnessError("백테스트에는 일봉 30개 이상 20,000개 이하가 필요합니다.")
    for index, (day, close) in enumerate(bars):
        if not math.isfinite(close) or close <= 0:
            raise HarnessError("종가는 0보다 큰 숫자여야 합니다.")
        if index and day <= bars[index - 1][0]:
            raise HarnessError("일봉은 날짜가 겹치지 않게 오래된 순서로 정렬해 주세요.")
    return bars


def positions(closes, strategy, fast, slow, lookback, allow_short):
    """Target position after each close. It earns the next bar's return, so nothing looks ahead."""
    short = -1 if allow_short else 0
    result = []
    held = 0
    for index in range(len(closes)):
        if strategy == "buy-hold":
            held = 1
        elif strategy == "sma-cross":
            if index + 1 >= slow:
                quick = sum(closes[index + 1 - fast:index + 1]) / fast
                base = sum(closes[index + 1 - slow:index + 1]) / slow
                held = 1 if quick > base else short
        elif strategy == "momentum":
            if index >= lookback:
                held = 1 if closes[index] > closes[index - lookback] else short
        elif index >= lookback:
            window = closes[index - lookback:index]
            if closes[index] > max(window):
                held = 1
            elif closes[index] < min(window):
                held = short
        result.append(held)
    return result


def drawdown(curve):
    peak = curve[0]
    worst = 0.0
    for value in curve:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1)
    return worst


def summarize(curve, days, daily, held):
    years = max((days[-1] - days[0]).days / 365.25, 1 / 365.25)
    total = curve[-1] / curve[0] - 1
    mean = sum(daily) / len(daily)
    variance = sum((value - mean) ** 2 for value in daily) / max(len(daily) - 1, 1)
    deviation = math.sqrt(variance)
    return {
        "totalReturnPct": round(total * 100, 2),
        "cagrPct": round(((curve[-1] / curve[0]) ** (1 / years) - 1) * 100, 2) if curve[-1] > 0 else None,
        "maxDrawdownPct": round(drawdown(curve) * 100, 2),
        "annualVolatilityPct": round(deviation * math.sqrt(TRADING_DAYS) * 100, 2),
        "sharpe": round(mean / deviation * math.sqrt(TRADING_DAYS), 2) if deviation else None,
        "positionChanges": sum(1 for index in range(1, len(held)) if held[index] != held[index - 1]) + (held[0] != 0),
        "exposurePct": round(sum(1 for value in held[:-1] if value) / max(len(held) - 1, 1) * 100, 1),
    }


def backtest(bars, strategy="sma-cross", *, fast=20, slow=60, lookback=120, allow_short=False,
             cost_bps=5.0, capital=None, multiplier=None, contracts=1, fee=0.0, margin=None):
    bars = validate_bars(list(bars))
    if strategy not in STRATEGIES:
        raise HarnessError("전략은 " + ", ".join(STRATEGIES) + " 중에서 골라 주세요.")
    if not (1 <= fast < slow <= 400 and 2 <= lookback <= 400):
        raise HarnessError("이동평균은 1 ≤ fast < slow ≤ 400, lookback은 2~400 범위로 입력해 주세요.")
    if not (0 <= cost_bps <= 500 and 0 <= fee <= 1_000_000 and 1 <= contracts <= 100000):
        raise HarnessError("비용과 계약 수를 확인해 주세요.")
    futures = multiplier is not None
    if futures and not (capital and capital > 0 and 0 < multiplier <= 10_000_000):
        raise HarnessError("선물 백테스트에는 --capital과 --multiplier가 필요합니다.")
    if margin is not None and not (futures and margin > 0):
        raise HarnessError("--margin은 선물 백테스트에서 0보다 큰 값으로 입력해 주세요.")

    days = [day for day, _ in bars]
    closes = [close for _, close in bars]
    held = positions(closes, strategy, fast, slow, lookback, allow_short)
    start = float(capital) if capital else 1.0
    equity = start
    curve = [equity]
    daily = []
    previous = 0
    ruined = None
    for index in range(len(closes) - 1):
        target = held[index]
        changed = abs(target - previous)
        before = equity
        if futures:
            notional = contracts * multiplier * closes[index]
            equity += target * contracts * multiplier * (closes[index + 1] - closes[index])
            equity -= changed * (contracts * fee + notional * cost_bps / 10000)
        else:
            equity *= 1 - changed * cost_bps / 10000
            equity *= 1 + target * (closes[index + 1] / closes[index] - 1)
        previous = target
        daily.append(equity / before - 1 if before > 0 else 0.0)
        curve.append(equity)
        if equity <= 0:
            ruined = days[index + 1].isoformat()
            break

    used = len(curve)
    hold = [1.0]
    for index in range(used - 1):
        hold.append(hold[-1] * closes[index + 1] / closes[index])
    warnings = ["과거 성과는 미래 수익을 보장하지 않습니다.", "체결은 종가 기준이며 호가 공백과 세금은 반영하지 않습니다."]
    if (days[used - 1] - days[0]).days < 365:
        warnings.append("표본이 1년 미만이라 결과를 일반화하기 어렵습니다.")
    if futures:
        warnings.append("연속 선물 데이터의 만기 교체(롤오버) 손익과 증거금 변경은 반영하지 않습니다.")
    result = {
        "dataScope": "user-supplied-bars",
        "mode": "futures-backtest" if futures else "backtest",
        "strategy": strategy,
        "parameters": {"fast": fast, "slow": slow, "lookback": lookback, "allowShort": allow_short,
                       "costBps": cost_bps},
        "period": {"start": days[0].isoformat(), "end": days[used - 1].isoformat(), "bars": used},
        "result": summarize(curve, days[:used], daily, held[:used]),
        "buyAndHold": {"totalReturnPct": round((hold[-1] - 1) * 100, 2),
                       "maxDrawdownPct": round(drawdown(hold) * 100, 2)},
        "warnings": warnings,
    }
    if futures:
        peak_notional = max(contracts * multiplier * close for close in closes[:used])
        result["futures"] = {
            "startingCapital": start, "endingCapital": round(equity, 2), "contracts": contracts,
            "multiplier": multiplier, "feePerContract": fee,
            "peakLeverage": round(peak_notional / start, 2),
            "ruinedOn": ruined,
        }
        if margin is not None:
            result["futures"]["initialMarginNeeded"] = round(contracts * margin, 2)
            result["futures"]["marginCoversStart"] = contracts * margin <= start
    return result


def position_size(capital, risk_pct, entry, stop, multiplier=1.0):
    values = (capital, risk_pct, entry, stop, multiplier)
    if not all(math.isfinite(value) and value > 0 for value in values) or entry == stop or risk_pct > 100:
        raise HarnessError("자본, 위험 비율(0~100), 진입가, 손절가, 승수를 확인해 주세요.")
    risk_per_unit = abs(entry - stop) * multiplier
    budget = capital * risk_pct / 100
    units = math.floor(budget / risk_per_unit)
    notional = units * entry * multiplier
    return {
        "dataScope": "calculation-only",
        "side": "long" if stop < entry else "short",
        "riskBudget": round(budget, 2),
        "riskPerUnit": round(risk_per_unit, 4),
        "units": units,
        "notional": round(notional, 2),
        "leverage": round(notional / capital, 2),
        "lossAtStop": round(units * risk_per_unit, 2),
        "note": "손절가에서 정확히 체결된다고 가정한 계산입니다. 갭 하락과 슬리피지는 반영하지 않습니다.",
    }


def demo_bars(count=750):
    """Deterministic synthetic prices so the demo needs no market data."""
    state = 20261121
    close = 100.0
    day = date(2022, 1, 3).toordinal()
    bars = []
    while len(bars) < count:
        if date.fromordinal(day).weekday() < 5:
            state = (state * 1103515245 + 12345) % 2 ** 31
            shock = (state / 2 ** 31 - 0.5) * 0.03
            trend = 0.0006 * math.sin(len(bars) / 90)
            close *= 1 + trend + shock
            bars.append((date.fromordinal(day), round(close, 2)))
        day += 1
    return bars


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    def add_backtest_options(command):
        command.add_argument("--strategy", choices=STRATEGIES, default="sma-cross")
        command.add_argument("--fast", type=int, default=20)
        command.add_argument("--slow", type=int, default=60)
        command.add_argument("--lookback", type=int, default=120)
        command.add_argument("--allow-short", action="store_true", help="하락 신호에서 매도 포지션을 잡습니다")
        command.add_argument("--cost-bps", type=float, default=5.0, help="포지션 변경 시 명목금액 대비 비용(bp)")
        command.add_argument("--capital", type=float, help="시작 자본 (선물 백테스트에 필요)")
        command.add_argument("--multiplier", type=float, help="선물 1포인트당 금액. 지정하면 선물 방식으로 계산")
        command.add_argument("--contracts", type=int, default=1)
        command.add_argument("--fee", type=float, default=0.0, help="계약당 편도 수수료")
        command.add_argument("--margin", type=float, help="계약당 개시증거금")

    run = commands.add_parser("backtest", help="일봉 CSV로 전략을 검증합니다")
    run.add_argument("csv")
    add_backtest_options(run)
    add_backtest_options(commands.add_parser("demo", help="합성 데이터로 백테스트를 시연합니다"))
    size = commands.add_parser("size", help="손절 기준으로 수량을 계산합니다")
    size.add_argument("--capital", type=float, required=True)
    size.add_argument("--risk-pct", type=float, required=True)
    size.add_argument("--entry", type=float, required=True)
    size.add_argument("--stop", type=float, required=True)
    size.add_argument("--multiplier", type=float, default=1.0)
    args = parser.parse_args()

    def options():
        return {"fast": args.fast, "slow": args.slow, "lookback": args.lookback,
                "allow_short": args.allow_short, "cost_bps": args.cost_bps, "capital": args.capital,
                "multiplier": args.multiplier, "contracts": args.contracts, "fee": args.fee, "margin": args.margin}

    try:
        if args.command == "size":
            result = position_size(args.capital, args.risk_pct, args.entry, args.stop, args.multiplier)
        elif args.command == "demo":
            result = backtest(demo_bars(), args.strategy, **options()) | {"dataScope": "synthetic-only"}
        else:
            result = backtest(read_bars(args.csv), args.strategy, **options())
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except HarnessError as exc:
        parser.exit(1, f"{exc}\n")
    except (OSError, ValueError):
        parser.exit(1, "파일과 입력값을 확인해 주세요.\n")


if __name__ == "__main__":
    main()
