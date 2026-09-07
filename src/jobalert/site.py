"""Generates the landing page the Instagram bio links to.

Nearly every visitor arrives by tapping the bio link inside the Instagram app, so
the page is mobile-first, static, and dependency-free - it is served straight from
GitHub Pages.

Job text comes from third-party APIs and lands on a public page, so every field is
HTML-escaped and every link is checked to be https before it is rendered.
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from jobalert.attribution import label_for

Record = Dict[str, Any]

ACCENTS = {"GOVERNMENT": "#34d399", "PRIVATE": "#60a5fa"}
CATEGORY_LABELS = {"GOVERNMENT": "GOVT", "PRIVATE": "PRIVATE"}


def _safe_url(url: Optional[str]) -> Optional[str]:
    """Return the URL only if it is https. Anything else is not linked."""
    if not url:
        return None
    cleaned = str(url).strip()
    return cleaned if cleaned.lower().startswith("https://") else None


def _esc(value: Optional[str]) -> str:
    return html.escape(str(value or ""), quote=True)


def _pretty_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y")
    except (ValueError, TypeError):
        return ""


def _card(record: Record) -> str:
    category = str(record.get("category") or "PRIVATE").upper()
    accent = ACCENTS.get(category, ACCENTS["PRIVATE"])
    apply_url = _safe_url(record.get("apply_url"))

    meta: List[str] = []
    if record.get("location"):
        meta.append(f'<span class="meta-item">\U0001f4cd {_esc(record["location"])}</span>')
    if record.get("salary"):
        suffix = " (estimated)" if record.get("salary_is_estimated") else ""
        meta.append(f'<span class="meta-item">\U0001f4b0 {_esc(record["salary"])}{_esc(suffix)}</span>')
    if record.get("vacancies"):
        count = record["vacancies"]
        posts = f"{count:,} posts" if isinstance(count, int) and count > 1 else f"{count} post"
        meta.append(f'<span class="meta-item">\U0001f465 {_esc(posts)}</span>')
    if record.get("age_limit"):
        meta.append(f'<span class="meta-item">\U0001f9d1 {_esc(record["age_limit"])}</span>')
    if record.get("application_fee"):
        meta.append(f'<span class="meta-item">\U0001f9fe {_esc(record["application_fee"])}</span>')

    summary = record.get("description")
    desc = f'<p class="desc">{_esc(summary)}</p>' if summary else ""

    deadline = _pretty_date(record.get("last_date"))
    if deadline:
        stamp = f'<span class="deadline">Apply by {_esc(deadline)}</span>'
    else:
        # "Added", not "Posted": this is when the job appeared on our feed, which
        # is not necessarily when the employer advertised it.
        added = _pretty_date(record.get("published_at"))
        stamp = f'<span class="posted">Added {_esc(added)}</span>' if added else ""

    if apply_url:
        action = (
            f'<a class="apply" href="{_esc(apply_url)}" target="_blank" '
            f'rel="noopener noreferrer">Apply</a>'
        )
    else:
        # Never render a link we could not verify as https.
        action = '<span class="apply apply-disabled">Link unavailable</span>'

    return f"""      <article class="card" style="--accent: {accent}">
        <span class="pill">{_esc(CATEGORY_LABELS.get(category, category))}</span>
        <h2>{_esc(record.get("title"))}</h2>
        <p class="org">{_esc(record.get("org"))}</p>
        <div class="meta">{"".join(meta)}</div>
        {desc}
        <div class="foot">{stamp}{action}</div>
        <p class="src">via {_esc(label_for(str(record.get("source") or "")))}</p>
      </article>"""


def _page(records: Sequence[Record], handle: str, generated_at: datetime) -> str:
    cards = "\n".join(_card(record) for record in records)
    if not records:
        cards = '      <p class="empty">No jobs published yet. Check back shortly.</p>'

    sources = sorted({label_for(str(r.get("source") or "")) for r in records}) or ["Adzuna"]
    count = len(records)
    summary = f"{count} recent opening{'' if count == 1 else 's'}" if count else "Updated twice daily"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(handle)} - Job Alerts</title>
<meta name="description" content="Recent government and private job openings, updated twice a day.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0c101b; --surface: #161d2d; --line: #263046;
    --text: #ffffff; --muted: #8d9cb4; --on-accent: #0a0e18;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: Poppins, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.5; -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 640px; margin: 0 auto; padding: 28px 20px 64px; }}
  header {{ padding: 8px 0 28px; border-bottom: 1px solid var(--line); margin-bottom: 24px; }}
  .handle {{ font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }}
  .tagline {{ color: var(--muted); font-size: 15px; margin: 6px 0 0; }}
  .count {{ color: var(--muted); font-size: 13px; margin: 14px 0 0;
            text-transform: uppercase; letter-spacing: 0.08em; }}
  .card {{
    background: var(--surface); border: 1px solid var(--line);
    border-left: 4px solid var(--accent); border-radius: 14px;
    padding: 20px; margin-bottom: 16px;
  }}
  .pill {{
    display: inline-block; background: var(--accent); color: var(--on-accent);
    font-size: 11px; font-weight: 700; letter-spacing: 0.12em;
    padding: 4px 12px; border-radius: 999px;
  }}
  .card h2 {{ font-size: 19px; font-weight: 700; margin: 12px 0 4px; line-height: 1.3; }}
  .org {{ color: var(--accent); font-weight: 600; font-size: 15px; margin: 0 0 12px; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 16px; }}
  .meta-item {{ color: var(--muted); font-size: 14px; }}
  .foot {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
  .deadline, .posted {{ font-size: 13px; color: var(--muted); }}
  .deadline {{ color: var(--accent); font-weight: 600; }}
  .apply {{
    background: var(--accent); color: var(--on-accent); text-decoration: none;
    font-weight: 700; font-size: 14px; padding: 10px 22px; border-radius: 999px;
    white-space: nowrap;
  }}
  .apply-disabled {{ background: var(--line); color: var(--muted); }}
  .desc {{ color: var(--muted); font-size: 14px; margin: -4px 0 16px; }}
  .src {{ color: #5f6c85; font-size: 11px; margin: 14px 0 0; }}
  .empty {{ color: var(--muted); text-align: center; padding: 48px 0; }}
  footer {{
    margin-top: 36px; padding-top: 20px; border-top: 1px solid var(--line);
    color: var(--muted); font-size: 12px;
  }}
  footer a {{ color: var(--muted); }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="handle">{_esc(handle)}</div>
      <p class="tagline">Government &amp; private job openings, updated twice a day.</p>
      <p class="count">{_esc(summary)}</p>
    </header>
    <main>
{cards}
    </main>
    <footer>
      <p>Listings sourced from {_esc(", ".join(sources))}. Always verify details on the
      employer's official notification before applying.</p>
      <p>Last updated {_esc(generated_at.strftime("%d %b %Y, %H:%M UTC"))}.</p>
    </footer>
  </div>
</body>
</html>
"""


def render_site(
    records: Sequence[Record],
    handle: str,
    dest: Path,
    generated_at: Optional[datetime] = None,
) -> Path:
    """Write the landing page to ``dest`` and return the path."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        _page(records, handle=handle, generated_at=generated_at or datetime.utcnow()),
        encoding="utf-8",
    )
    return dest
