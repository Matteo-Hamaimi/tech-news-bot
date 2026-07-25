"""Envoi SMTP via Gmail (nécessite un app password, pas le mot de passe du compte)."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send(subject: str, html_body: str, plain_fallback: str = "") -> None:
    user = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")  # Google affiche des espaces
    to_addr = os.environ["NEWSLETTER_TO"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr

    if not plain_fallback:
        plain_fallback = "Cette newsletter est en HTML. Ouvre dans un client compatible."
    msg.attach(MIMEText(plain_fallback, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, password)
        server.send_message(msg)

    print(f"Envoyé à {to_addr}")
