import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import integrations
from toss_client import HarnessError


class IntegrationTests(unittest.TestCase):
    def test_fixed_routes_keep_all_six_research_roles(self):
        plan = integrations.plan("nvda")
        self.assertEqual(plan["symbol"], "NVDA")
        self.assertEqual(plan["dataScope"], "public-market-and-filings")
        self.assertEqual(len({r for stage in plan["stages"] for r in stage["roles"]}), 6)
        self.assertEqual(set(tool["name"] for tool in plan["tools"].values()), set(integrations.TOOLS))

    def test_paper_accepts_only_synthetic_no_overdraft_or_shorting(self):
        demo = integrations.PAPER_DEMO
        self.assertEqual(integrations.paper_payload(demo), demo)
        bad_cases = [
            {**demo, "dataScope": "account"},
            {**demo, "account": "fixture"},
            {**demo, "startingCash": 1},
            {**demo, "startingCash": "NaN"},
            {**demo, "trades": list(reversed(demo["trades"]))},
            {**demo, "trades": [{**demo["trades"][0], "side": "sell"}]},
            {**demo, "trades": [{**demo["trades"][0], "quantity": True}]},
        ]
        for payload in bad_cases:
            with self.subTest(data=payload), self.assertRaises(HarnessError):
                integrations.paper_payload(payload)

    def test_paper_uses_offline_sim_broker_adapter(self):
        result = {"fills": [], "cash": 9440, "positions": {"DEMO": 6}}
        with patch.object(integrations, "run_adapter", return_value=result) as run:
            report = integrations.paper(integrations.PAPER_DEMO)
        run.assert_called_once_with("ai-hedge-fund", integrations.PAPER_RUN, integrations.PAPER_DEMO)
        self.assertEqual(report["mode"], "paper")
        self.assertEqual(report["costModel"], "zero")
        self.assertEqual(report["positions"], {"DEMO": 6})

    def test_child_does_not_inherit_broker_or_other_keys(self):
        def fake_run(command, *, input, cwd, env, **kwargs):
            self.assertEqual(command[1:3], ["-I", "-c"])
            self.assertEqual(json.loads(input), {"symbol": "NVDA"})
            self.assertNotIn("TOSSINVEST_CLIENT_SECRET", env)
            self.assertNotIn("BIZROUTER_API_KEY", env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn(integrations.DEBATE_KEY, env)
            (Path(cwd) / "result.json").write_text('{"safe": true}', encoding="utf-8")

        with patch.dict("os.environ", {
            "TOSSINVEST_CLIENT_SECRET": "<test fixture>", "BIZROUTER_API_KEY": "<test fixture>",
            "OPENAI_API_KEY": "<test fixture>", integrations.DEBATE_KEY: "<test fixture>",
        }), patch.object(integrations, "is_installed", return_value=True), patch(
            "integrations.subprocess.run", side_effect=fake_run
        ):
            self.assertEqual(integrations.run_adapter("openbb", "", {"symbol": "NVDA"}), {"safe": True})

    def test_debate_needs_a_dedicated_key(self):
        day = integrations.datetime.now(integrations.ET).date().isoformat()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "<openai fixture>"}, clear=True), patch.object(
            integrations, "run_adapter"
        ) as run:
            with self.assertRaises(HarnessError):
                integrations.debate("NVDA", day, "model-fixture")
            run.assert_not_called()
        with patch.dict("os.environ", {integrations.DEBATE_KEY: "<dedicated fixture>"}, clear=True), patch.object(
            integrations, "run_adapter", return_value={"bull": "fixture"}
        ) as run:
            self.assertEqual(integrations.debate("NVDA", day, "model-fixture")["evidenceCheck"], "required")
            self.assertEqual(run.call_args.kwargs["debate_key"], "<dedicated fixture>")
            self.assertEqual(run.call_args.args[2], {"symbol": "NVDA", "date": day, "model": "model-fixture"})

    def test_filings_only_accepts_sec_urls(self):
        row = {"filing_detail_url": "https://www.sec.gov/Archives/a", "report_url": "https://www.sec.gov/Archives/b"}
        with patch.object(integrations, "run_adapter", return_value=[row]):
            self.assertEqual(integrations.filings("NVDA", 1)["filings"], [row])
        with patch.object(integrations, "run_adapter", return_value=[{
            **row, "report_url": "https://www.sec.gov@example.org/Archives/b",
        }]):
            with self.assertRaises(HarnessError):
                integrations.filings("NVDA", 1)

    def test_openbb_drops_out_of_range_rows_and_keeps_provenance(self):
        rows = [{"date": day} for day in ("2024-01-05", "2024-01-02", "2024-01-10")]
        with patch.object(integrations, "run_adapter", return_value=rows):
            report = integrations.price("NVDA", "2024-01-02", "2024-01-05")
        self.assertEqual(report["provider"], "Nasdaq via OpenBB")
        self.assertEqual([row["date"] for row in report["bars"]], ["2024-01-02", "2024-01-05"])

    def test_doctor_uses_receipts_for_pinned_installations(self):
        with tempfile.TemporaryDirectory() as scratch, patch.object(integrations, "RUNTIME", Path(scratch)):
            status = integrations.doctor()
            self.assertFalse(any(entry["installed"] for entry in status.values()))
            name = "openbb"
            target = Path(scratch) / name
            target.mkdir()
            (target / "source").mkdir()
            binary = integrations.python_path(target)
            binary.parent.mkdir(parents=True)
            binary.touch()
            lock = integrations.read_lock()[name]
            receipt = {key: lock[key] for key in ("repository", "commit", "sha256")}
            (target / "receipt.json").write_text(json.dumps({"name": name, **receipt}), encoding="utf-8")
            self.assertTrue(integrations.doctor()[name]["installed"])
            receipt["commit"] = "unverified"
            (target / "receipt.json").write_text(json.dumps({"name": name, **receipt}), encoding="utf-8")
            self.assertFalse(integrations.doctor()[name]["installed"])


if __name__ == "__main__":
    unittest.main()
