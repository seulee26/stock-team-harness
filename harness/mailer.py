"""Send a finished report through the user's own Gmail account. Nothing is sent without --confirm."""

import argparse
from email.message import EmailMessage
import json
import os
from pathlib import Path
import re
import smtplib
import ssl

from toss_client import HarnessError


ADDRESS_VAR, SECRET_VAR = "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
ADDRESS = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
MAX_RECIPIENTS = 5
MAX_ATTACHMENT_BYTES = 20_000_000
TYPES = {".html": ("text", "html"), ".pdf": ("application", "pdf")}
DISCLAIMER = "이 리포트는 조사 자료이며 투자 조언이나 권유가 아닙니다. 투자 판단과 책임은 본인에게 있습니다."


def clean_address(value):
    address = str(value).strip()
    if not ADDRESS.fullmatch(address) or len(address) > 254:
        raise HarnessError("메일 주소를 확인해 주세요.")
    return address


def credentials():
    address = clean_address(os.environ.get(ADDRESS_VAR, ""))
    secret = os.environ.get(SECRET_VAR, "").replace(" ", "")
    if not re.fullmatch(r"[A-Za-z0-9]{16}", secret):
        raise HarnessError(f"{SECRET_VAR} 환경 변수에 Gmail 앱 비밀번호 16자리를 지정해 주세요.")
    return address, secret


def read_attachment(path):
    path = Path(path)
    if path.suffix.lower() not in TYPES:
        raise HarnessError("첨부는 .html과 .pdf 파일만 보낼 수 있습니다.")
    if path.is_symlink() or not path.is_file():
        raise HarnessError(f"첨부 파일을 찾지 못했습니다: {path.name}")
    body = path.read_bytes()
    if not body or len(body) > MAX_ATTACHMENT_BYTES:
        raise HarnessError(f"첨부 파일은 비어 있지 않고 20MB 이하여야 합니다: {path.name}")
    return path.name, path.suffix.lower(), body


def build_message(sender, recipients, subject, summary, attachments):
    recipients = [clean_address(item) for item in recipients]
    if not 1 <= len(set(recipients)) <= MAX_RECIPIENTS or len(set(recipients)) != len(recipients):
        raise HarnessError("받는 사람은 겹치지 않게 1~5명으로 입력해 주세요.")
    subject = " ".join(str(subject).split())
    summary = str(summary).strip()
    if not 1 <= len(subject) <= 150 or not 1 <= len(summary) <= 4000:
        raise HarnessError("제목은 1~150자, 본문 요약은 1~4,000자로 입력해 주세요.")
    files = [read_attachment(path) for path in attachments]
    if not 1 <= len(files) <= 4 or sum(len(body) for _, _, body in files) > MAX_ATTACHMENT_BYTES:
        raise HarnessError("첨부는 1~4개, 합계 20MB 이하로 입력해 주세요.")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, ", ".join(recipients), subject
    message.set_content(f"{summary}\n\n첨부 파일을 열어 전체 리포트를 확인하세요.\n\n{DISCLAIMER}\n")
    for name, suffix, body in files:
        main, sub = TYPES[suffix]
        message.add_attachment(body, maintype=main, subtype=sub, filename=name)
    return message, recipients, files


def deliver(message, sender, secret):
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30) as server:
        server.login(sender, secret)
        server.send_message(message)


def send(recipients, subject, summary, attachments, *, confirm=False, transport=deliver):
    sender, secret = credentials()
    message, recipients, files = build_message(sender, recipients or [sender], subject, summary, attachments)
    outside = [address for address in recipients if address.lower() != sender.lower()]
    preview = {
        "dataScope": "outgoing-mail", "from": sender, "to": recipients, "subject": message["Subject"],
        "attachments": [{"name": name, "bytes": len(body)} for name, _, body in files],
        "outsideRecipients": outside,
    }
    if not confirm:
        return preview | {"sent": False, "next": "내용이 맞으면 같은 명령에 --confirm을 붙여 다시 실행하세요."}
    try:
        transport(message, sender, secret)
    except smtplib.SMTPAuthenticationError:
        raise HarnessError("Gmail 로그인에 실패했습니다. 주소와 앱 비밀번호를 확인해 주세요.") from None
    except (smtplib.SMTPException, OSError):
        raise HarnessError("메일을 보내지 못했습니다. 네트워크와 받는 사람 주소를 확인해 주세요.") from None
    return preview | {"sent": True}


def doctor():
    configured = bool(os.environ.get(ADDRESS_VAR)) and bool(os.environ.get(SECRET_VAR))
    return {
        "status": "configured" if configured else "not-configured",
        "variables": [ADDRESS_VAR, SECRET_VAR],
        "setup": "Google 계정에서 2단계 인증을 켠 뒤 https://myaccount.google.com/apppasswords 에서 앱 비밀번호를 만듭니다.",
        "note": "계정 비밀번호가 아니라 앱 비밀번호를 씁니다. 값은 내 터미널 환경 변수에만 넣습니다.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="메일 설정 상태")
    mail = commands.add_parser("send", help="리포트 파일을 메일로 보냅니다")
    mail.add_argument("files", nargs="+", help="보낼 .html 또는 .pdf 파일")
    mail.add_argument("--to", action="append", default=[], help="받는 사람 (생략하면 나에게)")
    mail.add_argument("--subject", required=True)
    mail.add_argument("--summary", required=True, help="본문에 넣을 짧은 요약")
    mail.add_argument("--confirm", action="store_true", help="미리보기를 확인한 뒤 실제로 보냅니다")
    args = parser.parse_args()
    try:
        result = doctor() if args.command == "doctor" else send(
            args.to, args.subject, args.summary, args.files, confirm=args.confirm)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except HarnessError as exc:
        parser.exit(1, f"{exc}\n")
    except (OSError, ValueError):
        parser.exit(1, "입력값과 파일을 확인해 주세요.\n")


if __name__ == "__main__":
    main()
