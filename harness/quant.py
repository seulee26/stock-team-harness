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
    downside = math.sqrt(sum(min(value, 0.0) ** 2 for value in daily) / len(daily))
    worst = drawdown(curve)
    cagr = (curve[-1] / curve[0]) ** (1 / years) - 1 if curve[-1] > 0 else None
    active = [value for value in daily if value != 0]
    extra = {
        "sortino": round(mean / downside * math.sqrt(TRADING_DAYS), 2) if downside else None,
        "calmar": round(cagr / abs(worst), 2) if cagr is not None and worst < 0 else None,
        "winDaysPct": round(sum(1 for value in active if value > 0) / len(active) * 100, 1) if active else None,
        "bestDayPct": round(max(daily) * 100, 2), "worstDayPct": round(min(daily) * 100, 2),
    }
    return extra | {
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
    hold_daily = [hold[index + 1] / hold[index] - 1 for index in range(used - 1)]
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
        "buyAndHold": summarize(hold, days[:used], hold_daily, [1] * used) | {"note": "비용을 빼지 않은 단순 보유"},
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


def position_size(capital, risk_pct, entry, stop, multiplier=1.0, margin=None):
    values = (capital, risk_pct, entry, stop, multiplier)
    if not all(math.isfinite(value) and value > 0 for value in values) or entry == stop or risk_pct > 100:
        raise HarnessError("자본, 위험 비율(0~100), 진입가, 손절가, 승수를 확인해 주세요.")
    if margin is not None and not (math.isfinite(margin) and margin > 0):
        raise HarnessError("계약당 증거금은 0보다 큰 숫자로 입력해 주세요.")
    risk_per_unit = abs(entry - stop) * multiplier
    budget = capital * risk_pct / 100
    units = math.floor(budget / risk_per_unit)
    capped = None
    if margin is not None:
        affordable = math.floor(capital / margin)
        if units > affordable:
            capped, units = units, affordable
    notional = units * entry * multiplier
    margin_fields = {} if margin is None else {
        "marginPerUnit": margin, "marginNeeded": round(units * margin, 2),
        "unitsBeforeMarginCap": capped,
        "marginNote": "증거금으로 살 수 있는 수량까지만 계산했습니다. 증거금은 거래소와 증권사가 바꿀 수 있습니다.",
    }
    return margin_fields | {
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


def sma(values, window):
    return sum(values[-window:]) / window if len(values) >= window else None


def ema_series(values, span):
    alpha, result = 2 / (span + 1), [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def indicators(bars):
    """Trend, momentum and volatility read-outs from closing prices."""
    bars = validate_bars(list(bars))
    closes = [close for _, close in bars]
    last = closes[-1]
    averages = {f"sma{window}": round(sma(closes, window), 4) if sma(closes, window) else None for window in (20, 60, 120)}
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains, losses = [max(value, 0) for value in changes], [max(-value, 0) for value in changes]
    average_gain, average_loss = sum(gains[:14]) / 14, sum(losses[:14]) / 14
    for gain, loss in zip(gains[14:], losses[14:]):
        average_gain, average_loss = (average_gain * 13 + gain) / 14, (average_loss * 13 + loss) / 14
    rsi = 100.0 if average_loss == 0 else 100 - 100 / (1 + average_gain / average_loss)
    macd_line = [fast - slow for fast, slow in zip(ema_series(closes, 12), ema_series(closes, 26))]
    signal = ema_series(macd_line, 9)
    window = closes[-20:]
    middle = sum(window) / len(window)
    spread = math.sqrt(sum((value - middle) ** 2 for value in window) / len(window))
    returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))][-20:]
    mean = sum(returns) / len(returns)
    year = closes[-TRADING_DAYS:]
    order = [averages[key] for key in ("sma20", "sma60", "sma120") if averages[key]]
    trend = "판단 보류"
    if len(order) == 3:
        trend = "상승 정렬" if last > order[0] > order[1] > order[2] else (
            "하락 정렬" if last < order[0] < order[1] < order[2] else "혼조")
    return {
        "dataScope": "user-supplied-bars", "asOf": bars[-1][0].isoformat(), "close": last, "trend": trend,
        "movingAverages": averages, "rsi14": round(rsi, 1),
        "macd": {"line": round(macd_line[-1], 4), "signal": round(signal[-1], 4),
                 "histogram": round(macd_line[-1] - signal[-1], 4)},
        "bollinger20": {"upper": round(middle + 2 * spread, 4), "middle": round(middle, 4),
                        "lower": round(middle - 2 * spread, 4)},
        "dailyVolatilityPct": round(math.sqrt(sum((value - mean) ** 2 for value in returns) / len(returns)) * 100, 2),
        "range52w": {"high": max(year), "low": min(year),
                     "positionPct": round((last - min(year)) / (max(year) - min(year)) * 100, 1) if max(year) > min(year) else None},
        "note": "종가만으로 계산한 참고 지표입니다. 실적과 뉴스를 대신하지 않습니다.",
    }


