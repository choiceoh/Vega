"""
AuroraMdManager — AI-agent-first memory file manager.

Stores memories as structured entries in daily markdown files under memory/.
Supports save, recall, forget, consolidate, and section parsing.

Entry format:
    - [id:abcd1234] **2026-03-21T10:00:00Z** {high} content #tag1 #tag2

Pure Python 3.10+, no external dependencies.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

IMPORTANCE_ORDER: dict[str, int] = {
    "low": 0,
    "normal": 1,
    "high": 2,
    "critical": 3,
}

IMPORTANCE_LEVELS = list(IMPORTANCE_ORDER.keys())


@dataclass
class AuroraEntry:
    id: str
    timestamp: str
    content: str
    tags: list[str] = field(default_factory=list)
    importance: str = "normal"


@dataclass
class SaveResult:
    ok: bool
    action: str  # "created" | "updated" | "duplicate"
    id: str
    file: str
    entry: AuroraEntry


@dataclass
class ForgetResult:
    ok: bool
    removed: int = 0
    ids: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class RecallResult:
    entries: list[AuroraEntry]
    total: int
    file: str


@dataclass
class AuroraSection:
    level: int
    title: str
    content: str
    start_line: int
    end_line: int


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
ENTRY_RE = re.compile(
    r"^- \[id:([a-f0-9]+)\] \*\*(\d{4}-\d{2}-\d{2}T[\d:.Z+-]+)\*\*(?:\s+\{(\w+)\})?\s+(.+)$"
)
TRAILING_TAG_RE = re.compile(r"(?:^|\s)(#[a-z0-9_-]+)$", re.IGNORECASE)

READ_ONLY_FILES = {"memory.md", "soul.md", "tools.md", "agents.md"}

EMPTY_ENTRY = AuroraEntry(id="", timestamp="", content="", tags=[], importance="normal")
EMPTY_SAVE = SaveResult(ok=True, action="duplicate", id="", file="", entry=EMPTY_ENTRY)


# ---------------------------------------------------------------------------
# AuroraMdManager
# ---------------------------------------------------------------------------

class AuroraMdManager:
    """AI-agent-first memory file manager using daily markdown files."""

    def __init__(self, workspace_dir: str | Path, tz: str = "UTC"):
        self.workspace_dir = Path(workspace_dir)
        self.tz = ZoneInfo(tz)

    # ---- Save (create or upsert) ------------------------------------------

    def save(
        self,
        content: str,
        *,
        tags: list[str] | None = None,
        importance: str = "normal",
        file: str | None = None,
        timestamp: str | None = None,
    ) -> SaveResult:
        trimmed = content.strip()
        if not trimmed:
            return EMPTY_SAVE

        ts = timestamp or datetime.now(timezone.utc).isoformat()
        norm_tags = _normalize_tags(tags)
        imp = importance if importance in IMPORTANCE_ORDER else "normal"
        entry_id = content_id(trimmed)

        rel_path = file or self.daily_file_path()
        self._assert_writable(rel_path)
        abs_path = self.workspace_dir / rel_path

        existing = _read_file(abs_path)
        entries = _parse_all_entries(existing)

        # Exact duplicate
        for e in entries:
            if e.id == entry_id:
                return SaveResult(ok=True, action="duplicate", id=entry_id, file=rel_path, entry=e)

        # Fuzzy duplicate (>80% bigram overlap → upsert)
        similar = _find_similar_entry(entries, trimmed)
        if similar is not None:
            updated = AuroraEntry(
                id=entry_id,
                timestamp=ts,
                content=trimmed,
                tags=_merge_tags(similar.tags, norm_tags),
                importance=_max_importance(similar.importance, imp),
            )
            new_content = _replace_entry(existing, similar.id, format_entry(updated))
            _write_file(abs_path, new_content)
            return SaveResult(ok=True, action="updated", id=entry_id, file=rel_path, entry=updated)

        # New entry — append
        entry = AuroraEntry(id=entry_id, timestamp=ts, content=trimmed, tags=norm_tags, importance=imp)
        appended = _append_entry(existing, format_entry(entry))
        _write_file(abs_path, appended)
        return SaveResult(ok=True, action="created", id=entry_id, file=rel_path, entry=entry)

    # ---- Recall -----------------------------------------------------------

    def recall(
        self,
        *,
        file: str | None = None,
        tags: list[str] | None = None,
        min_importance: str | None = None,
        contains: str | None = None,
        limit: int | None = None,
    ) -> RecallResult:
        rel_path = file or self.daily_file_path()
        abs_path = self.workspace_dir / rel_path
        raw = _read_file(abs_path)
        entries = _parse_all_entries(raw)

        if tags:
            wanted = {t.lower() for t in tags}
            entries = [e for e in entries if any(t.lower() in wanted for t in e.tags)]

        if min_importance and min_importance in IMPORTANCE_ORDER:
            threshold = IMPORTANCE_ORDER[min_importance]
            entries = [e for e in entries if IMPORTANCE_ORDER.get(e.importance, 0) >= threshold]

        if contains:
            needle = contains.lower()
            entries = [e for e in entries if needle in e.content.lower()]

        total = len(entries)
        if limit and limit > 0:
            entries = entries[:limit]

        return RecallResult(entries=entries, total=total, file=rel_path)

    # ---- RecallAll --------------------------------------------------------

    def recall_all(
        self,
        *,
        tags: list[str] | None = None,
        min_importance: str | None = None,
        contains: str | None = None,
        limit: int | None = None,
    ) -> dict:
        """Recall across all memory/*.md files, sorted by timestamp desc."""
        memory_dir = self.workspace_dir / "memory"
        if not memory_dir.is_dir():
            return {"entries": [], "total": 0}

        md_files = sorted(memory_dir.glob("*.md"), reverse=True)
        all_entries: list[dict] = []

        for f in md_files:
            rel = f"memory/{f.name}"
            result = self.recall(
                file=rel, tags=tags, min_importance=min_importance,
                contains=contains, limit=None,
            )
            for entry in result.entries:
                all_entries.append({
                    "id": entry.id,
                    "timestamp": entry.timestamp,
                    "content": entry.content,
                    "tags": entry.tags,
                    "importance": entry.importance,
                    "file": rel,
                })

        all_entries.sort(key=lambda x: x["timestamp"], reverse=True)
        total = len(all_entries)
        if limit and limit > 0:
            all_entries = all_entries[:limit]

        return {"entries": all_entries, "total": total}

    # ---- Forget -----------------------------------------------------------

    def forget(
        self,
        *,
        ids: list[str] | None = None,
        tags: list[str] | None = None,
        contains: str | None = None,
        file: str | None = None,
    ) -> ForgetResult:
        if not ids and not tags and not contains:
            return ForgetResult(ok=False, reason="At least one filter (ids, tags, or contains) is required.")

        rel_path = file or self.daily_file_path()
        self._assert_writable(rel_path)
        abs_path = self.workspace_dir / rel_path
        content = _read_file(abs_path)
        entries = _parse_all_entries(content)

        ids_to_remove: set[str] = set()
        for entry in entries:
            if ids and entry.id in ids:
                ids_to_remove.add(entry.id)
                continue
            if tags:
                entry_tags = {t.lower() for t in entry.tags}
                if any(t.lower() in entry_tags for t in tags):
                    ids_to_remove.add(entry.id)
                    continue
            if contains and contains.lower() in entry.content.lower():
                ids_to_remove.add(entry.id)

        if not ids_to_remove:
            return ForgetResult(ok=True, removed=0, ids=[])

        lines = content.split("\n")
        filtered = []
        for line in lines:
            parsed = parse_entry_line(line)
            if parsed is not None and parsed.id in ids_to_remove:
                continue
            filtered.append(line)

        result_text = re.sub(r"\n{3,}", "\n\n", "\n".join(filtered)).rstrip()
        _write_file(abs_path, f"{result_text}\n" if result_text else "")
        return ForgetResult(ok=True, removed=len(ids_to_remove), ids=sorted(ids_to_remove))

    # ---- Consolidate ------------------------------------------------------

    def consolidate(
        self,
        *,
        before: str | None = None,
        min_importance: str = "normal",
        target_file: str = "memory/archive.md",
    ) -> dict:
        cutoff = before or (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        threshold = IMPORTANCE_ORDER.get(min_importance, 1)
        self._assert_writable(target_file)

        memory_dir = self.workspace_dir / "memory"
        if not memory_dir.is_dir():
            return {"merged": 0, "kept": 0, "removed_files": []}

        daily_re = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
        to_consolidate = sorted(
            [f for f in memory_dir.glob("*.md") if (m := daily_re.match(f.name)) and m.group(1) < cutoff]
        )

        if not to_consolidate:
            return {"merged": 0, "kept": 0, "removed_files": []}

        kept_entries: list[AuroraEntry] = []
        removed_files: list[str] = []

        for f in to_consolidate:
            raw = _read_file(f)
            for entry in _parse_all_entries(raw):
                if IMPORTANCE_ORDER.get(entry.importance, 0) >= threshold:
                    kept_entries.append(entry)
            f.unlink()
            removed_files.append(f"memory/{f.name}")

        if kept_entries:
            target_abs = self.workspace_dir / target_file
            existing = _read_file(target_abs)
            for entry in kept_entries:
                existing = _append_entry(existing, format_entry(entry))
            _write_file(target_abs, existing)

        return {"merged": len(to_consolidate), "kept": len(kept_entries), "removed_files": removed_files}

    # ---- Section helpers --------------------------------------------------

    def sections(self, file: str | None = None) -> list[AuroraSection]:
        rel_path = file or "MEMORY.md"
        abs_path = self.workspace_dir / rel_path
        content = _read_file(abs_path)
        return parse_sections(content)

    def list_sections(self, file: str | None = None) -> list[dict]:
        return [{"level": s.level, "title": s.title} for s in self.sections(file)]

    # ---- Helpers ----------------------------------------------------------

    def daily_file_path(self, now: datetime | None = None) -> str:
        dt = now or datetime.now(self.tz)
        date_str = dt.strftime("%Y-%m-%d")
        return f"memory/{date_str}.md"

    def _assert_writable(self, rel_path: str) -> None:
        basename = Path(rel_path).name.lower()
        if basename in READ_ONLY_FILES:
            raise ValueError(f"{rel_path} is read-only. Write to daily files (memory/YYYY-MM-DD.md) instead.")


# ---------------------------------------------------------------------------
# Entry formatting / parsing
# ---------------------------------------------------------------------------

def format_entry(entry: AuroraEntry) -> str:
    imp_part = f" {{{entry.importance}}}" if entry.importance != "normal" else ""
    tags_part = f" {' '.join(f'#{t}' for t in entry.tags)}" if entry.tags else ""
    return f"- [id:{entry.id}] **{entry.timestamp}**{imp_part} {entry.content}{tags_part}"


def parse_entry_line(line: str) -> AuroraEntry | None:
    m = ENTRY_RE.match(line)
    if not m:
        return None

    entry_id = m.group(1)
    timestamp = m.group(2)
    importance = m.group(3) if m.group(3) in IMPORTANCE_ORDER else "normal"
    rest = m.group(4)

    # Extract trailing #hashtag tokens
    tags: list[str] = []
    remaining = rest
    while True:
        tag_match = TRAILING_TAG_RE.search(remaining)
        if not tag_match:
            break
        tags.insert(0, tag_match.group(1)[1:])  # strip leading #
        remaining = remaining[: tag_match.start()].rstrip()

    return AuroraEntry(
        id=entry_id,
        timestamp=timestamp,
        content=remaining.strip(),
        tags=tags,
        importance=importance,
    )


def parse_sections(content: str) -> list[AuroraSection]:
    lines = content.split("\n")
    sections: list[AuroraSection] = []
    current: AuroraSection | None = None

    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            if current is not None:
                current.end_line = i - 1
                current.content = _trimmed_slice(lines, current.start_line, i - 1)
                sections.append(current)
            current = AuroraSection(
                level=len(m.group(1)),
                title=m.group(2).strip(),
                content="",
                start_line=i,
                end_line=i,
            )

    if current is not None:
        current.end_line = len(lines) - 1
        current.content = _trimmed_slice(lines, current.start_line, len(lines) - 1)
        sections.append(current)

    return sections


# ---------------------------------------------------------------------------
# Content ID
# ---------------------------------------------------------------------------

def content_id(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).lower().encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    return list({t.strip().lower() for t in tags if t.strip()})


def _merge_tags(a: list[str], b: list[str]) -> list[str]:
    return list({*a, *b})


def _max_importance(a: str, b: str) -> str:
    return a if IMPORTANCE_ORDER.get(a, 0) >= IMPORTANCE_ORDER.get(b, 0) else b


def _to_bigrams(text: str) -> set[str]:
    tokens = text.lower().split()
    bigrams: set[str] = set()
    for i in range(len(tokens) - 1):
        bigrams.add(f"{tokens[i]} {tokens[i + 1]}")
    # Single tokens for short texts
    if len(tokens) <= 3:
        bigrams.update(tokens)
    return bigrams


def _find_similar_entry(entries: list[AuroraEntry], new_content: str) -> AuroraEntry | None:
    new_bigrams = _to_bigrams(new_content)
    if not new_bigrams:
        return None

    best_match: AuroraEntry | None = None
    best_score = 0.0

    for entry in entries:
        existing_bigrams = _to_bigrams(entry.content)
        if not existing_bigrams:
            continue
        overlap = len(new_bigrams & existing_bigrams)
        score = (2 * overlap) / (len(new_bigrams) + len(existing_bigrams))
        if score > 0.8 and score > best_score:
            best_score = score
            best_match = entry

    return best_match


def _parse_all_entries(content: str) -> list[AuroraEntry]:
    if not content.strip():
        return []
    entries: list[AuroraEntry] = []
    for line in content.split("\n"):
        entry = parse_entry_line(line)
        if entry is not None:
            entries.append(entry)
    return entries


def _replace_entry(content: str, old_id: str, new_line: str) -> str:
    lines = content.split("\n")
    result = []
    for line in lines:
        entry = parse_entry_line(line)
        if entry is not None and entry.id == old_id:
            result.append(new_line)
        else:
            result.append(line)
    return "\n".join(result)


def _append_entry(content: str, entry_line: str) -> str:
    trimmed = content.rstrip()
    return f"{trimmed}\n{entry_line}\n" if trimmed else f"{entry_line}\n"


def _trimmed_slice(lines: list[str], start: int, end: int) -> str:
    while end > start and not lines[end].strip():
        end -= 1
    return "\n".join(lines[start : end + 1])


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
