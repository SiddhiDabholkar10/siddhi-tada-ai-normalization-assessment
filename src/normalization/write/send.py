"""Send a write plan (D-100): UKG Ready only, never a plan with a refusal, each call once.

The result keeps the outcome, the HTTP status, the new or updated account id and the provider's
error messages; never the response body, which can echo personal data.
"""
from importlib import import_module
from typing import Any

from ..live.client import Session
from ..live.fetch import PLANS
from .plan import Plan


def _messages(body: Any) -> list[str]:
    """Error texts from a provider error body (UKG: ``errors[].message``), at most 5."""
    if isinstance(body, dict):
        items = body.get("errors") if isinstance(body.get("errors"), list) else [body]
        texts = [str(item.get("message") or item.get("errorMessage") or "") for item in items if isinstance(item, dict)]
        return [text[:300] for text in texts if text][:5]
    return [body[:300]] if isinstance(body, str) and body.strip() else []


def send(plan: Plan, session: Session) -> dict:
    """Send every call of ``plan`` in order; stop at the first that fails. Raises ValueError for a
    plan that may not be sent (not UKG Ready, refusals, or a session of another provider)."""
    if not plan.sendable:
        why = "only UKG Ready plans are sent" if plan.destination != "ukg-ready" else "the plan has refusals"
        raise ValueError(f"not sent: {why}")
    if session.provider != plan.destination:
        raise ValueError(f"not sent: the session is for {session.provider}, the plan for {plan.destination}")
    prefix = getattr(import_module(PLANS[plan.destination], "normalization.live"), "PATH_PREFIX", "")
    result: dict[str, Any] = {"destination": plan.destination, "operation": plan.operation, "calls": []}
    for call in plan.calls:
        reply = session.send(call.method, prefix + call.path, call.body, call.content_type)
        entry: dict[str, Any] = {"method": call.method, "route": call.route, "status": reply.status}
        if reply.status == 0:
            entry["outcome"] = "unknown: no answer, so the write may or may not have been applied (not retried)"
        elif 200 <= reply.status < 300:
            entry["outcome"] = "done"
            location = {k.lower(): v for k, v in reply.headers.items()}.get("location", "")
            account = reply.body.get("id") if isinstance(reply.body, dict) else None
            entry["id"] = str(account) if account is not None else (location.rstrip("/").rsplit("/", 1)[-1] or None)
        else:
            entry["outcome"] = "failed"
            entry["messages"] = _messages(reply.body)
        result["calls"].append(entry)
        if entry["outcome"] != "done":
            break
    result["ok"] = all(call["outcome"] == "done" for call in result["calls"]) and len(result["calls"]) == len(plan.calls)
    return result
