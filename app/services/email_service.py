from __future__ import annotations

import os
import random
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib


def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _build_otp_html(otp_code: str, purpose: str) -> tuple[str, str]:
    if purpose == "email_verification":
        subject = "Xác thực email — Hệ thống phát hiện té ngã"
        color = "#2196F3"
        heading = "Xác thực địa chỉ email"
        note = "Nhập mã này để hoàn tất việc xác thực tài khoản."
    else:
        subject = "Đặt lại mật khẩu — Hệ thống phát hiện té ngã"
        color = "#F44336"
        heading = "Đặt lại mật khẩu"
        note = "Nhập mã này để đặt lại mật khẩu của bạn."

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:32px;
                border:1px solid #e0e0e0;border-radius:8px;">
      <h2 style="color:#333;">{heading}</h2>
      <p style="color:#555;">{note}</p>
      <div style="text-align:center;margin:24px 0;">
        <span style="font-size:36px;font-weight:bold;letter-spacing:8px;color:{color};">
          {otp_code}
        </span>
      </div>
      <p style="color:#888;font-size:13px;">
        Mã có hiệu lực trong <strong>10 phút</strong>.<br>
        Nếu bạn không yêu cầu điều này, hãy bỏ qua email này.
      </p>
    </div>
    """
    return subject, html


async def send_otp_email(to_email: str, otp_code: str, purpose: str) -> None:
    smtp_host = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("MAIL_PORT", "587"))
    username  = os.getenv("MAIL_USERNAME", "")
    password  = os.getenv("MAIL_PASSWORD", "")
    from_addr = os.getenv("MAIL_FROM", username)

    if not username or not password:
        raise RuntimeError("Email chưa được cấu hình (MAIL_USERNAME, MAIL_PASSWORD)")

    subject, html_body = _build_otp_html(otp_code, purpose)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=smtp_host,
        port=smtp_port,
        username=username,
        password=password,
        start_tls=True,
    )
async def send_report_reply_email(
    to_email:     str,
    user_name:    str,
    report_title: str,
    reply:        str,
) -> None:
    smtp_host = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("MAIL_PORT", "587"))
    username  = os.getenv("MAIL_USERNAME", "")
    password  = os.getenv("MAIL_PASSWORD", "")
    from_addr = os.getenv("MAIL_FROM", username)

    if not username or not password:
        return  # Email chưa cấu hình → bỏ qua, không lỗi

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:32px;
                border:1px solid #e0e0e0;border-radius:8px;">
      <h2 style="color:#333;">Phản hồi báo cáo</h2>
      <p style="color:#555;">Xin chào <strong>{user_name}</strong>,</p>
      <p style="color:#555;">Báo cáo <strong>"{report_title}"</strong> của bạn đã được phản hồi:</p>
      <div style="background:#f5f5f5;padding:16px;border-radius:8px;margin:16px 0;
                  border-left:4px solid #2196F3;">
        <p style="color:#333;margin:0;white-space:pre-wrap;">{reply}</p>
      </div>
      <p style="color:#888;font-size:13px;">
        Vui lòng mở ứng dụng để xem chi tiết.<br>
        Trân trọng, <strong>Fall Detection Team</strong>
      </p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Phản hồi báo cáo: {report_title}"
    msg["From"]    = from_addr
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname  = smtp_host,
            port      = smtp_port,
            username  = username,
            password  = password,
            start_tls = True,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Email send failed: %s", e)