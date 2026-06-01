"""
HTML rendering for the event-subscriptions web UI.

Pure and stdlib-only (``html`` + ``json``). Takes display-safe subscription
dicts (``Subscription.to_dict(include_token=False)``) and returns an HTML
string. No Indigo imports and no I/O, so it is unit-testable in isolation.

The page lists every active subscription with full detail and a Remove button
per row. Auth tokens are never rendered — the renderer selects an explicit
allow-list of keys, so a field added to ``to_dict`` later cannot leak.
"""

import html
import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

# Fields rendered for each subscription, in display order. ``auth_token`` is
# deliberately absent so a token can never reach the page.
_DETAIL_FIELDS = [
    ("Entity", "_entity"),
    ("Conditions", "_conditions"),
    ("Webhook URL", "webhook_url"),
    ("Auth mode", "auth_mode"),
    ("Verify SSL", "verify_ssl"),
    ("Dwell (s)", "duration_seconds"),
    ("Max fires", "max_fires"),
    ("Created", "created_at"),
]


def parse_delete_subscription_id(body: str) -> Optional[str]:
    """Extract ``subscription_id`` from a form-encoded POST body.

    Returns None when the body is empty or has no ``subscription_id`` field.
    """
    if not body:
        return None
    values = parse_qs(body).get("subscription_id")
    return values[0] if values else None


def _esc(value: Any) -> str:
    """HTML-escape any value. None / empty renders as an em dash."""
    if value is None or value == "":
        return "&mdash;"
    return html.escape(str(value), quote=True)


def _format_entity(sub: Dict[str, Any]) -> str:
    entity_type = sub.get("entity_type", "")
    entity_id = sub.get("entity_id")
    if entity_id is None:
        return f"{_esc(entity_type)} <span class=\"muted\">(all)</span>"
    return f"{_esc(entity_type)} <span class=\"muted\">#{_esc(entity_id)}</span>"


def _format_conditions(sub: Dict[str, Any]) -> str:
    conditions = sub.get("conditions") or {}
    if isinstance(conditions, dict) and conditions.get("any_change"):
        return '<span class="badge">any change</span>'
    return f'<code>{_esc(json.dumps(conditions))}</code>'


def _format_stats(sub: Dict[str, Any]) -> str:
    stats = sub.get("stats") or {}
    fires = stats.get("fires", 0)
    last_fired = stats.get("last_fired_at")
    last_status = stats.get("last_http_status")
    consec = stats.get("consecutive_failures", 0)
    last_error = stats.get("last_error")

    parts = [f'fires: <strong>{_esc(fires)}</strong>']
    if last_fired:
        parts.append(f"last fired: {_esc(last_fired)}")
    if last_status is not None:
        parts.append(f"last HTTP: {_esc(last_status)}")
    if consec:
        parts.append(f'<span class="err">consecutive failures: {_esc(consec)}</span>')
    if last_error:
        parts.append(f'<span class="err">last error: {_esc(last_error)}</span>')
    return " &middot; ".join(parts)


def _render_row(sub: Dict[str, Any]) -> str:
    """Render one subscription as a detail card with a Remove form."""
    sub_id = sub.get("subscription_id", "")
    description = sub.get("description") or "(no description)"

    detail_rows = []
    for label, key in _DETAIL_FIELDS:
        if key == "_entity":
            value_html = _format_entity(sub)
        elif key == "_conditions":
            value_html = _format_conditions(sub)
        else:
            value_html = _esc(sub.get(key))
        detail_rows.append(
            f'<div class="field"><span class="label">{html.escape(label)}</span>'
            f'<span class="value">{value_html}</span></div>'
        )

    return f"""
    <div class="card">
      <div class="card-head">
        <div>
          <div class="title">{_esc(description)}</div>
          <div class="subid">{_esc(sub_id)}</div>
        </div>
        <form method="POST" action="" onsubmit="return confirm('Remove this subscription?');">
          <input type="hidden" name="subscription_id" value="{_esc(sub_id)}">
          <button type="submit" class="remove">Remove</button>
        </form>
      </div>
      <div class="fields">
        {''.join(detail_rows)}
      </div>
      <div class="stats">{_format_stats(sub)}</div>
    </div>"""


