import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import yaml
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


# ---------- Utils ----------
def strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html5lib")
    return soup.get_text(" ", strip=True)

def first_sentences(text: str, max_sentences: int = 2) -> str:
    if not text:
        return ""
    parts, start = [], 0
    for i, ch in enumerate(text):
        if ch in ".!?":
            parts.append(text[start:i+1].strip())
            start = i + 1
            if len(parts) >= max_sentences:
                break
    if not parts:
        parts = [text[:240].strip()]
    return " ".join(parts)

def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def fetch_items(rss_url: str):
    feed = feedparser.parse(rss_url)
    return feed.entries if hasattr(feed, "entries") else []

def within_lookback(published_parsed, lookback_hours: int) -> bool:
    if not published_parsed:
        return True
    published_dt = datetime(*published_parsed[:6])
    return published_dt >= datetime.utcnow() - timedelta(hours=lookback_hours)

def telegram_send(token: str, chat_id: str, text: str):
    """Envoie un message Telegram et lève une erreur si l'API refuse."""
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    # Vérifie proprement la réponse
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.text[:200]}")
    if not data.get("ok"):
        # Exemple: {'ok': False, 'error_code': 400, 'description': 'Bad Request: chat not found'}
        raise RuntimeError(f"Telegram API error: {data}")

def build_html(items: list, template: str, title: str, lookback: int) -> str:
    def item_html(it):
        link = it.get("link", "#")
        title = strip_html(it.get("title", "(sans titre)"))
        desc = strip_html(it.get("summary", ""))
        desc = first_sentences(desc, 2)
        source = strip_html(it.get("source", {}).get("title", it.get("author", "")))
        source = source or (it.get("feedburner_origlink") and "FeedBurner") or ""
        return f"""
        <div class="item">
          <a class="title" href="{link}">{title}</a>
          <p>{desc}</p>
          <div class="source">{source}</div>
        </div>
        """

    items_html = "\n".join(item_html(i) for i in items)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        template
        .replace("{{TITLE}}", title)
        .replace("{{DATE}}", now)
        .replace("{{LOOKBACK}}", str(lookback))
        .replace("{{COUNT}}", str(len(items)))
        .replace("{{ITEMS}}", items_html)
    )

def send_email(smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str, from_addr: str, to_addr: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls(context=context)
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_addr, [to_addr], msg.as_string())


# ---------- Main ----------
if __name__ == "__main__":
    load_dotenv()

    EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "true").lower() == "true"
    TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"

    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)
    EMAIL_TO = os.getenv("EMAIL_TO", SMTP_USER)

    TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

    TITLE = os.getenv("NEWSLETTER_TITLE", "Daily Tech & AI Brief")
    LOOKBACK = int(os.getenv("LOOKBACK_HOURS", "24"))
    MAX_ITEMS = int(os.getenv("MAX_ITEMS", "12"))

    config = load_yaml("feeds.yaml")
    template = load_template("templates/email_template.html")

    # Collecte des articles
    items = []
    for url in config.get("feeds", []):
        try:
            for entry in fetch_items(url):
                if within_lookback(entry.get("published_parsed"), LOOKBACK):
                    items.append(entry)
        except Exception as e:
            print(f"[WARN] {url}: {e}")

    # Déduplication simple
    seen = set()
    uniq = []
    for it in items:
        link = it.get("link")
        if link and link not in seen:
            seen.add(link)
            uniq.append(it)

    # Limite
    uniq = uniq[:MAX_ITEMS]

    # Génère HTML (archive locale)
    html = build_html(uniq, template, TITLE, LOOKBACK)
    with open("newsletter.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK] Newsletter générée -> newsletter.html")

    # Email (désactivé dans ton workflow par défaut)
    if EMAIL_ENABLED and SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_TO:
        try:
            send_email(
                SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
                EMAIL_FROM, EMAIL_TO, TITLE, html
            )
            print("[OK] Email envoyé.")
        except Exception as e:
            print(f"[ERR] Envoi email: {e}")

    # Telegram (avec vérif d'erreurs)
    if TELEGRAM_ENABLED and TG_TOKEN and TG_CHAT:
        try:
            lines = [f"{TITLE} — {len(uniq)} actus"]
            for it in uniq:
                t = strip_html(it.get("title", "(sans titre)"))
                link = it.get("link", "")
                lines.append(f"• {t}\n{link}")

            masked = TG_TOKEN[:7] + "..." + TG_TOKEN[-4:] if len(TG_TOKEN) > 12 else "****"
            print(f"[DEBUG] Envoi Telegram → chat_id={TG_CHAT}, token={masked}")

            telegram_send(TG_TOKEN, TG_CHAT, "\n\n".join(lines))
            print("[OK] Telegram envoyé.")
        except Exception as e:
            print(f"[ERR] Telegram: {e}")
    else:
        print("[INFO] Telegram désactivé ou secrets manquants.")
