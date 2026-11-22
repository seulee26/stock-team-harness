#!/usr/bin/env python3
"""Turn a narration script into a 2D slide video with open-source TTS.

The script is a JSON file a person or an agent writes from a finished report.
Slides are drawn as plain HTML and captured with a local Chrome, narration is
synthesised by a locally installed TTS command, and ffmpeg joins them. Nothing
is sent to a model API, so a rebuild costs no tokens.

Two paid voice services can replace the local TTS when the user sets their own
key: Typecast and ElevenLabs. Only then is the narration text sent out, to that
one service.
"""

import argparse
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib import error, request

HOME = Path(os.environ.get("STOCK_HARNESS_BROADCAST_HOME") or Path.home() / ".local/share/stock-team/broadcast")
TTS_PACKAGE = "supertonic"
KINDS = ("title", "bullets", "table", "bars", "cards", "closing")
TONES = ("neutral", "good", "warn", "bad")
ENGINES = {
    "supertonic": {"label": "Supertonic (내 PC, 오픈소스)", "external": False},
    "typecast": {"label": "Typecast API", "external": True, "key": "TYPECAST_API_KEY", "voice": "TYPECAST_VOICE_ID",
                 "model": ("TYPECAST_MODEL", "ssfm-v31"), "speed": (0.5, 2.0), "suffix": "wav"},
    "elevenlabs": {"label": "ElevenLabs API", "external": True, "key": "ELEVENLABS_API_KEY", "voice": "ELEVENLABS_VOICE_ID",
                   "model": ("ELEVENLABS_MODEL", "eleven_multilingual_v2"), "speed": (0.7, 1.2), "suffix": "mp3"},
}
VOICE_ID = re.compile(r"[A-Za-z0-9_-]{6,80}")
VOICES = ("F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5")
WIDTH, HEIGHT, SCALE = 1280, 720, 1.5
PAUSE = 0.7
MAX_NARRATION = 900
MAX_SCENES = 40
SENTENCE = re.compile(r"[^.!?。]+[.!?。]+|[^.!?。]+$")
HARD_TO_READ = re.compile(r"[A-Za-z]{2,}|\d|[$%]")

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1280px;height:720px;overflow:hidden}
body{font-family:'Pretendard','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;
background:#f6f8fb;color:#12202f;word-break:keep-all}
.frame{position:absolute;inset:0;padding:54px 72px 80px;display:flex;flex-direction:column}
.eyebrow{font-size:22px;font-weight:700;color:#1f5fbf;letter-spacing:.02em}
h1{font-size:50px;line-height:1.25;font-weight:800;margin-top:10px}
.sub{font-size:27px;line-height:1.5;color:#44566b;margin-top:14px}
.body{flex:1;display:flex;flex-direction:column;justify-content:center;margin-top:20px}
ul{list-style:none;display:flex;flex-direction:column;gap:18px}
li{font-size:31px;line-height:1.45;padding-left:34px;position:relative}
li:before{content:'';position:absolute;left:4px;top:17px;width:13px;height:13px;border-radius:50%;background:#1f5fbf}
table{width:100%;border-collapse:collapse;font-size:25px}
th{text-align:left;font-weight:700;color:#44566b;border-bottom:3px solid #12202f;padding:10px 12px}
td{padding:13px 12px;border-bottom:1px solid #d5dde7}
td:first-child{font-weight:700}
table.compact{font-size:22px}table.compact td{padding:8px 12px}table.compact th{padding:7px 12px}
.bar{display:grid;grid-template-columns:270px 1fr 190px;align-items:center;gap:18px;margin:9px 0;font-size:26px}
.bar .label{font-weight:700}.bar .track{height:30px;background:#e3e9f1;border-radius:6px;overflow:hidden}
.bar .fill{height:100%;border-radius:6px}.bar .value{font-weight:700;text-align:right}
.cards{display:grid;gap:18px}
.card{background:#fff;border:1px solid #d5dde7;border-left:9px solid #8a99ab;border-radius:10px;padding:18px 22px}
.card .label{font-size:24px;font-weight:700;color:#44566b}
.card .value{font-size:36px;font-weight:800;margin-top:4px}
.card .note{font-size:22px;line-height:1.4;color:#44566b;margin-top:6px}
.fill.neutral{background:#5b7089}.fill.good{background:#18794e}.fill.warn{background:#b7791f}.fill.bad{background:#c0362c}
.card.good{border-left-color:#18794e}.card.warn{border-left-color:#b7791f}.card.bad{border-left-color:#c0362c}
.card.neutral{border-left-color:#5b7089}
.note-line{font-size:22px;color:#44566b;margin-top:18px;line-height:1.45}
.foot{position:absolute;left:72px;right:72px;bottom:26px;display:flex;justify-content:space-between;
font-size:18px;color:#6b7c90;border-top:1px solid #d5dde7;padding-top:11px}
.title .frame{background:#12202f;color:#fff;justify-content:center}
.title h1{font-size:60px}.title .body{flex:none}.title .sub{color:#c6d3e2}.title .eyebrow{color:#8fb8ff}
.title .foot{color:#9fb0c4;border-top-color:#33475c}
.closing .frame{justify-content:center}
"""


class BroadcastError(Exception):
    pass


def text(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise BroadcastError(f"{name}: 1~{limit}자의 글이어야 합니다.")
    return value.strip()


def load_script(path):
    try:
        script = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BroadcastError(f"대본 파일을 읽지 못했습니다. {error}") from error
    return validate(script)


def validate(script):
    if not isinstance(script, dict):
        raise BroadcastError("대본은 JSON 객체여야 합니다.")
    for name, limit in (("title", 80), ("as_of", 80), ("disclaimer", 120)):
        script[name] = text(script.get(name), name, limit)
    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
        raise BroadcastError(f"scenes: 1~{MAX_SCENES}개의 장면이 필요합니다.")
    if script.get("voice", "F1") not in VOICES:
        raise BroadcastError("voice: " + ", ".join(VOICES) + " 중 하나여야 합니다.")
    for number, scene in enumerate(scenes, start=1):
        where = f"장면 {number}"
        if not isinstance(scene, dict) or scene.get("kind") not in KINDS:
            raise BroadcastError(f"{where}: kind는 {', '.join(KINDS)} 중 하나여야 합니다.")
        scene["heading"] = text(scene.get("heading"), f"{where} heading", 70)
        scene["narration"] = text(scene.get("narration"), f"{where} narration", MAX_NARRATION)
        kind = scene["kind"]
        if kind == "bullets" and not 1 <= len(scene.get("bullets") or []) <= 5:
            raise BroadcastError(f"{where}: bullets는 1~5줄이어야 합니다.")
        if kind == "table":
            table = scene.get("table") or {}
            columns, rows = table.get("columns") or [], table.get("rows") or []
            if not 2 <= len(columns) <= 6 or not 1 <= len(rows) <= 8 or any(len(row) != len(columns) for row in rows):
                raise BroadcastError(f"{where}: 표는 2~6열, 1~8행이고 행마다 열 수가 같아야 합니다.")
        if kind == "bars":
            bars = scene.get("bars") or []
            if not 1 <= len(bars) <= 8:
                raise BroadcastError(f"{where}: bars는 1~8개여야 합니다.")
            for bar in bars:
                if not isinstance(bar.get("value"), (int, float)) or isinstance(bar.get("value"), bool):
                    raise BroadcastError(f"{where}: 막대의 value는 숫자여야 합니다.")
                if bar.get("tone", "neutral") not in TONES:
                    raise BroadcastError(f"{where}: tone은 {', '.join(TONES)} 중 하나여야 합니다.")
        if kind == "cards":
            cards = scene.get("cards") or []
            if not 1 <= len(cards) <= 6 or any(card.get("tone", "neutral") not in TONES for card in cards):
                raise BroadcastError(f"{where}: cards는 1~6개이고 tone은 {', '.join(TONES)} 중 하나여야 합니다.")
    return script


def reading_warnings(script):
    """Narration is read aloud as written, so tickers, digits and symbols are flagged."""
    warnings = []
    for number, scene in enumerate(script["scenes"], start=1):
        found = sorted(set(HARD_TO_READ.findall(scene["narration"])))
        if found:
            warnings.append(f"장면 {number}: 소리 내어 읽기 어려운 표기 {', '.join(found[:6])}")
    return warnings


def estimate_seconds(script, chars_per_second=6.5):
    return round(sum(len(scene["narration"]) / chars_per_second + PAUSE for scene in script["scenes"]))


def cell(value):
    return escape(str(value))


def scene_body(scene):
    kind = scene["kind"]
    if kind == "bullets":
        return "<ul>" + "".join(f"<li>{cell(item)}</li>" for item in scene["bullets"]) + "</ul>"
    if kind == "table":
        table = scene["table"]
        head = "".join(f"<th>{cell(column)}</th>" for column in table["columns"])
        rows = "".join("<tr>" + "".join(f"<td>{cell(item)}</td>" for item in row) + "</tr>" for row in table["rows"])
        compact = ' class="compact"' if len(table["rows"]) > 5 else ""
        return f"<table{compact}><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
    if kind == "bars":
        top = max(abs(bar["value"]) for bar in scene["bars"]) or 1
        return "".join(
            f'<div class="bar"><div class="label">{cell(bar["label"])}</div><div class="track">'
            f'<div class="fill {bar.get("tone", "neutral")}" style="width:{abs(bar["value"]) / top * 100:.1f}%"></div></div>'
            f'<div class="value">{cell(bar.get("display", bar["value"]))}</div></div>'
            for bar in scene["bars"]
        )
    if kind == "cards":
        cards = scene["cards"]
        columns = 1 if len(cards) == 1 else 2 if len(cards) in (2, 4) else 3
        items = "".join(
            f'<div class="card {card.get("tone", "neutral")}"><div class="label">{cell(card["label"])}</div>'
            f'<div class="value">{cell(card["value"])}</div>'
            + (f'<div class="note">{cell(card["note"])}</div>' if card.get("note") else "") + "</div>"
            for card in cards
        )
        return f'<div class="cards" style="grid-template-columns:repeat({columns},1fr)">{items}</div>'
    return "<ul>" + "".join(f"<li>{cell(item)}</li>" for item in scene.get("bullets") or []) + "</ul>"


def scene_html(script, number):
    scene = script["scenes"][number - 1]
    sub = f'<div class="sub">{cell(scene["sub"])}</div>' if scene.get("sub") else ""
    note = f'<div class="note-line">{cell(scene["note"])}</div>' if scene.get("note") else ""
    eyebrow = scene.get("eyebrow") or script["title"]
    return (
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{CSS}</style></head>'
        f'<body class="{scene["kind"]}"><div class="frame"><div class="eyebrow">{cell(eyebrow)}</div>'
        f'<h1>{cell(scene["heading"])}</h1>{sub}<div class="body">{scene_body(scene)}{note}</div></div>'
        f'<div class="foot"><span>{cell(script["disclaimer"])}</span>'
        f'<span>{cell(script["as_of"])} · {number} / {len(script["scenes"])}</span></div></body></html>'
    )


def clock(seconds):
    minutes, rest = divmod(max(seconds, 0), 60)
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}:{rest:06.3f}"


def subtitles(script, durations):
    """Split each narration into sentences and share the scene's audio time by length."""
    lines, start = ["WEBVTT", ""], 0.0
    for scene, duration in zip(script["scenes"], durations):
        sentences = [part.strip() for part in SENTENCE.findall(scene["narration"]) if part.strip()]
        total = sum(len(sentence) for sentence in sentences) or 1
        cursor = start
        for sentence in sentences:
            end = cursor + duration * len(sentence) / total
            lines += [f"{clock(cursor)} --> {clock(end)}", sentence, ""]
            cursor = end
        start += duration + PAUSE
    return "\n".join(lines)


def browser_path():
    configured = os.environ.get("CHROME_BIN")
    candidates = [configured] if configured else []
    candidates += [shutil.which(name) for name in ("google-chrome", "chromium", "chromium-browser")]
    candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def tts_path():
    configured = os.environ.get("STOCK_HARNESS_TTS")
    if configured:
        return configured if Path(configured).is_file() else None
    local = HOME / "venv" / "bin" / TTS_PACKAGE
    return str(local) if local.is_file() else shutil.which(TTS_PACKAGE)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def post_audio(url, headers, body):
    """POST JSON to a fixed HTTPS host and return the audio bytes. The key never appears in errors."""
    call = request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                           headers={**headers, "Content-Type": "application/json"}, method="POST")
    host = url.split("/")[2]
    try:
        with request.build_opener(NoRedirect).open(call, timeout=120) as response:
            audio = response.read(60_000_000)
    except error.HTTPError as failure:
        try:
            detail = json.loads(failure.read(2000).decode("utf-8", "ignore"))
            detail = detail.get("message") or detail.get("detail") or ""
            detail = detail.get("message", "") if isinstance(detail, dict) else str(detail)
        except ValueError:
            detail = ""
        raise BroadcastError(f"{host} 응답 {failure.code}. {detail[:200]}".strip()) from None
    except (error.URLError, TimeoutError, OSError):
        raise BroadcastError(f"{host}에 연결하지 못했습니다.") from None
    if len(audio) < 100:
        raise BroadcastError(f"{host}가 음성을 돌려주지 않았습니다.")
    return audio


def cloud_voice(engine, voice_id=None, environ=os.environ):
    """Return (credential, voice id, model) for a paid engine, read from the user's environment only."""
    setting = ENGINES[engine]
    credential = environ.get(setting["key"], "").strip()
    voice_id = (voice_id or environ.get(setting["voice"], "")).strip()
    if not credential:
        raise BroadcastError(f"{setting['label']}를 쓰려면 환경 변수 {setting['key']}가 필요합니다. 키는 대화창에 붙여 넣지 말고 터미널에서 지정해 주세요.")
    if not VOICE_ID.fullmatch(voice_id):
        raise BroadcastError(f"목소리 ID를 --voice-id 또는 환경 변수 {setting['voice']}로 지정해 주세요.")
    return credential, voice_id, environ.get(setting["model"][0], "").strip() or setting["model"][1]


def cloud_speech(engine, text_value, speed, credential, voice_id, model, language="ko", *, post=post_audio):
    if engine == "typecast":
        return post("https://api.typecast.ai/v1/text-to-speech", {"X-API-KEY": credential}, {
            "voice_id": voice_id, "text": text_value, "model": model,
            "language": {"ko": "kor", "en": "eng", "ja": "jpn"}.get(language, language),
            "output": {"audio_format": "wav", "audio_tempo": speed},
        })
    return post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                {"xi-api-key": credential}, {"text": text_value, "model_id": model, "voice_settings": {"speed": speed}})


def doctor(environ=os.environ):
    tools = {"ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"), "browser": browser_path(), "tts": tts_path()}
    return {
        "ready": all(tools.values()), "tools": tools,
        "engines": {name: ({"ready": bool(tools["tts"])} if not setting["external"] else
                           {"ready": bool(environ.get(setting["key"]) and environ.get(setting["voice"])),
                            "needs": [setting["key"], setting["voice"]], "sendsNarrationTo": setting["label"]})
                    for name, setting in ENGINES.items()},
        "ttsEngine": "Supertonic (코드 MIT, 음성 모델 OpenRAIL-M, 첫 실행 때 모델을 내려받음)",
        "install": {
            "tts": "python3 harness/broadcast.py install",
            "ffmpeg": "macOS는 brew install ffmpeg, Ubuntu는 sudo apt install ffmpeg",
            "browser": "Chrome 또는 Chromium을 설치하거나 CHROME_BIN으로 지정",
        },
        "modelApi": "사용하지 않음. 대본을 쓰는 단계 뒤에는 토큰이 들지 않습니다.",
    }


def run(command):
    result = subprocess.run([str(part) for part in command], capture_output=True, text=True, check=False)
    if result.returncode:
        raise BroadcastError(f"{Path(str(command[0])).name} 실행 실패: {(result.stderr or result.stdout).strip()[-400:]}")
    return result.stdout


def install(python=sys.executable, *, execute=run):
    if sys.version_info < (3, 10):
        raise BroadcastError("TTS 설치에는 Python 3.10 이상이 필요합니다. python3.12 harness/broadcast.py install 처럼 실행해 주세요.")
    venv = HOME / "venv"
    HOME.mkdir(parents=True, exist_ok=True)
    execute((python, "-m", "venv", venv))
    execute((venv / "bin" / "python", "-m", "pip", "install", "--quiet", TTS_PACKAGE))
    return {"installed": TTS_PACKAGE, "command": str(venv / "bin" / TTS_PACKAGE)}


def audio_seconds(path, *, execute=run):
    return float(execute(("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path)).strip())


def build(script, output, *, voice=None, speed=1.0, engine="supertonic", voice_id=None, execute=run, tools=None,
          post=post_audio, environ=os.environ):
    if engine not in ENGINES:
        raise BroadcastError("tts는 " + ", ".join(ENGINES) + " 중 하나여야 합니다.")
    external = ENGINES[engine]["external"]
    tools = dict(tools or doctor()["tools"])
    if external:
        tools.pop("tts", None)
        low, high = ENGINES[engine]["speed"]
        if not low <= speed <= high:
            raise BroadcastError(f"{ENGINES[engine]['label']}의 speed는 {low}~{high} 사이여야 합니다.")
        credential, voice_id, model = cloud_voice(engine, voice_id, environ)
    missing = [name for name, path in tools.items() if not path]
    if missing:
        raise BroadcastError("준비되지 않은 도구: " + ", ".join(missing) + ". python3 harness/broadcast.py doctor 로 확인해 주세요.")
    if not 0.7 <= speed <= 1.5:
        raise BroadcastError("speed는 0.7~1.5 사이여야 합니다.")
    output = Path(output)
    if output.suffix != ".mp4":
        raise BroadcastError("출력 파일 이름은 .mp4로 끝나야 합니다.")
    voice = voice or script.get("voice", "F1")
    output.parent.mkdir(parents=True, exist_ok=True)
    durations = []
    with TemporaryDirectory(prefix="broadcast-") as work:
        work = Path(work)
        parts = []
        for number, scene in enumerate(script["scenes"], start=1):
            sound = ENGINES[engine].get("suffix", "wav")
            page, image, audio, part = (work / f"{number:02d}.{ext}" for ext in ("html", "png", sound, "mp4"))
            page.write_text(scene_html(script, number), encoding="utf-8")
            execute((tools["browser"], "--headless=new", "--disable-gpu", "--hide-scrollbars",
                     f"--force-device-scale-factor={SCALE}", f"--window-size={WIDTH},{HEIGHT}",
                     f"--screenshot={image}", page.as_uri()))
            if external:
                audio.write_bytes(cloud_speech(engine, scene["narration"], speed, credential, voice_id, model,
                                               script.get("language", "ko"), post=post))
            else:
                execute((tools["tts"], "tts", scene["narration"], "-o", audio, "--lang", script.get("language", "ko"),
                         "--voice", voice, "--speed", f"{speed:.2f}"))
            seconds = audio_seconds(audio, execute=execute)
            durations.append(seconds)
            execute(("ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", image, "-i", audio,
                     "-vf", f"scale={int(WIDTH * SCALE)}:{int(HEIGHT * SCALE)},fade=t=in:st=0:d=0.35,format=yuv420p",
                     "-af", f"apad=pad_dur={PAUSE}", "-t", f"{seconds + PAUSE:.3f}",
                     "-c:v", "libx264", "-tune", "stillimage", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", part))
            parts.append(part)
            if number == 1 and image.is_file():
                shutil.copyfile(image, output.with_suffix(".png"))
        listing = work / "parts.txt"
        listing.write_text("".join(f"file '{part.name}'\n" for part in parts), encoding="utf-8")
        execute(("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing,
                 "-c", "copy", "-movflags", "+faststart", output))
    output.with_suffix(".vtt").write_text(subtitles(script, durations), encoding="utf-8")
    manifest = {
        "video": output.name, "subtitles": output.with_suffix(".vtt").name, "poster": output.with_suffix(".png").name,
        "title": script["title"], "asOf": script["as_of"], "scenes": len(durations),
        "seconds": round(sum(durations) + PAUSE * len(durations), 1), "voice": voice_id if external else voice, "speed": speed,
        "ttsEngine": ENGINES[engine]["label"], "narrationSentTo": ENGINES[engine]["label"] if external else None,
        "sourceReport": script.get("source_report"),
        "sceneSeconds": [round(value, 2) for value in durations],
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def template():
    return {
        "title": "리포트 제목", "as_of": "기준 2026년 1월 2일 종가", "language": "ko", "voice": "F1",
        "source_report": "reports/example.html",
        "disclaimer": "정보 제공용 해설이며 투자 권유가 아닙니다",
        "scenes": [
            {"kind": "title", "heading": "한 줄 결론", "sub": "무엇을 다루는지", "narration": "안녕하세요. 오늘 리포트의 결론부터 말씀드립니다."},
            {"kind": "bullets", "heading": "핵심 세 가지", "bullets": ["첫째", "둘째", "셋째"], "narration": "핵심은 세 가지입니다."},
            {"kind": "bars", "heading": "숫자 비교", "bars": [{"label": "가", "value": 44, "display": "+44%", "tone": "good"}],
             "narration": "매출은 사십사 퍼센트 늘었습니다."},
            {"kind": "cards", "heading": "판정", "cards": [{"label": "종목", "value": "통과", "note": "이유", "tone": "good"}],
             "narration": "판정은 통과입니다."},
            {"kind": "table", "heading": "표", "table": {"columns": ["항목", "값"], "rows": [["가", "1"]]}, "narration": "표로 정리했습니다."},
            {"kind": "closing", "heading": "기억할 것", "bullets": ["투자 판단과 책임은 본인에게 있습니다"], "narration": "시청해 주셔서 감사합니다."},
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="리포트 해설 영상을 만든다 (2D 슬라이드 + 오픈소스 TTS)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="필요한 도구가 준비됐는지 확인")
    commands.add_parser("install", help="TTS를 별도 가상 환경에 설치")
    commands.add_parser("template", help="대본 JSON 예시 출력")
    check = commands.add_parser("check", help="대본을 검사하고 길이를 추정")
    check.add_argument("script")
    make = commands.add_parser("build", help="대본으로 mp4, 자막, 표지 이미지를 생성")
    make.add_argument("script")
    make.add_argument("output", help="만들 .mp4 경로. 같은 이름의 .vtt, .png, .manifest.json이 함께 생깁니다")
    make.add_argument("--voice", choices=VOICES)
    make.add_argument("--speed", type=float, default=1.0)
    make.add_argument("--tts", choices=tuple(ENGINES), default=os.environ.get("STOCK_HARNESS_TTS_ENGINE") or "supertonic",
                      help="음성 엔진. typecast와 elevenlabs는 해설 문장을 해당 서비스로 보내며 본인 키와 요금이 필요합니다")
    make.add_argument("--voice-id", help="Typecast 또는 ElevenLabs의 목소리 ID")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            result = doctor()
        elif args.command == "install":
            result = install()
        elif args.command == "template":
            result = template()
        elif args.command == "check":
            script = load_script(args.script)
            result = {"valid": True, "scenes": len(script["scenes"]), "estimatedSeconds": estimate_seconds(script),
                      "readingWarnings": reading_warnings(script)}
        else:
            result = build(load_script(args.script), args.output, voice=args.voice, speed=args.speed, engine=args.tts, voice_id=args.voice_id)
    except BroadcastError as error:
        print(f"방송 제작 실패: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
