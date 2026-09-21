#!/usr/bin/env python3
"""Read-only admin dashboard for RERA project email notifications."""

from __future__ import annotations

import ast
import json
import math
import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from flask import Flask, Response, jsonify, render_template, request


app = Flask(__name__)
F = TypeVar("F", bound=Callable[..., Any])


def state_db() -> Path:
    return Path(os.getenv("STATE_DB", "data/haryana_rera.sqlite3"))


def admin_credentials() -> tuple[str, str]:
    return os.getenv("ADMIN_USERNAME", "admin"), os.getenv("ADMIN_PASSWORD", "")


def unauthorized(message: str = "Authentication required") -> Response:
    return Response(message, 401, {"WWW-Authenticate": 'Basic realm="RERA Mail Admin"'})


def require_auth(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        expected_user, expected_password = admin_credentials()
        if not expected_password:
            return Response("ADMIN_PASSWORD is not configured.", 503)
        supplied = request.authorization
        if not supplied or not (
            secrets.compare_digest(supplied.username or "", expected_user)
            and secrets.compare_digest(supplied.password or "", expected_password)
        ):
            return unauthorized()
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def decode_payload(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        try:
            value = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return {}
    return value if isinstance(value, dict) else {}


def format_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        return value


def load_rows() -> list[dict[str, Any]]:
    path = state_db()
    if not path.exists():
        return []
    with sqlite3.connect(path, timeout=10) as db:
        db.row_factory = sqlite3.Row
        try:
            rows = db.execute(
                """
                SELECT registration_key, first_seen_at, notified_at, payload,
                       attempts, last_error
                FROM registrations
                ORDER BY first_seen_at DESC, registration_key DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    recipient = os.getenv("EMAIL_TO", "bharadwajr278@gmail.com")
    result: list[dict[str, Any]] = []
    for row in rows:
        project = decode_payload(row["payload"])
        if row["notified_at"]:
            status = "sent"
        elif row["last_error"]:
            status = "failed"
        else:
            status = "pending"
        city = str(project.get("city", "Unknown"))
        source = str(project.get("source") or project.get("registered_with") or "Unknown")
        priority = source.upper() == "UP RERA" or city.upper() in {
            "GURUGRAM",
            "FARIDABAD",
            "NOIDA / GREATER NOIDA",
        }
        result.append(
            {
                **project,
                "registration_key": row["registration_key"],
                "source": source,
                "city": city,
                "status": status,
                "priority": priority,
                "first_seen_display": format_timestamp(row["first_seen_at"]),
                "notified_display": format_timestamp(row["notified_at"]),
                "first_seen_raw": row["first_seen_at"],
                "attempts": row["attempts"],
                "last_error": row["last_error"],
                "recipient": recipient,
            }
        )
    return result


def filtered_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query = request.args.get("q", "").strip().casefold()
    source = request.args.get("source", "").strip().casefold()
    city = request.args.get("city", "").strip().casefold()
    status = request.args.get("status", "").strip().casefold()
    output = []
    for row in rows:
        haystack = " ".join(
            str(row.get(field, ""))
            for field in ("name", "registration_number", "builder", "city", "location", "source")
        ).casefold()
        if query and query not in haystack:
            continue
        if source and str(row.get("source", "")).casefold() != source:
            continue
        if city and str(row.get("city", "")).casefold() != city:
            continue
        if status and str(row.get("status", "")).casefold() != status:
            continue
        output.append(row)
    return output


@app.after_request
def security_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    return response


@app.get("/health")
def health() -> Response:
    return jsonify(status="ok", database_exists=state_db().exists())


@app.get("/")
@require_auth
def dashboard() -> str:
    all_rows = load_rows()
    visible = filtered_rows(all_rows)
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    per_page = 50
    pages = max(1, math.ceil(len(visible) / per_page))
    page = min(page, pages)
    start = (page - 1) * per_page

    stats = {
        "total": len(all_rows),
        "sent": sum(row["status"] == "sent" for row in all_rows),
        "pending": sum(row["status"] == "pending" for row in all_rows),
        "failed": sum(row["status"] == "failed" for row in all_rows),
        "priority": sum(bool(row["priority"]) for row in all_rows),
    }
    sources = sorted({str(row["source"]) for row in all_rows})
    cities = sorted({str(row["city"]) for row in all_rows})
    return render_template(
        "dashboard.html",
        rows=visible[start : start + per_page],
        stats=stats,
        sources=sources,
        cities=cities,
        page=page,
        pages=pages,
        result_count=len(visible),
        filters=request.args,
        refreshed_at=datetime.now().astimezone().strftime("%d %b %Y, %I:%M:%S %p"),
    )


@app.get("/api/projects")
@require_auth
def projects_api() -> Response:
    rows = filtered_rows(load_rows())
    return jsonify(count=len(rows), projects=rows)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("ADMIN_PORT", "8080")), debug=False)
