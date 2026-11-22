#!/usr/bin/env python3
"""Find background music that may be reused, and keep its licence next to the file.

Search goes through the Openverse catalogue of openly licensed audio. Only
licences that allow reuse in a published video without extra conditions are
accepted: CC0, public domain, and CC BY (credit required). Every download gets
a .license.json file so the credit travels with the music.
"""

import argparse
import json
from pathlib import Path
import re
import sys
from urllib import error, parse, request

API = "https://api.openverse.org/v1/audio/"
LICENSES = {"cc0": "CC0", "pdm": "Public Domain", "by": "CC BY"}
MAX_BYTES = 60_000_000
AUDIO_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SUFFIXES = {"mp3", "mp32", "wav", "ogg", "oga", "ogx", "flac", "m4a"}
AGENT = {"User-Agent": "stock-harness-music/1.0 (+https://github.com/seulee26/stock-team-harness)"}


class MusicError(Exception):
    pass


class HttpsOnly(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_json(url):
    try:
        with request.build_opener(HttpsOnly).open(request.Request(url, headers=AGENT), timeout=30) as response:
            return json.loads(response.read(2_000_000).decode("utf-8"))
    except error.HTTPError as failure:
        raise MusicError(f"Openverse 응답 {failure.code}. 잠시 뒤에 다시 시도해 주세요.") from None
    except (error.URLError, OSError, ValueError):
        raise MusicError("Openverse에 연결하지 못했습니다.") from None


def download(url):
    if not url.startswith("https://"):
        raise MusicError("https 주소의 파일만 받습니다.")
    try:
        with request.build_opener(HttpsOnly).open(request.Request(url, headers=AGENT), timeout=120) as response:
            kind = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if kind and not (kind.startswith("audio/") or kind in ("application/ogg", "application/octet-stream")):
                raise MusicError(f"음악 파일이 아닙니다 ({kind}).")
            body = response.read(MAX_BYTES + 1)
    except error.HTTPError as failure:
        raise MusicError(f"파일 응답 {failure.code}. 다른 곡을 골라 주세요.") from None
    except (error.URLError, OSError):
        raise MusicError("파일을 받지 못했습니다.") from None
    if not 10_000 < len(body) <= MAX_BYTES:
        raise MusicError("파일이 비어 있거나 60MB를 넘습니다.")
    return body


def describe(item):
    """Keep only what a person needs to judge and credit a track."""
    license_id = item.get("license")
    version = item.get("license_version") or ""
    name = LICENSES.get(license_id)
    return {
        "id": item.get("id"), "title": item.get("title"), "creator": item.get("creator") or "작자 미상",
        "license": f"{name} {version}".strip() if name else license_id, "licenseUrl": item.get("license_url"),
        "allowed": license_id in LICENSES, "attributionRequired": license_id == "by",
        "seconds": round((item.get("duration") or 0) / 1000), "fileType": item.get("filetype"),
        "sizeMB": round((item.get("filesize") or 0) / 1_000_000, 1),
        "source": item.get("foreign_landing_url"), "provider": item.get("source"), "file": item.get("url"),
    }


def search(query, *, min_seconds=30, limit=10, get=fetch_json):
    query = " ".join(str(query).split())
    if not 2 <= len(query) <= 80:
        raise MusicError("검색어는 2~80자로 적어 주세요. 영어 검색어가 결과가 많습니다.")
    if not 1 <= limit <= 20:
        raise MusicError("limit는 1~20 사이여야 합니다.")
    data = get(API + "?" + parse.urlencode({"q": query, "license": ",".join(LICENSES), "page_size": 20}))
    tracks = [describe(item) for item in data.get("results") or []]
    tracks = [track for track in tracks if track["allowed"] and track["seconds"] >= min_seconds][:limit]
    return {
        "dataScope": "open-licensed-audio", "catalogue": "Openverse", "query": query, "tracks": tracks,
        "licenses": "CC0와 퍼블릭 도메인은 표기 없이, CC BY는 만든 사람과 라이선스를 표기하고 쓸 수 있습니다. "
                    "비영리(NC), 변경 금지(ND), 동일조건(SA) 라이선스는 결과에서 뺐습니다.",
        "next": "곡을 고르면 music.py fetch <id> --out <파일>로 받습니다. 받기 전에 source 주소에서 라이선스 표기를 한 번 확인하세요.",
    }


def credit_line(track):
    line = f"음악: {track['title']} · {track['creator']} · {track['license']}"
    return line[:160]


def sidecar(path):
    return Path(str(path) + ".license.json")


def fetch(audio_id, out, *, get=fetch_json, grab=download):
    if not AUDIO_ID.fullmatch(str(audio_id)):
        raise MusicError("검색 결과의 id를 그대로 넣어 주세요.")
    track = describe(get(f"{API}{audio_id}/"))
    if not track["allowed"]:
        raise MusicError(f"이 곡의 라이선스({track['license']})는 받지 않습니다. CC0, 퍼블릭 도메인, CC BY 곡만 받습니다.")
    out = Path(out)
    if out.suffix.lower().lstrip(".") not in SUFFIXES:
        raise MusicError("저장할 파일 이름은 " + ", ".join(sorted(SUFFIXES - {"mp32"})) + " 중 하나로 끝나야 합니다.")
    if out.exists() or sidecar(out).exists():
        raise MusicError("같은 이름의 파일이 이미 있습니다. 다른 이름을 지정해 주세요.")
    body = grab(track["file"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body)
    record = {key: track[key] for key in ("id", "title", "creator", "license", "licenseUrl", "attributionRequired", "source", "provider")}
    record["credit"] = credit_line(track)
    sidecar(out).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"dataScope": "open-licensed-audio", "file": str(out), "licenseFile": str(sidecar(out)), **record,
            "next": "broadcast.py build ... --music 이 파일 로 영상에 넣습니다. CC BY 곡은 영상과 게시 글에 credit을 적어야 합니다."}


def read_credit(path, manual=None):
    """Return the licence record for a music file, or build one from a credit the user typed."""
    record_path = sidecar(path)
    if record_path.is_file():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise MusicError("음악의 라이선스 기록을 읽지 못했습니다.") from None
        if not isinstance(record, dict) or not record.get("credit"):
            raise MusicError("음악의 라이선스 기록 형식이 올바르지 않습니다.")
        return record
    manual = " ".join(str(manual or "").split())
    if not 5 <= len(manual) <= 160:
        raise MusicError("이 음악의 출처와 라이선스를 알 수 없습니다. music.py fetch로 받거나, 직접 권리를 확인한 곡이면 "
                         "--music-credit \"곡명 · 만든 사람 · 라이선스\"로 적어 주세요.")
    return {"title": None, "creator": None, "license": None, "attributionRequired": True, "source": None, "credit": manual}


def main():
    parser = argparse.ArgumentParser(description="재사용할 수 있는 배경 음악을 찾고 라이선스와 함께 받는다")
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("search", help="Openverse에서 CC0, 퍼블릭 도메인, CC BY 음악 찾기")
    find.add_argument("query")
    find.add_argument("--min-seconds", type=int, default=30)
    find.add_argument("--limit", type=int, default=10)
    get = commands.add_parser("fetch", help="고른 곡을 받고 라이선스 기록을 함께 저장")
    get.add_argument("id")
    get.add_argument("--out", required=True)
    show = commands.add_parser("credit", help="받아 둔 음악의 표기 문구 보기")
    show.add_argument("file")
    args = parser.parse_args()
    try:
        if args.command == "search":
            result = search(args.query, min_seconds=args.min_seconds, limit=args.limit)
        elif args.command == "fetch":
            result = fetch(args.id, args.out)
        else:
            result = read_credit(args.file)
    except MusicError as failure:
        print(f"음악 작업 실패: {failure}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
