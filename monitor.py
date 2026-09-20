#!/usr/bin/env python3
"""Continuously monitor the official Haryana RERA registered-project list."""

from __future__ import annotations

import hashlib
import html
import logging
import os
import random
import re
import signal
import smtplib
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


PORTAL_URL = "https://haryanarera.gov.in/admincontrol/registered_projects/1"
BASE_URL = "https://haryanarera.gov.in/"
PRIORITY_CITIES = {"GURUGRAM", "FARIDABAD"}
STOP = False


@dataclass(frozen=True)
class Project:
    registration_number: str
    portal_project_id: str
    name: str
    builder: str
    location: str
    city: str
    registered_with: str
    registration_valid_until: str
    detail_url: str
    form_url: str
    registration_date: str = "Not available"
    project_type: str = "Not available"

    @property
    def key(self) -> str:
        registration = re.sub(r"\s+", " ", self.registration_number).strip().upper()
        raw = registration if registration not in {"", "NA", "N/A", "NOT AVAILABLE"} else (self.portal_project_id or self.detail_url)
        return re.sub(r"\s+", " ", raw).strip().upper()

    @property
    def priority(self) -> bool:
        return self.city.upper() in PRIORITY_CITIES


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {
            "User-Agent": "HaryanaRERARegistrationMonitor/1.0 (+personal notification service)",
            "Accept": "text/html,application/xhtml+xml",
        }
    )
    return session


def get_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=(15, 90))
    response.raise_for_status()
    if "text/html" not in response.headers.get("Content-Type", "text/html").lower():
        raise RuntimeError(f"Unexpected content type from {url}")
    return response.text


