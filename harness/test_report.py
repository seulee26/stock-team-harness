import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import report

CONTENT = {
    "kind": "기업 분석", "title": "가상 회사 (TEST)", "as_of": "2026년 1월 2일 종가", "headline": "지금은 대기",
    "summary": "가상 예시입니다.", "sections": [{"title": "실적", "paragraphs": ["매출이 10% 늘었습니다."]}],
    "sources": [{"label": "예시 출처", "url": "https://example.com/"}],
}


class ReportTest(unittest.TestCase):
    def test_render_uses_the_shared_design_and_check_tells_hand_written_files(self):
        with TemporaryDirectory() as folder:
            source, output = Path(folder) / "report.json", Path(folder) / "report.html"
            source.write_text(json.dumps(CONTENT, ensure_ascii=False), encoding="utf-8")
            made = report.render(source, output)
            self.assertTrue(made["standardDesign"])
            self.assertIn(report.MARK, output.read_text(encoding="utf-8"))
            hand = Path(folder) / "hand.html"
            hand.write_text("<html><body><h1>직접 쓴 리포트</h1></body></html>", encoding="utf-8")
            result = report.check([output, hand])
            self.assertEqual((result["allStandard"], [item["standardDesign"] for item in result["files"]]), (False, [True, False]))
            self.assertIn("report.py render", result["files"][1]["fix"])
            for arguments in ((hand, output), (source, Path(folder) / "report.txt"), (Path(folder) / "none.json", output)):
                with self.assertRaises(report.ReportError):
                    report.render(*arguments)
            with self.assertRaises(report.ReportError):
                report.check([source])

    def test_render_asks_for_pdf_only_when_wanted(self):
        calls = []
        with TemporaryDirectory() as folder:
            source = Path(folder) / "report.json"
            source.write_text(json.dumps(CONTENT, ensure_ascii=False), encoding="utf-8")
            made = report.render(source, Path(folder) / "report.html", pdf=True, run=lambda command: calls.append(Path(str(command[1])).name))
        self.assertEqual((calls, sorted(made)), (["render_report.py", "render_pdf.py"], ["html", "pdf", "standardDesign"]))


if __name__ == "__main__":
    unittest.main()