def aligned_returns(series):
    """Daily returns on the dates every series shares."""
    if not 2 <= len(series) <= 30:
        raise HarnessError("자산은 2~30개로 입력해 주세요.")
    maps = {name: dict(validate_bars(list(bars))) for name, bars in series.items()}
    shared = sorted(set.intersection(*(set(values) for values in maps.values())))
    if len(shared) < 60:
        raise HarnessError("자산들이 함께 거래된 날이 60일 이상 필요합니다.")
    return shared, {name: [values[shared[index]] / values[shared[index - 1]] - 1 for index in range(1, len(shared))]
                    for name, values in maps.items()}


def deviation(values):
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / max(len(values) - 1, 1))


def project_to_simplex(values):
    """Closest point with non-negative entries that sum to one."""
    ordered = sorted(values, reverse=True)
    running, threshold = 0.0, 0.0
    for index, value in enumerate(ordered, 1):
        running += value
        candidate = (running - 1) / index
        if value - candidate > 0:
            threshold = candidate
    return [max(value - threshold, 0.0) for value in values]


def minimum_variance(covariance, start, steps=4000):
    """Long-only weights that minimise portfolio variance (projected gradient descent)."""
    size = len(covariance)
    step = 1 / (2 * max(sum(abs(value) for value in row) for row in covariance))
    current = list(start)
    for _ in range(steps):
        gradient = [2 * sum(covariance[row][column] * current[column] for column in range(size)) for row in range(size)]
        current = project_to_simplex([current[index] - step * gradient[index] for index in range(size)])
    return current


def weights(series, method="inverse-vol"):
    """Starting weights for a basket: equal, inverse-volatility or minimum-variance, plus correlations."""
    if method not in ("equal", "inverse-vol", "min-variance"):
        raise HarnessError("방식은 equal, inverse-vol, min-variance 중에서 골라 주세요.")
    shared, returns = aligned_returns(series)
    names = list(returns)
    vols = {name: deviation(returns[name]) * math.sqrt(TRADING_DAYS) for name in names}
    if any(value == 0 for value in vols.values()):
        raise HarnessError("가격이 변하지 않은 자산이 있어 변동성을 계산할 수 없습니다.")
    raw = {name: 1.0 if method == "equal" else 1 / vols[name] for name in names}
    total = sum(raw.values())
    result = {name: raw[name] / total for name in names}
    means = {name: sum(returns[name]) / len(returns[name]) for name in names}
    if method == "min-variance":
        count = len(returns[names[0]])
        covariance = [[sum((returns[first][index] - means[first]) * (returns[second][index] - means[second])
                           for index in range(count)) / (count - 1) for second in names] for first in names]
        result = dict(zip(names, minimum_variance(covariance, [result[name] for name in names])))

    def correlation(first, second):
        count = len(returns[first])
        covariance = sum((returns[first][index] - means[first]) * (returns[second][index] - means[second])
                         for index in range(count)) / (count - 1)
        return covariance / (deviation(returns[first]) * deviation(returns[second]))

    pairs = [{"pair": [first, second], "correlation": round(correlation(first, second), 2)}
             for position, first in enumerate(names) for second in names[position + 1:]]
    portfolio = [sum(result[name] * returns[name][index] for name in names) for index in range(len(shared) - 1)]
    return {
        "dataScope": "user-supplied-bars", "method": method,
        "period": {"start": shared[0].isoformat(), "end": shared[-1].isoformat(), "days": len(shared)},
        "weightsPct": {name: round(result[name] * 100, 1) for name in names},
        "annualVolatilityPct": {name: round(vols[name] * 100, 1) for name in names},
        "portfolioVolatilityPct": round(deviation(portfolio) * math.sqrt(TRADING_DAYS) * 100, 1),
        "correlations": sorted(pairs, key=lambda item: -item["correlation"]),
        "note": "과거 변동성으로 계산한 출발점입니다. 상관계수가 0.8을 넘는 자산은 하나의 위험으로 보세요.",
    }


