from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import connectors
import desk
import mailer
import quant
import tax
import wiki
from toss_client import HarnessError


def bars(closes, start=date(2024, 1, 1)):
    return [(start + timedelta(days=index), close) for index, close in enumerate(closes)]


class QuantTests(unittest.TestCase):
    def test_buy_and_hold_matches_price_change_without_costs(self):
        closes = [100 + index for index in range(40)]
        result = quant.backtest(bars(closes), "buy-hold", cost_bps=0)
        self.assertEqual(result["result"]["totalReturnPct"], 39.0)
        self.assertEqual(result["buyAndHold"]["totalReturnPct"], 39.0)
        self.assertEqual(result["result"]["maxDrawdownPct"], 0.0)

    def test_signal_never_earns_the_bar_that_produced_it(self):
        closes = [100.0] * 30 + [200.0] + [200.0] * 9
        result = quant.backtest(bars(closes), "momentum", lookback=5, cost_bps=0)
        self.assertEqual(result["result"]["totalReturnPct"], 0.0)

    def test_short_side_profits_from_a_fall_only_when_allowed(self):
        closes = [200 - index * 2 for index in range(60)]
        flat = quant.backtest(bars(closes), "momentum", lookback=5, cost_bps=0)
        short = quant.backtest(bars(closes), "momentum", lookback=5, cost_bps=0, allow_short=True)
        self.assertEqual(flat["result"]["totalReturnPct"], 0.0)
        self.assertGreater(short["result"]["totalReturnPct"], 0)

    def test_costs_reduce_the_result(self):
        closes = [100 + (index % 7) * 3 for index in range(120)]
        free = quant.backtest(bars(closes), "sma-cross", fast=2, slow=5, cost_bps=0)
        paid = quant.backtest(bars(closes), "sma-cross", fast=2, slow=5, cost_bps=50)
        self.assertLess(paid["result"]["totalReturnPct"], free["result"]["totalReturnPct"])

    def test_futures_profit_uses_multiplier_and_fee(self):
        closes = [100 + index for index in range(40)]
        result = quant.backtest(bars(closes), "buy-hold", cost_bps=0, capital=10000, multiplier=50,
                                contracts=2, fee=2.5, margin=3000)
        self.assertEqual(result["futures"]["endingCapital"], 10000 + 39 * 50 * 2 - 2 * 2.5)
        self.assertTrue(result["futures"]["marginCoversStart"])
        self.assertIn("롤오버", " ".join(result["warnings"]))

    def test_futures_account_stops_when_capital_is_gone(self):
        closes = [100.0] * 30 + [50.0] + [50.0] * 9
        result = quant.backtest(bars(closes), "buy-hold", cost_bps=0, capital=1000, multiplier=50)
        self.assertEqual(result["futures"]["ruinedOn"], (date(2024, 1, 1) + timedelta(days=30)).isoformat())

    def test_invalid_inputs_are_rejected(self):
        for closes in ([100.0] * 10, [100.0] * 29 + [0.0], [100.0] * 29 + [float("nan")]):
            with self.assertRaises(HarnessError):
                quant.backtest(bars(closes), "buy-hold")
        with self.assertRaises(HarnessError):
            quant.backtest(bars([100.0] * 40), "sma-cross", fast=60, slow=20)
        with self.assertRaises(HarnessError):
            quant.backtest(bars([100.0] * 40), "buy-hold", multiplier=50)
        with self.assertRaises(HarnessError):
            quant.backtest([(date(2024, 1, 1), 100.0)] * 40, "buy-hold")

    def test_csv_reader_and_demo(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "bars.csv"
            path.write_text("Date,Close\n" + "\n".join(
                f"{day.isoformat()},{close}" for day, close in bars([100 + index for index in range(40)])
            ), encoding="utf-8")
            self.assertEqual(len(quant.read_bars(path)), 40)
            path.write_text("date,open\n2024-01-01,1\n", encoding="utf-8")
            with self.assertRaises(HarnessError):
                quant.read_bars(path)
        self.assertEqual(quant.demo_bars(), quant.demo_bars())
        self.assertEqual(quant.backtest(quant.demo_bars())["period"]["bars"], 750)

    def test_position_size_respects_the_risk_budget(self):
        sized = quant.position_size(10000, 1, 100, 95)
        self.assertEqual((sized["units"], sized["lossAtStop"], sized["side"]), (20, 100.0, "long"))
        future = quant.position_size(100000, 2, 5000, 5020, multiplier=50)
        self.assertEqual((future["units"], future["side"]), (2, "short"))
        with self.assertRaises(HarnessError):
            quant.position_size(10000, 1, 100, 100)
        capped = quant.position_size(30000000, 5, 400, 399, multiplier=250000, margin=12000000)
        self.assertEqual((capped["units"], capped["unitsBeforeMarginCap"], capped["marginNeeded"]), (2, 6, 24000000.0))
        self.assertIsNone(quant.position_size(30000000, 1, 400, 399, multiplier=250000, margin=12000000)["unitsBeforeMarginCap"])

    def test_buy_and_hold_block_has_the_same_metrics(self):
        result = quant.backtest(quant.demo_bars())
        self.assertEqual(set(result["result"]) | {"note"}, set(result["buyAndHold"]))


class AnalyticsTests(unittest.TestCase):
    def test_indicators_read_a_steady_uptrend(self):
        result = quant.indicators(bars([100 + index for index in range(150)]))
        self.assertEqual((result["trend"], result["rsi14"], result["range52w"]["positionPct"]), ("상승 정렬", 100.0, 100.0))
        self.assertEqual(result["movingAverages"]["sma20"], 239.5)
        self.assertGreater(result["macd"]["line"], 0)
        self.assertIsNone(quant.indicators(bars([100 + index for index in range(40)]))["movingAverages"]["sma60"])

    def test_inverse_volatility_gives_the_calm_asset_more_weight(self):
        calm = bars([100 + (index % 2) * 0.5 for index in range(100)])
        wild = bars([100 + (index % 2) * 10 for index in range(100)])
        result = quant.weights({"calm": calm, "wild": wild})
        self.assertGreater(result["weightsPct"]["calm"], 90)
        self.assertEqual(result["correlations"][0]["correlation"], 1.0)
        self.assertEqual(quant.weights({"calm": calm, "wild": wild}, "equal")["weightsPct"], {"calm": 50.0, "wild": 50.0})
        optimal = quant.minimum_variance([[4.0, 0.0], [0.0, 1.0]], [0.5, 0.5])
        self.assertAlmostEqual(optimal[0], 0.2, places=3)
        self.assertAlmostEqual(sum(optimal), 1.0, places=6)
        hedged = quant.minimum_variance([[1.0, 0.9, 0.0], [0.9, 1.0, 0.0], [0.0, 0.0, 1.0]], [1 / 3] * 3)
        self.assertTrue(all(value >= 0 for value in hedged))
        self.assertGreater(hedged[2], hedged[0])
        low = quant.weights({"calm": calm, "wild": wild}, "min-variance")
        self.assertLessEqual(low["portfolioVolatilityPct"], quant.weights({"calm": calm, "wild": wild})["portfolioVolatilityPct"] + 0.01)
        with self.assertRaises(HarnessError):
            quant.weights({"calm": calm})
        with self.assertRaises(HarnessError):
            quant.weights({"calm": calm, "flat": bars([100.0] * 100)})

    def test_rank_prefers_momentum_with_low_volatility(self):
        strong = bars([100 * 1.002 ** index for index in range(200)])
        weak = bars([100 + (index % 2) * 8 - index * 0.05 for index in range(200)])
        ranking = quant.rank({"strong": strong, "weak": weak})["ranking"]
        self.assertEqual([row["asset"] for row in ranking], ["strong", "weak"])
        with self.assertRaises(HarnessError):
            quant.rank({"strong": strong, "short": bars([100.0] * 50)})

    def test_limits_only_shrink_and_leave_the_rest_in_cash(self):
        capped = quant.apply_limits({"A": 40, "B": 30, "C": -50}, max_position=25, max_gross=60)
        self.assertEqual(capped["weightsPct"], {"A": 20.0, "B": 20.0, "C": -20.0})
        self.assertEqual((capped["grossPct"], capped["cashPct"]), (60.0, 40.0))
        self.assertEqual([event["rule"] for event in capped["events"]], ["max-position"] * 3 + ["max-gross"])
        halved = quant.apply_limits({"A": 20, "B": 10}, drawdown_pct=12)
        self.assertEqual(halved["weightsPct"], {"A": 10.0, "B": 5.0})
        self.assertEqual(quant.apply_limits({"A": 20}, drawdown_pct=25)["weightsPct"], {"A": 0.0})
        self.assertEqual(quant.apply_limits({"A": 10, "B": 5})["events"], [])
        for original, limited in zip((40, 30, -50), capped["weightsPct"].values()):
            self.assertLessEqual(abs(limited), abs(original))
        with self.assertRaises(HarnessError):
            quant.apply_limits({"A": "많이"})

    def test_extra_metrics_are_reported(self):
        result = quant.backtest(quant.demo_bars())["result"]
        self.assertTrue({"sortino", "calmar", "winDaysPct", "bestDayPct", "worstDayPct"} <= set(result))


def corp_archive(rows):
    body = "<result>" + "".join(
        f"<list><corp_code>{corp}</corp_code><corp_name>{name}</corp_name><stock_code>{stock}</stock_code></list>"
        for corp, name, stock in rows
    ) + "</result>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("CORPCODE.xml", body)
    return buffer.getvalue()


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.cache = Path(self.work.name)
        self.calls = []
        fake_dart, fake_fred = "d" * 40, "f" * 32
        environment = mock.patch.dict(os.environ, {connectors.DART_KEY: fake_dart, connectors.FRED_KEY: fake_fred})
        environment.start()
        self.addCleanup(environment.stop)

    def responder(self, responses):
        def get(host, path, params):
            self.calls.append((host, path, dict(params)))
            return responses[path]
        return get

    def test_dart_filings_resolve_company_and_link_to_dart(self):
        get = self.responder({
            "/api/corpCode.xml": corp_archive([("00126380", "삼성전자", "005930"), ("00000001", "비상장", " ")]),
            "/api/list.json": json.dumps({"status": "000", "list": [
                {"rcept_no": "20261114000123", "rcept_dt": "20261114", "report_nm": "분기보고서 (2026.09)", "flr_nm": "삼성전자"},
            ]}).encode(),
        })
        result = connectors.dart_filings("005930", get=get, cache=self.cache)
        self.assertEqual(result["company"], "삼성전자")
        self.assertEqual(result["filings"][0]["date"], "2026-11-14")
        self.assertEqual(result["filings"][0]["url"], "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261114000123")
        self.assertEqual(self.calls[1][2]["corp_code"], "00126380")
        self.assertNotIn("d" * 40, json.dumps(result))
        connectors.dart_filings("005930", get=get, cache=self.cache)
        self.assertEqual([path for _, path, _ in self.calls].count("/api/corpCode.xml"), 1)

    def test_dart_financials_prefer_consolidated_accounts(self):
        get = self.responder({
            "/api/corpCode.xml": corp_archive([("00126380", "삼성전자", "005930")]),
            "/api/fnlttSinglAcnt.json": json.dumps({"status": "000", "list": [
                {"rcept_no": "20260310000001", "fs_div": "OFS", "sj_nm": "손익계산서", "account_nm": "매출액", "thstrm_amount": "1"},
                {"rcept_no": "20260310000001", "fs_div": "CFS", "sj_nm": "손익계산서", "account_nm": "매출액",
                 "thstrm_amount": "300,000", "frmtrm_amount": "250,000", "currency": "KRW"},
            ]}).encode(),
        })
        result = connectors.dart_financials("005930", 2025, get=get, cache=self.cache)
        self.assertEqual(result["basis"], "연결")
        self.assertEqual([row["current"] for row in result["accounts"]], ["300,000"])
        self.assertEqual(self.calls[1][2]["reprt_code"], "11011")

    def test_dart_errors_do_not_leak_the_key(self):
        get = self.responder({
            "/api/corpCode.xml": corp_archive([("00126380", "삼성전자", "005930")]),
            "/api/list.json": json.dumps({"status": "020", "message": "한도 초과"}).encode(),
        })
        with self.assertRaises(HarnessError) as caught:
            connectors.dart_filings("005930", get=get, cache=self.cache)
        self.assertNotIn("d" * 40, str(caught.exception))
        with self.assertRaises(HarnessError):
            connectors.dart_filings("000001", get=get, cache=self.cache)
        with self.assertRaises(HarnessError):
            connectors.dart_filings("5930", get=get, cache=self.cache)
        empty = self.responder({
            "/api/corpCode.xml": corp_archive([("00126380", "삼성전자", "005930")]),
            "/api/list.json": json.dumps({"status": "013"}).encode(),
        })
        self.assertEqual(connectors.dart_filings("005930", get=empty, cache=self.cache)["filings"], [])

    def test_fred_skips_missing_points(self):
        get = self.responder({"/fred/series/observations": json.dumps({"observations": [
            {"date": "2026-11-17", "value": "4.21"}, {"date": "2026-11-18", "value": "."},
            {"date": "2026-11-19", "value": "4.25"},
        ]}).encode()})
        result = connectors.fred_series("DGS10", "2026-11-01", get=get)
        self.assertEqual([point["value"] for point in result["observations"]], [4.21, 4.25])
        self.assertEqual(result["source"], "https://fred.stlouisfed.org/series/DGS10")
        self.assertEqual(self.calls[0][2]["observation_start"], "2026-11-01")
        with self.assertRaises(HarnessError):
            connectors.fred_series("dgs10; drop", get=get)

    def test_missing_key_is_reported_before_any_request(self):
        with mock.patch.dict(os.environ, {connectors.FRED_KEY: ""}):
            with self.assertRaises(HarnessError):
                connectors.fred_series("DGS10", get=self.responder({}))
        self.assertEqual(self.calls, [])

    def test_doctor_and_setup_guides_hold_no_secret(self):
        report = connectors.doctor()
        self.assertEqual(report["opendart"]["status"], "configured")
        self.assertEqual(report["agent-store"]["status"], "client-setup")
        text = json.dumps([report, connectors.agent_store("claude"), connectors.agent_store("codex")])
        self.assertNotIn("d" * 40, text)
        self.assertIn("https://agent.store/mcp", text)

    def test_catalog_follows_its_own_rubric(self):
        document = connectors.catalog()
        entries = document["projects"]
        self.assertGreaterEqual(len(entries), 20)
        for entry in entries:
            self.assertTrue({"repository", "license", "liveOrders", "scores", "total", "verdict", "adopted"} <= set(entry))
            self.assertEqual(entry["total"], sum(entry["scores"].values()))
            self.assertTrue(all(value in (0, 1, 2) for value in entry["scores"].values()))
            if entry["verdict"] in ("연결", "접목"):
                self.assertGreaterEqual(entry["total"], 8, entry["repository"])
                self.assertGreaterEqual(min(entry["scores"][key] for key in ("license", "orderRisk", "maintenance")), 1)
            if entry["liveOrders"]:
                self.assertLessEqual(entry["scores"]["orderRisk"], 1, entry["repository"])
        self.assertEqual(document["summary"], {verdict: sum(1 for entry in entries if entry["verdict"] == verdict)
                                               for verdict in ("연결", "접목", "참고", "제외")})

    def test_evaluate_scores_candidates(self):
        good = connectors.evaluate("example/lib", "MIT", "none", 2, 2, 2)
        self.assertEqual((good["total"], good["verdict"]), (10, "연결 또는 접목 후보"))
        bot = connectors.evaluate("example/bot", "GPL-3.0", "core", 1, 0, 1)
        self.assertEqual((bot["verdict"], len(bot["reasons"])), ("제외", 2))
        self.assertEqual(connectors.evaluate("example/old", "Apache-2.0", "none", 30, 2, 2)["verdict"], "참고")
        for spelling, expected in (("Apache 2.0", 2), ("BSD", 2), ("apache", 2), ("LGPL", 1), ("MPL-2.0", 1),
                                   ("GPL-3.0", 0), ("AGPL-3.0", 0), ("none", 0)):
            self.assertEqual(connectors.evaluate("x", spelling, "none", 1, 2, 2)["scores"]["license"], expected, spelling)
        with self.assertRaises(HarnessError):
            connectors.evaluate("x", "MIT", "maybe", 1, 2, 2)

    def test_bars_writes_a_clean_csv_and_reports_missing_packages(self):
        target = self.cache / "es.csv"
        result = connectors.bars("es=f", "yfinance", "2026-01-01", "2026-02-01", target,
                                 run=lambda source, payload: [["2026-01-02", 100.0], ["2026-01-05", 101.5],
                                                              ["2026-01-05", 9.0], ["2026-01-06", float("nan")]])
        self.assertEqual((result["symbol"], result["rows"], result["lastClose"]), ("ES=F", 2, 101.5))
        self.assertEqual(target.read_text(encoding="utf-8"), "date,close\n2026-01-02,100.0\n2026-01-05,101.5\n")
        for arguments in (("ES=F", "bloomberg", "2026-01-01", "2026-02-01", self.cache / "a.csv"),
                          ("ES=F", "yfinance", "2026-02-01", "2026-01-01", self.cache / "a.csv"),
                          ("ES=F", "yfinance", "2026-01-01", "2026-02-01", target),
                          ("bad symbol", "fdr", "2026-01-01", "2026-02-01", self.cache / "a.csv")):
            with self.assertRaises(HarnessError):
                connectors.bars(*arguments, run=lambda source, payload: [])
        with mock.patch.dict(os.environ, {connectors.DATA_PYTHON: "/nonexistent/python"}):
            with self.assertRaises(HarnessError) as caught:
                connectors.bars("ES=F", "yfinance", "2026-01-01", "2026-02-01", self.cache / "b.csv")
        self.assertIn("pip install yfinance", str(caught.exception))


class DeskJournalTests(unittest.TestCase):
    def setUp(self):
        self.journal = {"theses": [], "decisions": [], "events": []}

    def test_report_catalog_points_to_skills(self):
        entries = desk.reports()["reports"]
        self.assertGreaterEqual(len(entries), 12)
        self.assertEqual(len({entry["id"] for entry in entries}), len(entries))
        self.assertTrue(all({"name", "when", "skill", "cadence", "desks", "length"} <= set(entry) for entry in entries))

    def test_thesis_needs_falsifiable_conditions_and_one_open_entry(self):
        with self.assertRaises(HarnessError):
            desk.thesis_add(self.journal, "NVDA", "US", "성장 지속", ["매출 증가"], [])
        entry = desk.thesis_add(self.journal, "nvda", "US", "성장  지속", ["매출 증가"], ["고객 투자 축소"], 180, 120,
                                "2026-11-21")
        self.assertEqual((entry["symbol"], entry["statement"], entry["status"]), ("NVDA", "성장 지속", "open"))
        with self.assertRaises(HarnessError):
            desk.thesis_add(self.journal, "NVDA", "US", "다시", ["근거"], ["조건"])
        desk.thesis_update(self.journal, "NVDA", "실적 상회", "strengthens", 4, "2026-11-22")
        self.assertEqual(self.journal["theses"][0]["updates"][0]["conviction"], 4)
        with self.assertRaises(HarnessError):
            desk.thesis_update(self.journal, "NVDA", "메모", "better", 4)
        desk.thesis_close(self.journal, "NVDA", "조건 도달", "2026-12-01")
        with self.assertRaises(HarnessError):
            desk.thesis_update(self.journal, "NVDA", "메모", "neutral", 3)
        desk.thesis_add(self.journal, "NVDA", "US", "새 논지", ["근거"], ["조건"])

    def test_scorecard_measures_alpha_against_the_benchmark(self):
        desk.decision_log(self.journal, "NVDA", "US", "buy", 100, "SPX", 5000, "2026-01-02")
        desk.decision_log(self.journal, "005930", "KR", "sell", 80000, "KOSPI", 3000, "2026-01-02")
        desk.decision_log(self.journal, "AAPL", "US", "hold", 200, "SPX", 5000, "2026-01-02")
        first = desk.decision_score(self.journal, 1, 120, 5500, "2026-02-02")
        self.assertEqual((first["settled"]["returnPct"], first["settled"]["alphaPct"], first["settled"]["hit"]),
                         (20.0, 10.0, True))
        second = desk.decision_score(self.journal, 2, 88000, 3150, "2026-02-02")
        self.assertEqual((second["settled"]["alphaPct"], second["settled"]["hit"]), (5.0, False))
        self.assertIsNone(desk.decision_score(self.journal, 3, 210, 5500, "2026-02-02")["settled"]["hit"])
        card = desk.scorecard(self.journal)
        self.assertEqual((card["settled"], card["hitRatePct"], card["open"]), (3, 50.0, []))
        self.assertEqual(card["byRating"]["buy"]["meanAlphaPct"], 10.0)
        self.assertIn("20건", card["note"])
        with self.assertRaises(HarnessError):
            desk.decision_score(self.journal, 9, 1, 1)
        with self.assertRaises(HarnessError):
            desk.decision_score(self.journal, 1, 120, 5500, "2025-12-31")
        with self.assertRaises(HarnessError):
            desk.decision_log(self.journal, "NVDA", "US", "buy", -1, "SPX", 5000)

    def test_events_are_sorted_and_windowed(self):
        desk.event_add(self.journal, "2026-12-10", "FOMC", "macro", "H")
        desk.event_add(self.journal, "2026-11-25", "실적 발표", "earnings", "H", "nvda")
        desk.event_add(self.journal, "2027-03-01", "주주총회", "corporate", "L", "005930")
        window = desk.event_list(self.journal, 30, "2026-11-21")
        self.assertEqual([event["title"] for event in window["events"]], ["실적 발표", "FOMC"])
        self.assertEqual(window["events"][0]["symbol"], "NVDA")
        for bad in ("12/10", "2026-13-45", "2026-02-30"):
            with self.assertRaises(HarnessError):
                desk.event_add(self.journal, bad, "잘못된 날짜")
        with self.assertRaises(HarnessError):
            desk.event_add(self.journal, "2026-12-10", "종류 오류", "party")

    def test_journal_round_trip_is_private_and_rejects_bad_files(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "desk" / "journal.json"
            self.assertEqual(desk.load(path), self.journal)
            desk.event_add(self.journal, "2026-12-10", "FOMC")
            desk.save(self.journal, path)
            self.assertEqual(desk.load(path), self.journal)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(HarnessError):
                desk.load(path)


class MailerTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.report = Path(self.work.name) / "report.html"
        self.report.write_text("<html><body>report</body></html>", encoding="utf-8")
        self.sent = []
        me, app_code = "me@example.com", "abcd efgh ijkl mnop"
        environment = mock.patch.dict(os.environ, {mailer.ADDRESS_VAR: me, mailer.SECRET_VAR: app_code})
        environment.start()
        self.addCleanup(environment.stop)

    def transport(self, message, sender, secret):
        self.sent.append((message, sender, secret))

    def test_preview_never_sends_and_defaults_to_self(self):
        result = mailer.send([], "모닝 브리프", "오늘 볼 것 세 가지", [self.report], transport=self.transport)
        self.assertEqual((result["sent"], result["to"], result["outsideRecipients"]), (False, ["me@example.com"], []))
        self.assertEqual(self.sent, [])
        self.assertNotIn("abcdefghijklmnop", json.dumps(result))

    def test_confirmed_send_attaches_report_and_disclaimer(self):
        result = mailer.send(["friend@example.org"], "리포트", "요약", [self.report], confirm=True,
                             transport=self.transport)
        message, sender, secret = self.sent[0]
        self.assertEqual((result["sent"], result["outsideRecipients"]), (True, ["friend@example.org"]))
        self.assertEqual((sender, secret, message["To"]), ("me@example.com", "abcdefghijklmnop", "friend@example.org"))
        parts = list(message.iter_attachments())
        self.assertEqual((parts[0].get_filename(), parts[0].get_content_type()), ("report.html", "text/html"))
        self.assertIn("투자 조언이나 권유가 아닙니다", message.get_body().get_content())

    def test_preview_works_before_setup_but_sending_does_not(self):
        with mock.patch.dict(os.environ, {mailer.ADDRESS_VAR: "", mailer.SECRET_VAR: ""}):
            preview = mailer.send(["friend@example.org"], "제목", "요약", [self.report], transport=self.transport)
            self.assertEqual((preview["sent"], preview["setupNeeded"], preview["outsideRecipients"]),
                             (False, True, ["friend@example.org"]))
            self.assertEqual(mailer.send([], "제목", "요약", [self.report])["to"], ["(본인 주소)"])
            with self.assertRaises(HarnessError) as caught:
                mailer.send(["friend@example.org"], "제목", "요약", [self.report], confirm=True,
                            transport=self.transport)
            self.assertIn(mailer.ADDRESS_VAR, str(caught.exception))
        self.assertEqual(self.sent, [])

    def test_holdings_never_leave_to_another_person(self):
        private = Path(self.work.name) / "portfolio.html"
        private.write_text("<p>NVDA 보유 수량 12주, 평가 금액 2,100</p>", encoding="utf-8")
        with self.assertRaises(HarnessError):
            mailer.send(["boss@example.org"], "제목", "요약", [private], transport=self.transport)
        with self.assertRaises(HarnessError):
            mailer.send(["boss@example.org"], "제목", "요약", [private], confirm=True, transport=self.transport)
        own = mailer.send([], "제목", "요약", [private], confirm=True, transport=self.transport)
        self.assertEqual((own["sent"], own["containsHoldings"], len(self.sent)), (True, True, 1))

    def test_bad_input_is_rejected_before_any_send(self):
        other = Path(self.work.name) / "notes.txt"
        other.write_text("x", encoding="utf-8")
        cases = [
            (["not-an-address"], "제목", "요약", [self.report]),
            (["a@example.com"] * 2, "제목", "요약", [self.report]),
            (["a@example.com"], "", "요약", [self.report]),
            (["a@example.com"], "제목", "요약", [other]),
            (["a@example.com"], "제목", "요약", [Path(self.work.name) / "missing.pdf"]),
            (["a@example.com"], "제목", "요약", []),
        ]
        for recipients, subject, summary, files in cases:
            with self.assertRaises(HarnessError):
                mailer.send(recipients, subject, summary, files, confirm=True, transport=self.transport)
        with mock.patch.dict(os.environ, {mailer.SECRET_VAR: "short"}):
            with self.assertRaises(HarnessError):
                mailer.send([], "제목", "요약", [self.report], confirm=True, transport=self.transport)
        self.assertEqual(self.sent, [])

    def test_login_failure_is_reported_without_the_secret(self):
        def refuse(message, sender, secret):
            raise mailer.smtplib.SMTPAuthenticationError(535, b"bad")
        with self.assertRaises(HarnessError) as caught:
            mailer.send([], "제목", "요약", [self.report], confirm=True, transport=refuse)
        self.assertNotIn("abcdefghijklmnop", str(caught.exception))
        self.assertEqual(mailer.doctor()["status"], "configured")


class WikiTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.base = Path(self.work.name)
        self.config_path = self.base / "config.json"
        self.report = self.base / "nvda.html"
        self.report.write_text("<html><body>NVDA report</body></html>", encoding="utf-8")

    def make(self, mode="local"):
        wiki.init(mode, self.base / "wiki", switch=self.config_path.exists(), config_path=self.config_path)
        return wiki.load_config(self.config_path)

    def test_init_add_index_search_and_lint(self):
        config = self.make()
        result = wiki.add(config, self.report, "company", "NVDA", "매수 시점 평가", "지금은 대기", "2026-11-20", ["반도체"])
        root = self.base / "wiki"
        self.assertTrue((root / "sources/2026/2026-11-20-company-NVDA.html").is_file())
        page = (root / "pages/company/NVDA.md").read_text(encoding="utf-8")
        self.assertIn("### 2026-11-20 · 매수 시점 평가", page)
        self.assertIn("(../../sources/2026/2026-11-20-company-NVDA.html)", page)
        self.assertIn("[NVDA](pages/company/NVDA.md) · 기록 1건 · 최근 2026-11-20", (root / "index.md").read_text(encoding="utf-8"))
        self.assertEqual(result["pages"], 1)
        wiki.add(config, self.report, "company", "NVDA", "실적 리뷰", "가이던스 상회", "2026-11-25")
        self.assertEqual(wiki.status(config)["entries"], 2)
        self.assertEqual(wiki.search(config, "가이던스")["hits"][0]["page"], "pages/company/NVDA.md")
        self.assertTrue(wiki.lint(config, 3650)["clean"])
        (root / "sources/2026/2026-11-25-company-NVDA.html").unlink()
        (root / "sources/2026/stray.pdf").write_bytes(b"x")
        report = wiki.lint(config, 3650)
        self.assertEqual((len(report["brokenLinks"]), report["unlinkedSources"], report["clean"]),
                         (1, ["sources/2026/stray.pdf"], False))

    def test_duplicates_bad_input_and_missing_wiki_are_rejected(self):
        with self.assertRaises(HarnessError):
            wiki.load_config(self.config_path)
        config = self.make()
        wiki.add(config, self.report, "company", "NVDA", "제목", "요약", "2026-11-20")
        note = self.base / "notes.txt"
        note.write_text("x", encoding="utf-8")
        for arguments in (
            (self.report, "company", "NVDA", "제목", "요약", "2026-11-20"),
            (self.report, "poetry", "NVDA", "제목", "요약", "2026-11-21"),
            (note, "company", "NVDA", "제목", "요약", "2026-11-21"),
            (self.report, "company", "../etc", "제목", "요약", "2026-13-40"),
            (self.report, "company", "///", "제목", "요약", "2026-11-21"),
        ):
            with self.assertRaises(HarnessError):
                wiki.add(config, *arguments)
        with self.assertRaises(HarnessError):
            wiki.init("cloud", self.base / "x", config_path=self.config_path)

    def test_holdings_stay_out_of_drive_wikis(self):
        private = self.base / "portfolio.html"
        private.write_text("<p>보유 수량 12주</p>", encoding="utf-8")
        drive = self.make("drive-folder")
        for allow in (False, True):
            with self.assertRaises(HarnessError):
                wiki.add(drive, private, "other", "내계좌", "점검", "요약", "2026-11-20", allow_holdings=allow)
        local = self.make("local")
        with self.assertRaises(HarnessError):
            wiki.add(local, private, "other", "내계좌", "점검", "요약", "2026-11-20")
        wiki.add(local, private, "other", "내계좌", "점검", "요약", "2026-11-20", allow_holdings=True)

    def test_switching_location_needs_an_explicit_flag(self):
        self.make()
        with self.assertRaises(HarnessError) as caught:
            wiki.init("drive-connector", config_path=self.config_path)
        self.assertIn("--switch", str(caught.exception))
        self.assertEqual(wiki.load_config(self.config_path)["mode"], "local")
        wiki.init("local", self.base / "wiki", config_path=self.config_path)
        wiki.init("drive-connector", switch=True, config_path=self.config_path)
        self.assertEqual(wiki.load_config(self.config_path)["mode"], "drive-connector")
        self.assertTrue((self.base / "wiki" / "index.md").is_file())

    def test_notion_report_page_is_filed_by_iso_week(self):
        self.assertEqual(wiki.week_label("2026-11-20"), "2026-W47 · 11.16–11.22")
        self.assertEqual(wiki.week_label("2027-01-01"), "2026-W53 · 12.28–01.03")
        source = self.base / "report.json"
        report = {"kind": "산업 리포트", "title": "가상 산업 | 5년", "as_of": "2026년 11월 20일 종가", "headline": "지금은 대기",
                  "summary": ["첫 문단", "둘째 문단"], "summary_refs": [1],
                  "metrics": [{"label": "매출", "value": "+44%", "note": "전년 대비"}],
                  "sections": [{"title": "표", "paragraphs": ["<b>는 글자</b>"], "table": {"caption": "비교", "columns": ["가", "나"], "rows": [["1|2", "3"]]}}],
                  "sources": [{"label": "예시", "url": "https://example.com/a"}]}
        source.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        page = wiki.notion_report(source, "sector", "가상 산업", "대기", "2026-11-20", ["AI"], "https://example.com/r.pdf", "https://example.com/v.mp4")
        self.assertEqual((page["week"], page["properties"]["주차"], page["properties"]["종류"], page["properties"]["date:기준일:start"]),
                         ("2026-W47 · 11.16–11.22", "2026-W47 · 11.16–11.22", "산업", "2026-11-20"))
        self.assertEqual(page["title"], "가상 산업 · 가상 산업 | 5년")
        for expected in ("**지금은 대기**", "둘째 문단 [1](https://example.com/a)", "| 1\\|2 | 3 |", "&lt;b>는 글자", "[해설 영상](https://example.com/v.mp4)",
                         "## 출처", "투자 조언이나 권유가 아닙니다"):
            self.assertIn(expected, page["content"])
        private = self.base / "private.json"
        private.write_text(json.dumps({**report, "summary": "보유 수량 10주"}, ensure_ascii=False), encoding="utf-8")
        for arguments in ((private, "sector", "가", "요약"), (source, "movie", "가", "요약"), (self.report, "sector", "가", "요약"),
                          (source, "sector", "가", "요약", None, (), "http://example.com/a")):
            with self.assertRaises(wiki.HarnessError):
                wiki.notion_report(*arguments)

    def test_notion_connector_mode_and_short_entry(self):
        result = wiki.init("notion-connector", config_path=self.config_path)
        self.assertIn("notion-entry", result["next"])
        config = wiki.load_config(self.config_path)
        self.assertIn("Notion", wiki.status(config)["note"])
        with self.assertRaises(wiki.HarnessError):
            wiki.add(config, self.report, "company", "NVDA", "제목", "요약")
        page = self.base / "long.html"
        page.write_text("<html><head><title>NVDA 리포트</title></head><body><h1>NVDA</h1><h2>실적 <b>요약</b></h2>"
                        + "<p>본문</p>" * 4000 + "<h2>위험</h2></body></html>", encoding="utf-8")
        entry = wiki.notion_entry(page, "company", "NVDA", "실적 리뷰", "가이던스 상회", "2026-11-25", ["반도체"],
                                  "https://example.com/report.pdf")
        fields = {item["name"]: item for item in entry["fields"]}
        self.assertEqual((fields["대상"]["value"], fields["종류"]["value"], fields["기준일"]["value"], fields["태그"]["value"]),
                         ("NVDA", "기업", "2026-11-25", ["반도체"]))
        self.assertIn("- 실적 요약\n- 위험\n", entry["content"])
        self.assertIn("https://example.com/report.pdf", entry["content"])
        self.assertNotIn("본문", entry["content"])
        self.assertLess(entry["sizes"]["payloadChars"] * 20, entry["sizes"]["reportChars"])
        private = self.base / "private.html"
        private.write_text("<p>보유 수량 10주</p>", encoding="utf-8")
        for arguments in ((private, "other", "내계좌", "점검", "요약"), (page, "movie", "NVDA", "제목", "요약"),
                          (page, "company", "NVDA", "제목", "요약", None, (), "http://example.com/a")):
            with self.assertRaises(wiki.HarnessError):
                wiki.notion_entry(*arguments)

    def test_connector_mode_keeps_files_to_the_connector(self):
        result = wiki.init("drive-connector", config_path=self.config_path)
        self.assertEqual((result["mode"], result["path"]), ("drive-connector", None))
        config = wiki.load_config(self.config_path)
        self.assertIn("커넥터", wiki.status(config)["note"])
        with self.assertRaises(HarnessError):
            wiki.add(config, self.report, "company", "NVDA", "제목", "요약")

class TaxTests(unittest.TestCase):
    def test_rules_carry_a_source_for_every_entry(self):
        document = tax.rules()
        self.assertGreaterEqual(len(document["rules"]), 25)
        for rule in document["rules"]:
            self.assertTrue(rule["url"].startswith("https://www.law.go.kr/"), rule["id"])
            self.assertTrue(rule["basis"] and rule["applies"] and rule["confidence"], rule["id"])
        self.assertEqual(len({rule["id"] for rule in document["rules"]}), len(document["rules"]))

    def test_overseas_gain_applies_deduction_netting_and_rate(self):
        result = tax.overseas_gain(10_000_000)
        self.assertEqual((result["taxBase"], result["tax"], result["afterTax"]), (7_500_000, 1_650_000, 8_350_000))
        self.assertEqual(tax.overseas_gain(2_500_000)["tax"], 0)
        self.assertEqual(tax.overseas_gain(10_000_000, losses=4_000_000, domestic_taxable=-1_000_000)["taxBase"], 2_500_000)
        self.assertEqual(tax.overseas_gain(1_000_000, losses=5_000_000)["tax"], 0)
        self.assertEqual(tax.overseas_gain(10_000_000, small_business=True)["tax"], 825_000)
        self.assertTrue(all(item["url"] for item in result["sources"]))
        self.assertIn("세무 자문이 아닙니다", result["warnings"][-1])
        with self.assertRaises(HarnessError):
            tax.overseas_gain(-1)

    def test_gift_tax_follows_deductions_and_brackets(self):
        adult = tax.gift(100_000_000, "child-adult", gift_date="2026-11-21")
        self.assertEqual((adult["deduction"], adult["taxBase"], adult["computedTax"], adult["filingCredit"], adult["taxDue"]),
                         (50_000_000, 50_000_000, 5_000_000, 150_000, 4_850_000))
        self.assertEqual(adult["filingDeadline"], "2027-02-28")
        self.assertEqual(tax.gift(20_000_000, "child-minor")["taxDue"], 0)
        self.assertEqual(tax.gift(30_000_000, "child-adult")["taxFreeRoom"], 20_000_000)
        self.assertEqual(tax.gift(600_000_000, "spouse")["taxDue"], 0)
        big = tax.gift(600_000_000, "child-adult")
        self.assertEqual((big["taxBase"], big["topRatePct"], big["computedTax"]), (550_000_000, 30, 105_000_000))
        self.assertEqual(tax.gift(150_000_000, "child-adult", marriage_birth=100_000_000)["taxDue"], 0)
        self.assertEqual(tax.gift(5_000_000_000, "other")["computedTax"], 2_040_000_000)

    def test_gift_aggregates_ten_years_and_surcharges_generation_skips(self):
        again = tax.gift(50_000_000, "child-adult", prior=100_000_000, prior_tax=5_000_000)
        self.assertEqual((again["aggregated"], again["taxBase"], again["computedTax"]), (150_000_000, 100_000_000, 10_000_000))
        self.assertEqual(again["taxDue"], 5_000_000 - 150_000)
        self.assertEqual(tax.gift(50_000_000, "child-adult", deduction_used=50_000_000)["taxBase"], 50_000_000)
        skipped = tax.gift(100_000_000, "child-adult", skip_generation=True)
        self.assertEqual((skipped["generationSkipSurcharge"], skipped["taxDue"]), (1_500_000, 6_305_000))
        self.assertEqual(tax.gift(3_000_000_000, "child-minor", skip_generation=True)["generationSkipSurcharge"],
                         int(tax.gift(3_000_000_000, "child-minor")["computedTax"] * 0.4))
        for arguments in ((0, "child-adult"), (1, "cousin"), (10, "spouse", 0, 0, 0, 1),
                          (10, "spouse", 0, 0, 0, 0, True), (10, "child-adult", 0, 0, 0, 200_000_000)):
            with self.assertRaises(HarnessError):
                tax.gift(*arguments)
        with self.assertRaises(HarnessError):
            tax.gift(10, "child-adult", gift_date="2026-02-30")

    def test_gift_value_averages_two_months_each_side(self):
        days = [date(2026, 1, 1) + timedelta(days=index) for index in range(200)]
        series = [(day, 100.0 if day < date(2026, 4, 1) else 200.0) for day in days]
        result = tax.gift_value(series, "2026-04-01")
        self.assertEqual((result["window"], result["complete"]),
                         ({"start": "2026-02-02", "end": "2026-05-31"}, True))
        before = sum(1 for day in days if date(2026, 2, 2) <= day < date(2026, 4, 1))
        after = sum(1 for day in days if date(2026, 4, 1) <= day <= date(2026, 5, 31))
        self.assertEqual(result["averageClose"], round((before * 100 + after * 200) / (before + after), 4))
        self.assertFalse(tax.gift_value(series[:120], "2026-04-01")["complete"])
        with self.assertRaises(HarnessError):
            tax.gift_value(series[:40], "2026-04-01")

    def test_transaction_dividend_and_pension(self):
        self.assertEqual(tax.transaction_tax("kospi", 10_000_000)["tax"], 20_000)
        self.assertEqual(tax.transaction_tax("konex", 10_000_000)["tax"], 10_000)
        self.assertEqual(tax.transaction_tax("otc", 10_000_000)["tax"], 35_000)
        home = tax.dividend(1_000_000)
        self.assertEqual((home["withheld"], home["comprehensiveTaxation"]), (154_000, False))
        self.assertEqual(tax.dividend(1_000_000, foreign_withheld_pct=15)["withheld"], 150_000)
        self.assertEqual(tax.dividend(1_000_000, foreign_withheld_pct=10)["withheld"], 144_000)
        self.assertTrue(tax.dividend(5_000_000, other_financial_income=16_000_000)["comprehensiveTaxation"])
        self.assertEqual(tax.pension_credit(6_000_000, 3_000_000)["taxCredit"], 1_188_000)
        self.assertEqual(tax.pension_credit(9_000_000, 0, lower_income=True)["eligible"], 6_000_000)
        self.assertEqual(tax.pension_credit(9_000_000, 3_000_000, lower_income=True)["taxCredit"], 1_485_000)
        with self.assertRaises(HarnessError):
            tax.transaction_tax("nasdaq", 1)

    def test_stale_rules_are_flagged(self):
        document = tax.rules() | {"checkedOn": "2025-01-01"}
        self.assertIn("오래됐습니다", tax.envelope(document, {}, "gift-rates")["warnings"][0])

if __name__ == "__main__":
    unittest.main()
