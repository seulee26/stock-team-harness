"""Local CLI for the Toss Securities research harness."""

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time

from toss_client import (
    CATALOG, MARKET_OPERATIONS, OPERATIONS, PATH_VALUE, STREAM_HOST, STREAM_URL, HarnessError, TossClient,
    locked, private_dir, read_private_json, write_private_json,
)
from research import check_research_evidence, market_packet, replay_alert, research_plan
from workflows import (
    alert_message, decimal_value, evaluate_alert, iso_time, latest_completed_sessions,
    portfolio, read_rule, rule_key, sale_fee,
)


DEFAULT_RULE = Path(__file__).with_name("ant-alert.example.json")


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def parse_params(items):
    parameters = {}
    for item in items:
        key, equals, value = item.partition("=")
        if not equals or not key or not value or key in parameters:
            raise HarnessError("--param은 이름=값 형식으로 한 번씩 지정해 주세요.")
        parameters[key] = value
    return parameters


def api_read(client, args):
    operation = OPERATIONS.get(args.operation)
    if not operation or operation["method"] != "GET":
        raise HarnessError("catalog에서 조회 작업의 이름을 확인해 주세요.")
    account = client.resolve_account(args.account) if operation.get("account") else None
    params = parse_params(args.param)
    if "account" in params:
        raise HarnessError("계좌 식별값은 --account로 지정해 주세요.")
    return client.get(args.operation, account=account, **params)


