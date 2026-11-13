import os
import re
import base64
import logging
import requests
from django.conf import settings
logger = logging.getLogger(__name__)
def _resolve_local_pdf_file(pdf_path: str):
    if not pdf_path:
        return None
    raw = str(pdf_path).strip()
    if os.path.exists(raw) and os.path.isfile(raw):
        return raw
    pdf_dir = os.path.join(settings.BASE_DIR, "media", "generated_pdf")
    m_req = re.search(r"/requests/(\d+)/", raw)
    if m_req:
        candidate = os.path.join(pdf_dir, f"surat_{m_req.group(1)}.pdf")
        if os.path.exists(candidate):
            return candidate
    basename = os.path.basename(raw.split("?")[0])
    if basename:
        candidate = os.path.join(pdf_dir, basename)
        if os.path.exists(candidate):
            return candidate
    return None
def _load_env_var(key: str, default: str = "") -> str:
    val = os.environ.get(key) or getattr(settings, key, None)
    if val:
        return str(val).strip()
    env_file = os.path.join(settings.BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default
def send_surat_via_gmail_admin(recipient_email: str, subject: str, body_message: str, pdf_path: str = None):
    local_pdf = _resolve_local_pdf_file(pdf_path)
    attachments_payload = []
    if local_pdf and os.path.exists(local_pdf):
        with open(local_pdf, "rb") as f_pdf:
            b64_data = base64.b64encode(f_pdf.read()).decode("utf-8")
        attachments_payload.append({
            "content": b64_data,
            "name": os.path.basename(local_pdf),
        })
    # 1. Coba Resend jika RESEND_API_KEY tersedia
    resend_key = _load_env_var("RESEND_API_KEY")
    if resend_key:
        from_email = _load_env_var("RESEND_FROM_EMAIL", "ASURA Kampus <onboarding@resend.dev>")
        payload = {
            "from": from_email,
            "to": [recipient_email],
            "subject": subject,
            "text": body_message,
        }
        if attachments_payload:
            payload["attachments"] = [
                {"filename": a["name"], "content": a["content"]} for a in attachments_payload
            ]
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        if 200 <= resp.status_code < 300:
            return {"status": "SUCCESS", "provider": "resend", "response": resp.json()}
    # 2. Coba Brevo HTTP API jika BREVO_API_KEY tersedia
    brevo_key = _load_env_var("BREVO_API_KEY")
    if brevo_key:
        sender_email = _load_env_var("DEFAULT_FROM_EMAIL", "bintangwp123@gmail.com")
        html_body = (body_message or "").replace("\n", "<br>")
        brevo_payload = {
            "sender": {"name": "ASURA Persuratan Kampus", "email": sender_email},
            "to": [{"email": recipient_email}],
            "subject": subject,
            "htmlContent": f"<div style='font-family:sans-serif;line-height:1.6'>{html_body}</div>",
            "textContent": body_message or "",
        }
        if attachments_payload:
            brevo_payload["attachment"] = attachments_payload
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"accept": "application/json", "api-key": brevo_key, "content-type": "application/json"},
            json=brevo_payload,
            timeout=20,
        )
        if 200 <= resp.status_code < 300:
            return {"status": "SUCCESS", "provider": "brevo", "response": resp.json()}
        logger.error("Brevo gagal (%s): %s", resp.status_code, resp.text)
        return {"status": "ERROR", "message": f"Brevo menolak pengiriman ({resp.status_code}): {resp.text}"}
    # 3. Coba Gmail SMTP jika EMAIL_HOST_USER & EMAIL_HOST_PASSWORD tersedia
    smtp_user = _load_env_var("EMAIL_HOST_USER")
    smtp_pass = _load_env_var("EMAIL_HOST_PASSWORD")
    if smtp_user and smtp_pass:
        from django.core.mail import EmailMessage, get_connection
        conn = get_connection(
            host="smtp.gmail.com",
            port=587,
            username=smtp_user,
            password=smtp_pass,
            use_tls=True,
        )
        msg = EmailMessage(subject=subject, body=body_message, from_email=smtp_user, to=[recipient_email], connection=conn)
        if local_pdf and os.path.exists(local_pdf):
            msg.attach_file(local_pdf)
        msg.send(fail_silently=False)
        return {"status": "SUCCESS", "provider": "smtp"}
    return {"status": "ERROR", "message": "Konfigurasi email (BREVO_API_KEY / RESEND_API_KEY / SMTP) belum diisi di .env."}