_STYLE = """
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 0;
         background: #f4f5f7; color: #1d1d1f; }
  .wrap { max-width: 880px; margin: 0 auto; padding: 24px 16px 48px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: #6b7280; font-size: 13px; margin: 0 0 20px; }
  .dispatcher { font-size: 12px; color: #6b7280; margin: 0 0 20px; }
  .card { background: #fff; border: 1px solid #e3e5e8; border-radius: 10px;
          padding: 16px 18px; margin-bottom: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
  .card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .title { font-weight: 600; font-size: 15px; }
  .subid { font-family: ui-monospace, Menlo, monospace; font-size: 11px; color: #8a8f98; margin-top: 2px; }
  .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin: 14px 0 10px; }
  .field { display: flex; flex-direction: column; font-size: 13px; min-width: 0; }
  .label { color: #6b7280; font-size: 11px; text-transform: uppercase; letter-spacing: .03em; }
  .value { word-break: break-word; }
  .value code { font-family: ui-monospace, Menlo, monospace; font-size: 12px;
                background: #f0f1f3; padding: 1px 5px; border-radius: 4px; }
  .muted { color: #8a8f98; }
  .badge { display: inline-block; background: #e6f0ff; color: #1c5fd6; font-size: 11px;
           font-weight: 600; padding: 2px 8px; border-radius: 10px; }
  .stats { font-size: 12px; color: #4b5563; border-top: 1px solid #f0f1f3; padding-top: 10px; }
  .err { color: #c0392b; }
  button.remove { background: #fff; color: #c0392b; border: 1px solid #e6b8b2;
                  border-radius: 7px; padding: 6px 14px; font-size: 13px; cursor: pointer; }
  button.remove:hover { background: #c0392b; color: #fff; border-color: #c0392b; }
  .empty, .disabled { background: #fff; border: 1px solid #e3e5e8; border-radius: 10px;
                      padding: 32px; text-align: center; color: #6b7280; }
  @media (max-width: 600px) { .fields { grid-template-columns: 1fr; } }
"""


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>{html.escape(title)}</title>
  <style>{_STYLE}</style>
</head>
<body>
  <div class="wrap">
{body}
  </div>
</body>
</html>"""


def _dispatcher_line(dispatcher_stats: Optional[Dict[str, Any]]) -> str:
    if not dispatcher_stats:
        return ""
    sent = dispatcher_stats.get("events_sent", 0)
    failed = dispatcher_stats.get("events_failed", 0)
    depth = dispatcher_stats.get("queue_depth", 0)
    running = dispatcher_stats.get("running", False)
    return (
        f'<p class="dispatcher">Dispatcher: '
        f'{"running" if running else "stopped"} &middot; '
        f'sent {_esc(sent)} &middot; failed {_esc(failed)} &middot; '
        f'queue {_esc(depth)}</p>'
    )


def render_subscriptions_page(
    subscriptions: List[Dict[str, Any]],
    dispatcher_stats: Optional[Dict[str, Any]] = None,
) -> str:
    """Render the full subscriptions list page."""
    count = len(subscriptions)
    header = (
        f'<h1>Event Subscriptions</h1>'
        f'<p class="sub">{count} active subscription{"" if count == 1 else "s"}'
        f' &middot; in-memory only (lost on plugin restart)</p>'
        f'{_dispatcher_line(dispatcher_stats)}'
    )

    if not subscriptions:
        body = header + '<div class="empty">No active subscriptions.</div>'
    else:
        body = header + "".join(_render_row(s) for s in subscriptions)

    return _page("Event Subscriptions", body)


def render_disabled_page() -> str:
    """Render the page shown when event webhooks are disabled."""
    body = (
        '<h1>Event Subscriptions</h1>'
        '<div class="disabled">Event webhooks are disabled.<br>'
        'Enable them in Plugins &rarr; MCP Server &rarr; Configure &rarr; '
        '"Enable Event Webhooks", then reload this page.</div>'
    )
    return _page("Event Subscriptions", body)
