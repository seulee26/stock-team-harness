"""Opt-in public data connections. Each one stays off until the user supplies their own key."""

import argparse
from datetime import date, datetime, timedelta
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from xml.etree import ElementTree
import zipfile

from toss_client import HarnessError, NoRedirect
from workflows import ET, KST


ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".local" / "cache"
CATALOG = Path(__file__).with_name("quant-catalog.json")
MAX_RESPONSE = 40_000_000
DART_KEY, FRED_KEY = "DART_API_KEY", "FRED_API_KEY"
DART_REPORTS = {"annual": "11011", "half": "11012", "q1": "11013", "q3": "11014"}
AGENT_STORE_URL = "https://agent.store/mcp"
AGENT_STORE_SERVERS = {
    "dart": "금융감독원 전자공시 · 재무비율과 공시",
    "corporate-data": "상장사·ETF 재무, 뉴스, 증권사 리서치",
    "kr-equity-report": "국내 상장사 리포트",
    "capital-markets": "ETF·ETN·ELW·채권 시세와 펀드 통계",
    "corp-financials": "금융위원회 기업 재무제표",
    "bok-stats": "한국은행 금리·환율·물가",
    "national-stats": "통계청 국가통계",
    "trade-stats": "수출입 무역통계",
    "us-market-data": "미국 주식·환율·원자재·경제지표",
    "us-equity-report": "미국 상장사 리포트",
}
CONNECTORS = {
    "agent-store": {
        "kind": "mcp", "env": None, "desks": ["국내 주식", "선물·매크로", "미국 주식"],
        "provides": "AI3 에이전트 스토어의 공시·재무·거시 MCP 서버",
        "signup": "https://agent.store/signup/",
        "howTo": "python3 harness/connectors.py agent-store --client claude",
    },
    "opendart": {
        "kind": "api", "env": DART_KEY, "desks": ["국내 주식"],
        "provides": "금융감독원 전자공시 목록과 주요 재무 계정",
        "signup": "https://opendart.fss.or.kr/",
        "howTo": "python3 harness/connectors.py dart-filings 005930",
    },
    "fred": {
        "kind": "api", "env": FRED_KEY, "desks": ["선물·매크로"],
        "provides": "미국 금리·물가·고용 등 거시 시계열",
        "signup": "https://fred.stlouisfed.org/docs/api/api_key.html",
        "howTo": "python3 harness/connectors.py fred DGS10 --start 2026-01-01",
    },
    "yfinance": {
        "kind": "package", "env": None, "desks": ["미국 주식", "선물·매크로", "퀀트"],
        "provides": "미국 주식·ETF, 지수, 연속 선물(ES=F, NQ=F, CL=F, GC=F), 환율(KRW=X) 일봉",
        "signup": "https://github.com/ranaroussi/yfinance",
        "howTo": "pip install yfinance 후 python3 harness/connectors.py bars ES=F --source yfinance --start 2025-01-01 --end 2026-11-20 --out es.csv",
    },
    "fdr": {
        "kind": "package", "env": None, "desks": ["국내 주식", "퀀트"],
        "provides": "국내 상장 주식·ETF(6자리 종목코드), 지수(KS11, KQ11), 환율 일봉",
        "signup": "https://github.com/FinanceData/FinanceDataReader",
        "howTo": "pip install finance-datareader 후 python3 harness/connectors.py bars 005930 --source fdr --start 2025-01-01 --end 2026-11-20 --out samsung.csv",
    },
    "toss": {
        "kind": "local", "env": "TOSSINVEST_ENV_FILE", "desks": ["국내 주식", "미국 주식"],
        "provides": "토스증권 공개 시세와 본인 계좌 조회 (조회 전용)",
        "signup": "https://developers.tossinvest.com/docs/auth",
        "howTo": "python3 harness/stock_harness.py market-packet 005930",
    },
}


def secret(name):
    value = os.environ.get(name, "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{16,64}", value):
        raise HarnessError(f"{name} 환경 변수에 본인 키를 지정해 주세요. 발급 방법은 connectors.py doctor에 있습니다.")
    return value


