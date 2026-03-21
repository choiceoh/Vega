"""Tests for aurora_md_manager — mirrors the TS test suite."""

import os
import tempfile
import shutil
from pathlib import Path

import pytest

from aurora_md_manager import (
    AuroraEntry,
    AuroraMdManager,
    content_id,
    format_entry,
    parse_entry_line,
    parse_sections,
    AuroraSection,
)


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp(prefix="aurora-test-")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def mgr(tmp_dir):
    return AuroraMdManager(tmp_dir, tz="UTC")


# ---------------------------------------------------------------------------
# Entry format round-trip
# ---------------------------------------------------------------------------

class TestFormatParseRoundTrip:
    def test_basic_entry(self):
        entry = AuroraEntry(
            id="abcd1234",
            timestamp="2026-03-21T10:00:00.000Z",
            content="Use TypeScript for the project",
            tags=[],
            importance="normal",
        )
        line = format_entry(entry)
        assert line == "- [id:abcd1234] **2026-03-21T10:00:00.000Z** Use TypeScript for the project"
        parsed = parse_entry_line(line)
        assert parsed == entry

    def test_entry_with_tags_and_importance(self):
        entry = AuroraEntry(
            id="ef567890",
            timestamp="2026-03-21T10:00:00.000Z",
            content="Deploy to production",
            tags=["ci", "deploy"],
            importance="high",
        )
        line = format_entry(entry)
        assert "#ci #deploy" in line
        assert "{high}" in line
        parsed = parse_entry_line(line)
        assert parsed == entry

    def test_non_entry_line_returns_none(self):
        assert parse_entry_line("# Some heading") is None
        assert parse_entry_line("plain text") is None
        assert parse_entry_line("") is None

    def test_critical_importance(self):
        entry = AuroraEntry(
            id="ff000001",
            timestamp="2026-03-21T12:00:00Z",
            content="System down",
            tags=["urgent"],
            importance="critical",
        )
        line = format_entry(entry)
        parsed = parse_entry_line(line)
        assert parsed.importance == "critical"
        assert parsed.tags == ["urgent"]


# ---------------------------------------------------------------------------
# Content ID
# ---------------------------------------------------------------------------

class TestContentId:
    def test_deterministic(self):
        assert content_id("hello world") == content_id("hello world")

    def test_case_insensitive(self):
        assert content_id("Hello World") == content_id("hello world")

    def test_whitespace_insensitive(self):
        assert content_id("hello  world") == content_id("hello world")

    def test_different_content(self):
        assert content_id("aaa") != content_id("bbb")

    def test_length(self):
        assert len(content_id("test")) == 8


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