def extract_registered_projects(page: str) -> list[Project]:
    soup = BeautifulSoup(page, "html.parser")
    table = soup.select_one("#compliant_hearing")
    if table is None:
        raise RuntimeError("Registered-project table was not found; portal layout may have changed")

    projects: list[Project] = []
    for row in table.select("tbody > tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 10:
            continue
        links = [urljoin(BASE_URL, a.get("href", "")) for a in row.select("a[href]")]
        detail_url = next((u for u in links if "/searchprojectDetail/" in u), "")
        form_url = next((u for u in links if "/project_preview_open/" in u), "")
        registration_number = clean(cells[1].get_text(" ", strip=True))
        registration_number = re.sub(r"\s+Lapsed Project\s*$", "", registration_number, flags=re.I)
        project = Project(
            registration_number=registration_number,
            portal_project_id=clean(cells[2].get_text(" ", strip=True)),
            name=clean(cells[3].get_text(" ", strip=True)),
            builder=clean(cells[4].get_text(" ", strip=True)),
            location=clean(cells[5].get_text(" ", strip=True)),
            city=clean(cells[6].get_text(" ", strip=True)),
            registered_with=clean(cells[7].get_text(" ", strip=True)),
            registration_valid_until=clean(cells[9].get_text(" ", strip=True)),
            detail_url=detail_url,
            form_url=form_url,
        )
        if project.key:
            projects.append(project)

    if len(projects) < 500:
        raise RuntimeError(f"Only {len(projects)} projects parsed; refusing a suspicious partial result")
    return projects


def table_records(soup: BeautifulSoup) -> Iterable[dict[str, str]]:
    for table in soup.select("table"):
        headers = [clean(x.get_text(" ", strip=True)) for x in table.select("thead th")]
        if not headers:
            continue
        for row in table.select("tbody tr"):
            values = [clean(x.get_text(" ", strip=True)) for x in row.find_all("td", recursive=False)]
            if values:
                yield dict(zip(headers, values))


def infer_project_type(project: Project, form_page: str | None) -> str:
    # Only return a type when the project's public text contains a strong category phrase.
    text = " ".join((project.name, project.location)).upper()
    if form_page:
        soup = BeautifulSoup(form_page, "html.parser")
        # The portal's "Project Type: NEW" means application type, not asset class; ignore it.
        for row in soup.select("tr"):
            cells = [clean(x.get_text(" ", strip=True)) for x in row.find_all(["th", "td"], recursive=False)]
            if len(cells) >= 2 and re.search(r"^(?:NATURE|CATEGORY|ASSET TYPE|TYPE) OF (?:THE )?PROJECT", cells[0], re.I):
                candidate = cells[-1].upper()
                if candidate not in {"NEW", "ONGOING", "EXTENSION"}:
                    text += " " + candidate
    patterns = (
        (r"\bINDUSTRIAL(?:\s+PARK|\s+COLONY)?\b", "Industrial"),
        (r"\bCOMMERCIAL(?:\s+COLONY|\s+COMPLEX|\s+PROJECT|\s+SITE)?\b|\bMALL\b|\bSCO\b", "Commercial"),
        (r"\bGROUP HOUSING\b", "Residential – Group Housing"),
        (r"\bAFFORDABLE HOUSING\b", "Residential – Affordable Housing"),
        (r"\bPLOTTED COLONY\b|\bRESIDENTIAL PLOTS?\b", "Residential – Plotted Development"),
        (r"\bRESIDENTIAL(?:\s+COLONY|\s+PROJECT)?\b", "Residential"),
    )
    for pattern, label in patterns:
        if re.search(pattern, text):
            return label
    return "Not available"


def enrich_project(session: requests.Session, project: Project) -> Project:
    values = asdict(project)
    if project.detail_url:
        detail_soup = BeautifulSoup(get_html(session, project.detail_url), "html.parser")
        for record in table_records(detail_soup):
            approval_date = record.get("Approval Date", "")
            if approval_date:
                values["registration_date"] = approval_date
                break
    form_page = None
    if project.form_url:
        try:
            form_page = get_html(session, project.form_url)
        except Exception as exc:  # Optional field; do not suppress the core alert.
            logging.warning("Could not fetch project type for %s: %s", project.key, exc)
    values["project_type"] = infer_project_type(project, form_page)
    return Project(**values)


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS registrations (
            registration_key TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            notified_at TEXT,
            payload TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        )
        """
    )
    connection.commit()
    return connection


def smtp_send(project: Project) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = required_env("SMTP_USERNAME")
    password = required_env("SMTP_PASSWORD")
    recipient = os.getenv("EMAIL_TO", "bharadwajr278@gmail.com").strip()
    sender = os.getenv("EMAIL_FROM", user).strip()

    badge = "[PRIORITY] " if project.priority else ""
    msg = EmailMessage()
    msg["Subject"] = f"{badge}New Haryana RERA registration: {project.name}"
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    domain = sender.split("@", 1)[-1] if "@" in sender else None
    digest = hashlib.sha256(project.key.encode("utf-8")).hexdigest()[:24]
    msg["Message-ID"] = f"<hrera-{digest}@{domain or 'localhost'}>"

    rows = [
        ("Project Name", project.name),
        ("RERA Registration Number", project.registration_number),
        ("Portal Project ID", project.portal_project_id),
        ("Developer/Builder Name", project.builder),
        ("Project Location", project.location),
        ("City", project.city),
        ("Registration Date", project.registration_date),
        ("Project Type", project.project_type),
        ("Registered With", project.registered_with),
        ("Direct Haryana RERA Link", project.detail_url or PORTAL_URL),
    ]
    priority_text = "PRIORITY CITY\n\n" if project.priority else ""
    msg.set_content(priority_text + "\n".join(f"{label}: {value}" for label, value in rows))
    html_rows = "".join(
        f"<tr><th style='text-align:left;padding:7px;background:#f3f4f6'>{html.escape(label)}</th>"
        f"<td style='padding:7px'>{html.escape(value)}</td></tr>"
        for label, value in rows[:-1]
    )
    link = html.escape(project.detail_url or PORTAL_URL, quote=True)
    msg.add_alternative(
        f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#172033">
        <h2>{html.escape(badge)}New Haryana RERA registration</h2>
        <table style="border-collapse:collapse;border:1px solid #d1d5db">{html_rows}</table>
        <p><a href="{link}" style="display:inline-block;padding:10px 14px;background:#1d4ed8;color:white;text-decoration:none;border-radius:5px">Open official Haryana RERA record</a></p>
        <p style="color:#6b7280;font-size:12px">Detected by your Haryana RERA monitor. Source: official Haryana RERA portal.</p>
        </body></html>""",
        subtype="html",
    )

    with smtplib.SMTP(host, port, timeout=45) as smtp:
        smtp.ehlo()
        if env_bool("SMTP_STARTTLS", True):
            smtp.starttls()
            smtp.ehlo()
        smtp.login(user, password)
        smtp.send_message(msg)


