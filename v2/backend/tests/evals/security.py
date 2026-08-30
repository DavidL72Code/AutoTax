"""Security checks for the receipt pipeline.

The risk that matters most here is simple: **email bodies are attacker
controlled**. Anyone can send you a message. Every check below either keeps
untrusted text away from anything privileged, or keeps privileged material out
of places untrusted text can reach.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import stat
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from harness import PromptRecorder, use_memory_store  # noqa: E402

from app import auth  # noqa: E402
from app.config import settings  # noqa: E402
from app.graph import runner  # noqa: E402
from app.graph.runner import run_many  # noqa: E402
from app.insights import exports  # noqa: E402
from app.store import accounts, repository  # noqa: E402

RECEIPT = {
    "id": "sec-1",
    "sender": "no-reply@chipotle.com",
    "subject": "Your receipt from Chipotle",
    "date": "2026-07-01",
    "body": "Receipt\nVendor: Chipotle\nSubtotal: $18.40\nTax: $1.15\nBalance Due Now: $19.55\n",
}

# A body with a long non-financial tail. The excerpt property is only testable
# on an email that has something to leave out.
_PADDING = "\n".join(
    f"Recommended for you: product {i}, read our blog, manage preferences, view in browser"
    for i in range(40)
)
LONG_RECEIPT = {
    **RECEIPT,
    "id": "sec-long",
    "body": RECEIPT["body"] + _PADDING + "\nDelivery notes: leave at door. Customer since 2019.\n",
}


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _configured_secrets() -> dict[str, str]:
    return {
        name: (value or "").strip()
        for name, value in {
            "GOOGLE_API_KEY": settings.google_api_key,
            "FERNET_KEY": settings.fernet_key,
            "OAUTH_CLIENT_SECRET": settings.google_oauth_client_secret,
        }.items()
        if (value or "").strip()
    }


async def _prompt_hygiene() -> list[dict[str, Any]]:
    """Nothing privileged may appear in text sent to the model."""
    use_memory_store()
    with PromptRecorder() as recorder:
        records = await run_many([LONG_RECEIPT], "sec", interactive=False)

    joined = "\n".join(recorder.prompts)
    leaked = [name for name, value in _configured_secrets().items() if value in joined]
    checks = [
        _check(
            "no credential appears in any prompt",
            not leaked,
            "prompts carry receipt text only" if not leaked else f"leaked: {', '.join(leaked)}",
        )
    ]

    if recorder.prompts:
        # How much of the email itself reached the model, ignoring the static
        # instructions, those are ours, and lengthening them is not a leak.
        body_lines = [line for line in LONG_RECEIPT["body"].splitlines() if len(line.strip()) > 12]
        carried = [line for line in body_lines if line.strip() in joined]
        share = round(100 * len(carried) / max(len(body_lines), 1))
        checks.append(
            _check(
                "prompts carry a financial excerpt, not the whole email",
                LONG_RECEIPT["body"].strip() not in joined and share <= 40,
                f"{share}% of the body's lines reached the model ({len(carried)}/{len(body_lines)})",
            )
        )

    # The review queue reaches a browser. Whatever it carries about a paused
    # thread must identify the email, never reproduce it, a body can hold
    # anything the merchant put there, and the app has no reason to hold it.
    paused = await runner.paused_threads("sec", [LONG_RECEIPT["id"]])
    exposed = json.dumps(paused)
    checks.append(
        _check(
            "the review queue never carries an email body",
            "body" not in exposed and LONG_RECEIPT["body"][:60] not in exposed,
            "paused threads expose sender and subject only",
        )
    )

    stored = json.dumps(records)
    body_leaked = LONG_RECEIPT["body"][:60] in stored or "email_body" in stored
    checks.append(
        _check(
            "email bodies are never stored",
            not body_leaked,
            "records hold extracted fields and a trace only"
            if not body_leaked
            else "raw body found in the stored record",
        )
    )
    return checks


def _csv_hygiene() -> list[dict[str, Any]]:
    """A vendor name is attacker-controlled text that ends up in a spreadsheet."""
    hostile = [
        {
            "date": "2026-07-01",
            "vendor": "=cmd|' /C calc'!A1",
            "category": "Other",
            "amount": 12.75,
            "tax": 0.75,
            "payment_method": "+1234567",
            "email_id": "@SUM(A1:A9)",
            "currency": "USD",
            "order_number": "-2+3+cmd",
            "status": "parsed",
            "confidence": 0.9,
        }
    ]
    results = []
    for name, writer in exports.FORMATS.items():
        output = writer(hostile)
        risky = [
            cell.strip('"')
            for line in output.splitlines()[1:]
            for cell in line.split(",")
            if cell.strip('"')[:1] in ("=", "+", "@")
            or (cell.strip('"')[:1] == "-" and not cell.strip('"')[1:2].isdigit())
        ]
        results.append(
            _check(
                f"{name} export neutralises spreadsheet formulas",
                not risky,
                "no cell begins with a formula trigger"
                if not risky
                else f"unescaped: {risky[:3]}",
            )
        )
    return results


def _crypto() -> list[dict[str, Any]]:
    try:
        token = "1//0f-not-a-real-refresh-token"
        sealed = auth.encrypt(token)
        ok = sealed != token and auth.decrypt(sealed) == token and token not in sealed
        return [
            _check(
                "refresh tokens are encrypted at rest",
                ok,
                "Fernet round-trip holds and the plaintext is absent from the ciphertext",
            )
        ]
    except Exception as exc:  # noqa: BLE001
        return [_check("refresh tokens are encrypted at rest", False, f"{type(exc).__name__}: {exc}")]


async def _file_permissions() -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "accounts.json"
        store = accounts.JsonAccountStore(path)
        await store.put_account("u1", {"email": "a@b.com", "refresh_token_enc": "sealed"})
        mode = stat.S_IMODE(os.stat(path).st_mode)
        return [
            _check(
                "local credential file is not group or world readable",
                mode & 0o077 == 0,
                f"mode {oct(mode)}",
            )
        ]


async def _api_boundaries() -> list[dict[str, Any]]:
    """Authorisation, isolation and input bounds, driven through the real app."""
    import httpx
    from httpx import ASGITransport

    tmp = tempfile.TemporaryDirectory()
    repository.use(repository.JsonBackend(pathlib.Path(tmp.name) / "tx.json"))
    accounts.use(accounts.JsonAccountStore(pathlib.Path(tmp.name) / "accounts.json"))

    from app.main import app

    checks: list[dict[str, Any]] = []
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        protected = [
            ("GET", "/api/transactions"),
            ("GET", "/api/stats"),
            ("GET", "/api/insights"),
            ("GET", "/api/statement"),
            ("GET", "/api/tax-summary"),
            ("GET", "/api/export/ledger"),
            ("POST", "/api/sync"),
            ("POST", "/api/google/disconnect"),
        ]
        unguarded = [
            f"{method} {path} -> {(await client.request(method, path)).status_code}"
            for method, path in protected
            if (await client.request(method, path)).status_code != 401
        ]
        checks.append(
            _check(
                "every data route refuses an anonymous caller",
                not unguarded,
                f"{len(protected)} routes return 401 without a session"
                if not unguarded
                else str(unguarded),
            )
        )

        token_a = await auth.link_google_account("a@example.com", "", user_id="user_a")
        token_b = await auth.link_google_account("b@example.com", "", user_id="user_b")
        id_a = await repository.save(
            "user_a",
            {"email_id": "e-a", "vendor": "AlphaCo", "amount": 10.0, "status": "parsed", "date": "2026-07-01"},
        )
        await repository.save(
            "user_b",
            {"email_id": "e-b", "vendor": "BetaCo", "amount": 20.0, "status": "parsed", "date": "2026-07-01"},
        )

        cookie_a = {auth.SESSION_COOKIE: token_a}
        cookie_b = {auth.SESSION_COOKIE: token_b}

        listed = (await client.get("/api/transactions", cookies=cookie_b)).json()["transactions"]
        vendors = {row.get("vendor") for row in listed}
        checks.append(
            _check(
                "one account cannot list another's receipts",
                vendors == {"BetaCo"},
                f"account B sees {sorted(v for v in vendors if v)}",
            )
        )

        patched = await client.patch(f"/api/transactions/{id_a}", json={"amount": 999.0}, cookies=cookie_b)
        deleted = await client.delete(f"/api/transactions/{id_a}", cookies=cookie_b)
        checks.append(
            _check(
                "one account cannot edit or delete another's receipts",
                patched.status_code == 404 and deleted.status_code == 404,
                f"PATCH {patched.status_code}, DELETE {deleted.status_code} (404 expected for both)",
            )
        )

        oversized = await client.post(
            "/api/sync", json={"max_results": 10_000_000, "days_back": 99_999}, cookies=cookie_a
        )
        checks.append(
            _check(
                "sync parameters are bounded",
                oversized.status_code == 422,
                f"an absurd max_results returns {oversized.status_code} (422 expected)",
            )
        )

        health = (await client.get("/api/health")).text
        exposed = [name for name, value in _configured_secrets().items() if value in health]
        checks.append(
            _check(
                "diagnostics never echo a secret",
                not exposed,
                "health output carries status and remediation only"
                if not exposed
                else f"exposed: {exposed}",
            )
        )

        issued = await client.post("/api/demo?months=0", cookies={})
        set_cookie = issued.headers.get("set-cookie", "")
        checks.append(
            _check(
                "session cookie is HttpOnly and SameSite",
                "httponly" in set_cookie.lower() and "samesite" in set_cookie.lower(),
                set_cookie.split(";", 1)[-1].strip() or "no cookie issued",
            )
        )

    tmp.cleanup()
    return checks


async def run() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks += await _prompt_hygiene()
    checks += _csv_hygiene()
    checks += _crypto()
    checks += await _file_permissions()
    checks += await _api_boundaries()

    failed = [c for c in checks if not c["ok"]]
    return {
        "passed": not failed,
        "threshold": "every security check holds",
        "metrics": {"checks": len(checks), "passed": len(checks) - len(failed)},
        "failures": failed,
        "results": checks,
    }
