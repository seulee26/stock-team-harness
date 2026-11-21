"""Install the pinned optional upstream tools into independent local runtimes."""

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".local" / "upstream"
LOCK = Path(__file__).with_name("upstream-lock.json")
OPENBB_PACKAGES = (
    "core", "extensions/platform_api", "extensions/equity", "providers/nasdaq",
    "providers/sec",
)
FINANCIAL_PLUGINS = (
    "agent-plugins/earnings-reviewer",
    "agent-plugins/market-researcher",
    "agent-plugins/valuation-reviewer",
    "vertical-plugins/equity-research",
    "vertical-plugins/financial-analysis",
)


def clean_environment():
    keys = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TMP", "TEMP",
            "SystemRoot", "WINDIR")
    return {key: os.environ[key] for key in keys if key in os.environ} | {
        "PYTHONNOUSERSITE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }


def python_path(target):
    binary = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return target / "venv" / binary


def read_lock():
    return json.loads(LOCK.read_text(encoding="utf-8"))


def receipt_for(name, entry):
    return {"name": name, **{key: entry[key] for key in ("repository", "commit", "sha256")}}


def is_installed(name, entry, runtime=RUNTIME):
    directory = runtime / name
    entrypoint = (directory / "plugins" if name == "financial-services"
                  else python_path(directory))
    try:
        receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return False
    return entrypoint.exists() and (directory / "source").is_dir() and receipt == receipt_for(name, entry)


def verify_archive(archive, entry):
    if archive.stat().st_size != entry["bytes"]:
        raise ValueError("소스 아카이브 크기가 잠금 파일과 다릅니다.")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != entry["sha256"]:
        raise ValueError("소스 아카이브 SHA-256이 잠금 파일과 다릅니다.")


def obtain_archive(entry, work):
    archive = ROOT / "references" / "upstream" / entry["filename"]
    if archive.is_file():
        verify_archive(archive, entry)
        return archive

    url = f'https://codeload.github.com/{entry["repository"]}/tar.gz/{entry["commit"]}'
    if url != entry["source"]:
        raise ValueError("잠금 파일의 다운로드 주소가 공식 소스와 다릅니다.")
    archive = work / "source.tar.gz"
    with urlopen(url, timeout=60) as download, archive.open("xb") as stream:
        remaining = entry["bytes"]
        while chunk := download.read(min(remaining + 1, 1024 * 1024)):
            remaining -= len(chunk)
            if remaining < 0:
                raise ValueError("다운로드가 잠금 파일의 크기를 초과했습니다.")
            stream.write(chunk)
    verify_archive(archive, entry)
    return archive


def extract_source(archive, destination, entry):
    tree = f'{entry["repository"].split("/")[1]}-{entry["commit"]}'
    destination.mkdir()
    expanded_bytes = 0
    with tarfile.open(archive, mode="r:gz") as bundle:
        for member in bundle:
            parts = PurePosixPath(member.name).parts
            if (not parts or parts[0] != tree
                    or any(part in {".", ".."} or "\\" in part or ":" in part for part in parts)
                    or not (member.isfile() or member.isdir())):
                raise ValueError(f"지원하지 않는 소스 파일 경로입니다: {member.name}")
            target = destination.joinpath(*parts[1:])
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            expanded_bytes += member.size
            if expanded_bytes > 512 * 1024 * 1024:
                raise ValueError("압축을 푼 소스가 최대 크기를 초과했습니다.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, target.open("xb") as stream:
                shutil.copyfileobj(source, stream)


def run(command, cwd):
    subprocess.run(
        [str(arg) for arg in command], check=True, cwd=cwd,
        env=clean_environment(), stdin=subprocess.DEVNULL,
    )


def install_python(name, directory):
    source = directory / "source"
    runtime_python = python_path(directory)
    run((sys.executable, "-I", "-m", "venv", directory / "venv"), directory)
    targets = ([source / "openbb_platform" / component for component in OPENBB_PACKAGES]
               if name == "openbb" else [source])
    if name != "ai-hedge-fund":
        targets.append("python-dotenv>=1.2.1")
    run((runtime_python, "-I", "-m", "pip", "install", "--no-input", *targets), directory)
    run((runtime_python, "-I", "-m", "pip", "check"), directory)
    imports = {
        "tradingagents": "import tradingagents; import cli.main",
        "openbb": "import openbb_core; import openbb_equity; import openbb_nasdaq; import openbb_sec",
        "ai-hedge-fund": "import hedge_fund.run",
    }
    run((runtime_python, "-I", "-c", imports[name]), directory)


def install_financial_plugins(directory):
    installed = directory / "plugins"
    claude = shutil.which("claude")
    for location in FINANCIAL_PLUGINS:
        original = directory / "source" / "plugins" / location
        chosen = installed / original.name
        shutil.copytree(original, chosen, ignore=shutil.ignore_patterns(
            ".mcp.json", "hooks", ".claude", "settings.json", "settings.local.json",
        ))
        manifest = json.loads((chosen / ".claude-plugin" / "plugin.json").read_text())
        if manifest.get("name") != original.name or set(manifest) & {"mcpServers", "hooks"}:
            raise ValueError(f"검토가 필요한 Claude 플러그인: {original.name}")
        if claude:
            run((claude, "plugin", "validate", chosen), directory)


@contextlib.contextmanager
def install_lock(runtime, name):
    lock = runtime / f".{name}.installing"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise RuntimeError(f"{name} 설치가 이미 실행 중입니다. 중단된 설치라면 {lock} 폴더를 확인하세요.") from exc
    try:
        yield
    finally:
        lock.rmdir()


def install(name, entry, runtime=RUNTIME):
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    with install_lock(runtime, name):
        if is_installed(name, entry, runtime):
            print(f"{name} · 설치 확인", flush=True)
            return
        directory = runtime / name
        if directory.exists():
            raise RuntimeError(f"{directory}에 기존 설치 파일이 있습니다. 보관 위치로 옮긴 뒤 다시 실행하세요.")
        directory.mkdir(mode=0o700)
        try:
            with tempfile.TemporaryDirectory(prefix=".source-", dir=runtime) as temporary:
                work = Path(temporary)
                extract_source(obtain_archive(entry, work), directory / "source", entry)
            if name == "financial-services":
                install_financial_plugins(directory)
            else:
                install_python(name, directory)
            (directory / "receipt.json").write_text(
                json.dumps(receipt_for(name, entry), indent=2) + "\n", encoding="utf-8",
            )
        except (Exception, KeyboardInterrupt):
            shutil.rmtree(directory)
            raise
    print(f"{name} · 설치 완료", flush=True)


def main():
    entries = read_lock()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", metavar="TARGET",
                        help="tradingagents, openbb, ai-hedge-fund, financial-services")
    parser.add_argument("--status", action="store_true", help="설치 상태만 확인")
    options = parser.parse_args()
    targets = tuple(dict.fromkeys(options.targets)) if options.targets else tuple(entries)
    unsupported = set(targets) - entries.keys()
    if unsupported:
        parser.error(f"지원하지 않는 설치 대상: {', '.join(sorted(unsupported))}")
    if options.status:
        print(json.dumps({name: is_installed(name, entries[name]) for name in targets}))
        return 0
    if sys.version_info < (3, 11):
        parser.error("설치에 Python 3.11 이상이 필요합니다. python3.12로 실행하세요.")

    failed = []
    for name in targets:
        try:
            install(name, entries[name])
        except (OSError, RuntimeError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
            print(f"{name} · 설치 실패: {exc}", file=sys.stderr)
            failed.append(name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
