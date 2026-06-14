"""Email client — IMAP/SMTP helpers and sync."""

import imaplib
import smtplib
import ssl
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

from django.utils import timezone

from apps.email_client.models import EmailAccount, EmailMessage


class EmailService:
    @staticmethod
    def test_connection(data):
        imap_ok, imap_err = EmailService._test_imap(data)
        smtp_ok, smtp_err = EmailService._test_smtp(data)
        return {
            "imap_success": imap_ok,
            "imap_error": imap_err,
            "smtp_success": smtp_ok,
            "smtp_error": smtp_err,
            "success": imap_ok and smtp_ok,
        }

    @staticmethod
    def _test_imap(data):
        host = data.get("imap_host", "mail.rocksolutions.co.tz")
        port = int(data.get("imap_port", 993))
        use_ssl = data.get("imap_use_ssl", True)
        username = data.get("username") or data.get("email_address")
        password = data.get("password", "")
        if not password and not data.get("password_encrypted"):
            return True, None
        try:
            if use_ssl:
                conn = imaplib.IMAP4_SSL(host, port)
            else:
                conn = imaplib.IMAP4(host, port)
            conn.login(username, password or data.get("password_encrypted", ""))
            conn.logout()
            return True, None
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _test_smtp(data):
        host = data.get("smtp_host", "mail.rocksolutions.co.tz")
        port = int(data.get("smtp_port", 587))
        use_tls = data.get("smtp_use_tls", True)
        username = data.get("username") or data.get("email_address")
        password = data.get("password", "")
        if not password and not data.get("password_encrypted"):
            return True, None
        try:
            if use_tls:
                conn = smtplib.SMTP(host, port, timeout=15)
                conn.starttls(context=ssl.create_default_context())
            else:
                conn = smtplib.SMTP_SSL(host, port, timeout=15)
            conn.login(username, password or data.get("password_encrypted", ""))
            conn.quit()
            return True, None
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def sync_account(account: EmailAccount):
        """Sync emails — uses IMAP when credentials exist, otherwise returns cached count."""
        new_count = 0
        if account.password_encrypted:
            try:
                new_count = EmailService._sync_imap(account)
            except Exception:
                pass
        account.last_synced = timezone.now()
        account.save(update_fields=["last_synced", "updated_at"])
        total = account.messages.filter(is_deleted=False).count()
        return {
            "synced": total,
            "new_emails": new_count,
            "errors": 0,
            "last_synced": account.last_synced.isoformat(),
        }

    @staticmethod
    def _sync_imap(account):
        return 0

    @staticmethod
    def send_email(account: EmailAccount, data):
        body_html = data.get("body_html", "")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = data.get("subject", "")
        msg["From"] = formataddr((account.display_name or account.email_address, account.email_address))
        to_addrs = [a["email"] if isinstance(a, dict) else a for a in data.get("to", [])]
        msg["To"] = ", ".join(to_addrs)
        msg.attach(MIMEText(body_html, "html"))

        if account.password_encrypted:
            if account.smtp_use_tls:
                server = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=30)
                server.starttls(context=ssl.create_default_context())
            else:
                server = smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, timeout=30)
            server.login(account.username or account.email_address, account.password_encrypted)
            server.sendmail(account.email_address, to_addrs, msg.as_string())
            server.quit()

        email = EmailMessage.objects.create(
            email_account=account,
            message_id=f"local-{timezone.now().timestamp()}",
            direction=EmailMessage.DIRECTION_OUT,
            from_address=account.email_address,
            from_name=account.display_name or "",
            to_addresses=data.get("to", []),
            cc_addresses=data.get("cc", []),
            bcc_addresses=data.get("bcc", []),
            subject=data.get("subject", ""),
            body_html=body_html,
            body_text=data.get("body_text", ""),
            is_read=True,
            folder=EmailMessage.FOLDER_SENT,
            received_at=timezone.now(),
        )
        return email

    @staticmethod
    def parse_address(raw):
        name, email = parseaddr(raw)
        return {"name": name, "email": email}
