"""Offline checks for session boundaries, alert rules, and read-only behavior."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import Mock, patch

from research import ROLES, check_research_evidence, market_packet, replay_alert
from stock_harness import DEFAULT_RULE, connect_stream, watch_once
from toss_client import CATALOG, MARKET_OPERATIONS, OPERATIONS, STREAM_HOST, STREAM_URL, HarnessError, TossClient, read_private_text
from workflows import ET, MINUTE, evaluate_alert, latest_completed_sessions, read_rule, sale_fee, session_prices


def regular(day):
    opened = datetime(2026, 11, day, 9, 30, tzinfo=ET)
    return (opened.date().isoformat(), opened, opened + 4 * MINUTE)


def minute(end, close="99", low="94"):
    return {"timestamp": end.isoformat(), "closePrice": close, "lowPrice": low, "currency": "USD"}


class Candles:
    def __init__(self, *items):
        self.items = items

    def get(self, name, *, before, **params):
        assert name == "getCandles" and params["interval"] == "1m"
        boundary = datetime.fromisoformat(before)
        found = sorted(
            (row for row in self.items if datetime.fromisoformat(row["timestamp"]) <= boundary),
            key=lambda row: row["timestamp"], reverse=True,
        )
        take = found[:2]
        return {"candles": take, "nextBefore": found[2]["timestamp"] if len(found) > 2 else None}


def candle_rows(opened, *, close="99", low="94"):
    return [minute(opened + i * MINUTE, close=close, low=low) for i in range(1, 5)]


class HarnessTests(TestCase):
    def test_catalog_blocks_order_changes_before_authentication(self):
        self.assertEqual(len(OPERATIONS), 43)
        self.assertEqual(sum(item["method"] == "GET" for item in OPERATIONS.values()), 36)
        self.assertEqual(len(CATALOG["channels"]), 4)
        client = TossClient.__new__(TossClient)
        client.market_only = False
        for operation in OPERATIONS.values():
            if operation["method"] != "GET":
                with self.assertRaises(HarnessError):
                    client.get(operation["id"])
        with self.assertRaises(HarnessError):
            client.get("getOrder", account="1", orderId="../orders")

    def test_public_queries_cannot_resolve_an_account_or_load_a_token(self):
        client = TossClient.__new__(TossClient)
        client.market_only = True
        client.token = Mock(side_effect=AssertionError("Account access reached token exchange"))
        private = [
            name for name, op in OPERATIONS.items()
            if op["method"] == "GET" and (op.get("account") or name == "getAccounts")
        ]
        self.assertTrue(private)
        self.assertFalse(set(private) & MARKET_OPERATIONS)
        for name in private:
            with self.assertRaises(HarnessError):
                client.get(name)
        with self.assertRaises(HarnessError):
            client.resolve_account()
        client.token.assert_not_called()

    def test_private_transport_refuses_nonofficial_path_before_network(self):
        client = TossClient.__new__(TossClient)
        for path, form in (
            ("https://github.com/", None), ("/api/v1/../../upload", None),
            ("/api/v1/orders", {"unexpected": "synthetic"}), ("/oauth2/token", None),
        ):
            with self.subTest(path=path), self.assertRaises(HarnessError):
                client._request(path, form=form)

    def test_stream_starts_tls_to_official_host_before_sending_bearer(self):
        websocket = Mock()
        with patch("stock_harness.socket.create_connection") as socket, patch("stock_harness.ssl.create_default_context") as ssl:
            connect_stream(websocket, "synthetic")
        socket.assert_called_once_with((STREAM_HOST, 443), timeout=10)
        ssl.return_value.wrap_socket.assert_called_once_with(socket.return_value, server_hostname=STREAM_HOST)
        websocket.create_connection.assert_called_once_with(
            STREAM_URL, socket=ssl.return_value.wrap_socket.return_value,
            header={"Authorization": "Bearer synthetic"}, timeout=10, suppress_origin=True, redirect_limit=0,
        )

    def test_key_files_require_owner_only_regular_files(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            original = folder / "private.txt"
            original.write_text("synthetic")
            original.chmod(0o600)
            self.assertEqual(read_private_text(original), "synthetic")
            link = folder / "symlink"
            link.symlink_to(original)
            with self.assertRaises(OSError):
                read_private_text(link)
            original.chmod(0o644)
            with self.assertRaises(HarnessError):
                read_private_text(original)

    def test_market_packet_has_only_public_allowlisted_fields(self):
        client = Mock(market_only=True)
        client.get.return_value = [{
            "symbol": "ANT", "currency": "USD", "lastPrice": "90.93",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "accountSeq": 12345, "cashBuyingPower": {"USD": "987"},
        }]
        quote = market_packet(client, "ant")
        self.assertEqual(set(quote), {
            "dataScope", "symbol", "currency", "lastPrice", "observedAtEt", "receivedAtEt", "source",
        })
        client.get.assert_called_once_with("getPrices", symbols="ANT")

    def test_research_gate_rejects_future_evidence_and_credential_urls(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        findings = [
            {"role": role, "source": "https://www.sec.gov/", "availableAt": cutoff.isoformat()}
            for role in sorted(ROLES)
        ]
        document = {"symbol": "ANT", "asOfEt": cutoff.isoformat(), "findings": findings}
        self.assertTrue(check_research_evidence(document)["ready"])
        original = findings.pop()
        self.assertFalse(check_research_evidence(document)["ready"])
        findings.append({**original, "availableAt": (cutoff + MINUTE).isoformat()})
        with self.assertRaises(HarnessError):
            check_research_evidence(document)
        findings[-1] = {**original, "source": "https://www.sec.gov/?api_key=synthetic"}
        with self.assertRaises(HarnessError):
            check_research_evidence(document)

    def test_alert_replay_resets_on_gap_and_obeys_cutoff(self):
        sequence = [("05", "02"), ("07", "06"), ("08", "07"), ("09", "08")]
        rows = [{
            "date": "2026-10-" + day, "previousSessionDate": "2026-10-" + before,
            "close": "100", "low": "94", "complete": True,
        } for day, before in sequence]
        rule = read_rule(DEFAULT_RULE)
        result = replay_alert(rule, rows, date(2026, 10, 8))
        self.assertEqual(result["firstSignalDates"], ["2026-10-08"])
        self.assertEqual(result["completeSessions"], 3)
        self.assertEqual(replay_alert(rule, rows, date(2026, 10, 7))["firstSignalDates"], [])

    def test_opening_boundary_excludes_premarket_and_keeps_closing_minute(self):
        session = regular(20)
        _, opened, closed = session
        client = Candles(minute(opened, low="12"), *candle_rows(opened), minute(closed + MINUTE, low="1"))
        result = session_prices(client, "ANT", session)
        self.assertTrue(result["complete"])
        self.assertEqual(result["low"], Decimal("94"))
        self.assertEqual(result["close"], Decimal("99"))

    def test_missing_intraday_minute_blocks_signal(self):
        first, second = regular(20), regular(23)
        client = Candles(*candle_rows(first[1]), *candle_rows(second[1])[1:])
        result = evaluate_alert(client, read_rule(DEFAULT_RULE), [first, second])
        self.assertEqual(result["status"], "insufficient-data")

    def test_strict_close_and_inclusive_low_on_two_sessions(self):
        first, second = regular(20), regular(23)
        rule = read_rule(DEFAULT_RULE)
        close_threshold, low_threshold = rule["closeAbove"], rule["lowAtLeast"]
        qualifying_close = str(close_threshold + Decimal("0.01"))
        first_bars = candle_rows(first[1], low=str(low_threshold), close=qualifying_close)
        scenarios = [
            (str(close_threshold), str(low_threshold), "waiting"),
            (qualifying_close, str(low_threshold - Decimal("0.01")), "waiting"),
            (qualifying_close, str(low_threshold), "satisfied"),
        ]
        for close, low, expected in scenarios:
            with self.subTest(close=close, low=low):
                client = Candles(*first_bars, *candle_rows(second[1], close=close, low=low))
                self.assertEqual(evaluate_alert(client, rule, [first, second])["status"], expected)

    def test_calendar_picks_completed_sessions_and_waits_for_close_grace(self):
        def market(day):
            date, opened, closed = regular(day)
            return {"date": date, "regularMarket": {"startTime": opened.isoformat(), "endTime": closed.isoformat()}}

        class Calendar:
            def get(self, name, *, date):
                if date == "2026-11-23":
                    return {"today": market(23), "previousBusinessDay": market(20), "nextBusinessDay": market(24)}
                return {"today": None, "previousBusinessDay": market(19), "nextBusinessDay": market(20)}

        just_closed = regular(23)[2] + timedelta(minutes=4)
        self.assertEqual([row[0][-2:] for row in latest_completed_sessions(Calendar(), just_closed)], ["19", "20"])
        after_grace = just_closed + MINUTE
        self.assertEqual([row[0][-2:] for row in latest_completed_sessions(Calendar(), after_grace)], ["20", "23"])

    def test_watcher_notifies_once_per_valid_streak(self):
        rule = read_rule(DEFAULT_RULE)
        today = regular(23)[2]
        with TemporaryDirectory() as directory, patch("stock_harness.private_dir", return_value=Path(directory)):
            with patch("stock_harness.latest_completed_sessions") as sessions:
                with patch("stock_harness.evaluate_alert") as evaluate, patch("stock_harness.send_notification") as notify:
                    evaluate.side_effect = [
                        {"status": "satisfied"}, {"status": "satisfied"},
                        {"status": "waiting"}, {"status": "satisfied"},
                    ]
                    for day in (23, 23, 24, 25, 27):
                        sessions.return_value = [regular(20), regular(day)]
                        watch_once(None, rule, "stdout", today)
                    self.assertEqual(evaluate.call_count, 4)
                    self.assertEqual(notify.call_count, 2)

    def test_sale_fee_uses_account_rate_and_small_order_rule(self):
        class Account:
            def resolve_account(self, account):
                return "1"

            def get(self, name, **params):
                return [{"marketCountry": "KR", "commissionRate": "0.00015"},
                        {"marketCountry": "US", "commissionRate": "0.001"}]

        kr = sale_fee(Account(), "KOSPI", Decimal("100000000"), None)
        us = sale_fee(Account(), "US", Decimal("10"), None)
        self.assertEqual(kr["total"], "215000")
        self.assertEqual(us["commission"], "0.00")
        self.assertEqual(us["total"], "0.01")


if __name__ == "__main__":
    main()