def fetch(host, path, params):
    """GET a fixed HTTPS host. Errors never echo the address, because it carries the key."""
    request = Request(f"https://{host}{path}?{urlencode(params)}", headers={"User-Agent": "stock-harness"})
    try:
        with build_opener(NoRedirect).open(request, timeout=30) as response:
            body = response.read(MAX_RESPONSE + 1)
    except HTTPError as error:
        raise HarnessError(f"{host} 응답 오류(HTTP {error.code})입니다. 키와 요청 한도를 확인해 주세요.") from None
    except (URLError, OSError):
        raise HarnessError(f"{host}에 연결하지 못했습니다. 네트워크를 확인해 주세요.") from None
    if len(body) > MAX_RESPONSE:
        raise HarnessError(f"{host} 응답이 너무 큽니다.")
    return body


def stock_code(value):
    code = str(value).upper()
    if not re.fullmatch(r"[0-9][0-9A-Z]{5}", code):
        raise HarnessError("국내 종목코드는 6자리로 입력해 주세요. 예: 005930")
    return code


def parse_corp_codes(archive):
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            names = bundle.namelist()
            if len(names) != 1 or bundle.getinfo(names[0]).file_size > 200_000_000:
                raise ValueError
            root = ElementTree.fromstring(bundle.read(names[0]))
    except (zipfile.BadZipFile, ElementTree.ParseError, ValueError, KeyError):
        raise HarnessError("OpenDART 회사 목록을 읽지 못했습니다. 키와 요청 한도를 확인해 주세요.") from None
    codes = {}
    for item in root.iter("list"):
        listed = (item.findtext("stock_code") or "").strip()
        if listed:
            codes[listed] = {"corpCode": (item.findtext("corp_code") or "").strip(),
                             "corpName": (item.findtext("corp_name") or "").strip()}
    if not codes:
        raise HarnessError("OpenDART 회사 목록에 상장사가 없습니다.")
    return codes


