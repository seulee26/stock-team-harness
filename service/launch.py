"""Start the local Stock Team dashboard without installing packages or storing API keys."""

import argparse
import getpass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import warnings
import webbrowser


HERE = Path(__file__).resolve().parent
SAFE_URL = re.compile(r"http://localhost:[0-9]{1,5}/\Z")
SAFE_KEY = re.compile(r"[A-Za-z0-9._-]{12,300}\Z")


def key_from_terminal(label):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass(label)
    except (getpass.GetPassWarning, EOFError) as error:
        raise ValueError("키는 숨김 입력이 가능한 로컬 터미널에서 입력해 주세요.") from error
    if not SAFE_KEY.fullmatch(value):
        raise ValueError("API 키 형식을 확인해 주세요.")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--personal", action="store_true", help="토스증권 키를 로컬 터미널에서 입력")
    parser.add_argument("--bizrouter", action="store_true", help="비즈라우터 키를 로컬 터미널에서 입력")
    parser.add_argument("--account", help="토스증권 계좌가 여러 개일 때 사용할 계좌 식별값")
    parser.add_argument("--no-browser", action="store_true", help="로컬 주소만 표시")
    args = parser.parse_args()

    if (args.personal and os.name != "posix") or sys.version_info < (3, 9):
        parser.error("Python 3.9 이상이 필요합니다. 토스증권 연결은 macOS·Linux·WSL에서 지원합니다.")
    if args.account and (not args.personal or not re.fullmatch(r"[1-9][0-9]{0,20}", args.account)):
        parser.error("--account는 --personal과 함께 양의 정수로 지정해 주세요.")
    node = shutil.which("node")
    if not node:
        parser.error("로컬 웹 화면을 열려면 Node.js 20 이상을 설치해 주세요.")
    try:
        major = subprocess.check_output([node, "--version"], text=True, timeout=5).lstrip("v").split(".")[0]
        if int(major) < 20:
            raise ValueError("로컬 웹 화면에는 Node.js 20 이상이 필요합니다.")
        # Explicitly pass only input the user opted into. Never inherit previously configured tokens.
        env = {name: os.environ[name] for name in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT")
               if name in os.environ}
        if args.personal:
            print("토스 키는 이 실행에서만 사용합니다. 토스 공식 Open API에만 전달됩니다.", flush=True)
            env["TOSSINVEST_CLIENT_ID"] = key_from_terminal("토스 Client ID: ")
            env["TOSSINVEST_CLIENT_SECRET"] = key_from_terminal("토스 Client Secret: ")
            env["STOCK_TEAM_PYTHON"] = sys.executable
            if args.account:
                env["STOCK_TEAM_ACCOUNT"] = args.account
        if args.bizrouter:
            print("BizRouter에는 지원되는 공개 주제와 종목만 전달됩니다. 기본 답변에는 키가 필요 없습니다.", flush=True)
            env["RESEARCH_CHAT_PROVIDER"] = "bizrouter"
            env["BIZROUTER_API_KEY"] = key_from_terminal("BizRouter API Key: ")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error) if isinstance(error, ValueError) else "로컬 실행 준비에 실패했습니다.", file=sys.stderr)
        return 1

    with TemporaryDirectory(prefix="stock-team-local-") as state:
        env["STOCK_TEAM_LOCAL_STATE"] = state
        process = subprocess.Popen([node, str(HERE / "server.mjs")], env=env, cwd=HERE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True)
        try:
            address = process.stdout.readline().strip()
            if not SAFE_URL.fullmatch(address):
                print("로컬 웹 화면을 열지 못했습니다.", file=sys.stderr)
                return 1
            print(f"{address}\n종료하려면 Ctrl+C를 누르세요.", flush=True)
            if not args.no_browser:
                webbrowser.open(address)
            return process.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
