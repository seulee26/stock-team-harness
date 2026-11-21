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
import quant
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

    def test_catalog_marks_live_trading_tools(self):
        entries = connectors.catalog()["projects"]
        self.assertTrue(all({"repository", "license", "use", "liveOrders", "harnessMode"} <= set(entry) for entry in entries))
        self.assertTrue(all(entry["harnessMode"] in ("research", "backtest", "paper", "data", "reference") for entry in entries))


if __name__ == "__main__":
    unittest.main()