def rank(series, lookback=120, skip=20):
    """Cross-sectional momentum and volatility ranks for a list of assets."""
    if not (20 <= lookback <= 400 and 0 <= skip < lookback):
        raise HarnessError("lookback은 20~400, skip은 0 이상 lookback 미만으로 입력해 주세요.")
    if not 2 <= len(series) <= 200:
        raise HarnessError("자산은 2~200개로 입력해 주세요.")
    rows = []
    for name, bars in series.items():
        closes = [close for _, close in validate_bars(list(bars))]
        if len(closes) <= lookback:
            raise HarnessError(f"{name}의 일봉이 lookback보다 짧습니다.")
        returns = [closes[index] / closes[index - 1] - 1 for index in range(len(closes) - lookback, len(closes))]
        rows.append({"asset": name, "momentumPct": round((closes[-1 - skip] / closes[-1 - lookback] - 1) * 100, 2),
                     "annualVolatilityPct": round(deviation(returns) * math.sqrt(TRADING_DAYS) * 100, 1)})
    for key, reverse in (("momentumPct", True), ("annualVolatilityPct", False)):
        for position, row in enumerate(sorted(rows, key=lambda item: item[key], reverse=reverse), 1):
            row[key.replace("Pct", "Rank")] = position
    for row in rows:
        row["score"] = row["momentumRank"] + row["annualVolatilityRank"]
    return {"dataScope": "user-supplied-bars", "lookback": lookback, "skip": skip,
            "ranking": sorted(rows, key=lambda item: (item["score"], item["asset"])),
            "note": "모멘텀이 높고 변동성이 낮을수록 순위가 앞섭니다. 순위는 조사 대상을 고르는 용도이며 매수 근거가 아닙니다."}


def apply_limits(target, max_position=25.0, max_gross=100.0, drawdown_pct=0.0, halve_at=10.0, stop_at=20.0):
    """Shrink proposed weights to the limits. Risk control only reduces; the rest stays in cash."""
    if not isinstance(target, dict) or not 1 <= len(target) <= 100:
        raise HarnessError("비중은 1~100개 자산으로 입력해 주세요.")
    numbers = (max_position, max_gross, drawdown_pct, halve_at, stop_at)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (*target.values(), *numbers)):
        raise HarnessError("비중과 한도는 숫자로 입력해 주세요.")
    if not (0 < max_position <= 100 and 0 < max_gross <= 1000 and 0 <= drawdown_pct <= 100 and 0 < halve_at < stop_at):
        raise HarnessError("한도 값을 확인해 주세요.")
    result, events = {name: float(value) for name, value in target.items()}, []
    if drawdown_pct >= stop_at:
        events.append({"rule": "drawdown-stop", "detail": f"낙폭 {drawdown_pct}%가 {stop_at}% 이상이라 전량 현금"})
        result = {name: 0.0 for name in result}
    else:
        for name, value in result.items():
            if abs(value) > max_position:
                events.append({"rule": "max-position", "asset": name, "from": value, "to": math.copysign(max_position, value)})
                result[name] = math.copysign(max_position, value)
        if drawdown_pct >= halve_at:
            events.append({"rule": "drawdown-halve", "detail": f"낙폭 {drawdown_pct}%가 {halve_at}% 이상이라 절반으로 축소"})
            result = {name: value / 2 for name, value in result.items()}
        gross = sum(abs(value) for value in result.values())
        if gross > max_gross:
            events.append({"rule": "max-gross", "from": round(gross, 2), "to": max_gross})
            result = {name: value * max_gross / gross for name, value in result.items()}
    gross = sum(abs(value) for value in result.values())
    return {"dataScope": "calculation-only", "weightsPct": {name: round(value, 2) for name, value in result.items()},
            "grossPct": round(gross, 2), "netPct": round(sum(result.values()), 2),
            "cashPct": round(max(100 - gross, 0), 2), "events": events,
            "note": "한도는 비중을 줄이기만 합니다. 줄인 만큼은 현금으로 둡니다."}