class TestSave:
    def test_create_entry(self, mgr: AuroraMdManager, tmp_dir):
        result = mgr.save("Remember to update docs", tags=["docs"])
        assert result.ok
        assert result.action == "created"
        assert result.id
        assert result.file.startswith("memory/2026")

        # Verify file on disk
        files = list(Path(tmp_dir, "memory").glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "Remember to update docs" in content
        assert "#docs" in content

    def test_exact_duplicate(self, mgr: AuroraMdManager):
        r1 = mgr.save("Same content here")
        r2 = mgr.save("Same content here")
        assert r1.action == "created"
        assert r2.action == "duplicate"
        assert r1.id == r2.id

    def test_fuzzy_duplicate_upsert(self, mgr: AuroraMdManager):
        r1 = mgr.save("The deployment to production server needs to be done now", tags=["deploy"])
        r2 = mgr.save("The deployment to production server needs to be done today", tags=["ops"])
        assert r1.action == "created"
        assert r2.action == "updated"
        assert r2.entry.tags == ["deploy", "ops"]  # merged tags

    def test_empty_content(self, mgr: AuroraMdManager):
        result = mgr.save("")
        assert result.action == "duplicate"
        result2 = mgr.save("   ")
        assert result2.action == "duplicate"

    def test_explicit_file(self, mgr: AuroraMdManager, tmp_dir):
        result = mgr.save("Custom file entry", file="notes/custom.md")
        assert result.file == "notes/custom.md"
        assert (Path(tmp_dir) / "notes" / "custom.md").exists()

    def test_read_only_guard(self, mgr: AuroraMdManager):
        with pytest.raises(ValueError, match="read-only"):
            mgr.save("protected", file="memory.md")


# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------

class TestRecall:
    def test_recall_all_entries(self, mgr: AuroraMdManager):
        mgr.save("First entry", tags=["a"])
        mgr.save("Second entry", tags=["b"])
        result = mgr.recall()
        assert result.total == 2

    def test_recall_by_tag(self, mgr: AuroraMdManager):
        mgr.save("Important thing", tags=["urgent"])
        mgr.save("Normal thing", tags=["info"])
        result = mgr.recall(tags=["urgent"])
        assert result.total == 1
        assert result.entries[0].content == "Important thing"

    def test_recall_by_importance(self, mgr: AuroraMdManager):
        mgr.save("Low priority", importance="low")
        mgr.save("Critical issue", importance="critical")
        result = mgr.recall(min_importance="high")
        assert result.total == 1
        assert result.entries[0].importance == "critical"

    def test_recall_by_contains(self, mgr: AuroraMdManager):
        mgr.save("Deploy to staging")
        mgr.save("Fix login bug")
        result = mgr.recall(contains="deploy")
        assert result.total == 1

    def test_recall_with_limit(self, mgr: AuroraMdManager):
        for i in range(5):
            mgr.save(f"Entry {i}")
        result = mgr.recall(limit=2)
        assert result.total == 5
        assert len(result.entries) == 2


# ---------------------------------------------------------------------------
# RecallAll
# ---------------------------------------------------------------------------

class TestRecallAll:
    def test_cross_file_recall(self, mgr: AuroraMdManager, tmp_dir):
        # Write entries to different files
        mgr.save("Today entry", file="memory/2026-03-21.md", tags=["today"])
        mgr.save("Yesterday entry", file="memory/2026-03-20.md", tags=["yesterday"])

        result = mgr.recall_all()
        assert result["total"] == 2

    def test_recall_all_with_filter(self, mgr: AuroraMdManager, tmp_dir):
        mgr.save("Match this", file="memory/2026-03-21.md", tags=["findme"])
        mgr.save("Skip this", file="memory/2026-03-20.md", tags=["other"])

        result = mgr.recall_all(tags=["findme"])
        assert result["total"] == 1
        assert result["entries"][0]["content"] == "Match this"


# ---------------------------------------------------------------------------
# Forget
# ---------------------------------------------------------------------------

class TestForget:
    def test_forget_by_id(self, mgr: AuroraMdManager):
        r = mgr.save("To be removed")
        result = mgr.forget(ids=[r.id])
        assert result.ok
        assert result.removed == 1

    def test_forget_by_tag(self, mgr: AuroraMdManager):
        mgr.save("Keep this", tags=["keep"])
        mgr.save("Delete this", tags=["delete"])
        result = mgr.forget(tags=["delete"])
        assert result.removed == 1
        recall = mgr.recall()
        assert recall.total == 1

    def test_forget_by_content(self, mgr: AuroraMdManager):
        mgr.save("Important note")
        mgr.save("Trash item")
        result = mgr.forget(contains="Trash")
        assert result.removed == 1

    def test_forget_requires_filter(self, mgr: AuroraMdManager):
        result = mgr.forget()
        assert not result.ok
        assert "required" in result.reason

    def test_forget_nonexistent(self, mgr: AuroraMdManager):
        result = mgr.forget(ids=["nonexistent"])
        assert result.ok
        assert result.removed == 0


# ---------------------------------------------------------------------------
# Consolidate
# ---------------------------------------------------------------------------

class TestConsolidate:
    def test_consolidate_old_files(self, mgr: AuroraMdManager, tmp_dir):
        mem_dir = Path(tmp_dir) / "memory"
        mem_dir.mkdir(exist_ok=True)

        # Create old file with high importance
        old_file = mem_dir / "2026-01-01.md"
        old_file.write_text(
            "- [id:aabbcc01] **2026-01-01T00:00:00Z** {high} Old important entry #keep\n"
        )

        # Create old file with low importance (should be dropped)
        old_file2 = mem_dir / "2026-01-02.md"
        old_file2.write_text(
            "- [id:aabbcc02] **2026-01-02T00:00:00Z** {low} Old low entry #drop\n"
        )

        result = mgr.consolidate(before="2026-03-01", min_importance="normal")
        assert result["merged"] == 2
        assert result["kept"] == 1  # only high importance kept
        assert not old_file.exists()
        assert not old_file2.exists()

        # Check archive
        archive = Path(tmp_dir) / "memory" / "archive.md"
        assert archive.exists()
        assert "Old important entry" in archive.read_text()

    def test_consolidate_no_old_files(self, mgr: AuroraMdManager):
        result = mgr.consolidate(before="2020-01-01")
        assert result["merged"] == 0


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------

class TestSectionParsing:
    def test_parse_sections(self):
        content = """# Project Info

This is the project info.

## Team

- Alice
- Bob

### Contact
Email: test@example.com
"""
        sections = parse_sections(content)
        assert len(sections) == 3
        assert sections[0].level == 1
        assert sections[0].title == "Project Info"
        assert sections[1].level == 2
        assert sections[1].title == "Team"
        assert sections[2].level == 3
        assert sections[2].title == "Contact"

    def test_section_content(self):
        content = "# Heading\n\nSome body text\n"
        sections = parse_sections(content)
        assert len(sections) == 1
        assert "Some body text" in sections[0].content

    def test_list_sections(self, mgr: AuroraMdManager, tmp_dir):
        (Path(tmp_dir) / "MEMORY.md").write_text("# Section A\n\n## Section B\n\n")
        result = mgr.list_sections()
        assert len(result) == 2
        assert result[0]["title"] == "Section A"
        assert result[1]["level"] == 2


# ---------------------------------------------------------------------------
# Daily file path
# ---------------------------------------------------------------------------

class TestDailyFilePath:
    def test_returns_memory_path(self, mgr: AuroraMdManager):
        from datetime import datetime
        path = mgr.daily_file_path(datetime(2026, 3, 21))
        assert path == "memory/2026-03-21.md"

    def test_timezone(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        # 2026-03-21 02:00 UTC = 2026-03-21 11:00 KST
        mgr_kst = AuroraMdManager("/tmp", tz="Asia/Seoul")
        path = mgr_kst.daily_file_path(datetime(2026, 3, 21, 2, 0, tzinfo=ZoneInfo("UTC")))
        assert path == "memory/2026-03-21.md"
