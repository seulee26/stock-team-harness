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
        self.assertEqual((programs.count("chrome"), programs.count("tts"), programs.count("ffprobe"), programs.count("ffmpeg")),
                         (1 + sum(len(broadcast.caption_chunks(scene["narration"])) for scene in broadcast.template()["scenes"]), 6, 6, 7))
        self.assertTrue(any("overlay=x=" in part for call in calls for part in call))
        self.assertIn("가나다", broadcast.tape_html(broadcast.template()))
        spoken = [call[2] for call in calls if call[0] == "tts"]
        self.assertEqual(spoken, [scene["narration"] for scene in broadcast.template()["scenes"]])
        self.assertIn("concat", calls[-1])

    def test_paid_engines_send_only_narration_with_the_users_key(self):
        tools = {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "browser": "chrome", "tts": None}
        cases = (
            ("typecast", {"TYPECAST_API_KEY": "example-key", "TYPECAST_VOICE_ID": "tc_0123456789"}, "https://api.typecast.ai/v1/text-to-speech", "X-API-KEY"),
            ("elevenlabs", {"ELEVENLABS_API_KEY": "example-key", "ELEVENLABS_VOICE_ID": "voice0123456789"},
             "https://api.elevenlabs.io/v1/text-to-speech/voice0123456789?output_format=mp3_44100_128", "xi-api-key"),
        )
        for engine, environ, url, header in cases:
            sent, programs = [], []

            def post(target, headers, body):
                sent.append((target, headers, body))
                return b"audio" * 100

            def execute(command):
                programs.append(str(command[0]))
                return "2.0\n" if str(command[0]) == "ffprobe" else ""

            with TemporaryDirectory() as folder:
                manifest = broadcast.build(sample(), Path(folder) / "show.mp4", engine=engine, execute=execute, tools=tools,
                                           post=post, environ=environ)
                saved = (Path(folder) / "show.manifest.json").read_text(encoding="utf-8")
            self.assertEqual(len(sent), 6)
            self.assertEqual((sent[0][0], sent[0][1]), (url, {header: "example-key"}))
            self.assertEqual(sent[0][2].get("text"), broadcast.template()["scenes"][0]["narration"])
            self.assertNotIn("tts", programs)
            self.assertNotIn("example-key", saved)
            self.assertEqual(manifest["narrationSentTo"], broadcast.ENGINES[engine]["label"])
        self.assertEqual(sent[0][2]["voice_settings"], {"speed": 1.0})

    def test_paid_engines_need_key_voice_and_valid_speed(self):
        tools = {"ffmpeg": "x", "ffprobe": "x", "browser": "x", "tts": None}
        cases = (
            ("typecast", {}, 1.0), ("typecast", {"TYPECAST_API_KEY": "example-key"}, 1.0),
            ("elevenlabs", {"ELEVENLABS_API_KEY": "example-key", "ELEVENLABS_VOICE_ID": "bad id!"}, 1.0),
            ("elevenlabs", {"ELEVENLABS_API_KEY": "example-key", "ELEVENLABS_VOICE_ID": "voice0123456789"}, 1.4),
            ("google", {}, 1.0),
        )
        for engine, environ, speed in cases:
            with self.assertRaises(broadcast.BroadcastError) as caught:
                broadcast.build(sample(), "show.mp4", engine=engine, speed=speed, tools=tools, environ=environ,
                                post=lambda *arguments: self.fail("no request expected"))
            self.assertNotIn("example-key", str(caught.exception))
        ready = broadcast.doctor({"TYPECAST_API_KEY": "example-key", "TYPECAST_VOICE_ID": "tc_0123456789"})["engines"]
        self.assertEqual((ready["typecast"]["ready"], ready["elevenlabs"]["ready"]), (True, False))
        self.assertNotIn("example-key", json.dumps(ready))

    def test_broadcast_frame_has_program_caption_and_ticker_rules(self):
        script = sample()
        page = broadcast.scene_html(script, 2, "data:image/png;base64,AAAA")
        for expected in ('class="badge">리서치 브리핑', 'class="caption">핵심 세 가지', 'class="presenter"', 'class="tape"'):
            self.assertIn(expected, page)
        for change in (lambda s: s["ticker"][0].update(tone="rocket"), lambda s: s["ticker"][0].pop("value"),
                       lambda s: s.update(ticker=[{"label": "가", "value": "1"}] * 25)):
            broken = json.loads(json.dumps(broadcast.template()))
            change(broken)
            with self.assertRaises(broadcast.BroadcastError):
                broadcast.validate(broken)
        with self.assertRaises(broadcast.BroadcastError):
            broadcast.presenter_uri({"presenter": "missing.png"})

    def test_interview_uses_each_speakers_voice_and_names_them(self):
        script = broadcast.validate(broadcast.template("interview"))
        self.assertEqual([(turn[0], turn[1], turn[3]) for turn in broadcast.turns(script)][:3],
                         [(1, "anchor", broadcast.TURN_PAUSE), (1, "expert", broadcast.PAUSE), (2, "anchor", broadcast.TURN_PAUSE)])
        page = broadcast.scene_html(script, 2, None, {}, "expert")
        self.assertIn('class="chip">AI 애널리스트', page)
        self.assertEqual(page.count('class="guest on"'), 1)
        calls = []

        def execute(command):
            command = [str(part) for part in command]
            calls.append(command)
            return "2.0\n" if command[0] == "ffprobe" else ""

        tools = {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "browser": "chrome", "tts": "tts"}
        with TemporaryDirectory() as folder:
            manifest = broadcast.build(script, Path(folder) / "talk.mp4", execute=execute, tools=tools)
            captions = (Path(folder) / "talk.vtt").read_text(encoding="utf-8")
        voices = [call[call.index("--voice") + 1] for call in calls if call[0] == "tts"]
        self.assertEqual(voices, ["F1", "M2", "F1", "M2", "F1", "M2", "F1"])
        self.assertEqual((manifest["format"], manifest["speakers"], manifest["scenes"], len(manifest["sceneSeconds"])),
                         ("interview", ["AI 앵커", "AI 애널리스트"], 3, 3))
        self.assertIn("AI 앵커: 안녕하십니까.", captions)
        self.assertIn("AI 애널리스트: 네, 결론은 한 가지입니다.", captions)
        sent = []
        with TemporaryDirectory() as folder:
            script["speakers"]["expert"]["voice_id"] = "tc_expert0001"
            broadcast.build(script, Path(folder) / "talk.mp4", engine="typecast", execute=execute, tools=tools,
                            post=lambda url, headers, body: sent.append(body["voice_id"]) or b"audio" * 100,
                            environ={"TYPECAST_API_KEY": "example-key", "TYPECAST_VOICE_ID": "tc_anchor0001"}, settings={})
        self.assertEqual(sent[:2], ["tc_anchor0001", "tc_expert0001"])

    def test_experts_take_announcer_tagged_voices_and_anchor_keeps_its_own(self):
        listed = [
            {"voice_id": "tc_eng000001", "voice_name": {"eng": "Hermes", "kor": "헤르메스"}, "gender": "male", "age": "middle_age", "use_cases": ["Announcer"]},
            {"voice_id": "tc_kor000001", "voice_name": {"eng": "Jinsub", "kor": "송진섭 앵커"}, "gender": "male", "age": "middle_age", "use_cases": ["Announcer"]},
            {"voice_id": "tc_kor000002", "voice_name": {"eng": "Lee", "kor": "이승주 기자"}, "gender": "male", "age": "young_adult", "use_cases": ["Announcer"]},
            {"voice_id": "tc_docu00001", "voice_name": {"eng": "Doc", "kor": "다큐"}, "gender": "male", "age": "middle_age", "use_cases": ["Documentary"]},
        ]
        asked = []

        def get(url, headers):
            asked.append(url)
            if "/v3/voices" in url:
                return listed
            return [{"voice_id": "tc_docu00001"}, {"voice_id": "tc_kor000002"}, {"voice_id": "tc_kor000001"}]

        script = broadcast.validate(broadcast.template("interview"))
        script["speakers"]["guest"] = {"name": "AI 전략가", "voice": "M1", "gender": "male"}
        voices = broadcast.cast_voices(script, "typecast", "tc_anchor0001", "example-key", settings={}, get=get)
        self.assertEqual(voices, {"anchor": "tc_anchor0001", "expert": "tc_kor000001", "guest": "tc_kor000002"})
        self.assertIn("use_cases=Announcer", asked[0])
        pinned = broadcast.cast_voices(script, "typecast", "tc_anchor0001", "example-key",
                                       settings={"typecast": {"anchor": "tc_mine00001", "experts": ["tc_pin000001"]}}, get=get)
        self.assertEqual((pinned["anchor"], pinned["expert"]), ("tc_mine00001", "tc_pin000001"))
        script["speakers"]["expert"]["voice_tag"] = "Rapper"
        with self.assertRaises(broadcast.BroadcastError):
            broadcast.cast_voices({"speakers": {"expert": script["speakers"]["expert"]}}, "typecast", "tc_anchor0001", "example-key",
                                  settings={}, get=lambda url, headers: [])
        broken = broadcast.template("interview")
        broken["speakers"]["expert"]["age"] = "baby"
        with self.assertRaises(broadcast.BroadcastError):
            broadcast.validate(broken)

    def test_interview_script_rules_and_options(self):
        cases = (
            lambda s: s["scenes"][0]["dialogue"][0].update(speaker="guest"),
            lambda s: s["scenes"][0].update(narration="둘 다 쓰면 안 됩니다."),
            lambda s: s["scenes"][0].update(dialogue=[]),
            lambda s: s.update(speakers={"anchor": {"name": "AI 앵커"}}),
            lambda s: s["speakers"]["expert"].update(voice="X1"),
            lambda s: s.update(format="debate"),
        )
        for change in cases:
            script = broadcast.template("interview")
            change(script)
            with self.assertRaises(broadcast.BroadcastError):
                broadcast.validate(script)
        choices = {choice["item"]: choice for choice in broadcast.options()["choices"]}
        self.assertEqual(set(choices["진행 방식"]["options"]), {"anchor", "interview"})
        self.assertEqual(set(choices["목소리"]["options"]), set(broadcast.ENGINES))
        self.assertIn("배경 음악", choices)

    def test_items_come_in_one_by_one_and_pictures_follow_the_layout(self):
        script = sample()
        self.assertEqual(broadcast.reveal_plan(script), [[None], [1, 2, 3], [None], [None], [None], [None]])
        page = broadcast.scene_html(script, 2, shown=1)
        self.assertEqual(page.count('<li class="wait">'), 2)
        script["reveal"] = False
        self.assertEqual(broadcast.reveal_plan(script)[1], [None])
        talk = broadcast.validate(broadcast.template("interview"))
        self.assertEqual(broadcast.reveal_plan(talk)[2:6], [[1], [2], [2], [3]])
        picture = "data:image/webp;base64,AAAA"
        self.assertIn('class="cols"', broadcast.scene_html(script, 2, art=picture))
        self.assertIn('class="backdrop"', broadcast.scene_html(script, 1, art=picture))
        self.assertIn('class="art corner"', broadcast.scene_html(script, 5, art=picture))
        script["style"] = "3d"
        self.assertIn('class="backdrop clear"', broadcast.scene_html(script, 1, art=picture))
        self.assertNotIn("<img", broadcast.scene_html(script, 2))

    def test_illustrate_draws_only_scenes_with_art_and_keeps_the_key_out(self):
        sent = []

        def post(url, headers, body):
            sent.append((url, headers, body))
            return {"data": [{"b64_json": "QUJDRA=="}]}

        with TemporaryDirectory() as folder:
            path = Path(folder) / "show.script.json"
            script = broadcast.template()
            script["scenes"][1]["art"] = "server racks with cooling pipes"
            path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
            result = broadcast.illustrate(path, "3d", post=post, environ={"OPENAI_API_KEY": "example-key"})
            saved = json.loads(path.read_text(encoding="utf-8"))
            again = broadcast.illustrate(path, "3d", post=post, environ={"OPENAI_API_KEY": "example-key"})
            self.assertEqual((Path(folder) / "show.art" / "3d-02.webp").read_bytes(), b"ABCD")
            for style, environ in (("board", {"OPENAI_API_KEY": "example-key"}), ("3d", {})):
                with self.assertRaises(broadcast.BroadcastError):
                    broadcast.illustrate(path, style, post=post, environ=environ)
        self.assertEqual((result["drawn"], result["scenesWithoutArt"], again["drawn"], again["kept"]), ([2], [1, 3, 4, 5, 6], [], [2]))
        self.assertEqual((saved["style"], saved["scenes"][1]["image"]), ("3d", "show.art/3d-02.webp"))
        self.assertEqual(len(sent), 1)
        self.assertIn("server racks with cooling pipes", sent[0][2]["prompt"])
        self.assertIn("no real people", sent[0][2]["prompt"])
        self.assertEqual(sent[0][2]["background"], "transparent")
        self.assertNotIn("example-key", json.dumps([result, saved], ensure_ascii=False))

    def test_paid_speech_is_reused_from_the_cache(self):
        calls = []

        def make():
            calls.append(1)
            return b"audio" * 100

        with TemporaryDirectory() as folder:
            first = broadcast.cached_speech(["typecast", "v", "문장"], make, folder)
            second = broadcast.cached_speech(["typecast", "v", "문장"], make, folder)
            broadcast.cached_speech(["typecast", "v", "다른 문장"], make, folder)
        self.assertEqual((first, len(calls)), (second, 2))

    def test_captions_break_at_sentences_and_commas_and_show_on_screen(self):
        lines = broadcast.caption_chunks("크리도는 육십칠 퍼센트, 컴포트 시스템즈는 약 오십 퍼센트, 엔벤트는 사십오 퍼센트 내려와 있습니다. 가장 덜 내린 것은 비바입니다.")
        self.assertEqual(lines, ["크리도는 육십칠 퍼센트, 컴포트 시스템즈는 약 오십 퍼센트,", "엔벤트는 사십오 퍼센트 내려와 있습니다.", "가장 덜 내린 것은 비바입니다."])
        self.assertTrue(all(len(line) <= broadcast.CAPTION_CHARS for line in broadcast.caption_chunks("가" * 100)))
        script = sample()
        page = broadcast.scene_html(script, 2, spoken="핵심은 세 가지입니다.")
        self.assertIn('class="caption say">핵심은 세 가지입니다.', page)
        self.assertIn(script["disclaimer"], page.split('class="frame')[0])
        calls = []

        def execute(command):
            calls.append([str(part) for part in command])
            return "2.0\n" if str(command[0]) == "ffprobe" else ""

        tools = {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "browser": "chrome", "tts": "tts"}
        script["captions"] = False
        with TemporaryDirectory() as folder:
            broadcast.build(script, Path(folder) / "plain.mp4", execute=execute, tools=tools)
        self.assertEqual(sum(call[0] == "chrome" for call in calls), 9)

    def test_build_refuses_missing_tools_and_bad_output(self):
        script = sample()
        with self.assertRaises(broadcast.BroadcastError):
            broadcast.build(script, "show.mp4", tools={"ffmpeg": None, "ffprobe": "x", "browser": "x", "tts": "x"})
        with self.assertRaises(broadcast.BroadcastError):
            broadcast.build(script, "show.mov", tools={"ffmpeg": "x", "ffprobe": "x", "browser": "x", "tts": "x"})


if __name__ == "__main__":
    unittest.main()