def store_baseline(db: sqlite3.Connection, projects: list[Project]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.executemany(
        "INSERT OR IGNORE INTO registrations(registration_key, first_seen_at, notified_at, payload) VALUES (?, ?, ?, ?)",
        ((p.key, now, now, repr(asdict(p))) for p in projects),
    )
    db.commit()


def process_snapshot(db: sqlite3.Connection, session: requests.Session, projects: list[Project]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    known = {row[0] for row in db.execute("SELECT registration_key FROM registrations")}
    new_projects = [p for p in projects if p.key not in known]
    for project in new_projects:
        db.execute(
            "INSERT OR IGNORE INTO registrations(registration_key, first_seen_at, payload) VALUES (?, ?, ?)",
            (project.key, now, repr(asdict(project))),
        )
    db.commit()

    pending = {row[0] for row in db.execute("SELECT registration_key FROM registrations WHERE notified_at IS NULL")}
    pending_projects = [p for p in projects if p.key in pending]
    sent = 0
    for project in pending_projects:
        try:
            enriched = enrich_project(session, project)
            if env_bool("DRY_RUN"):
                logging.info("DRY RUN alert: %s", asdict(enriched))
            else:
                smtp_send(enriched)
            db.execute(
                "UPDATE registrations SET notified_at=?, payload=?, attempts=attempts+1, last_error=NULL WHERE registration_key=?",
                (datetime.now(timezone.utc).isoformat(), repr(asdict(enriched)), project.key),
            )
            db.commit()
            sent += 1
            logging.info("Alert sent for %s (%s)", enriched.name, enriched.registration_number)
        except Exception as exc:
            db.execute(
                "UPDATE registrations SET attempts=attempts+1, last_error=? WHERE registration_key=?",
                (clean(str(exc))[:1000], project.key),
            )
            db.commit()
            logging.exception("Alert failed for %s; it remains queued", project.key)
    return sent


def check_once(db: sqlite3.Connection, session: requests.Session) -> tuple[int, int]:
    projects = extract_registered_projects(get_html(session, PORTAL_URL))
    total = db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]
    if total == 0 and not env_bool("ALERT_ON_FIRST_RUN"):
        store_baseline(db, projects)
        logging.info("Baseline created with %d existing registrations; no historical alerts sent", len(projects))
        return len(projects), 0
    sent = process_snapshot(db, session, projects)
    logging.info("Checked %d registrations; %d alert(s) sent", len(projects), sent)
    return len(projects), sent


def handle_stop(_signum: int, _frame: object) -> None:
    global STOP
    STOP = True


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handle_stop)
    state_path = Path(os.getenv("STATE_DB", "data/haryana_rera.sqlite3"))
    interval = max(60, int(os.getenv("POLL_INTERVAL_SECONDS", "120")))
    db = open_database(state_path)
    session = make_session()
    if "--test-email" in sys.argv:
        smtp_send(
            Project(
                registration_number="TEST-NOT-A-REAL-REGISTRATION",
                portal_project_id="TEST",
                name="Haryana RERA Monitor Test",
                builder="Test message",
                location="Test message only",
                city="GURUGRAM",
                registered_with="HRERA",
                registration_valid_until="Not applicable",
                detail_url=PORTAL_URL,
                form_url="",
                registration_date=datetime.now().strftime("%d-%b-%Y"),
                project_type="Test",
            )
        )
        logging.info("Test email sent successfully")
        db.close()
        return 0
    once = "--once" in sys.argv
    failures = 0
    while not STOP:
        try:
            check_once(db, session)
            failures = 0
        except Exception:
            failures += 1
            logging.exception("Monitor check failed")
            if once:
                return 1
        if once:
            break
        delay = min(interval * (2 ** min(failures, 5)), 3600)
        delay += random.randint(0, max(1, min(15, delay // 10)))
        logging.info("Next check in %d seconds", delay)
        for _ in range(delay):
            if STOP:
                break
            time.sleep(1)
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
