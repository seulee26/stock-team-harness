import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import broadcast


def sample():
    return broadcast.validate(json.loads(json.dumps(broadcast.template())))


class BroadcastTest(unittest.TestCase):
    def test_template_is_valid_and_reads_aloud(self):
        script = sample()
        self.assertEqual(len(script["scenes"]), 6)
        self.assertEqual(broadcast.reading_warnings(script), [])
        self.assertGreater(broadcast.estimate_seconds(script), 0)

    def test_narration_with_tickers_or_digits_is_flagged(self):
        script = sample()
        script["scenes"][1]["narration"] = "NVT 매출이 44% 늘었습니다."
        warning = broadcast.reading_warnings(script)[0]
        self.assertTrue(warning.startswith("장면 2"))
        self.assertIn("NVT", warning)

    def test_invalid_scripts_are_rejected(self):
        cases = (
            lambda s: s["scenes"][0].update(kind="movie"),
            lambda s: s["scenes"][0].update(narration=""),
            lambda s: s["scenes"][0].update(narration="가" * (broadcast.MAX_NARRATION + 1)),
            lambda s: s["scenes"][2]["bars"][0].update(value="44"),
            lambda s: s["scenes"][3]["cards"][0].update(tone="great"),
            lambda s: s["scenes"][4]["table"]["rows"].append(["열이 모자람"]),
            lambda s: s.update(voice="X9"),
            lambda s: s.update(scenes=[]),
            lambda s: s.pop("disclaimer"),
        )
        for change in cases:
            script = json.loads(json.dumps(broadcast.template()))
            change(script)
            with self.assertRaises(broadcast.BroadcastError):
                broadcast.validate(script)

    def test_slide_escapes_text_and_shows_disclaimer(self):
        script = sample()
        script["scenes"][1]["bullets"][0] = "<script>alert(1)</script>"
        page = broadcast.scene_html(script, 2)
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn(script["disclaimer"], page)
        self.assertIn("2 / 6", page)
        self.assertIn('class="fill good" style="width:100.0%"', broadcast.scene_html(script, 3))

    def test_subtitles_share_scene_time_by_sentence_length(self):
        script = sample()
        script["scenes"] = script["scenes"][:2]
        script["scenes"][0]["narration"] = "가나. 다라마바사."
        text = broadcast.subtitles(script, [9.0, 4.0])
        self.assertTrue(text.startswith("WEBVTT"))
        self.assertIn("00:00:00.000 --> 00:00:03.000\n가나.", text)
        self.assertIn("00:00:03.000 --> 00:00:09.000\n다라마바사.", text)
        self.assertIn(f"00:00:{9 + broadcast.PAUSE:06.3f} --> ", text)

    def test_build_runs_browser_tts_and_ffmpeg_without_overwriting_the_script(self):
        calls = []

        def execute(command):
            command = [str(part) for part in command]
            calls.append(command)
            return "2.5\n" if command[0] == "ffprobe" else ""

        tools = {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "browser": "chrome", "tts": "tts"}
        with TemporaryDirectory() as folder:
            source = Path(folder) / "show.json"
            source.write_text(json.dumps(broadcast.template(), ensure_ascii=False), encoding="utf-8")
            before = source.read_text(encoding="utf-8")
            manifest = broadcast.build(broadcast.load_script(source), Path(folder) / "show.mp4", execute=execute, tools=tools)
            self.assertEqual(source.read_text(encoding="utf-8"), before)
            self.assertTrue((Path(folder) / "show.vtt").is_file())
            self.assertEqual(json.loads((Path(folder) / "show.manifest.json").read_text(encoding="utf-8")), manifest)
        self.assertEqual((manifest["scenes"], manifest["seconds"]), (6, round(6 * (2.5 + broadcast.PAUSE), 1)))
        programs = [call[0] for call in calls]
        self.assertEqual((programs.count("chrome"), programs.count("tts"), programs.count("ffprobe"), programs.count("ffmpeg")), (6, 6, 6, 7))
        spoken = [call[2] for call in calls if call[0] == "tts"]
        self.assertEqual(spoken, [scene["narration"] for scene in broadcast.template()["scenes"]])
        self.assertIn("concat", calls[-1])

    def test_build_refuses_missing_tools_and_bad_output(self):
        script = sample()
        with self.assertRaises(broadcast.BroadcastError):
            broadcast.build(script, "show.mp4", tools={"ffmpeg": None, "ffprobe": "x", "browser": "x", "tts": "x"})
        with self.assertRaises(broadcast.BroadcastError):
            broadcast.build(script, "show.mov", tools={"ffmpeg": "x", "ffprobe": "x", "browser": "x", "tts": "x"})


if __name__ == "__main__":
    unittest.main()
