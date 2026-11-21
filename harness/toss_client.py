"""Read-only client for the published Toss Securities Open API."""

from contextlib import contextmanager
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import stat
from tempfile import NamedTemporaryFile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


API_URL = "https://openapi.tossinvest.com"
STREAM_HOST = "openapi-ws.tossinvest.com"
STREAM_URL = f"wss://{STREAM_HOST}/ws/v1"
STATE_DIR = Path.home() / ".local/state/stock-team-harness"
CATALOG = json.loads(Path(__file__).with_name("toss_catalog.json").read_text(encoding="utf-8"))
OPERATIONS = {item["id"]: item for item in CATALOG["operations"]}
PATH_VALUE = re.compile(r"[A-Za-z0-9._-]+")
MARKET_OPERATIONS = frozenset(
    name for name, operation in OPERATIONS.items()
    if operation["method"] == "GET" and not operation.get("account") and name != "getAccounts"
)
SAFE_API_CODES = frozenset({
    "invalid_client", "invalid_request", "access_denied", "unsupported_grant_type",
    "invalid-token", "account-not-found", "account-header-required", "unsupported-symbol",
    "unsupported-market", "invalid-request", "stock-not-found", "rate-limit-exceeded",
})


class HarnessError(RuntimeError):
    pass


class ApiError(HarnessError):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(f"토스 API HTTP {status} ({code})")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_private_file(file):
    info = os.fstat(file.fileno())
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise HarnessError("민감한 파일은 현재 사용자만 읽고 쓸 수 있는 일반 파일이어야 합니다.")


