import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import broadcast
import music

TRACK = "c42c476d-ceb8-4042-bdca-e3244597db32"


def item(license_id="by", seconds=184, **changes):
    return {"id": TRACK, "title": "Breaking News 1", "creator": "Sascha Ende", "license": license_id, "license_version": "4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/", "duration": seconds * 1000, "filetype": "wav",
            "filesize": 32_000_000, "foreign_landing_url": "https://example.org/track", "source": "wikimedia_audio",
            "url": "https://example.org/track.wav", **changes}


class MusicTest(unittest.TestCase):
    def test_search_keeps_only_reusable_long_enough_tracks(self):
        asked = []

        def get(url):
            asked.append(url)
            return {"results": [item(), item("by-nc"), item("cc0", 12), item("cc0", 60, title="Free Bed"), item("by-nd")]}

        result = music.search("breaking  news", get=get)
        self.assertIn("license=cc0%2Cpdm%2Cby", asked[0])
        self.assertIn("q=breaking+news", asked[0])
        self.assertEqual([(track["title"], track["license"], track["attributionRequired"]) for track in result["tracks"]],
                         [("Breaking News 1", "CC BY 4.0", True), ("Free Bed", "CC0 4.0", False)])
        for query in ("a", "가" * 81):
            with self.assertRaises(music.MusicError):
                music.search(query, get=get)

    def test_fetch_saves_the_licence_next_to_the_file_and_refuses_other_licences(self):
        with TemporaryDirectory() as folder:
            out = Path(folder) / "bed.wav"
            result = music.fetch(TRACK, out, get=lambda url: item(), grab=lambda url: b"RIFF" + b"0" * 20_000)
            record = json.loads(music.sidecar(out).read_text(encoding="utf-8"))
            self.assertEqual(record["credit"], "음악: Breaking News 1 · Sascha Ende · CC BY 4.0")
            self.assertEqual((result["attributionRequired"], music.read_credit(out)["source"]), (True, "https://example.org/track"))
            with self.assertRaises(music.MusicError):
                music.fetch(TRACK, out, get=lambda url: item(), grab=lambda url: b"0" * 20_000)
            for arguments, source in (((TRACK, Path(folder) / "nc.wav"), item("by-nc-sa")), (("not-an-id", Path(folder) / "x.wav"), item()),
                                      ((TRACK, Path(folder) / "x.exe"), item())):
                with self.assertRaises(music.MusicError):
                    music.fetch(*arguments, get=lambda url, source=source: source, grab=lambda url: self.fail("no download expected"))
            self.assertFalse((Path(folder) / "nc.wav").exists())
        with self.assertRaises(music.MusicError):
            music.download("http://example.org/a.mp3")

    def test_unknown_music_needs_a_typed_credit(self):
        with TemporaryDirectory() as folder:
            loose = Path(folder) / "mine.mp3"
            loose.write_bytes(b"0" * 100)
            with self.assertRaises(music.MusicError):
                music.read_credit(loose)
            self.assertEqual(music.read_credit(loose, "내 곡 · 홍길동 · 직접 제작")["credit"], "내 곡 · 홍길동 · 직접 제작")

    def test_build_mixes_music_and_shows_the_credit(self):
        calls, pages = [], []

        def execute(command):
            command = [str(part) for part in command]
            calls.append(command)
            if command[0] == "chrome":
                page = next(part for part in command if part.startswith("file:"))
                pages.append(Path(page[7:]).read_text(encoding="utf-8") if Path(page[7:]).is_file() else "")
            return "2.0\n" if command[0] == "ffprobe" else ""

        tools = {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "browser": "chrome", "tts": "tts"}
        script = broadcast.validate(json.loads(json.dumps(broadcast.template())))
        with TemporaryDirectory() as folder:
            bed = Path(folder) / "bed.wav"
            music.fetch(TRACK, bed, get=lambda url: item(), grab=lambda url: b"RIFF" + b"0" * 20_000)
            manifest = broadcast.build(script, Path(folder) / "show.mp4", execute=execute, tools=tools, music=bed)
            with self.assertRaises(broadcast.BroadcastError):
                broadcast.build(script, Path(folder) / "b.mp4", execute=execute, tools=tools, music=bed, music_volume=0.9)
            loose = Path(folder) / "loose.mp3"
            loose.write_bytes(b"0" * 100)
            with self.assertRaises(broadcast.BroadcastError):
                broadcast.build(script, Path(folder) / "c.mp4", execute=execute, tools=tools, music=loose)
        mix = next(call for call in calls if "-stream_loop" in call)
        self.assertIn("sidechaincompress", " ".join(mix))
        self.assertIn("volume=0.140", " ".join(mix))
        self.assertEqual(manifest["music"]["credit"], "음악: Breaking News 1 · Sascha Ende · CC BY 4.0")
        self.assertTrue(any("음악: Breaking News 1 · Sascha Ende · CC BY 4.0" in page for page in pages))
        self.assertNotIn("음악:", script["scenes"][-1].get("note") or "")


if __name__ == "__main__":
    unittest.main()