def read_series(paths):
    series = {}
    for path in paths:
        name = Path(path).stem
        if name in series:
            raise HarnessError("파일 이름이 겹칩니다. 자산마다 다른 이름의 CSV를 써 주세요.")
        series[name] = read_bars(path)
    return series


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
    size.add_argument("--margin", type=float, help="계약당 증거금. 주면 증거금으로 살 수 있는 수량으로 제한합니다")
    commands.add_parser("indicators", help="추세·모멘텀·변동성 지표").add_argument("csv")
    basket = commands.add_parser("weights", help="여러 자산의 출발 비중과 상관계수")
    basket.add_argument("csv", nargs="+")
    basket.add_argument("--method", default="inverse-vol", help="equal, inverse-vol, min-variance")
    ranking = commands.add_parser("rank", help="여러 자산의 모멘텀·변동성 순위")
    ranking.add_argument("csv", nargs="+")
    ranking.add_argument("--lookback", type=int, default=120)
    ranking.add_argument("--skip", type=int, default=20)
    limit = commands.add_parser("limits", help="제안 비중을 한도에 맞게 줄입니다")
    limit.add_argument("weights", help='비중 JSON. 예: \'{"NVDA": 40, "005930": 30}\'')
    limit.add_argument("--max-position", type=float, default=25.0)
    limit.add_argument("--max-gross", type=float, default=100.0)
    limit.add_argument("--drawdown", type=float, default=0.0, help="최근 고점 대비 낙폭(%)")
    args = parser.parse_args()

    def options():
        return {"fast": args.fast, "slow": args.slow, "lookback": args.lookback,
                "allow_short": args.allow_short, "cost_bps": args.cost_bps, "capital": args.capital,
                "multiplier": args.multiplier, "contracts": args.contracts, "fee": args.fee, "margin": args.margin}

    try:
        if args.command == "indicators":
            result = indicators(read_bars(args.csv))
        elif args.command == "weights":
            result = weights(read_series(args.csv), args.method)
        elif args.command == "rank":
            result = rank(read_series(args.csv), args.lookback, args.skip)
        elif args.command == "limits":
            result = apply_limits(json.loads(args.weights), args.max_position, args.max_gross, args.drawdown)
        elif args.command == "size":
            result = position_size(args.capital, args.risk_pct, args.entry, args.stop, args.multiplier, args.margin)
        elif args.command == "demo":
            result = backtest(demo_bars(), args.strategy, **options()) | {"dataScope": "synthetic-only"}
            result["warnings"].insert(0, "합성 데이터로 만든 시연입니다. 실제 시장 결과가 아닙니다.")
        else:
            result = backtest(read_bars(args.csv), args.strategy, **options())
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except HarnessError as exc:
        parser.exit(1, f"{exc}\n")
    except (OSError, ValueError):
        parser.exit(1, "파일과 입력값을 확인해 주세요.\n")


if __name__ == "__main__":
    main()
