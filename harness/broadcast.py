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
from base64 import b64decode, b64encode
from hashlib import sha256
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

import music as music_library

HOME = Path(os.environ.get("STOCK_HARNESS_BROADCAST_HOME") or Path.home() / ".local/share/stock-team/broadcast")
TTS_PACKAGE = "supertonic"
KINDS = ("title", "bullets", "table", "bars", "cards", "closing")
TONES = ("neutral", "good", "warn", "bad", "up", "down")
TAPE_SPEED = 110
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
TURN_PAUSE = 0.3
MAX_TURN = 600
CAPTION_CHARS = 34
FORMATS = {"anchor": "앵커 한 명이 전달", "interview": "앵커와 전문가의 대담"}
STYLES = {
    "board": {"label": "방송 보드 · 그림 없이 숫자와 표 중심 (무료)", "prompt": None},
    "illustration": {
        "label": "2D 일러스트 · 장면마다 그림 한 장 (이미지 API 필요)", "background": "opaque",
        "prompt": "Flat editorial vector illustration for a financial news broadcast, bold simple shapes, deep navy background, "
                  "accents in signal red, bright yellow and cobalt blue, subtle grain, wide composition with the subject centred.",
    },
    "3d": {
        "label": "3D 오브젝트 · 장면마다 입체 그림 한 장 (이미지 API 필요)", "background": "transparent",
        "prompt": "Soft 3D clay toy style object render, matte clay and glossy cobalt blue glass, coral and yellow accents, "
                  "soft top-left studio light, rounded friendly shapes, single object group centred, fully transparent background.",
    },
}
ART_RULES = " No text, no letters, no numbers, no logos, no brand marks, no real people."
IMAGE_LAYOUTS = ("side", "corner", "full")
MAX_NARRATION = 900
MAX_SCENES = 40
SENTENCE = re.compile(r"[^.!?。]+[.!?。]+|[^.!?。]+$")
HARD_TO_READ = re.compile(r"[A-Za-z]{2,}|\d|[$%]")

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1280px;height:720px;overflow:hidden}
body{font-family:'Pretendard','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;color:#f4f7fb;word-break:keep-all;
background:#0a1322 linear-gradient(180deg,#101d33 0%,#0a1322 60%,#070d18 100%)}
body:before{content:'';position:absolute;inset:0;background-image:linear-gradient(#ffffff0a 1px,transparent 1px),
linear-gradient(90deg,#ffffff0a 1px,transparent 1px);background-size:64px 64px}
.top{position:absolute;left:0;right:0;top:0;height:56px;display:flex;align-items:center;background:#060b15;border-bottom:2px solid #e11d2e}
.badge{height:100%;display:flex;align-items:center;padding:0 22px;background:#e11d2e;color:#fff;font-size:21px;font-weight:800;letter-spacing:.02em}
.program{padding-left:18px;font-size:20px;font-weight:700;color:#dbe6f3;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.clock{padding-right:24px;font-size:18px;color:#9fb3c8;font-variant-numeric:tabular-nums;white-space:nowrap}
.frame{position:absolute;left:0;right:0;top:56px;bottom:108px;padding:26px 56px 18px;display:flex;flex-direction:column}
h1{font-size:42px;line-height:1.25;font-weight:800;padding-left:18px;border-left:8px solid #e11d2e}
.sub{font-size:23px;line-height:1.45;color:#9fb3c8;margin-top:10px;padding-left:26px}
.body{flex:1;display:flex;flex-direction:column;justify-content:center;margin-top:14px;min-height:0}
ul{list-style:none;display:flex;flex-direction:column;gap:15px}
li{font-size:29px;line-height:1.42;padding-left:34px;position:relative}
li:before{content:'';position:absolute;left:4px;top:15px;width:14px;height:14px;background:#ffd400}
.wait{visibility:hidden}
table{width:100%;border-collapse:collapse;font-size:24px;font-variant-numeric:tabular-nums}
th{text-align:left;font-weight:700;color:#ffd400;border-bottom:2px solid #ffd400;padding:9px 12px;background:#ffffff0a}
td{padding:12px 12px;border-bottom:1px solid #24324a}
td:first-child{font-weight:700}
table.compact{font-size:21px}table.compact td{padding:7px 12px}table.compact th{padding:6px 12px}
.bar{display:grid;grid-template-columns:270px 1fr 170px;align-items:center;gap:18px;margin:7px 0;font-size:25px}
.bar .label{font-weight:700}.bar .track{height:28px;background:#1b2740;overflow:hidden}
.bar .fill{height:100%}.bar .value{font-weight:800;text-align:right;font-variant-numeric:tabular-nums}
.fill.neutral{background:#64748b}.fill.good{background:#22c55e}.fill.warn{background:#f59e0b}.fill.bad{background:#ef4444}
.fill.up{background:#ff4d4f}.fill.down{background:#3b82f6}
.cards{display:grid;gap:14px}
.card{background:#131c2e;border:1px solid #24324a;border-top:6px solid #64748b;padding:14px 18px}
.card .label{font-size:21px;font-weight:700;color:#9fb3c8}
.card .value{font-size:33px;font-weight:800;margin-top:3px}
.card .note{font-size:20px;line-height:1.4;color:#c5d2e2;margin-top:5px}
.card.good{border-top-color:#22c55e}.card.good .value{color:#4ade80}
.card.warn{border-top-color:#f59e0b}.card.warn .value{color:#fbbf24}
.card.bad{border-top-color:#ef4444}.card.bad .value{color:#f87171}
.card.up{border-top-color:#ff4d4f}.card.up .value{color:#ff6b6d}
.card.down{border-top-color:#3b82f6}.card.down .value{color:#60a5fa}
.note-line{font-size:19px;color:#9fb3c8;margin-top:14px;line-height:1.4}
.lower{position:absolute;left:0;right:0;bottom:44px;height:64px;display:flex;align-items:center;background:#f4f7fb;color:#0a1322}
.chip{height:100%;display:flex;align-items:center;padding:0 20px;background:#ffd400;font-size:21px;font-weight:800}
.caption{flex:1;padding:0 18px;font-size:25px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.caption.say{font-size:27px;font-weight:700;letter-spacing:-.01em}
.top .fine{padding:0 18px;font-size:15px;color:#8fa3b8;white-space:nowrap}
.fine{padding-right:18px;font-size:15px;color:#44566b;white-space:nowrap}
.lower.cast .caption{margin-right:150px}
.presenter{position:absolute;right:22px;bottom:44px;width:122px;height:122px;border-radius:50%;background:#ffe3d8;border:4px solid #ffd400;overflow:hidden}
.presenter img{width:118%;margin-left:-9%;display:block}
.panel{position:absolute;right:20px;bottom:44px;display:flex;gap:12px;align-items:flex-end}
.guest{width:112px;text-align:center;opacity:.55}
.guest img,.guest span{display:block;width:104px;height:104px;margin:0 auto;border-radius:50%;background:#ffe3d8;border:4px solid #8a99ab;object-fit:cover;object-position:top}
.guest span{line-height:96px;font-size:44px;font-weight:800;color:#0a1322}
.guest b{display:block;margin-top:-14px;position:relative;padding:3px 0;font-size:15px;font-weight:800;color:#0a1322;background:#dbe6f3;border-radius:4px}
.guest.on{opacity:1}.guest.on img,.guest.on span{border-color:#ffd400;width:116px;height:116px}.guest.on b{background:#ffd400}
.lower.talk2 .caption{margin-right:268px}.lower.talk3 .caption{margin-right:392px}.lower.talk4 .caption{margin-right:516px}
.tape{position:absolute;left:0;right:0;bottom:0;height:44px;background:#03060c;border-top:2px solid #e11d2e}
.cols{flex:1;min-height:0;display:grid;grid-template-columns:1.5fr 1fr;gap:30px;align-items:center;margin-top:14px}
.cols .body{margin-top:0;height:100%}.cols li{font-size:26px}.cols .card .value{font-size:28px}
.art{height:100%;max-height:392px;border-radius:20px;overflow:hidden;border:1px solid #2b3b57;
background:radial-gradient(circle at 35% 30%,#22365a 0%,#131c2e 70%);box-shadow:0 18px 40px #0008}
.art img{width:100%;height:100%;object-fit:cover;display:block}.art.clear img{object-fit:contain}
.art.corner{position:absolute;right:56px;top:14px;width:214px;height:142px;max-height:none;border-radius:14px}
.frame.corner h1,.frame.corner .sub{margin-right:240px}
.backdrop{position:absolute;inset:56px 0 108px 0;overflow:hidden}
.backdrop img{position:absolute;right:0;top:0;height:100%;width:62%;object-fit:cover}
.backdrop.clear img{object-fit:contain;right:4%;width:46%}
.backdrop:after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,#0a1322 0%,#0a1322 36%,#0a132299 58%,#0a132200 100%)}
.backdrop.clear:after{background:none}
.frame.full h1,.frame.full .sub,.frame.full .body{max-width:50%}
.title h1{font-size:64px;border-left-width:12px}.title .sub{font-size:28px}.title .body{flex:none}
.title .frame,.closing .frame{justify-content:center}
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
    ticker = script.get("ticker") or []
    if not isinstance(ticker, list) or len(ticker) > 24 or any(
            not isinstance(item, dict) or not item.get("label") or not item.get("value")
            or item.get("tone", "neutral") not in TONES for item in ticker):
        raise BroadcastError(f"ticker: 24개 이하이고 항목마다 label과 value가 있어야 하며 tone은 {', '.join(TONES)} 중 하나여야 합니다.")
    if script.get("style", "board") not in STYLES:
        raise BroadcastError("style: " + ", ".join(STYLES) + " 중 하나여야 합니다.")
    if script.get("format", "anchor") not in FORMATS:
        raise BroadcastError("format: " + ", ".join(FORMATS) + " 중 하나여야 합니다.")
    speakers = script.get("speakers") or {}
    if not isinstance(speakers, dict) or len(speakers) > 4:
        raise BroadcastError("speakers: 출연자는 4명까지입니다.")
    for key, person in speakers.items():
        if not isinstance(person, dict):
            raise BroadcastError(f"speakers.{key}: 이름과 목소리를 적어 주세요.")
        person["name"] = text(person.get("name"), f"speakers.{key} name", 20)
        if person.get("voice", "F1") not in VOICES:
            raise BroadcastError(f"speakers.{key} voice: " + ", ".join(VOICES) + " 중 하나여야 합니다.")
        if person.get("voice_id") and not VOICE_ID.fullmatch(str(person["voice_id"])):
            raise BroadcastError(f"speakers.{key} voice_id의 형식이 올바르지 않습니다.")
    if script.get("format") == "interview" and len(speakers) < 2:
        raise BroadcastError("대담 형식은 speakers에 출연자 두 명 이상이 필요합니다.")
    for number, scene in enumerate(scenes, start=1):
        where = f"장면 {number}"
        if not isinstance(scene, dict) or scene.get("kind") not in KINDS:
            raise BroadcastError(f"{where}: kind는 {', '.join(KINDS)} 중 하나여야 합니다.")
        scene["heading"] = text(scene.get("heading"), f"{where} heading", 70)
        dialogue = scene.get("dialogue")
        if dialogue is not None:
            if scene.get("narration") or not isinstance(dialogue, list) or not 1 <= len(dialogue) <= 8:
                raise BroadcastError(f"{where}: narration과 dialogue 중 하나만 쓰고, dialogue는 1~8마디여야 합니다.")
            for turn in dialogue:
                if not isinstance(turn, dict) or turn.get("speaker") not in speakers:
                    raise BroadcastError(f"{where}: dialogue의 speaker는 speakers에 있는 이름표여야 합니다.")
                turn["text"] = text(turn.get("text"), f"{where} 대사", MAX_TURN)
            scene["narration"] = " ".join(turn["text"] for turn in dialogue)
            if len(scene["narration"]) > MAX_NARRATION * 2:
                raise BroadcastError(f"{where}: 한 장면의 대화는 {MAX_NARRATION * 2}자 이내여야 합니다.")
        else:
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


def turns(script):
    """Flatten the script into spoken turns: (scene number, speaker key or None, text, pause after)."""
    result = []
    for number, scene in enumerate(script["scenes"], start=1):
        lines = [(turn["speaker"], turn["text"]) for turn in scene["dialogue"]] if scene.get("dialogue") else [(None, scene["narration"])]
        for index, (speaker, words) in enumerate(lines):
            result.append((number, speaker, words, PAUSE if index == len(lines) - 1 else TURN_PAUSE))
    return result


def cell(value):
    return escape(str(value))


def reveal_count(scene):
    """How many items a scene can bring in one by one."""
    kind = scene["kind"]
    if kind == "table":
        return len(scene["table"]["rows"])
    if kind == "bars":
        return len(scene["bars"])
    if kind == "cards":
        return len(scene["cards"])
    return len(scene.get("bullets") or [])


def scene_body(scene, shown=None):
    """Draw the scene. Items past `shown` keep their place but stay invisible, so the layout never jumps."""
    kind = scene["kind"]

    def wait(index):
        return " wait" if shown is not None and index >= shown else ""

    if kind == "table":
        table = scene["table"]
        head = "".join(f"<th>{cell(column)}</th>" for column in table["columns"])
        rows = "".join(f'<tr class="{wait(index).strip()}">' + "".join(f"<td>{cell(item)}</td>" for item in row) + "</tr>"
                       for index, row in enumerate(table["rows"]))
        compact = ' class="compact"' if len(table["rows"]) > 5 else ""
        return f"<table{compact}><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
    if kind == "bars":
        top = max(abs(bar["value"]) for bar in scene["bars"]) or 1
        return "".join(
            f'<div class="bar{wait(index)}"><div class="label">{cell(bar["label"])}</div><div class="track">'
            f'<div class="fill {bar.get("tone", "neutral")}" style="width:{abs(bar["value"]) / top * 100:.1f}%"></div></div>'
            f'<div class="value">{cell(bar.get("display", bar["value"]))}</div></div>'
            for index, bar in enumerate(scene["bars"])
        )
    if kind == "cards":
        cards = scene["cards"]
        columns = 1 if len(cards) == 1 else 2 if len(cards) in (2, 4) else 3
        items = "".join(
            f'<div class="card {card.get("tone", "neutral")}{wait(index)}"><div class="label">{cell(card["label"])}</div>'
            f'<div class="value">{cell(card["value"])}</div>'
            + (f'<div class="note">{cell(card["note"])}</div>' if card.get("note") else "") + "</div>"
            for index, card in enumerate(cards)
        )
        return f'<div class="cards" style="grid-template-columns:repeat({columns},1fr)">{items}</div>'
    return "<ul>" + "".join(f'<li class="{wait(index).strip()}">{cell(item)}</li>'
                            for index, item in enumerate(scene.get("bullets") or [])) + "</ul>"


def image_layout(scene):
    if scene.get("image_layout") in IMAGE_LAYOUTS:
        return scene["image_layout"]
    return {"title": "full", "closing": "full", "table": "corner", "bars": "corner"}.get(scene["kind"], "side")


def picture_uri(name, base=None):
    """Inline a presenter picture so the slide stays one self-contained file."""
    if not name:
        return None
    path = Path(name) if Path(name).is_absolute() else Path(base or ".") / name
    if path.suffix.lower() not in (".png", ".webp", ".jpg", ".jpeg") or not path.is_file() or path.stat().st_size > 8_000_000:
        raise BroadcastError(f"그림은 8MB 이하의 png, webp, jpg 파일이어야 합니다: {name}")
    kind = {"png": "png", "webp": "webp"}.get(path.suffix.lower()[1:], "jpeg")
    return f"data:image/{kind};base64," + b64encode(path.read_bytes()).decode("ascii")


def presenter_uri(script, base=None):
    return picture_uri(script.get("presenter"), base)


def cast_pictures(script, base=None):
    return {key: picture_uri(person.get("image"), base) for key, person in (script.get("speakers") or {}).items()}


def scene_html(script, number, presenter=None, cast=None, active=None, shown=None, art=None, spoken=None):
    scene = script["scenes"][number - 1]
    sub = f'<div class="sub">{cell(scene["sub"])}</div>' if scene.get("sub") else ""
    note = f'<div class="note-line">{cell(scene["note"])}</div>' if scene.get("note") else ""
    caption = scene.get("caption") or scene.get("sub") or scene["heading"]
    speakers = script.get("speakers") or {}
    chip, people, lower = "해설", "", ""
    if scene.get("dialogue") and speakers:
        # A talk scene shows every speaker and lights up the one who is talking.
        chip = speakers[active]["name"] if active in speakers else "대담"
        people = '<div class="panel">' + "".join(
            f'<div class="guest{" on" if key == active else ""}">'
            + (f'<img src="{(cast or {}).get(key)}" alt="">' if (cast or {}).get(key) else f'<span>{cell(person["name"][:1])}</span>')
            + f'<b>{cell(person["name"])}</b></div>' for key, person in speakers.items()) + "</div>"
        lower = f" talk{len(speakers)}"
    elif presenter:
        people, lower = f'<div class="presenter"><img src="{presenter}" alt=""></div>', " cast"
    body = f'<div class="body">{scene_body(scene, shown)}{note}</div>'
    layout, backdrop, clear = "", "", " clear" if script.get("style") == "3d" else ""
    if art:
        layout = image_layout(scene)
        picture = f'<img src="{art}" alt="">'
        if layout == "full":
            backdrop = f'<div class="backdrop{clear}">{picture}</div>'
        elif layout == "corner":
            body = f'<div class="art corner{clear}">{picture}</div>' + body
        else:
            body = f'<div class="cols">{body}<div class="art{clear}">{picture}</div></div>'
    return (
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{CSS}</style></head>'
        f'<body class="{scene["kind"]}"><div class="top"><div class="badge">{cell(script.get("program") or "리서치 브리핑")}</div>'
        f'<div class="program">{cell(scene.get("eyebrow") or script["title"])}</div>'
        f'<div class="fine">{cell(script["disclaimer"])}</div>'
        f'<div class="clock">{cell(script["as_of"])} · {number} / {len(script["scenes"])}</div></div>{backdrop}'
        f'<div class="frame {layout}"><h1>{cell(scene["heading"])}</h1>{sub}{body}</div>'
        f'<div class="lower{lower}"><div class="chip">{cell(chip)}</div>'
        f'<div class="caption{" say" if spoken else ""}">{cell(spoken or caption)}</div></div>'
        f'{people}<div class="tape"></div></body></html>'
    )


def caption_chunks(words, limit=CAPTION_CHARS):
    """Cut speech into short caption lines at sentence ends and commas, the way broadcast captions break."""
    chunks = []
    for sentence in (part.strip() for part in SENTENCE.findall(words) if part.strip()):
        line = ""
        for piece in re.findall(r"[^,，]+[,，]?\s*", sentence):
            piece = piece.strip()
            if line and len(line) + len(piece) + 1 > limit:
                chunks.append(line)
                line = piece
            else:
                line = (line + " " + piece).strip()
            while len(line) > limit:
                cut = line.rfind(" ", 0, limit + 1)
                cut = cut if cut > limit // 2 else limit
                chunks.append(line[:cut].strip())
                line = line[cut:].strip()
        if line:
            chunks.append(line)
    return chunks or [words]


def reveal_plan(script):
    """For every spoken turn, the item counts to show one after another while it plays."""
    plan, spoken = [], turns(script)
    for index, (number, _, _, _) in enumerate(spoken):
        scene = script["scenes"][number - 1]
        total = reveal_count(scene)
        scene_turns = [position for position, turn in enumerate(spoken) if turn[0] == number]
        if total <= 1 or script.get("reveal") is False:
            plan.append([None])
        elif len(scene_turns) == 1:
            plan.append(list(range(1, total + 1)))
        else:
            # In a talk the list grows as the conversation moves on; the first turn only opens the scene.
            place = scene_turns.index(index)
            before = round(total * place / len(scene_turns))
            after = round(total * (place + 1) / len(scene_turns))
            plan.append(list(range(before + 1, after + 1)) or [before])
    return plan


TAPE_CSS = """
*{margin:0;padding:0}html,body{background:transparent;height:44px;overflow:hidden}
body{font-family:'Pretendard','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;white-space:nowrap;
font-size:22px;line-height:44px;color:#f4f7fb;font-variant-numeric:tabular-nums}
span{margin-right:44px}b{font-weight:800;margin-right:10px}i{font-style:normal;font-weight:700;margin-left:10px}
.up{color:#ff6b6d}.down{color:#60a5fa}.neutral{color:#9fb3c8}.good{color:#4ade80}.warn{color:#fbbf24}.bad{color:#f87171}
"""


def tape_html(script):
    """One long transparent strip of quotes; ffmpeg slides it along the bottom band."""
    items = "".join(
        f'<span><b>{cell(item["label"])}</b>{cell(item["value"])}'
        + (f'<i class="{item.get("tone", "neutral")}">{cell(item["change"])}</i>' if item.get("change") else "") + "</span>"
        for item in script.get("ticker") or []
    )
    return f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{TAPE_CSS}</style></head><body>{items}</body></html>'


def tape_width(script):
    letters = sum(len(str(item["label"])) + len(str(item["value"])) + len(str(item.get("change", ""))) for item in script["ticker"])
    return min(letters * 22 + len(script["ticker"]) * 64, 10000)


def clock(seconds):
    minutes, rest = divmod(max(seconds, 0), 60)
    return f"{int(minutes // 60):02d}:{int(minutes % 60):02d}:{rest:06.3f}"


def subtitles(script, durations):
    """Split each spoken turn into sentences and share its audio time by length. Talk turns carry the speaker's name."""
    lines, start = ["WEBVTT", ""], 0.0
    speakers = script.get("speakers") or {}
    for (_, speaker, words, pause), duration in zip(turns(script), durations):
        sentences = [part.strip() for part in SENTENCE.findall(words) if part.strip()]
        total = sum(len(sentence) for sentence in sentences) or 1
        cursor = start
        for index, sentence in enumerate(sentences):
            end = cursor + duration * len(sentence) / total
            label = f"{speakers[speaker]['name']}: " if speaker in speakers and index == 0 else ""
            lines += [f"{clock(cursor)} --> {clock(end)}", label + sentence, ""]
            cursor = end
        start += duration + pause
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


def post_json(url, headers, body):
    call = request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                           headers={**headers, "Content-Type": "application/json"}, method="POST")
    host = url.split("/")[2]
    try:
        with request.build_opener(NoRedirect).open(call, timeout=300) as response:
            return json.loads(response.read(80_000_000).decode("utf-8"))
    except error.HTTPError as failure:
        try:
            detail = (json.loads(failure.read(4000).decode("utf-8", "ignore")).get("error") or {}).get("message", "")
        except ValueError:
            detail = ""
        raise BroadcastError(f"{host} 응답 {failure.code}. {str(detail)[:200]}".strip()) from None
    except (error.URLError, TimeoutError, OSError, ValueError):
        raise BroadcastError(f"{host}에 연결하지 못했습니다.") from None


def illustrate(script_path, style, *, post=post_json, environ=os.environ, redo=False):
    """Draw one picture per scene from its `art` line with the user's image API key, and note the files in the script."""
    if style not in STYLES or not STYLES[style]["prompt"]:
        raise BroadcastError("그림을 그리는 화면 스타일은 " + ", ".join(name for name, item in STYLES.items() if item["prompt"]) + " 입니다.")
    credential = environ.get("OPENAI_API_KEY", "").strip()
    if not credential:
        raise BroadcastError("그림을 그리려면 환경 변수 OPENAI_API_KEY가 필요합니다. 키는 대화창에 붙여 넣지 말고 터미널에서 지정해 주세요. "
                             "키가 없으면 board 스타일을 쓰거나 장면의 image에 직접 그림 파일을 적어 주세요.")
    script_path = Path(script_path)
    script = load_script(script_path)
    folder = script_path.with_name(script_path.name.split(".")[0] + ".art")
    folder.mkdir(parents=True, exist_ok=True)
    model = environ.get("STOCK_HARNESS_IMAGE_MODEL", "").strip() or "gpt-image-2.6-flare"
    quality = environ.get("STOCK_HARNESS_IMAGE_QUALITY", "").strip() or "medium"
    drawn, kept, skipped = [], [], []
    for number, scene in enumerate(script["scenes"], start=1):
        target = folder / f"{style}-{number:02d}.webp"
        if not scene.get("art"):
            skipped.append(number)
            continue
        if target.is_file() and not redo:
            kept.append(number)
        else:
            subject = text(scene["art"], f"장면 {number} art", 400)
            reply = post("https://api.openai.com/v1/images/generations", {"Authorization": "Bearer " + credential}, {
                "model": model, "prompt": f"{STYLES[style]['prompt']} Subject: {subject}.{ART_RULES}", "size": "1536x1024",
                "background": STYLES[style]["background"], "output_format": "webp", "quality": quality,
            })
            try:
                target.write_bytes(b64decode(reply["data"][0]["b64_json"]))
            except (KeyError, IndexError, TypeError, ValueError):
                raise BroadcastError(f"장면 {number}의 그림을 받지 못했습니다.") from None
            drawn.append(number)
        scene["image"] = f"{folder.name}/{target.name}"
    script["style"] = style
    for scene in script["scenes"]:
        if scene.get("dialogue"):
            scene.pop("narration", None)
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"style": style, "model": model, "drawn": drawn, "kept": kept, "scenesWithoutArt": skipped, "folder": str(folder),
            "promptsSentTo": "OpenAI 이미지 API (장면의 art 문장만 전송)",
            "next": "그림을 열어 글자나 로고, 실제 인물처럼 보이는 것이 없는지 확인한 뒤 build로 영상을 만듭니다."}


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


def cloud_speech(engine, text_value, speed, credential, voice_id, model, language="ko", *, post=post_audio, context=("", "")):
    if engine == "typecast":
        # Neighbouring sentences let the service keep one steady newsreader tone across scenes.
        return post("https://api.typecast.ai/v1/text-to-speech", {"X-API-KEY": credential}, {
            "voice_id": voice_id, "text": text_value, "model": model,
            "language": {"ko": "kor", "en": "eng", "ja": "jpn"}.get(language, language),
            "prompt": {"emotion_type": "smart", "previous_text": context[0][-300:], "next_text": context[1][:300]},
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


def cached_speech(key_parts, make, cache=None):
    """Paid speech is kept by what was said and how, so a rebuild for new pictures does not pay again."""
    if cache is None:
        return make()
    name = sha256(json.dumps(key_parts, ensure_ascii=False).encode("utf-8")).hexdigest()
    path = Path(cache) / name
    if path.is_file() and path.stat().st_size > 100:
        return path.read_bytes()
    audio = make()
    Path(cache).mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio


def audio_seconds(path, *, execute=run):
    return float(execute(("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path)).strip())


def mix_music(video, track, volume, seconds, *, execute=run):
    """Loop the music under the narration, lower it while the voice speaks, and fade it in and out."""
    mixed = video.with_name(video.stem + ".music.mp4")
    fade_out = max(seconds - 3.0, 0)
    graph = (
        f"[1:a]volume={volume:.3f},afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out:.2f}:d=3[bed];"
        "[0:a]asplit=2[voice][key];"
        "[bed][key]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=450[duck];"
        "[voice][duck]amix=inputs=2:duration=first:normalize=0[a]"
    )
    execute(("ffmpeg", "-y", "-loglevel", "error", "-i", video, "-stream_loop", "-1", "-i", track, "-filter_complex", graph,
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
             "-t", f"{seconds:.3f}", "-movflags", "+faststart", mixed))
    if mixed.is_file():
        mixed.replace(video)


def build(script, output, *, voice=None, speed=1.0, engine="supertonic", voice_id=None, execute=run, tools=None,
          post=post_audio, environ=os.environ, base=None, music=None, music_volume=0.14, music_credit=None, cache=None):
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
    track = None
    if music:
        if not 0.02 <= music_volume <= 0.5:
            raise BroadcastError("music-volume은 0.02~0.5 사이여야 합니다. 해설이 묻히지 않게 0.1~0.2를 권합니다.")
        if not Path(music).is_file():
            raise BroadcastError("배경 음악 파일을 찾지 못했습니다.")
        try:
            track = music_library.read_credit(music, music_credit)
        except music_library.MusicError as failure:
            raise BroadcastError(str(failure)) from None
        if track.get("attributionRequired"):
            # A CC BY track must be credited where the video is shown, so the credit is put on the closing slide.
            script = json.loads(json.dumps(script))
            last = script["scenes"][-1]
            last["note"] = " · ".join(part for part in (last.get("note"), track["credit"]) if part)
    voice = voice or script.get("voice", "F1")
    output.parent.mkdir(parents=True, exist_ok=True)
    durations = []
    with TemporaryDirectory(prefix="broadcast-") as work:
        work = Path(work)
        parts, elapsed = [], 0.0
        presenter = presenter_uri(script, base)
        tape = None
        if script.get("ticker"):
            tape = work / "tape.png"
            (work / "tape.html").write_text(tape_html(script), encoding="utf-8")
            execute((tools["browser"], "--headless=new", "--disable-gpu", "--hide-scrollbars", "--default-background-color=00000000",
                     f"--force-device-scale-factor={SCALE}", f"--window-size={tape_width(script)},44",
                     f"--screenshot={tape}", (work / "tape.html").as_uri()))
        cast = cast_pictures(script, base)
        speakers = script.get("speakers") or {}
        spoken = turns(script)
        sound = ENGINES[engine].get("suffix", "wav")
        plan = reveal_plan(script)
        pictures = {number: picture_uri(scene.get("image"), base) for number, scene in enumerate(script["scenes"], start=1)}
        for index, (number, speaker, words, pause) in enumerate(spoken, start=1):
            audio, part = (work / f"{index:03d}.{ext}" for ext in (sound, "mp4"))
            stills, weights = [], []
            reveal = plan[index - 1]
            lines = caption_chunks(words) if script.get("captions", True) else [None] * len(reveal)
            for step, line in enumerate(lines):
                shown = reveal[min(len(reveal) - 1, step * len(reveal) // len(lines))]
                page, image = (work / f"{index:03d}-{step:02d}.{ext}" for ext in ("html", "png"))
                page.write_text(scene_html(script, number, presenter, cast, speaker, shown, pictures[number], line), encoding="utf-8")
                execute((tools["browser"], "--headless=new", "--disable-gpu", "--hide-scrollbars",
                         f"--force-device-scale-factor={SCALE}", f"--window-size={WIDTH},{HEIGHT}",
                         f"--screenshot={image}", page.as_uri()))
                stills.append(image)
                weights.append(len(line) if line else 1)
            person = speakers.get(speaker) or {}
            if external:
                context = (spoken[index - 2][2] if index > 1 else "", spoken[index][2] if index < len(spoken) else "")
                speaking = person.get("voice_id") or voice_id
                audio.write_bytes(cached_speech(
                    [engine, speaking, model, speed, script.get("language", "ko"), words, context],
                    lambda: cloud_speech(engine, words, speed, credential, speaking, model, script.get("language", "ko"),
                                         post=post, context=context), cache))
            else:
                execute((tools["tts"], "tts", words, "-o", audio, "--lang", script.get("language", "ko"),
                         "--voice", person.get("voice") or voice, "--speed", f"{speed:.2f}"))
            seconds = audio_seconds(audio, execute=execute)
            durations.append(seconds)
            first = index == 1 or spoken[index - 2][0] != number
            size = f"fps=30,scale={int(WIDTH * SCALE)}:{int(HEIGHT * SCALE)}" + (",fade=t=in:st=0:d=0.35" if first else "")
            if len(stills) == 1:
                command = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", stills[0], "-i", audio]
            else:
                # Captions and items change while the turn is spoken, timed by how long each caption line is.
                order = work / f"{index:03d}.txt"
                order.write_text("".join(
                    f"file '{still.name}'\nduration {seconds * weight / sum(weights) + (pause if still is stills[-1] else 0):.3f}\n"
                    for still, weight in zip(stills, weights)) + f"file '{stills[-1].name}'\n", encoding="utf-8")
                command = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", order, "-i", audio]
            if tape:
                # The strip keeps moving across scene cuts because its position depends on total elapsed time.
                command += ["-loop", "1", "-framerate", "30", "-i", tape, "-filter_complex",
                            f"[0:v]{size}[bg];[bg][2:v]overlay=x='W-mod((t+{elapsed:.3f})*{int(TAPE_SPEED * SCALE)}\\,w+W)':y=H-h,format=yuv420p[v]",
                            "-map", "[v]", "-map", "1:a", "-preset", "veryfast"]
            else:
                command += ["-vf", size + ",format=yuv420p", "-tune", "stillimage"]
            command += ["-af", f"loudnorm=I=-16:TP=-1.5:LRA=11,apad=pad_dur={pause}", "-t", f"{seconds + pause:.3f}",
                        "-c:v", "libx264", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", part]
            execute(command)
            elapsed += seconds + pause
            parts.append(part)
            if index == 1 and stills[-1].is_file():
                shutil.copyfile(stills[-1], output.with_suffix(".png"))
        listing = work / "parts.txt"
        listing.write_text("".join(f"file '{part.name}'\n" for part in parts), encoding="utf-8")
        execute(("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listing,
                 "-c", "copy", "-movflags", "+faststart", output))
    pauses = [item[3] for item in turns(script)]
    total = sum(durations) + sum(pauses)
    per_scene = {}
    for (number, _, _, pause), seconds in zip(turns(script), durations):
        per_scene[number] = per_scene.get(number, 0) + seconds + pause
    if track:
        mix_music(output, music, music_volume, total, execute=execute)
    output.with_suffix(".vtt").write_text(subtitles(script, durations), encoding="utf-8")
    manifest = {
        "video": output.name, "subtitles": output.with_suffix(".vtt").name, "poster": output.with_suffix(".png").name,
        "title": script["title"], "asOf": script["as_of"], "scenes": len(script["scenes"]),
        "format": script.get("format", "anchor"), "style": script.get("style", "board"), "speakers": [person["name"] for person in (script.get("speakers") or {}).values()],
        "seconds": round(total, 1), "voice": voice_id if external else voice, "speed": speed,
        "ttsEngine": ENGINES[engine]["label"], "narrationSentTo": ENGINES[engine]["label"] if external else None,
        "sourceReport": script.get("source_report"),
        "music": ({key: track.get(key) for key in ("title", "creator", "license", "source", "credit")} | {"volume": music_volume}
                  if track else None),
        "sceneSeconds": [round(per_scene[number] - PAUSE, 2) for number in sorted(per_scene)],
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def options():
    """The choices a person should be shown every time before a video is made."""
    return {
        "ask": "영상을 만들기 전에 아래 선택지를 항상 보여 주고 고르게 합니다. 고르지 않은 항목은 default를 쓰고 무엇을 썼는지 알립니다.",
        "choices": [
            {"item": "진행 방식", "default": "anchor", "options": FORMATS},
            {"item": "화면 스타일", "default": "board", "options": {name: item["label"] for name, item in STYLES.items()} | {"내 그림": "장면마다 내가 가진 그림 파일을 넣기"}},
            {"item": "길이", "default": "8~10분", "options": ["3분 요약", "8~10분", "15분 심층"]},
            {"item": "목소리", "default": "supertonic", "options": {name: setting["label"] + (" · 본인 키와 요금 필요, 해설 문장이 전송됨" if setting["external"] else " · 무료") for name, setting in ENGINES.items()}},
            {"item": "진행 속도", "default": "1.0", "options": ["1.0 차분하게", "1.08 뉴스처럼 빠르게"]},
            {"item": "배경 음악", "default": "없음", "options": ["없음", "뉴스풍 음악을 찾아서 넣기 (broadcast-music)", "내가 가진 음악 넣기"]},
            {"item": "시청자", "default": "주식을 처음 보는 사람", "options": ["주식을 처음 보는 사람", "투자 경험이 있는 사람"]},
        ],
    }


def template(kind="anchor"):
    if kind == "interview":
        return {
            "title": "리포트 제목", "as_of": "기준 2026년 1월 2일 종가", "language": "ko", "format": "interview", "program": "리서치 대담",
            "source_report": "reports/example.html", "disclaimer": "정보 제공용 해설이며 투자 권유가 아닙니다",
            "speakers": {"anchor": {"name": "AI 앵커", "voice": "F1"}, "expert": {"name": "AI 애널리스트", "voice": "M2"}},
            "ticker": [{"label": "가나다", "value": "$100.00", "change": "+1.2%", "tone": "up"}],
            "scenes": [
                {"kind": "title", "heading": "한 줄 결론", "dialogue": [
                    {"speaker": "anchor", "text": "안녕하십니까. 오늘 리포트의 결론부터 여쭙겠습니다."},
                    {"speaker": "expert", "text": "네, 결론은 한 가지입니다."}]},
                {"kind": "bullets", "heading": "핵심 세 가지", "bullets": ["첫째", "둘째", "셋째"], "dialogue": [
                    {"speaker": "anchor", "text": "근거는 무엇입니까."},
                    {"speaker": "expert", "text": "세 가지입니다."},
                    {"speaker": "anchor", "text": "위험은 없습니까."},
                    {"speaker": "expert", "text": "있습니다. 그 점도 말씀드리겠습니다."}]},
                {"kind": "closing", "heading": "기억할 것", "bullets": ["투자 판단과 책임은 본인에게 있습니다"], "dialogue": [
                    {"speaker": "anchor", "text": "정보 제공을 위한 대담이며 투자 권유가 아닙니다. 시청해 주셔서 감사합니다."}]},
            ],
        }
    return {
        "title": "리포트 제목", "as_of": "기준 2026년 1월 2일 종가", "language": "ko", "voice": "F1", "program": "리서치 브리핑",
        "ticker": [{"label": "가나다", "value": "$100.00", "change": "+1.2%", "tone": "up"},
                   {"label": "라마바", "value": "$50.00", "change": "-0.8%", "tone": "down"}],
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
    sample = commands.add_parser("template", help="대본 JSON 예시 출력")
    sample.add_argument("--format", choices=tuple(FORMATS), default="anchor", help="anchor는 앵커 단독, interview는 앵커와 전문가 대담")
    commands.add_parser("options", help="영상을 만들기 전에 사용자에게 보여 줄 선택지")
    draw = commands.add_parser("illustrate", help="장면의 art 문장으로 그림을 그려 대본에 넣기 (이미지 API 키와 요금 필요)")
    draw.add_argument("script")
    draw.add_argument("--style", required=True, choices=tuple(name for name, item in STYLES.items() if item["prompt"]))
    draw.add_argument("--redo", action="store_true", help="이미 그린 장면도 다시 그립니다")
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
    make.add_argument("--music", help="배경 음악 파일. music.py fetch로 받은 파일이면 라이선스 표기가 자동으로 들어갑니다")
    make.add_argument("--music-volume", type=float, default=0.14, help="해설 대비 음악 크기 (0.02~0.5)")
    make.add_argument("--music-credit", help="직접 권리를 확인한 음악의 표기 문구. 예: \"곡명 · 만든 사람 · CC BY 4.0\"")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            result = doctor()
        elif args.command == "install":
            result = install()
        elif args.command == "template":
            result = template(args.format)
        elif args.command == "options":
            result = options()
        elif args.command == "illustrate":
            result = illustrate(args.script, args.style, redo=args.redo)
        elif args.command == "check":
            script = load_script(args.script)
            result = {"valid": True, "format": script.get("format", "anchor"), "scenes": len(script["scenes"]), "turns": len(turns(script)),
                      "estimatedSeconds": estimate_seconds(script),
                      "readingWarnings": reading_warnings(script)}
        else:
            result = build(load_script(args.script), args.output, voice=args.voice, speed=args.speed, engine=args.tts,
                           voice_id=args.voice_id, base=Path(args.script).resolve().parent,
                           music=args.music, music_volume=args.music_volume, music_credit=args.music_credit,
                           cache=HOME / "speech-cache")
    except BroadcastError as error:
        print(f"방송 제작 실패: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
