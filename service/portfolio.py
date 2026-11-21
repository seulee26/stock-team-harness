"""Return the minimum Toss account fields for the local dashboard."""

from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
import toss_client
from toss_client import ApiError, HarnessError, TossClient
from workflows import portfolio


SYMBOL = re.compile(r"[A-Za-z0-9._-]{1,32}")


def number(value):
    parsed = Decimal(str(value))
    if not parsed.is_finite() or abs(parsed) > 10**16:
        raise ValueError("Invalid number")
    return float(parsed)


def display_portfolio(result):
    rows = []
    for item in result["items"]:
        currency = item["currency"]
        symbol = str(item["symbol"])
        if currency not in ("KRW", "USD") or not SYMBOL.fullmatch(symbol):
            raise ValueError("Invalid holdings")
        rows.append({
            "symbol": symbol,
            "name": str(item["name"])[:120],
            "quantity": number(item["quantity"]),
            "marketValue": number(item["marketValue"]),
            "currency": currency,
            "returnPct": number(item["returnPct"]),
        })
    return {
        "currency": "KRW",
        "buyingPower": {
            "krw": number(result["cashBuyingPower"]["KRW"]),
            "usd": number(result["cashBuyingPower"]["USD"]),
        },
        "holdings": rows,
    }


def main():
    if not all(os.getenv(name) for name in ("TOSSINVEST_CLIENT_ID", "TOSSINVEST_CLIENT_SECRET", "STOCK_TEAM_LOCAL_STATE")):
        return {"error": "personal_mode_unavailable"}
    toss_client.STATE_DIR = Path(os.environ["STOCK_TEAM_LOCAL_STATE"])
    try:
        return display_portfolio(portfolio(TossClient(), os.getenv("STOCK_TEAM_ACCOUNT") or None))
    except ApiError as error:
        return {"error": "toss_access_denied" if error.status in (401, 403) else "portfolio_unavailable"}
    except (HarnessError, OSError, ValueError, KeyError, ArithmeticError, TypeError):
        return {"error": "portfolio_unavailable"}


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, allow_nan=False))