def read_private_text(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8") as file:
        check_private_file(file)
        return file.read()


def load_keys():
    id_key, secret_key = "TOSSINVEST_CLIENT_ID", "TOSSINVEST_CLIENT_SECRET"
    client_id, secret = os.environ.get(id_key), os.environ.get(secret_key)
    if client_id and secret:
        return client_id, secret
    if client_id or secret:
        raise HarnessError("환경 변수로 연결할 때는 토스 API 키 두 값을 함께 지정해 주세요.")
    configured_file = os.environ.get("TOSSINVEST_ENV_FILE")
    if not configured_file:
        raise HarnessError("토스 API 키를 찾지 못했습니다. README의 로컬 연결 방법을 확인해 주세요.")
    key_file = Path(configured_file).expanduser()
    try:
        contents = read_private_text(key_file)
    except FileNotFoundError:
        contents = ""
    values = {}
    for line in contents.splitlines():
        key, separator, value = line.removeprefix("export ").partition("=")
        if separator and key.strip() in (id_key, secret_key):
            values[key.strip()] = value.strip().strip('"').strip("'")
    if values.get(id_key) and values.get(secret_key):
        return values[id_key], values[secret_key]
    raise HarnessError("토스 API 키를 찾지 못했습니다. README의 로컬 연결 방법을 확인해 주세요.")


def private_dir():
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = STATE_DIR.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise HarnessError("하네스 상태 폴더의 접근을 소유자에게만 허용해 주세요.")
    return STATE_DIR


def write_private_json(path, value):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(value, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


@contextmanager
def locked(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, "r+") as file:
        check_private_file(file)
        fcntl.flock(file, fcntl.LOCK_EX)
        yield


def read_private_json(path):
    try:
        return json.loads(read_private_text(path))
    except FileNotFoundError:
        return {}


def account_id(value):
    if value is None or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise HarnessError("계좌 식별값은 계좌 목록에 나온 양의 정수여야 합니다.")
    return str(value)


class TossClient:
    def __init__(self, *, market_only=False):
        self.market_only = market_only
        self.client_id, self.secret = load_keys()
        self.opener = build_opener(ProxyHandler({}), NoRedirect)
        key = sha256(self.client_id.encode()).hexdigest()[:24]
        self.cache = private_dir() / f"token-{key}.json"

    def _request(self, path, *, query=None, form=None, headers=None, retry=False):
        if form is not None:
            allowed = path == "/oauth2/token"
        else:
            allowed = re.fullmatch(r"/api/v1(?:/[A-Za-z0-9._-]+)+", path) and not (
                {".", ".."} & set(path.split("/"))
            )
        if not allowed:
            raise HarnessError("토스증권 공식 인증·조회 경로만 호출할 수 있습니다.")
        headers = {"Accept": "application/json", **(headers or {})}
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        url = API_URL + path
        if query:
            url += "?" + urlencode(query)
        req = Request(url, data=urlencode(form).encode() if form is not None else None, headers=headers)
        for attempt in range(3 if retry else 1):
            try:
                with self.opener.open(req, timeout=15) as response:
                    return json.load(response)
            except HTTPError as error:
                try:
                    body = json.load(error)
                    code = body.get("error", {})
                    code = code.get("code") if isinstance(code, dict) else code
                    if not isinstance(code, str) or code not in SAFE_API_CODES:
                        code = "request-failed"
                except (ValueError, AttributeError):
                    code = "request-failed"
                if retry and attempt < 2 and error.code in (429, 500, 502, 503, 504):
                    try:
                        delay = float(error.headers.get("Retry-After", "1"))
                    except ValueError:
                        delay = 1
                    time.sleep(min(5, max(1, delay)))
                    continue
                raise ApiError(error.code, code) from None
            except (TimeoutError, URLError) as error:
                if retry and attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                raise HarnessError("토스 API에 연결하지 못했습니다.") from error

    def token(self, rejected=None):
        with locked(self.cache.with_suffix(".lock")):
            cached = read_private_json(self.cache)
            token = cached.get("token")
            if token and token != rejected and cached.get("expires_at", 0) > time.time():
                return token
            data = self._request("/oauth2/token", form={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.secret,
            })
            token = data.get("access_token")
            if not token:
                raise HarnessError("토스가 접속용 토큰을 반환하지 않았습니다.")
            ttl = max(1, int(data.get("expires_in", 3600)) - 60)
            write_private_json(self.cache, {"token": token, "expires_at": time.time() + ttl})
            return token

    def get(self, name, *, account=None, **params):
        operation = OPERATIONS.get(name)
        if not operation or operation["method"] != "GET":
            raise HarnessError("공식 목록에 있는 조회 작업만 실행할 수 있습니다.")
        if self.market_only and (name not in MARKET_OPERATIONS or account is not None):
            raise HarnessError("공개 시세 경로에서는 계좌 자료를 조회할 수 없습니다.")
        path = operation["path"]
        for key in operation.get("path_parameters", []):
            value = str(params.pop(key, ""))
            if not PATH_VALUE.fullmatch(value) or value in (".", ".."):
                raise HarnessError(f"{key} 값이 필요합니다.")
            path = path.replace("{" + key + "}", quote(value, safe=""))
        allowed = operation.get("query", {})
        if set(params) - allowed.keys() or any(required and not params.get(key) for key, required in allowed.items()):
            raise HarnessError(f"{name} 조회 항목을 확인해 주세요.")
        headers = {}
        if operation.get("account"):
            headers["X-Tossinvest-Account"] = account_id(account)
        token = self.token()
        for attempt in range(2):
            headers["Authorization"] = f"Bearer {token}"
            try:
                data = self._request(path, query=params, headers=headers, retry=True)
                if "result" not in data:
                    raise HarnessError("토스 API 응답에서 조회 결과를 찾지 못했습니다.")
                return data["result"]
            except ApiError as error:
                if attempt or error.status != 401:
                    raise
                token = self.token(rejected=token)

    def resolve_account(self, account=None):
        if self.market_only:
            raise HarnessError("공개 시세 경로에서는 계좌를 선택할 수 없습니다.")
        if account is not None:
            return account_id(account)
        accounts = self.get("getAccounts")
        if not isinstance(accounts, list) or len(accounts) != 1:
            raise HarnessError("계좌 목록을 확인하고 --account로 사용할 계좌를 지정해 주세요.")
        return account_id(accounts[0]["accountSeq"])
