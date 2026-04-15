from __future__ import annotations

import base64
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from app.config import GMAIL_CLIENT_SECRET_FILE, GMAIL_TOKEN_FILE

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except Exception:  # pragma: no cover
    Request = None
    Credentials = None
    InstalledAppFlow = None
    build = None

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


class GmailDraftServiceError(RuntimeError):
    pass


class GmailDraftService:
    def __init__(self, token_file: Optional[str] = None, client_secret_file: Optional[str] = None):
        self.token_file = Path(token_file or GMAIL_TOKEN_FILE)
        self.client_secret_file = Path(client_secret_file or GMAIL_CLIENT_SECRET_FILE)

    def create_draft(
        self,
        subject: str,
        body: str,
        to: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
    ) -> dict:
        if build is None:
            raise GmailDraftServiceError(
                "Gmail 라이브러리가 설치되지 않았습니다. requirements.txt를 다시 설치하세요."
            )

        service = self._build_service()
        message = EmailMessage()
        message["To"] = to
        if cc:
            message["Cc"] = cc
        if bcc:
            message["Bcc"] = bcc
        message["Subject"] = subject
        message.set_content(body)

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        created = service.users().drafts().create(userId="me", body={"message": {"raw": encoded_message}}).execute()
        return {
            "draft_id": created.get("id", ""),
            "message_id": created.get("message", {}).get("id", ""),
        }

    def _build_service(self):
        creds = None
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_file.write_text(creds.to_json(), encoding="utf-8")

        if not creds or not creds.valid:
            if not self.client_secret_file.exists():
                raise GmailDraftServiceError(
                    f"Gmail OAuth 설정 파일이 없습니다: {self.client_secret_file}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret_file), SCOPES)
            creds = flow.run_local_server(port=0)
            self.token_file.write_text(creds.to_json(), encoding="utf-8")

        return build("gmail", "v1", credentials=creds)


_service = GmailDraftService()


def create_gmail_draft(subject: str, body: str, to: str, cc: Optional[str] = None, bcc: Optional[str] = None) -> dict:
    return _service.create_draft(subject=subject, body=body, to=to, cc=cc, bcc=bcc)