def send_notification(message, destination):
    if destination == "mac":
        osascript = Path("/usr/bin/osascript")
        if not osascript.is_file():
            raise HarnessError("Mac 알림은 macOS에서 사용할 수 있습니다.")
        script = 'on run argv\n display notification (item 1 of argv) with title "주식 하네스"\nend run'
        env = {key: os.environ[key] for key in ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL") if key in os.environ}
        try:
            subprocess.run([osascript, "-e", script, message], check=True,
                           capture_output=True, timeout=10, env=env)
        except (subprocess.SubprocessError, OSError):
            raise HarnessError("Mac 알림을 보낼 수 없습니다. 알림 권한을 확인해 주세요.") from None
    print(message, flush=True)


def watch_once(client, rule, destination, now):
    state_file = private_dir() / f"alert-{rule_key(rule)}.json"
    with locked(state_file.with_suffix(".lock")):
        state = read_private_json(state_file)
        sessions = latest_completed_sessions(client, now)
        latest_date = sessions[-1][0]
        if state.get("lastChecked") == latest_date:
            return
        result = evaluate_alert(client, rule, sessions)
        status = result["status"]
        if status == "insufficient-data":
            return
        active = status == "satisfied"
        if active and not state.get("active"):
            send_notification(alert_message(rule, status), destination)
        write_private_json(state_file, {"lastChecked": latest_date, "active": active})


def watch(client, rule, destination, interval):
    failures = 0
    while True:
        try:
            watch_once(client, rule, destination, datetime.now(timezone.utc))
            failures = 0
        except (HarnessError, OSError, ValueError, KeyError) as error:
            failures += 1
            if failures == 1:
                print(str(error) if isinstance(error, HarnessError) else "알림 확인 중 오류가 발생했습니다.",
                      file=sys.stderr, flush=True)
        time.sleep(interval)


def connect_stream(websocket, token):
    # Establish TLS here so the optional library never resolves a proxy or another hostname.
    tcp = socket.create_connection((STREAM_HOST, 443), timeout=10)
    try:
        secured = ssl.create_default_context().wrap_socket(tcp, server_hostname=STREAM_HOST)
    except BaseException:
        tcp.close()
        raise
    try:
        return websocket.create_connection(
            STREAM_URL, socket=secured, header={"Authorization": f"Bearer {token}"},
            timeout=10, suppress_origin=True, redirect_limit=0,
        )
    except BaseException:
        secured.close()
        raise


def stream(client, args):
    try:
        import websocket
    except ImportError:
        raise HarnessError("실시간 수신은 requirements-realtime.txt 설치 후 실행할 수 있습니다.") from None
    channel = CATALOG["channels"][args.channel]["type"]
    if channel.startswith("personal:"):
        codes = [client.resolve_account(args.account)]
    else:
        if not args.symbols or len(args.symbols) > 100 or any(
            not PATH_VALUE.fullmatch(symbol) or symbol in (".", "..") for symbol in args.symbols
        ):
            raise HarnessError("실시간 수신할 종목코드를 1~100개 입력해 주세요.")
        channel = channel.replace("MARKET", args.market.lower())
        codes = [value.upper() for value in args.symbols]
    token = client.token()
    for attempt in range(2):
        try:
            connection = connect_stream(websocket, token)
            break
        except websocket.WebSocketBadStatusException as error:
            if attempt or error.status_code != 401:
                raise HarnessError(f"실시간 연결 요청이 거부됐습니다. HTTP {error.status_code}") from None
            token = client.token(rejected=token)
        except (websocket.WebSocketException, OSError):
            raise HarnessError("토스 실시간 채널에 연결하지 못했습니다.") from None
    try:
        connection.send(json.dumps([{"type": channel, "codes": codes}]))
        ping_at = time.monotonic() + 45
        while True:
            if time.monotonic() >= ping_at:
                connection.send("PING")
                ping_at = time.monotonic() + 45
            try:
                raw = connection.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw:
                raise HarnessError("실시간 연결이 종료됐습니다. 다시 실행해 주세요.")
            event = json.loads(raw)
            print(json.dumps(event, ensure_ascii=False), flush=True)
            if event.get("type") == "error" or (
                event.get("type") == "subscriptions" and not event.get("subscribed")
            ):
                raise HarnessError("실시간 구독을 시작하지 못했거나 연결이 종료됐습니다.")
    except websocket.WebSocketException:
        raise HarnessError("실시간 연결이 종료됐습니다. 다시 실행해 주세요.") from None
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="토스 공식 작업과 실시간 채널 목록")
    raw = commands.add_parser("api", help="토스 조회 작업 실행")
    raw.add_argument("operation")
    raw.add_argument("--param", action="append", default=[])
    raw.add_argument("--account")
    raw.add_argument("--market-only", action="store_true", help="계좌성 조회 접근 차단")
    plan = commands.add_parser("research-plan", help="공개 자료 조사 역할·시점 생성")
    plan.add_argument("symbol")
    plan.add_argument("--as-of", help="시간대가 포함된 자료 기준 시각")
    reviewer = commands.add_parser("research-check", help="공개 리포트의 조사 역할과 자료 시각 검증")
    reviewer.add_argument("evidence", type=Path)
    packet = commands.add_parser("market-packet", help="계좌 필드를 제외한 공개 시세 자료")
    packet.add_argument("symbol")
    replay = commands.add_parser("replay-alert", help="과거 정규장 자료로 알림 조건 재현")
    replay.add_argument("sessions", type=Path)
    replay.add_argument("--through", type=date.fromisoformat, required=True)
    replay.add_argument("--rule", type=Path, default=DEFAULT_RULE)
    hold = commands.add_parser("portfolio", help="보유 종목, 수익률, 매수 가능 금액")
    hold.add_argument("--account")
    fee = commands.add_parser("sale-fee", help="내 계좌 요율로 일반주식 매도 비용 추정")
    fee.add_argument("market", choices=("KOSPI", "KOSDAQ", "US"))
    fee.add_argument("amount", help="국내는 원화, 미국은 달러")
    fee.add_argument("--account")
    fee.add_argument("--json", action="store_true")
    check = commands.add_parser("check-alert", help="최근 두 정규장 매수 조건 확인")
    check.add_argument("--rule", type=Path, default=DEFAULT_RULE)
    check.add_argument("--json", action="store_true")
    loop = commands.add_parser("watch-alert", help="실행 중 새로 충족된 조건을 알림")
    loop.add_argument("--rule", type=Path, default=DEFAULT_RULE)
    loop.add_argument("--notify", choices=("stdout", "mac"), default="stdout")
    loop.add_argument("--interval", type=int, default=300)
    live = commands.add_parser("stream", help="실시간 채널 구독")
    live.add_argument("channel", choices=CATALOG["channels"])
    live.add_argument("symbols", nargs="*")
    live.add_argument("--market", choices=("KR", "US"), default="US")
    live.add_argument("--account")
    args = parser.parse_args()

    try:
        if args.command == "catalog":
            print_json(CATALOG)
            return 0
        if args.command == "research-plan":
            cutoff = iso_time(args.as_of) if args.as_of else datetime.now(timezone.utc)
            print_json(research_plan(args.symbol, cutoff))
            return 0
        if args.command == "research-check":
            result = check_research_evidence(json.loads(args.evidence.read_text(encoding="utf-8")))
            print_json(result)
            return 0 if result["ready"] else 2
        if args.command == "replay-alert":
            rows = json.loads(args.sessions.read_text(encoding="utf-8"))
            print_json(replay_alert(read_rule(args.rule), rows, args.through))
            return 0
        market_only = args.command in ("market-packet", "check-alert", "watch-alert")
        if args.command == "api":
            if OPERATIONS.get(args.operation, {}).get("method") != "GET":
                raise HarnessError("공식 목록에 있는 조회 작업만 실행할 수 있습니다.")
            market_only = args.market_only
            if market_only and (args.operation not in MARKET_OPERATIONS or args.account is not None):
                raise HarnessError("공개 시세 경로에서는 계좌 자료를 조회할 수 없습니다.")
        if args.command == "stream":
            market_only = not CATALOG["channels"][args.channel]["type"].startswith("personal:")
        client = TossClient(market_only=market_only)
        if args.command == "api":
            print_json(api_read(client, args))
        elif args.command == "market-packet":
            print_json(market_packet(client, args.symbol))
        elif args.command == "portfolio":
            print_json(portfolio(client, args.account))
        elif args.command == "sale-fee":
            result = sale_fee(client, args.market, decimal_value(args.amount, "매도 금액"), args.account)
            if args.json:
                print_json(result)
            else:
                amount = decimal_value(result["total"], "매도 비용")
                suffix = "달러" if result["currency"] == "USD" else "원"
                print(f"예상 매도 비용은 약 {amount:,}{suffix}입니다.")
        elif args.command == "check-alert":
            rule = read_rule(args.rule)
            sessions = latest_completed_sessions(client, datetime.now(timezone.utc))
            result = evaluate_alert(client, rule, sessions)
            print_json(result) if args.json else print(alert_message(rule, result["status"]))
        elif args.command == "watch-alert":
            if args.interval < 60:
                raise HarnessError("조회 간격은 60초 이상으로 지정해 주세요.")
            watch(client, read_rule(args.rule), args.notify, args.interval)
        else:
            stream(client, args)
    except HarnessError as error:
        print(error, file=sys.stderr)
        return 1
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
        print("입력값, 로컬 설정 또는 토스 API 응답을 확인해 주세요.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
