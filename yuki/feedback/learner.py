"""Daily learner.

Reads yesterday's 60-Episodes/control-YYYY-MM-DD.md, groups records by
apps_involved, runs one LLM call per app via the provider factory,
replaces the auto-managed `## Auto-learned` section in 40-Apps/<slug>.md.
The handwritten part of each app note (everything above `## Auto-learned`)
is never touched.

Provider follows the same resolution as the rest of Yuki -- whichever
provider is set in settings.json or YUKI_LLM_PROVIDER env var. So Gemini
and Ollama users don't need an Anthropic key.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from yuki.memory import frontmatter as fm
from yuki.memory import paths
from yuki.memory.vault import slugify
from yuki.messages import HumanMessage

log = logging.getLogger(__name__)

# Minimum distinct task records in a day before a skeleton note is
# auto-created for an app that has no note yet.
_MIN_RECORDS_FOR_NEW_NOTE = 2

# Bundle ids whose last component is not the app's display name.
_KNOWN_BUNDLE_NAMES: dict[str, str] = {
    "com.spotify.client": "Spotify",
    "com.google.Chrome": "Google Chrome",
    "com.tinyspeck.slackmacgap": "Slack",
    "net.whatsapp.WhatsApp": "WhatsApp",
}

_AUTO_HEADER = "## Auto-learned"
_AUTO_LEARNED_RE = re.compile(
    rf"\n{re.escape(_AUTO_HEADER)}.*?(?=\n## |\Z)",
    re.DOTALL,
)
_PROMPT_TMPL = """You are reviewing yesterday's recorded /control task outcomes for the macOS application `{app_name}` (bundle id `{bundle_id}`).

For each successful action, identify any reusable coordinate or pattern.
For each failure, identify the failure mode and propose specific guidance the agent should follow next time.

Output ONLY two markdown subsections, no narrative:

### Confirmed working
- bullet 1
- bullet 2

### Avoid
- bullet 1
- bullet 2

If there are no items under a heading, write `- (none)` under it. Be concrete: include exact coordinates, exact AX role names, exact placeholder strings.

Records:
{records_yaml}
"""


def _client() -> Any:
    """Build an LLM via the provider factory (same as /chat)."""
    from yuki.providers.factory import make_llm

    return make_llm()


def _read_records(day: date) -> list[dict[str, Any]]:
    path = paths.vault_dir() / "60-Episodes" / f"control-{day.isoformat()}.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "```yaml" not in text:
        return []
    body = text.split("```yaml", 1)[1].split("```", 1)[0]
    parsed = yaml.safe_load(body) or []
    return list(parsed) if isinstance(parsed, list) else []


def _by_bundle(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        for bundle_id in r.get("apps_involved") or []:
            if bundle_id:
                out[bundle_id].append(r)
    return out


def derive_app_name(bundle_id: str) -> str:
    """Best-effort display name for an app from its bundle id.

    Known bundles map to their real product name (com.spotify.client →
    Spotify); otherwise the last dot-component is used, title-cased when it
    is all-lowercase and kept verbatim when it already has capitals
    (net.whatsapp.WhatsApp → WhatsApp).
    """
    known = _KNOWN_BUNDLE_NAMES.get(bundle_id)
    if known:
        return known
    last = bundle_id.rsplit(".", 1)[-1].strip()
    if not last:
        return bundle_id
    return last.title() if last.islower() else last


def _create_skeleton_note(
    bundle_id: str, auto_block: str, today: date
) -> Path | None:
    """Create a new 40-Apps note for an app Yuki has no note for yet."""
    app_name = derive_app_name(bundle_id)
    slug = slugify(app_name)
    if not slug:
        return None
    path = paths.vault_dir() / "40-Apps" / f"{slug}.md"
    if path.exists():  # name collision with an unrelated note — don't clobber
        return None

    meta: dict[str, object] = {
        "id": f"app-{slug.lower()}",
        "type": "app",
        "name": app_name,
        "bundle_id": bundle_id,
        "importance": "occasional",
        "common_uses": [],
        "created_at": today.isoformat(),
        "updated_at": today.isoformat(),
        "confidence": 0.5,
    }
    body = _replace_auto_section("", auto_block, today).lstrip("\n")
    try:
        fm.write_file(path, meta, body)
    except Exception as e:
        log.warning("learner: skeleton note write failed for %s: %s", bundle_id, e)
        return None
    return path


def _resolve_app_note_path(bundle_id: str) -> Path | None:
    apps_dir = paths.vault_dir() / "40-Apps"
    if not apps_dir.exists():
        return None
    for path in apps_dir.glob("*.md"):
        try:
            meta, _ = fm.read_file(path)
        except Exception:
            continue
        if meta.get("type") == "app" and meta.get("bundle_id") == bundle_id:
            return path
    return None


def _summarize_via_llm(
    app_name: str, bundle_id: str, records: list[dict[str, Any]]
) -> str | None:
    try:
        llm = _client()
    except Exception as e:
        log.warning("learner: LLM init failed: %s", e)
        return None

    records_yaml = yaml.safe_dump(records, sort_keys=False, allow_unicode=True)
    prompt = _PROMPT_TMPL.format(
        app_name=app_name, bundle_id=bundle_id, records_yaml=records_yaml
    )
    try:
        event = asyncio.run(
            llm.ainvoke(messages=[HumanMessage(content=prompt)], tools=[])
        )
        text = (event.content or "").strip() if event else ""
    except Exception as e:
        log.warning(
            "learner: LLM call failed for %s via %s: %s",
            bundle_id, getattr(llm, "provider", "?"), e,
        )
        return None

    if "### Confirmed working" not in text or "### Avoid" not in text:
        log.warning("learner: malformed LLM output for %s", bundle_id)
        return None
    return text


def _replace_auto_section(body: str, new_block: str, today: date) -> str:
    block = (
        f"\n{_AUTO_HEADER}\n\n"
        f"_Last updated: {today.isoformat()} (auto-managed -- do not edit)_\n\n"
        f"{new_block}\n"
    )
    if _AUTO_HEADER in body:
        return _AUTO_LEARNED_RE.sub(block, body, count=1)
    if not body.endswith("\n"):
        body += "\n"
    return body + block


def run_for_date(day: date) -> int:
    """Process control-<day>.md and update matching 40-Apps notes.

    Returns the count of app notes updated (including skeleton notes created
    for apps seen in >= 2 records that had no note yet). Failures (malformed
    LLM response, network error) leave existing app notes untouched.
    """
    records = _read_records(day)
    if not records:
        return 0

    today = date.today()
    updated = 0
    for bundle_id, recs in _by_bundle(records).items():
        path = _resolve_app_note_path(bundle_id)
        if path is None:
            # No note yet — auto-create a skeleton once the app shows up in
            # enough records to be worth remembering.
            if len(recs) < _MIN_RECORDS_FOR_NEW_NOTE:
                continue
            new_block = _summarize_via_llm(derive_app_name(bundle_id), bundle_id, recs)
            if new_block is None:
                continue
            if _create_skeleton_note(bundle_id, new_block, today) is not None:
                updated += 1
            continue
        try:
            meta, body = fm.read_file(path)
        except Exception:
            continue
        app_name = str(meta.get("name") or path.stem)

        new_block = _summarize_via_llm(app_name, bundle_id, recs)
        if new_block is None:
            continue

        new_body = _replace_auto_section(body, new_block, today)
        meta["updated_at"] = today.isoformat()
        try:
            fm.write_file(path, meta, new_body)
            updated += 1
        except Exception as e:
            log.warning("learner: write failed for %s: %s", path, e)

    return updated