def corp_lookup(code, *, get=fetch, cache=CACHE):
    """Map a listed stock code to its DART company code. The public list is cached for a week."""
    store = cache / "dart-corp-codes.json"
    codes = None
    try:
        if time.time() - store.stat().st_mtime < 7 * 86400:
            codes = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        codes = None
    if codes is None:
        codes = parse_corp_codes(get("opendart.fss.or.kr", "/api/corpCode.xml", {"crtfc_key": secret(DART_KEY)}))
        try:
            cache.mkdir(parents=True, exist_ok=True)
            store.write_text(json.dumps(codes, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    if code not in codes or not re.fullmatch(r"\d{8}", codes[code]["corpCode"]):
        raise HarnessError("OpenDART에서 해당 종목코드의 회사를 찾지 못했습니다.")
    return codes[code]


def dart_json(path, params, *, get=fetch):
    try:
        document = json.loads(get("opendart.fss.or.kr", path, {"crtfc_key": secret(DART_KEY), **params}))
    except ValueError:
        raise HarnessError("OpenDART 응답 형식을 확인하지 못했습니다.") from None
    status = document.get("status")
    if status == "013":
        return []
    if status != "000" or not isinstance(document.get("list"), list):
        raise HarnessError(f"OpenDART가 요청을 처리하지 못했습니다(상태 {status}). 키와 요청 한도를 확인해 주세요.")
    return document["list"]


def kst_now():
    return datetime.now(KST)


def dart_filings(code, days=90, limit=20, *, get=fetch, cache=CACHE):
    code = stock_code(code)
    if not (1 <= days <= 365 and 1 <= limit <= 100):
        raise HarnessError("조회 기간은 1~365일, 건수는 1~100건으로 입력해 주세요.")
    company = corp_lookup(code, get=get, cache=cache)
    today = kst_now().date()
    rows = dart_json("/api/list.json", {
        "corp_code": company["corpCode"], "bgn_de": (today - timedelta(days=days)).strftime("%Y%m%d"),
        "end_de": today.strftime("%Y%m%d"), "page_count": 100,
    }, get=get)
    filings = []
    for row in rows[:limit]:
        receipt = str(row.get("rcept_no", ""))
        filed = str(row.get("rcept_dt", ""))
        if not re.fullmatch(r"\d{14}", receipt) or not re.fullmatch(r"\d{8}", filed):
            raise HarnessError("OpenDART 공시 목록의 형식을 확인하지 못했습니다.")
        filings.append({
            "date": f"{filed[:4]}-{filed[4:6]}-{filed[6:]}", "title": str(row.get("report_nm", "")).strip(),
            "filer": str(row.get("flr_nm", "")).strip(),
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
        })
    return {
        "dataScope": "public-filings", "market": "KR", "stockCode": code, "company": company["corpName"],
        "provider": "금융감독원 OpenDART", "source": "https://dart.fss.or.kr/",
        "retrievedAtKst": kst_now().isoformat(timespec="seconds"), "filings": filings,
    }


def dart_financials(code, year, report="annual", *, get=fetch, cache=CACHE):
    code = stock_code(code)
    if report not in DART_REPORTS or not 2015 <= year <= kst_now().year:
        raise HarnessError("사업연도는 2015년 이후, 보고서는 annual·half·q1·q3 중에서 골라 주세요.")
    company = corp_lookup(code, get=get, cache=cache)
    rows = dart_json("/api/fnlttSinglAcnt.json", {
        "corp_code": company["corpCode"], "bsns_year": year, "reprt_code": DART_REPORTS[report],
    }, get=get)
    basis = "CFS" if any(row.get("fs_div") == "CFS" for row in rows) else "OFS"
    accounts = [{
        "statement": row.get("sj_nm"), "account": row.get("account_nm"),
        "current": row.get("thstrm_amount"), "currentPeriod": row.get("thstrm_dt"),
        "previous": row.get("frmtrm_amount"), "previousPeriod": row.get("frmtrm_dt"),
        "currency": row.get("currency"),
    } for row in rows if row.get("fs_div") == basis]
    if not accounts:
        raise HarnessError("해당 보고서의 주요 계정이 아직 공시되지 않았습니다.")
    receipt = str(rows[0].get("rcept_no", ""))
    return {
        "dataScope": "public-filings", "market": "KR", "stockCode": code, "company": company["corpName"],
        "fiscalYear": year, "report": report, "basis": "연결" if basis == "CFS" else "별도",
        "provider": "금융감독원 OpenDART",
        "source": (f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
                   if re.fullmatch(r"\d{14}", receipt) else "https://dart.fss.or.kr/"),
        "retrievedAtKst": kst_now().isoformat(timespec="seconds"), "accounts": accounts,
    }


def iso_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise HarnessError("날짜는 YYYY-MM-DD 형식으로 입력해 주세요.")
    return date.fromisoformat(value).isoformat()


def fred_series(series, start=None, end=None, *, get=fetch):
    if not re.fullmatch(r"[A-Z0-9_]{1,40}", series):
        raise HarnessError("FRED 시계열 ID를 확인해 주세요. 예: DGS10, CPIAUCSL, DEXKOUS")
    params = {"series_id": series, "file_type": "json", "sort_order": "asc"}
    if start:
        params["observation_start"] = iso_day(start)
    if end:
        params["observation_end"] = iso_day(end)
    params["api_key"] = secret(FRED_KEY)
    try:
        rows = json.loads(get("api.stlouisfed.org", "/fred/series/observations", params))["observations"]
    except (ValueError, KeyError, TypeError):
        raise HarnessError("FRED 응답 형식을 확인하지 못했습니다.") from None
    points = []
    for row in rows:
        try:
            points.append({"date": iso_day(row["date"]), "value": float(row["value"])})
        except (ValueError, KeyError, TypeError):
            continue  # FRED marks a missing observation with "."
    if not points:
        raise HarnessError("FRED에서 해당 구간의 관측값을 받지 못했습니다.")
    return {
        "dataScope": "public-macro", "series": series, "provider": "Federal Reserve Bank of St. Louis (FRED)",
        "source": f"https://fred.stlouisfed.org/series/{series}",
        "retrievedAtEt": datetime.now(ET).isoformat(timespec="seconds"),
        "observations": points[-2000:],
    }


BAR_SOURCES = {
    "yfinance": {
        "package": "yfinance", "provider": "Yahoo Finance via yfinance",
        "covers": "미국 주식·ETF, 지수, 연속 선물(ES=F, NQ=F, CL=F, GC=F), 환율(KRW=X)",
        "terms": "개인 연구용입니다. Yahoo 이용 조건을 따르며 받은 데이터를 재배포하지 않습니다.",
        "code": (
            "import yfinance as yf\n"
            "frame = yf.download(payload['symbol'], start=payload['start'], end=payload['end'], progress=False, auto_adjust=True)\n"
            "close = frame['Close']\n"
            "close = close.iloc[:, 0] if hasattr(close, 'columns') else close\n"
            "rows = [[index.strftime('%Y-%m-%d'), float(value)] for index, value in close.dropna().items()]\n"
        ),
    },
    "fdr": {
        "package": "finance-datareader", "provider": "FinanceDataReader",
        "covers": "국내 상장 주식·ETF(6자리 종목코드), 지수(KS11, KQ11), 환율",
        "terms": "데이터 저작권은 원 제공처(KRX 등)에 있습니다. 개인 연구용으로 쓰고 재배포하지 않습니다.",
        "code": (
            "import FinanceDataReader as fdr\n"
            "frame = fdr.DataReader(payload['symbol'], payload['start'], payload['end'])\n"
            "rows = [[index.strftime('%Y-%m-%d'), float(value)] for index, value in frame['Close'].dropna().items()]\n"
        ),
    },
}
DATA_PYTHON = "STOCK_HARNESS_DATA_PYTHON"


def run_bar_source(source, payload):
    interpreter = os.environ.get(DATA_PYTHON) or sys.executable
    script = "import json, sys\npayload = json.load(sys.stdin)\n" + BAR_SOURCES[source]["code"] + "json.dump(rows, sys.stdout)\n"
    try:
        done = subprocess.run([interpreter, "-c", script], input=json.dumps(payload), text=True,
                              capture_output=True, timeout=120, check=True)
        return json.loads(done.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        package = BAR_SOURCES[source]["package"]
        raise HarnessError(f"{source}에서 일봉을 받지 못했습니다. `pip install {package}`로 설치했는지, 기호와 기간이 맞는지 확인해 주세요. "
                           f"다른 파이썬에 설치했다면 {DATA_PYTHON} 환경 변수로 그 파이썬 경로를 지정합니다.") from None


def bars(symbol, source, start, end, out, *, run=run_bar_source):
    if source not in BAR_SOURCES:
        raise HarnessError("source는 yfinance 또는 fdr 중에서 골라 주세요.")
    symbol = str(symbol).upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.=^-]{0,14}", symbol):
        raise HarnessError("기호를 확인해 주세요. 예: NVDA, ES=F, 005930")
    start, end = iso_day(start), iso_day(end)
    if not start < end:
        raise HarnessError("시작일은 종료일보다 앞서야 합니다.")
    target = Path(out)
    if target.suffix.lower() != ".csv" or target.exists():
        raise HarnessError("저장할 파일은 아직 없는 .csv 경로로 지정해 주세요.")
    rows = run(source, {"symbol": symbol, "start": start, "end": end})
    clean = []
    for row in rows if isinstance(rows, list) else []:
        if (isinstance(row, list) and len(row) == 2 and isinstance(row[1], (int, float))
                and row[1] > 0 and row[1] == row[1] and (not clean or iso_day(row[0]) > clean[-1][0])):
            clean.append((iso_day(row[0]), float(row[1])))
    if len(clean) < 2:
        raise HarnessError("받은 일봉이 없습니다. 기호와 기간을 확인해 주세요.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("date,close\n" + "".join(f"{day},{close}\n" for day, close in clean), encoding="utf-8")
    entry = BAR_SOURCES[source]
    return {
        "dataScope": "public-market", "symbol": symbol, "provider": entry["provider"], "interval": "1d",
        "rows": len(clean), "first": clean[0][0], "last": clean[-1][0], "lastClose": clean[-1][1], "file": str(target),
        "retrievedAtKst": kst_now().isoformat(timespec="seconds"), "terms": entry["terms"],
        "note": "수정주가 기준 종가입니다. 연속 선물은 만기 교체가 이어 붙여진 가격입니다.",
    }


def agent_store(client):
    setups = {
        "claude": {
            "run": f"claude mcp add --transport http agent-store {AGENT_STORE_URL}",
            "then": "Claude Code에서 /mcp 를 입력하고 agent-store 인증을 선택해 로그인합니다.",
        },
        "codex": {
            "file": "~/.codex/config.toml",
            "append": ("[features]\nexperimental_use_rmcp_client = true\n\n[mcp_servers.agent-store]\n"
                       f'url = "{AGENT_STORE_URL}"\nhttp_headers = {{ "X-API-Key" = "<AGENT_STORE_KEY>" }}\n'
                       "enabled = true"),
            "then": "키는 https://agent.store/console/keys/ 에서 발급해 본인 설정 파일에만 넣습니다.",
        },
    }
    if client not in setups:
        raise HarnessError("client는 claude 또는 codex 중에서 골라 주세요.")
    return {
        "dataScope": "setup-guide", "connector": "agent-store", "gateway": AGENT_STORE_URL,
        "before": "https://agent.store/servers/ 콘솔에서 아래 서버를 먼저 켭니다. 켜 둔 서버만 보입니다.",
        "servers": AGENT_STORE_SERVERS, "setup": setups[client],
        "docs": "https://agent.store/docs/connect/",
        "note": "유료 호출이 있을 수 있습니다. 키는 대화창이나 저장소에 넣지 않습니다.",
    }


def doctor():
    result = {}
    for name, entry in CONNECTORS.items():
        env = entry["env"]
        if entry["kind"] == "mcp":
            state = "client-setup"
        elif entry["kind"] == "package":
            state = "install-to-use"
        else:
            state = "configured" if os.environ.get(env) else "not-configured"
        result[name] = {"status": state, "keyVariable": env, **{key: entry[key] for key in ("provides", "desks", "signup", "howTo")}}
    return result


def catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


PERMISSIVE = ("mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc")
WEAK_COPYLEFT = ("lgpl-2.1", "lgpl-3.0", "mpl-2.0")


def evaluate(name, license_id, live_orders, months_since_update, fit, offline):
    """Score an open-source candidate with the same rubric the catalog uses."""
    name = " ".join(str(name).split())
    if not 1 <= len(name) <= 100:
        raise HarnessError("프로젝트 이름을 확인해 주세요.")
    if live_orders not in ("none", "separable", "core"):
        raise HarnessError("주문 기능은 none, separable, core 중에서 골라 주세요.")
    if not (0 <= months_since_update <= 600 and fit in (0, 1, 2) and offline in (0, 1, 2)):
        raise HarnessError("갱신 경과 개월 수는 0 이상, 적합성과 검증 가능성은 0~2로 입력해 주세요.")
    key = "".join(str(license_id).lower().split()).replace("license", "").replace("_", "-")
    permissive = key in PERMISSIVE or key.startswith(("mit", "apache", "bsd", "isc"))
    weak = key in WEAK_COPYLEFT or key.startswith(("lgpl", "mpl"))
    scores = {
        "license": 2 if permissive else 1 if weak else 0,
        "orderRisk": {"none": 2, "separable": 1, "core": 0}[live_orders],
        "maintenance": 2 if months_since_update <= 6 else 1 if months_since_update <= 24 else 0,
        "fit": fit, "offline": offline,
    }
    total = sum(scores.values())
    eligible = total >= 8 and min(scores["license"], scores["orderRisk"], scores["maintenance"]) >= 1
    if eligible:
        verdict = "연결 또는 접목 후보"
    elif scores["orderRisk"] == 0 or scores["fit"] == 0:
        verdict = "제외"
    else:
        verdict = "참고"
    reasons = []
    if scores["license"] == 0:
        reasons.append("라이선스가 허용적이지 않아 코드를 넣거나 함께 배포할 수 없습니다.")
    if scores["orderRisk"] == 0:
        reasons.append("실거래가 중심이라 주문을 넣지 않는 하네스 원칙과 맞지 않습니다.")
    if scores["maintenance"] == 0:
        reasons.append("2년 넘게 갱신되지 않았습니다.")
    if scores["offline"] == 0:
        reasons.append("유료 데이터나 별도 장비 없이는 검증할 수 없습니다.")
    return {"dataScope": "calculation-only", "project": name, "scores": scores, "total": total,
            "verdict": verdict, "reasons": reasons, "rubric": catalog()["rubric"],
            "next": "후보라도 실제로 실행해 결과를 확인한 뒤에만 연결 또는 접목으로 기록합니다."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="연결 가능한 데이터와 설정 상태")
    commands.add_parser("catalog", help="검토한 퀀트·선물 오픈소스 목록")
    store = commands.add_parser("agent-store", help="AI3 에이전트 스토어 연결 방법")
    store.add_argument("--client", choices=("claude", "codex"), default="claude")
    filings = commands.add_parser("dart-filings", help="국내 상장사 최근 공시 (OpenDART)")
    filings.add_argument("stock_code")
    filings.add_argument("--days", type=int, default=90)
    filings.add_argument("--limit", type=int, default=20)
    financials = commands.add_parser("dart-financials", help="국내 상장사 주요 재무 계정 (OpenDART)")
    financials.add_argument("stock_code")
    financials.add_argument("--year", type=int, required=True)
    financials.add_argument("--report", choices=DART_REPORTS, default="annual")
    judge = commands.add_parser("evaluate", help="오픈소스 후보를 같은 기준으로 채점합니다")
    judge.add_argument("name")
    judge.add_argument("--license", required=True, help="SPDX 표기. 예: MIT, Apache-2.0, GPL-3.0, none")
    judge.add_argument("--live-orders", required=True, help="none, separable, core")
    judge.add_argument("--months-since-update", type=int, required=True)
    judge.add_argument("--fit", type=int, required=True, help="0~2")
    judge.add_argument("--offline", type=int, required=True, help="0~2")
    daily = commands.add_parser("bars", help="일봉을 CSV로 받습니다 (yfinance 또는 FinanceDataReader 설치 필요)")
    daily.add_argument("symbol")
    daily.add_argument("--source", required=True, help="yfinance 또는 fdr")
    daily.add_argument("--start", required=True)
    daily.add_argument("--end", required=True)
    daily.add_argument("--out", required=True, help="저장할 CSV 경로")
    fred = commands.add_parser("fred", help="미국 거시 시계열 (FRED)")
    fred.add_argument("series")
    fred.add_argument("--start")
    fred.add_argument("--end")
    args = parser.parse_args()
    actions = {
        "doctor": doctor,
        "catalog": catalog,
        "agent-store": lambda: agent_store(args.client),
        "dart-filings": lambda: dart_filings(args.stock_code, args.days, args.limit),
        "dart-financials": lambda: dart_financials(args.stock_code, args.year, args.report),
        "fred": lambda: fred_series(args.series, args.start, args.end),
        "evaluate": lambda: evaluate(args.name, args.license, args.live_orders, args.months_since_update,
                                     args.fit, args.offline),
        "bars": lambda: bars(args.symbol, args.source, args.start, args.end, args.out),
    }
    try:
        print(json.dumps(actions[args.command](), ensure_ascii=False, indent=2, allow_nan=False))
    except HarnessError as exc:
        parser.exit(1, f"{exc}\n")
    except (OSError, ValueError):
        parser.exit(1, "입력값과 설치 파일을 확인해 주세요.\n")


if __name__ == "__main__":
    main()
