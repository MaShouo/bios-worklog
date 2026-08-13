#!/usr/bin/env python3
"""Portable Markdown knowledge-base manager for the bios-worklog Agent Skill.

The script intentionally uses only the Python standard library. Markdown issue
files are the source of truth; generated indexes and state can be rebuilt.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple


VERSION = "1.0.0"
KB_KIND = "bios-worklog-knowledge-base"
# Keep machine-readable JSON usable when Windows inherits a legacy console code
# page (for example CP936). This is a no-op on UTF-8 terminals.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

VALID_STATUSES = {"investigating", "paused", "verifying", "solved"}
STATUS_LABELS = {
    "investigating": "调查中",
    "paused": "已暂停",
    "verifying": "验证中",
    "solved": "已解决",
}
VALID_CONFIDENCE = {"unknown", "hypothesis", "probable", "confirmed"}
META_ORDER = [
    "id",
    "project",
    "title",
    "status",
    "created",
    "updated",
    "resolved",
    "categories",
    "tags",
    "confidence",
]
REQUIRED_META = {"id", "project", "title", "status", "created", "updated"}
MARKER_NAMES = ("DESCRIPTION", "ENVIRONMENT", "REPRODUCTION", "CURRENT", "HISTORY", "FINAL", "RELATED")


class WorklogError(RuntimeError):
    """An expected, user-actionable worklog error."""


@dataclass
class Record:
    path: Path
    metadata: Dict[str, Any]
    body: str
    text: str


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now().astimezone().replace(second=0, microsecond=0).isoformat(timespec="minutes")


def display_time(value: Optional[str] = None) -> str:
    if value:
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def minutes_since(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        delta = datetime.now().astimezone() - parsed
        return max(0, int(delta.total_seconds() // 60))
    except (TypeError, ValueError):
        return None


def ensure_mapping(value: Any, label: str = "input") -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WorklogError(f"{label} 必须是 JSON 对象。")
    return dict(value)


def load_json_file(path_value: Optional[str]) -> Dict[str, Any]:
    if not path_value:
        return {}
    try:
        if path_value == "-":
            payload = json.load(sys.stdin)
        else:
            with Path(path_value).expanduser().open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise WorklogError(f"无法读取 JSON 输入 {path_value!r}: {exc}") from exc
    return ensure_mapping(payload)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise WorklogError(f"无法读取 JSON 文件 {path}: {exc}") from exc


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    temp_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            temp_name = handle.name
            handle.write(normalized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sanitize_markdown(value: Any) -> str:
    text = str(value or "").strip()
    # Managed markers must never be injectable through model-generated content.
    return text.replace("<!-- BIOS-WORKLOG:", "&lt;!-- BIOS-WORKLOG:")


def as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result: List[str] = []
        for item in value:
            text = sanitize_markdown(item)
            if text:
                result.append(text)
        return result
    text = sanitize_markdown(value)
    return [text] if text else []


def coalesce(data: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def format_value(value: Any, empty: str = "暂无。", numbered: bool = False) -> str:
    if value is None:
        return empty
    if isinstance(value, Mapping):
        rows = []
        for key, item in value.items():
            clean_key = sanitize_markdown(key)
            if isinstance(item, (list, tuple)):
                clean_item = "；".join(as_list(item))
            else:
                clean_item = sanitize_markdown(item)
            if clean_key or clean_item:
                rows.append(f"- **{clean_key or '项目'}**：{clean_item or '未记录'}")
        return "\n".join(rows) if rows else empty
    if isinstance(value, (list, tuple, set)):
        items = as_list(value)
        if not items:
            return empty
        if numbered:
            return "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1))
        return "\n".join(f"- {item}" for item in items)
    text = sanitize_markdown(value)
    return text or empty


def safe_slug(value: str, fallback: str, max_length: int = 72) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    chars: List[str] = []
    previous_dash = False
    for char in normalized:
        allowed = char.isalnum() or char in "._-"
        if allowed:
            chars.append(char.lower() if char.isascii() else char)
            previous_dash = False
        else:
            if not previous_dash:
                chars.append("-")
                previous_dash = True
    slug = "".join(chars).strip(" .-_")[:max_length].rstrip(" .-_")
    if not slug:
        slug = fallback
    reserved = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
    if slug.casefold() in reserved:
        slug = f"{slug}-item"
    return slug


def canonical_workspace(path_value: Optional[str]) -> str:
    path = Path(path_value).expanduser() if path_value else Path.cwd()
    try:
        path = path.resolve()
    except OSError:
        path = path.absolute()
    text = str(path)
    return os.path.normcase(text) if os.name == "nt" else text


def markdown_cell(value: Any) -> str:
    return sanitize_markdown(value).replace("|", "\\|").replace("\n", " ")


def normalize_rel_link(path: Path) -> str:
    return path.as_posix().replace(" ", "%20")


# ---------------------------------------------------------------------------
# Restricted YAML front matter (top-level JSON scalars and scalar lists)
# ---------------------------------------------------------------------------


def parse_scalar(raw: str) -> Any:
    raw = raw.strip()
    if raw == "":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        lowered = raw.casefold()
        if lowered == "null":
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return raw.strip("\"'")


def parse_frontmatter(text: str, source: str = "record") -> Tuple[Dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        raise WorklogError(f"{source} 缺少 YAML front matter。")
    try:
        closing = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise WorklogError(f"{source} 的 YAML front matter 未闭合。") from exc

    metadata: Dict[str, Any] = {}
    current_list_key: Optional[str] = None
    for line_number, line in enumerate(lines[1:closing], 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if current_list_key is None:
                raise WorklogError(f"{source}:{line_number} 出现无归属的列表项。")
            metadata.setdefault(current_list_key, []).append(parse_scalar(line[4:]))
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if not match:
            raise WorklogError(f"{source}:{line_number} 含不支持的 front matter 格式。")
        key, raw = match.group(1), match.group(2) or ""
        value = parse_scalar(raw)
        if raw.strip() == "":
            value = []
            current_list_key = key
        else:
            current_list_key = None
        metadata[key] = value

    body = "\n".join(lines[closing + 1 :]).lstrip("\n")
    return metadata, body


def dump_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def dump_frontmatter(metadata: Mapping[str, Any]) -> str:
    keys = [key for key in META_ORDER if key in metadata]
    keys.extend(sorted(key for key in metadata if key not in keys))
    lines = ["---"]
    for key in keys:
        value = metadata[key]
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.extend(f"  - {dump_scalar(item)}" for item in value)
        elif isinstance(value, Mapping):
            # Nested maps are deliberately serialized as one JSON scalar.
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}")
        else:
            lines.append(f"{key}: {dump_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def compose_document(metadata: Mapping[str, Any], body: str) -> str:
    return f"{dump_frontmatter(metadata)}\n\n{body.strip()}\n"


# ---------------------------------------------------------------------------
# Managed Markdown regions
# ---------------------------------------------------------------------------


def marker_start(name: str) -> str:
    return f"<!-- BIOS-WORKLOG:{name}:START -->"


def marker_end(name: str) -> str:
    return f"<!-- BIOS-WORKLOG:{name}:END -->"


def extract_marker(body: str, name: str) -> str:
    start, end = marker_start(name), marker_end(name)
    start_index = body.find(start)
    end_index = body.find(end)
    if start_index < 0 or end_index < 0 or end_index < start_index:
        raise WorklogError(f"问题记录缺少受管理区域 {name}。请先运行 validate 检查文件。")
    return body[start_index + len(start) : end_index].strip()


def replace_marker(body: str, name: str, new_content: str) -> str:
    start, end = marker_start(name), marker_end(name)
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{start}\n{new_content.strip()}\n{end}"
    updated, count = pattern.subn(lambda _: replacement, body, count=1)
    if count != 1:
        raise WorklogError(f"问题记录中的受管理区域 {name} 缺失或重复。")
    return updated


def append_marker(body: str, name: str, new_content: str) -> str:
    existing = extract_marker(body, name)
    combined = f"{existing}\n\n---\n\n{new_content.strip()}" if existing else new_content.strip()
    return replace_marker(body, name, combined)


def parse_level_three_sections(content: str) -> Tuple[str, Dict[str, str], List[str]]:
    matches = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", content))
    if not matches:
        return content.strip(), {}, []
    preface = content[: matches[0].start()].strip()
    sections: Dict[str, str] = {}
    order: List[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        title = match.group(1).strip()
        sections[title] = content[start:end].strip()
        order.append(title)
    return preface, sections, order


def render_current_state(data: Mapping[str, Any], existing: Optional[str] = None) -> str:
    existing_sections: Dict[str, str] = {}
    if existing:
        _, existing_sections, _ = parse_level_three_sections(existing)

    current = ensure_mapping(data.get("current_state"), "current_state") if "current_state" in data else {}

    def select(keys: Sequence[str], heading: str, fallback: Any = None) -> Any:
        for source in (current, data):
            for key in keys:
                if key in source:
                    return source[key]
        if heading in existing_sections:
            return existing_sections[heading]
        return fallback

    facts = select(("confirmed_facts", "facts"), "已确认事实", [])
    assessment = select(("current_assessment", "assessment", "current_judgment"), "当前判断", "尚未形成明确判断。")
    unknowns = select(("unknowns", "unconfirmed"), "尚未确认", [])
    next_steps = select(("next_steps",), "下一步", [])

    return "\n\n".join(
        [
            f"### 已确认事实\n\n{format_value(facts)}",
            f"### 当前判断\n\n{format_value(assessment, '尚未形成明确判断。')}",
            f"### 尚未确认\n\n{format_value(unknowns)}",
            f"### 下一步\n\n{format_value(next_steps, numbered=True)}",
        ]
    )


def render_checkpoint(data: Mapping[str, Any], default_title: str = "调查检查点", kind: Optional[str] = None) -> str:
    title = sanitize_markdown(coalesce(data, "title", "checkpoint_title", default=default_title)) or default_title
    timestamp = sanitize_markdown(data.get("timestamp")) or display_time()
    sections: List[Tuple[str, Any, str]] = [
        ("目的", coalesce(data, "purpose", "goal"), "normal"),
        ("操作", coalesce(data, "actions", "operations", "steps_taken"), "normal"),
        ("结果", coalesce(data, "result", "outcome"), "normal"),
        ("得到的信息", coalesce(data, "findings", "learned", "information_gained"), "normal"),
        ("证据与参考", coalesce(data, "evidence", "references"), "normal"),
        ("对当前判断的影响", coalesce(data, "impact", "assessment_impact"), "normal"),
        ("下一步", coalesce(data, "next_steps"), "numbered"),
    ]
    rendered = [f"### {timestamp} — {title}"]
    if kind:
        rendered.append(f"**记录类型**：{sanitize_markdown(kind)}")
    for heading, value, style in sections:
        if value is None or value == [] or value == "":
            continue
        rendered.append(f"#### {heading}\n\n{format_value(value, numbered=style == 'numbered')}")
    if len(rendered) == 1 or (len(rendered) == 2 and kind):
        rendered.append("#### 结果\n\n已保存当前调查状态。")
    return "\n\n".join(rendered)


def render_final(data: Mapping[str, Any]) -> str:
    fields = [
        ("根因", coalesce(data, "root_cause", "rootCause"), "尚未确认。"),
        ("解决方法", coalesce(data, "solution", "resolution"), "尚未解决。"),
        ("修改文件", coalesce(data, "changed_files", "files_changed"), "未记录。"),
        ("修改原理", coalesce(data, "principle", "rationale"), "未记录。"),
        ("验证结果", coalesce(data, "validation", "verification"), "尚未验证。"),
        ("回归范围", coalesce(data, "regression_scope", "regression"), "尚未确定。"),
        ("已知风险", coalesce(data, "known_risks", "risks"), "暂无已知风险。"),
        ("可复用经验", coalesce(data, "reusable_lessons", "lessons"), "尚未总结。"),
    ]
    return "\n\n".join(f"### {heading}\n\n{format_value(value, empty)}" for heading, value, empty in fields)


def render_related(value: Any) -> str:
    items = as_list(value)
    return "\n".join(f"- {item}" for item in items) if items else "暂无。"


def render_issue_body(issue_id: str, title: str, data: Mapping[str, Any]) -> str:
    description = coalesce(data, "description", "problem", default="待补充。")
    environment = coalesce(data, "environment", "env", default={})
    reproduction = coalesce(data, "reproduction", "reproduction_steps", default=[])
    current = render_current_state(data)

    initial = ensure_mapping(data.get("initial_checkpoint"), "initial_checkpoint") if data.get("initial_checkpoint") else {}
    if not initial:
        initial = {
            "title": "创建问题",
            "purpose": "建立问题记录并保存初始调查上下文。",
            "result": description,
            "findings": coalesce(data, "confirmed_facts", "facts"),
            "impact": coalesce(data, "current_assessment", "assessment"),
            "next_steps": coalesce(data, "next_steps"),
        }
    history = render_checkpoint(initial, default_title="创建问题", kind="创建")

    final = render_final({})
    related = render_related(coalesce(data, "related_issues", "related"))
    return f"""# {issue_id}：{sanitize_markdown(title)}

## 问题描述

{marker_start('DESCRIPTION')}
{format_value(description, '待补充。')}
{marker_end('DESCRIPTION')}

## 环境

{marker_start('ENVIRONMENT')}
{format_value(environment)}
{marker_end('ENVIRONMENT')}

## 复现步骤

{marker_start('REPRODUCTION')}
{format_value(reproduction, numbered=True)}
{marker_end('REPRODUCTION')}

## 当前状态

{marker_start('CURRENT')}
{current}
{marker_end('CURRENT')}

## 调查记录

{marker_start('HISTORY')}
{history}
{marker_end('HISTORY')}

## 最终结论

{marker_start('FINAL')}
{final}
{marker_end('FINAL')}

## 相关记录

{marker_start('RELATED')}
{related}
{marker_end('RELATED')}
""".strip()


def extract_history_entries(history: str) -> List[str]:
    matches = list(re.finditer(r"(?m)^###\s+", history))
    if not matches:
        return [history.strip()] if history.strip() else []
    entries: List[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(history)
        entry = history[match.start() : end].strip().strip("-").strip()
        if entry:
            entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------


class KnowledgeBase:
    def __init__(self, root: Path, workspace: Optional[str] = None) -> None:
        self.root = root.expanduser().resolve()
        self.workspace = canonical_workspace(workspace)
        self.control_dir = self.root / ".bios-worklog"
        self.internal_config_path = self.control_dir / "config.json"
        self.state_path = self.control_dir / "state.json"
        self.projects_dir = self.root / "projects"

    def assert_initialized(self) -> None:
        config = load_json(self.internal_config_path, {})
        if not isinstance(config, dict) or config.get("kind") != KB_KIND:
            raise WorklogError(
                f"{self.root} 不是已初始化的 BIOS worklog 知识库。"
                "请先执行 init <目录>。"
            )

    def config(self) -> Dict[str, Any]:
        self.assert_initialized()
        value = load_json(self.internal_config_path, {})
        return ensure_mapping(value, "knowledge-base config")

    @contextmanager
    def write_lock(self, timeout_seconds: float = 10.0) -> Iterator[None]:
        self.control_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.control_dir / "write.lock"
        deadline = time.monotonic() + timeout_seconds
        token = json.dumps({"pid": os.getpid(), "created": now_iso()})
        while True:
            try:
                descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(token)
                break
            except FileExistsError:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                    if age > 300:
                        lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise WorklogError(f"知识库正被其他进程写入：{lock_path}")
                time.sleep(0.1)
        try:
            yield
        finally:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    def read_record(self, path: Path) -> Record:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise WorklogError(f"无法读取问题记录 {path}: {exc}") from exc
        metadata, body = parse_frontmatter(text, str(path))
        return Record(path=path, metadata=metadata, body=body, text=text)

    def scan_records(self) -> Tuple[List[Record], List[Dict[str, str]]]:
        records: List[Record] = []
        errors: List[Dict[str, str]] = []
        if not self.projects_dir.exists():
            return records, errors
        for path in sorted(self.projects_dir.glob("*/issues/*.md")):
            try:
                records.append(self.read_record(path))
            except WorklogError as exc:
                errors.append({"path": str(path), "error": str(exc)})
        return records, errors

    def find_issue(self, issue_id: str) -> Record:
        target = issue_id.strip().casefold()
        records, _ = self.scan_records()
        exact = [record for record in records if str(record.metadata.get("id", "")).casefold() == target]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise WorklogError(f"检测到重复问题 ID：{issue_id}。请运行 validate。")
        raise WorklogError(f"未找到问题：{issue_id}")

    def load_state(self) -> Dict[str, Any]:
        raw = load_json(self.state_path, {"version": 1, "workspaces": {}})
        state = ensure_mapping(raw, "state")
        if not isinstance(state.get("workspaces"), dict):
            state["workspaces"] = {}
        state.setdefault("version", 1)
        return state

    def save_state(self, state: Mapping[str, Any]) -> None:
        atomic_write_json(self.state_path, dict(state))

    def set_active(self, record: Record) -> None:
        state = self.load_state()
        workspaces = ensure_mapping(state.get("workspaces"), "state.workspaces")
        relative = record.path.relative_to(self.root).as_posix()
        entry = {
            "id": record.metadata.get("id"),
            "project": record.metadata.get("project"),
            "path": relative,
            "updated": now_iso(),
        }
        workspaces[self.workspace] = entry
        state["workspaces"] = workspaces
        state["lastActive"] = entry
        state["lastWorkspace"] = self.workspace
        self.save_state(state)

    def clear_active(self, issue_id: str) -> None:
        state = self.load_state()
        workspaces = ensure_mapping(state.get("workspaces"), "state.workspaces")
        current = workspaces.get(self.workspace)
        if isinstance(current, dict) and str(current.get("id", "")).casefold() == issue_id.casefold():
            workspaces.pop(self.workspace, None)
        state["workspaces"] = workspaces
        last = state.get("lastActive")
        if isinstance(last, dict) and str(last.get("id", "")).casefold() == issue_id.casefold():
            state.pop("lastActive", None)
            state.pop("lastWorkspace", None)
        self.save_state(state)

    def active_issue_id(self) -> Optional[str]:
        state = self.load_state()
        workspaces = state.get("workspaces", {})
        current = workspaces.get(self.workspace) if isinstance(workspaces, dict) else None
        if isinstance(current, dict) and current.get("id"):
            return str(current["id"])
        last = state.get("lastActive")
        if isinstance(last, dict) and last.get("id"):
            return str(last["id"])
        return None

    def resolve_issue(self, issue_id: Optional[str] = None, allow_single_open: bool = True) -> Record:
        if issue_id:
            return self.find_issue(issue_id)
        active = self.active_issue_id()
        if active:
            try:
                return self.find_issue(active)
            except WorklogError:
                pass
        if allow_single_open:
            records, _ = self.scan_records()
            open_records = [record for record in records if record.metadata.get("status") != "solved"]
            if len(open_records) == 1:
                return open_records[0]
            if len(open_records) > 1:
                choices = ", ".join(str(record.metadata.get("id")) for record in open_records[:8])
                raise WorklogError(f"存在多个未解决问题，请指定 ID：{choices}")
        raise WorklogError("当前工作区没有活动问题。请先 start 或 resume <ID>。")

    def next_issue_id(self) -> str:
        prefix = datetime.now().astimezone().strftime("BIOS-%Y%m%d-")
        records, _ = self.scan_records()
        numbers: List[int] = []
        pattern = re.compile(rf"^{re.escape(prefix)}(\d{{3,}})$", re.IGNORECASE)
        for record in records:
            match = pattern.match(str(record.metadata.get("id", "")))
            if match:
                numbers.append(int(match.group(1)))
        return f"{prefix}{(max(numbers, default=0) + 1):03d}"

    def project_directory(self, project: str) -> Path:
        slug = safe_slug(project, "project")
        candidate = self.projects_dir / slug
        # A deterministic slug normally identifies the project. Guard against a
        # pre-existing directory that belongs to a differently named project.
        index_meta = candidate / ".project.json"
        if index_meta.exists():
            existing = load_json(index_meta, {})
            if isinstance(existing, dict) and existing.get("name") not in (None, project):
                suffix = safe_slug(project, "project", 16)
                candidate = self.projects_dir / f"{slug}-{suffix}"
                index_meta = candidate / ".project.json"
        candidate.mkdir(parents=True, exist_ok=True)
        (candidate / "issues").mkdir(parents=True, exist_ok=True)
        if not index_meta.exists():
            atomic_write_json(index_meta, {"name": project, "created": now_iso()})
        return candidate

    def write_record(self, record: Record) -> None:
        atomic_write_text(record.path, compose_document(record.metadata, record.body))

    def create_issue(self, project: str, title: str, data: Mapping[str, Any]) -> Dict[str, Any]:
        project = sanitize_markdown(project)
        title = sanitize_markdown(title)
        if not project:
            raise WorklogError("start 需要项目名称。")
        if not title:
            raise WorklogError("start 需要问题标题。")
        self.assert_initialized()
        with self.write_lock():
            issue_id = self.next_issue_id()
            project_dir = self.project_directory(project)
            filename = f"{issue_id}-{safe_slug(title, 'issue')}.md"
            issue_path = project_dir / "issues" / filename
            if issue_path.exists():
                raise WorklogError(f"问题文件已存在：{issue_path}")
            timestamp = now_iso()
            categories = as_list(coalesce(data, "categories", "category"))
            tags = as_list(data.get("tags"))
            confidence = sanitize_markdown(data.get("confidence")) or "unknown"
            if confidence not in VALID_CONFIDENCE:
                confidence = "unknown"
            status = sanitize_markdown(data.get("status")) or "investigating"
            if status not in VALID_STATUSES or status == "solved":
                status = "investigating"
            metadata: Dict[str, Any] = {
                "id": issue_id,
                "project": project,
                "title": title,
                "status": status,
                "created": timestamp,
                "updated": timestamp,
                "categories": categories,
                "tags": tags,
                "confidence": confidence,
            }
            body = render_issue_body(issue_id, title, data)
            record = Record(issue_path, metadata, body, compose_document(metadata, body))
            self.write_record(record)
            self.set_active(record)
            warnings = self.reindex_unlocked()
        return {
            "message": "已创建 BIOS 问题记录。",
            "id": issue_id,
            "project": project,
            "title": title,
            "status": status,
            "path": str(issue_path),
            "warnings": warnings,
        }

    def _apply_state_update(self, body: str, data: Mapping[str, Any]) -> str:
        existing = extract_marker(body, "CURRENT")
        state_data = dict(data)
        current = ensure_mapping(data.get("current_state"), "current_state") if data.get("current_state") is not None else {}
        if "next_steps" in data and "next_steps" not in current:
            current["next_steps"] = data["next_steps"]
        if current:
            state_data["current_state"] = current
        return replace_marker(body, "CURRENT", render_current_state(state_data, existing=existing))

    def _checkpoint_unlocked(
        self,
        record: Record,
        data: Mapping[str, Any],
        default_title: str,
        kind: str,
        forced_status: Optional[str] = None,
    ) -> Record:
        status = str(record.metadata.get("status", "investigating"))
        if status == "solved":
            raise WorklogError("已解决的问题不能直接添加检查点；请先执行 reopen。")
        checkpoint = render_checkpoint(data, default_title=default_title, kind=kind)
        body = append_marker(record.body, "HISTORY", checkpoint)
        body = self._apply_state_update(body, data)
        metadata = dict(record.metadata)
        timestamp = now_iso()
        metadata["updated"] = timestamp
        requested_status = forced_status or sanitize_markdown(data.get("status"))
        if requested_status:
            if requested_status not in VALID_STATUSES or requested_status == "solved":
                raise WorklogError(f"检查点状态无效：{requested_status}")
            metadata["status"] = requested_status
        elif status == "paused":
            metadata["status"] = "investigating"
        for source_key, meta_key in (("categories", "categories"), ("category", "categories"), ("tags", "tags")):
            if source_key in data:
                metadata[meta_key] = as_list(data[source_key])
        if data.get("confidence") is not None:
            confidence = sanitize_markdown(data.get("confidence"))
            if confidence not in VALID_CONFIDENCE:
                raise WorklogError(f"confidence 无效：{confidence}")
            metadata["confidence"] = confidence
        updated = Record(record.path, metadata, body, compose_document(metadata, body))
        self.write_record(updated)
        self.set_active(updated)
        return updated

    def checkpoint(self, issue_id: Optional[str], data: Mapping[str, Any]) -> Dict[str, Any]:
        self.assert_initialized()
        with self.write_lock():
            record = self.resolve_issue(issue_id)
            updated = self._checkpoint_unlocked(record, data, "调查检查点", "检查点")
            warnings = self.reindex_unlocked()
        return {
            "message": "已把检查点追加到当前问题记录。",
            "id": updated.metadata.get("id"),
            "status": updated.metadata.get("status"),
            "updated": updated.metadata.get("updated"),
            "path": str(updated.path),
            "warnings": warnings,
        }

    def pause(self, issue_id: Optional[str], data: Mapping[str, Any]) -> Dict[str, Any]:
        self.assert_initialized()
        payload = dict(data)
        payload.setdefault("title", "暂停调查")
        payload.setdefault("result", "保存当前调查状态，等待后续恢复。")
        with self.write_lock():
            record = self.resolve_issue(issue_id)
            updated = self._checkpoint_unlocked(record, payload, "暂停调查", "暂停", forced_status="paused")
            warnings = self.reindex_unlocked()
        return {
            "message": "已保存暂停检查点。",
            "id": updated.metadata.get("id"),
            "status": "paused",
            "path": str(updated.path),
            "warnings": warnings,
        }

    def build_context(self, record: Record, recent: int = 3) -> str:
        recent = max(1, min(recent, 20))
        history = extract_marker(record.body, "HISTORY")
        entries = extract_history_entries(history)[-recent:]
        metadata = record.metadata
        categories = "、".join(as_list(metadata.get("categories"))) or "未分类"
        parts = [
            f"# 恢复问题 {metadata.get('id')}：{metadata.get('title')}",
            "## 记录信息\n\n"
            f"- 项目：{metadata.get('project')}\n"
            f"- 状态：{STATUS_LABELS.get(str(metadata.get('status')), metadata.get('status'))}\n"
            f"- 分类：{categories}\n"
            f"- 最后更新：{metadata.get('updated')}",
            f"## 问题描述\n\n{extract_marker(record.body, 'DESCRIPTION')}",
            f"## 环境\n\n{extract_marker(record.body, 'ENVIRONMENT')}",
            f"## 复现步骤\n\n{extract_marker(record.body, 'REPRODUCTION')}",
            f"## 当前状态\n\n{extract_marker(record.body, 'CURRENT')}",
        ]
        if entries:
            parts.append("## 最近调查记录\n\n" + "\n\n---\n\n".join(entries))
        if metadata.get("status") == "solved":
            parts.append(f"## 最终结论\n\n{extract_marker(record.body, 'FINAL')}")
        parts.append(f"## 原始记录\n\n`{record.path}`")
        return "\n\n".join(parts)

    def context(self, issue_id: Optional[str], recent: int) -> Dict[str, Any]:
        self.assert_initialized()
        record = self.resolve_issue(issue_id)
        return {
            "message": "已生成问题恢复上下文。",
            "id": record.metadata.get("id"),
            "metadata": record.metadata,
            "path": str(record.path),
            "context": self.build_context(record, recent=recent),
        }

    def resume(self, issue_id: Optional[str], recent: int, record_event: bool = True) -> Dict[str, Any]:
        self.assert_initialized()
        with self.write_lock():
            record = self.resolve_issue(issue_id)
            if record.metadata.get("status") == "solved":
                raise WorklogError("该问题已解决。如需继续调查，请先执行 reopen。")
            metadata = dict(record.metadata)
            body = record.body
            if metadata.get("status") == "paused":
                metadata["status"] = "investigating"
            metadata["updated"] = now_iso()
            if record_event:
                event = render_checkpoint(
                    {
                        "title": "恢复调查",
                        "result": "在新的工作上下文中恢复该问题。",
                    },
                    default_title="恢复调查",
                    kind="恢复",
                )
                body = append_marker(body, "HISTORY", event)
            updated = Record(record.path, metadata, body, compose_document(metadata, body))
            self.write_record(updated)
            self.set_active(updated)
            warnings = self.reindex_unlocked()
            context = self.build_context(updated, recent=recent)
        return {
            "message": "已恢复问题并设为当前活动问题。",
            "id": updated.metadata.get("id"),
            "status": updated.metadata.get("status"),
            "path": str(updated.path),
            "context": context,
            "warnings": warnings,
        }

    def solve(self, issue_id: Optional[str], data: Mapping[str, Any]) -> Dict[str, Any]:
        self.assert_initialized()
        root_cause = coalesce(data, "root_cause", "rootCause")
        solution = coalesce(data, "solution", "resolution")
        validation = coalesce(data, "validation", "verification")
        missing = [name for name, value in (("root_cause", root_cause), ("solution", solution), ("validation", validation)) if not value]
        if missing:
            raise WorklogError("solve 缺少必填字段：" + ", ".join(missing))
        with self.write_lock():
            record = self.resolve_issue(issue_id)
            if record.metadata.get("status") == "solved":
                raise WorklogError("该问题已经是 solved 状态。")
            body = replace_marker(record.body, "FINAL", render_final(data))
            if "related_issues" in data or "related" in data:
                body = replace_marker(body, "RELATED", render_related(coalesce(data, "related_issues", "related")))
            closing_data = {
                "title": sanitize_markdown(data.get("checkpoint_title")) or "问题结案",
                "purpose": "记录最终根因、解决方法和验证结果。",
                "result": root_cause,
                "findings": solution,
                "evidence": validation,
                "impact": coalesce(data, "reusable_lessons", "lessons"),
                "next_steps": coalesce(data, "follow_up", "next_steps"),
            }
            body = append_marker(body, "HISTORY", render_checkpoint(closing_data, "问题结案", "结案"))
            state_payload: Dict[str, Any] = {}
            if data.get("current_state") is not None:
                state_payload["current_state"] = data["current_state"]
            else:
                state_payload["current_state"] = {
                    "current_assessment": f"已确认根因：{sanitize_markdown(root_cause)}",
                    "unknowns": [],
                    "next_steps": coalesce(data, "follow_up", "next_steps", default=[]),
                }
            body = self._apply_state_update(body, state_payload)
            metadata = dict(record.metadata)
            timestamp = now_iso()
            confidence = sanitize_markdown(data.get("confidence")) or "confirmed"
            if confidence not in VALID_CONFIDENCE:
                raise WorklogError(f"confidence 无效：{confidence}")
            metadata.update(
                {
                    "status": "solved",
                    "confidence": confidence,
                    "updated": timestamp,
                    "resolved": timestamp,
                }
            )
            updated = Record(record.path, metadata, body, compose_document(metadata, body))
            self.write_record(updated)
            self.clear_active(str(metadata.get("id")))
            warnings = self.reindex_unlocked()
        return {
            "message": "问题已结案并标记为 solved。",
            "id": updated.metadata.get("id"),
            "status": "solved",
            "resolved": updated.metadata.get("resolved"),
            "path": str(updated.path),
            "warnings": warnings,
        }

    def reopen(self, issue_id: Optional[str], data: Mapping[str, Any]) -> Dict[str, Any]:
        self.assert_initialized()
        with self.write_lock():
            record = self.resolve_issue(issue_id, allow_single_open=False)
            if record.metadata.get("status") != "solved":
                raise WorklogError("reopen 只能用于已解决的问题。")
            payload = dict(data)
            payload.setdefault("title", "重新打开问题")
            payload.setdefault("result", coalesce(data, "reason", default="问题再次出现，需要继续调查。"))
            body = append_marker(record.body, "HISTORY", render_checkpoint(payload, "重新打开问题", "重新打开"))
            body = self._apply_state_update(body, payload)
            previous_final = extract_marker(body, "FINAL")
            warning = "> ⚠️ 此问题已重新打开；以下内容是上一次结案结论，需要重新验证。"
            if not previous_final.startswith("> ⚠️"):
                body = replace_marker(body, "FINAL", f"{warning}\n\n{previous_final}")
            metadata = dict(record.metadata)
            metadata["status"] = "investigating"
            metadata["confidence"] = sanitize_markdown(data.get("confidence")) or "hypothesis"
            metadata["updated"] = now_iso()
            metadata.pop("resolved", None)
            updated = Record(record.path, metadata, body, compose_document(metadata, body))
            self.write_record(updated)
            self.set_active(updated)
            warnings = self.reindex_unlocked()
        return {
            "message": "已重新打开问题并设为当前活动问题。",
            "id": updated.metadata.get("id"),
            "status": "investigating",
            "path": str(updated.path),
            "warnings": warnings,
        }

    def list_records(self, project: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
        self.assert_initialized()
        records, errors = self.scan_records()
        filtered = []
        for record in records:
            meta = record.metadata
            if project and str(meta.get("project", "")).casefold() != project.casefold():
                continue
            if status and str(meta.get("status", "")).casefold() != status.casefold():
                continue
            filtered.append(self.summary(record))
        filtered.sort(key=lambda item: str(item.get("updated", "")), reverse=True)
        return {
            "message": f"找到 {len(filtered)} 条问题记录。",
            "count": len(filtered),
            "issues": filtered,
            "errors": errors,
        }

    def summary(self, record: Record) -> Dict[str, Any]:
        return {
            "id": record.metadata.get("id"),
            "project": record.metadata.get("project"),
            "title": record.metadata.get("title"),
            "status": record.metadata.get("status"),
            "statusLabel": STATUS_LABELS.get(str(record.metadata.get("status")), record.metadata.get("status")),
            "updated": record.metadata.get("updated"),
            "categories": as_list(record.metadata.get("categories")),
            "tags": as_list(record.metadata.get("tags")),
            "path": str(record.path),
        }

    def search(self, query: str, project: Optional[str], status: Optional[str], limit: int) -> Dict[str, Any]:
        self.assert_initialized()
        query_project, query_status, query_category, query_tag, terms = self._parse_search_query(query)
        project = project or query_project
        status = status or query_status
        records, errors = self.scan_records()
        matches: List[Tuple[int, Record, List[str]]] = []
        for record in records:
            meta = record.metadata
            if project and str(meta.get("project", "")).casefold() != project.casefold():
                continue
            if status and str(meta.get("status", "")).casefold() != status.casefold():
                continue
            categories = as_list(meta.get("categories"))
            tags = as_list(meta.get("tags"))
            if query_category and not any(query_category.casefold() in item.casefold() for item in categories):
                continue
            if query_tag and not any(query_tag.casefold() in item.casefold() for item in tags):
                continue
            title_blob = " ".join(
                [str(meta.get("id", "")), str(meta.get("title", "")), str(meta.get("project", "")), " ".join(categories), " ".join(tags)]
            ).casefold()
            body_blob = record.body.casefold()
            score = 0
            reasons: List[str] = []
            for term in terms:
                folded = term.casefold()
                if folded in title_blob:
                    score += 8
                    reasons.append(term)
                elif folded in body_blob:
                    score += 2
                    reasons.append(term)
                else:
                    score = -1
                    break
            if not terms:
                score = 1
            if score >= 0:
                matches.append((score, record, reasons))
        matches.sort(key=lambda item: (item[0], str(item[1].metadata.get("updated", ""))), reverse=True)
        results = []
        for score, record, reasons in matches[: max(1, min(limit, 100))]:
            item = self.summary(record)
            item.update({"score": score, "matched": sorted(set(reasons))})
            results.append(item)
        return {
            "message": f"搜索到 {len(results)} 条相关问题。",
            "query": query,
            "count": len(results),
            "issues": results,
            "errors": errors,
        }

    @staticmethod
    def _parse_search_query(query: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], List[str]]:
        try:
            tokens = shlex.split(query)
        except ValueError:
            tokens = query.split()
        filters: Dict[str, str] = {}
        terms: List[str] = []
        for token in tokens:
            if ":" in token:
                key, value = token.split(":", 1)
                if key.casefold() in {"project", "status", "category", "tag"} and value:
                    filters[key.casefold()] = value
                    continue
            terms.append(token)
        return filters.get("project"), filters.get("status"), filters.get("category"), filters.get("tag"), terms

    def status(self, issue_id: Optional[str]) -> Dict[str, Any]:
        self.assert_initialized()
        try:
            record = self.resolve_issue(issue_id, allow_single_open=False)
        except WorklogError:
            if issue_id:
                raise
            config = self.config()
            return {
                "message": "当前工作区没有活动问题。",
                "active": False,
                "workspace": self.workspace,
                "reminderMinutes": int(config.get("reminderMinutes", 45)),
                "checkpointRecommended": False,
            }
        config = self.config()
        reminder = int(config.get("reminderMinutes", 45))
        elapsed = minutes_since(record.metadata.get("updated"))
        recommended = bool(record.metadata.get("status") != "solved" and elapsed is not None and elapsed >= reminder)
        result = self.summary(record)
        result.update(
            {
                "message": "已读取当前问题状态。",
                "active": True,
                "workspace": self.workspace,
                "minutesSinceCheckpoint": elapsed,
                "reminderMinutes": reminder,
                "checkpointRecommended": recommended,
            }
        )
        return result

    def validate(self) -> Dict[str, Any]:
        self.assert_initialized()
        records, parse_errors = self.scan_records()
        issues: List[Dict[str, str]] = list(parse_errors)
        seen: Dict[str, str] = {}
        for record in records:
            meta = record.metadata
            for key in sorted(REQUIRED_META - set(meta)):
                issues.append({"path": str(record.path), "error": f"缺少 metadata 字段：{key}"})
            issue_id = str(meta.get("id", ""))
            if issue_id:
                folded = issue_id.casefold()
                if folded in seen:
                    issues.append({"path": str(record.path), "error": f"重复 ID；首次出现于 {seen[folded]}"})
                else:
                    seen[folded] = str(record.path)
            if meta.get("status") not in VALID_STATUSES:
                issues.append({"path": str(record.path), "error": f"无效 status：{meta.get('status')}"})
            for marker in MARKER_NAMES:
                start_count = record.body.count(marker_start(marker))
                end_count = record.body.count(marker_end(marker))
                if start_count != 1 or end_count != 1:
                    issues.append(
                        {
                            "path": str(record.path),
                            "error": f"受管理区域 {marker} 标记数量异常：START={start_count}, END={end_count}",
                        }
                    )
                    continue
                try:
                    extract_marker(record.body, marker)
                except WorklogError as exc:
                    issues.append({"path": str(record.path), "error": str(exc)})
        return {
            "message": "知识库校验通过。" if not issues else f"知识库发现 {len(issues)} 个问题。",
            "valid": not issues,
            "recordCount": len(records),
            "issues": issues,
        }

    def reindex(self) -> Dict[str, Any]:
        self.assert_initialized()
        with self.write_lock():
            warnings = self.reindex_unlocked()
        records, _ = self.scan_records()
        return {
            "message": "已重新生成总目录和项目目录。",
            "recordCount": len(records),
            "path": str(self.root / "INDEX.md"),
            "warnings": warnings,
        }

    def reindex_unlocked(self) -> List[Dict[str, str]]:
        records, errors = self.scan_records()
        records.sort(key=lambda record: str(record.metadata.get("updated", "")), reverse=True)
        by_project: Dict[str, List[Record]] = {}
        for record in records:
            by_project.setdefault(str(record.metadata.get("project", "未分类项目")), []).append(record)

        root_lines = [
            "# BIOS 问题总目录",
            "",
            "> 本文件由 `bios-worklog` 自动生成。问题 Markdown 是唯一真实来源，请勿手工维护本表。",
            "",
            f"最后生成：{display_time()}",
            "",
            "## 项目概览",
            "",
            "| 项目 | 调查中/暂停/验证中 | 已解决 | 总数 | 项目目录 |",
            "|---|---:|---:|---:|---|",
        ]
        for project in sorted(by_project, key=str.casefold):
            project_records = by_project[project]
            solved = sum(1 for record in project_records if record.metadata.get("status") == "solved")
            open_count = len(project_records) - solved
            project_dir = project_records[0].path.parent.parent
            project_index = project_dir / "INDEX.md"
            link = normalize_rel_link(project_index.relative_to(self.root))
            root_lines.append(
                f"| {markdown_cell(project)} | {open_count} | {solved} | {len(project_records)} | [查看]({link}) |"
            )

        root_lines.extend(
            [
                "",
                "## 全部问题",
                "",
                "| ID | 项目 | 问题 | 状态 | 分类 | 更新时间 |",
                "|---|---|---|---|---|---|",
            ]
        )
        for record in records:
            meta = record.metadata
            link = normalize_rel_link(record.path.relative_to(self.root))
            categories = "、".join(as_list(meta.get("categories"))) or "—"
            root_lines.append(
                "| {id} | {project} | [{title}]({link}) | {status} | {categories} | {updated} |".format(
                    id=markdown_cell(meta.get("id")),
                    project=markdown_cell(meta.get("project")),
                    title=markdown_cell(meta.get("title")),
                    link=link,
                    status=markdown_cell(STATUS_LABELS.get(str(meta.get("status")), meta.get("status"))),
                    categories=markdown_cell(categories),
                    updated=markdown_cell(meta.get("updated")),
                )
            )
        if not records:
            root_lines.append("| — | — | 尚无问题记录 | — | — | — |")
        atomic_write_text(self.root / "INDEX.md", "\n".join(root_lines))

        for project, project_records in by_project.items():
            project_records.sort(key=lambda record: str(record.metadata.get("updated", "")), reverse=True)
            project_dir = project_records[0].path.parent.parent
            lines = [
                f"# {project} — 问题目录",
                "",
                "> 本文件由 `bios-worklog` 自动生成。",
                "",
                "| ID | 问题 | 状态 | 分类 | 更新时间 |",
                "|---|---|---|---|---|",
            ]
            for record in project_records:
                meta = record.metadata
                link = normalize_rel_link(record.path.relative_to(project_dir))
                categories = "、".join(as_list(meta.get("categories"))) or "—"
                lines.append(
                    "| {id} | [{title}]({link}) | {status} | {categories} | {updated} |".format(
                        id=markdown_cell(meta.get("id")),
                        title=markdown_cell(meta.get("title")),
                        link=link,
                        status=markdown_cell(STATUS_LABELS.get(str(meta.get("status")), meta.get("status"))),
                        categories=markdown_cell(categories),
                        updated=markdown_cell(meta.get("updated")),
                    )
                )
            atomic_write_text(project_dir / "INDEX.md", "\n".join(lines))
        return errors


# ---------------------------------------------------------------------------
# Configuration and initialization
# ---------------------------------------------------------------------------


def user_config_path() -> Path:
    override = os.environ.get("BIOS_WORKLOG_CONFIG")
    return Path(override).expanduser() if override else Path.home() / ".bios-worklog" / "config.json"


def find_knowledge_root(explicit: Optional[str], cwd: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    environment = os.environ.get("BIOS_WORKLOG_ROOT")
    if environment:
        return Path(environment).expanduser().resolve()
    start = Path(cwd).expanduser() if cwd else Path.cwd()
    try:
        start = start.resolve()
    except OSError:
        start = start.absolute()
    for candidate in (start, *start.parents):
        config_path = candidate / ".bios-worklog" / "config.json"
        if config_path.exists():
            config = load_json(config_path, {})
            if isinstance(config, dict) and config.get("kind") == KB_KIND:
                return candidate
    config = load_json(user_config_path(), {})
    if isinstance(config, dict) and config.get("knowledgeBase"):
        return Path(str(config["knowledgeBase"])).expanduser().resolve()
    raise WorklogError(
        "尚未配置 BIOS worklog 知识库。请执行：\n"
        "python scripts/bios_worklog.py init <目标大文件夹>"
    )


def initialize(root: Path, set_default: bool, reminder_minutes: int) -> Dict[str, Any]:
    root = root.expanduser().resolve()
    control = root / ".bios-worklog"
    projects = root / "projects"
    root.mkdir(parents=True, exist_ok=True)
    control.mkdir(parents=True, exist_ok=True)
    projects.mkdir(parents=True, exist_ok=True)
    config_path = control / "config.json"
    config = load_json(config_path, {}) if config_path.exists() else {}
    if config and (not isinstance(config, dict) or config.get("kind") not in (None, KB_KIND)):
        raise WorklogError(f"目录中存在不兼容配置：{config_path}")
    config = {
        **(config if isinstance(config, dict) else {}),
        "kind": KB_KIND,
        "version": 1,
        "created": (config or {}).get("created", now_iso()) if isinstance(config, dict) else now_iso(),
        "reminderMinutes": max(1, reminder_minutes),
    }
    atomic_write_json(config_path, config)
    state_path = control / "state.json"
    if not state_path.exists():
        atomic_write_json(state_path, {"version": 1, "workspaces": {}})
    readme = root / "README.md"
    if not readme.exists():
        atomic_write_text(
            readme,
            """# BIOS Worklog 知识库

本目录由 `bios-worklog` Agent Skill 管理。

- `projects/<项目>/issues/`：每个 BIOS 问题对应一个 Markdown 文件。
- `INDEX.md`：自动生成的顶层目录。
- `projects/<项目>/INDEX.md`：自动生成的项目目录。
- `.bios-worklog/`：配置和当前活动问题状态。

问题 Markdown 是唯一真实来源。可以人工阅读和补充正文，但不要删除
`BIOS-WORKLOG` HTML 标记；目录文件应通过 `reindex` 重建。
""",
        )
    kb = KnowledgeBase(root)
    with kb.write_lock():
        warnings = kb.reindex_unlocked()
    if set_default:
        config_file = user_config_path()
        existing = load_json(config_file, {}) if config_file.exists() else {}
        user_config = dict(existing) if isinstance(existing, dict) else {}
        user_config.update({"version": 1, "knowledgeBase": str(root)})
        atomic_write_json(config_file, user_config)
    return {
        "message": "BIOS worklog 知识库初始化完成。",
        "root": str(root),
        "defaultConfigured": set_default,
        "userConfig": str(user_config_path()) if set_default else None,
        "reminderMinutes": max(1, reminder_minutes),
        "warnings": warnings,
    }


def configure(kb: KnowledgeBase, reminder_minutes: Optional[int], set_default: bool) -> Dict[str, Any]:
    kb.assert_initialized()
    with kb.write_lock():
        config = kb.config()
        if reminder_minutes is not None:
            config["reminderMinutes"] = max(1, reminder_minutes)
            atomic_write_json(kb.internal_config_path, config)
        if set_default:
            path = user_config_path()
            existing = load_json(path, {}) if path.exists() else {}
            user_config = dict(existing) if isinstance(existing, dict) else {}
            user_config.update({"version": 1, "knowledgeBase": str(kb.root)})
            atomic_write_json(path, user_config)
    return {
        "message": "已更新 BIOS worklog 配置。",
        "root": str(kb.root),
        "reminderMinutes": int(kb.config().get("reminderMinutes", 45)),
        "defaultConfigured": set_default,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bios_worklog.py",
        description="Manage a portable Markdown knowledge base for BIOS debugging issues.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--root", help="知识库根目录；优先于环境变量和用户配置。")
    parser.add_argument("--workspace", help="当前代码工作区；默认使用当前目录。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="初始化指定知识库大文件夹。")
    init_parser.add_argument("path", help="目标知识库目录。")
    init_parser.add_argument("--reminder-minutes", type=int, default=45)
    init_parser.add_argument("--no-set-default", action="store_true", help="不写入用户级默认路径配置。")

    config_parser = subparsers.add_parser("configure", help="更新知识库配置。")
    config_parser.add_argument("--reminder-minutes", type=int)
    config_parser.add_argument("--set-default", action="store_true", help="把当前知识库设为用户默认。")

    start_parser = subparsers.add_parser("start", help="创建问题记录并设为当前活动问题。")
    start_parser.add_argument("--project", help="项目名称；也可放在输入 JSON 中。")
    start_parser.add_argument("--title", help="问题标题；也可放在输入 JSON 中。")
    start_parser.add_argument("--input", help="UTF-8 JSON 文件，或 - 表示 stdin。")

    checkpoint_parser = subparsers.add_parser("checkpoint", help="向当前问题追加调查检查点。")
    checkpoint_parser.add_argument("--id", dest="issue_id")
    checkpoint_parser.add_argument("--input", help="检查点 JSON 文件，或 - 表示 stdin。")
    checkpoint_parser.add_argument("--title")
    checkpoint_parser.add_argument("--result")

    pause_parser = subparsers.add_parser("pause", help="保存暂停检查点并把状态设为 paused。")
    pause_parser.add_argument("--id", dest="issue_id")
    pause_parser.add_argument("--input", help="暂停检查点 JSON 文件，或 - 表示 stdin。")

    resume_parser = subparsers.add_parser("resume", help="恢复问题、设为活动问题并输出上下文。")
    resume_parser.add_argument("issue_id", nargs="?")
    resume_parser.add_argument("--recent", type=int, default=3)
    resume_parser.add_argument("--no-record", action="store_true", help="不追加恢复事件。")

    context_parser = subparsers.add_parser("context", help="只读输出问题恢复上下文。")
    context_parser.add_argument("issue_id", nargs="?")
    context_parser.add_argument("--recent", type=int, default=3)

    solve_parser = subparsers.add_parser("solve", help="填写最终结论并结案。")
    solve_parser.add_argument("--id", dest="issue_id")
    solve_parser.add_argument("--input", required=True, help="结案 JSON 文件，或 - 表示 stdin。")

    reopen_parser = subparsers.add_parser("reopen", help="重新打开已解决问题。")
    reopen_parser.add_argument("issue_id")
    reopen_parser.add_argument("--input", help="重新打开检查点 JSON 文件，或 - 表示 stdin。")
    reopen_parser.add_argument("--reason")

    status_parser = subparsers.add_parser("status", help="查看当前问题和检查点提醒状态。")
    status_parser.add_argument("--id", dest="issue_id")

    list_parser = subparsers.add_parser("list", help="列出问题记录。")
    list_parser.add_argument("--project")
    list_parser.add_argument("--status", choices=sorted(VALID_STATUSES))

    search_parser = subparsers.add_parser("search", help="搜索历史问题。")
    search_parser.add_argument("query", nargs="*", help="关键词；支持 project:/status:/category:/tag:。")
    search_parser.add_argument("--project")
    search_parser.add_argument("--status", choices=sorted(VALID_STATUSES))
    search_parser.add_argument("--limit", type=int, default=20)

    subparsers.add_parser("reindex", help="重建总目录和项目目录。")
    subparsers.add_parser("validate", help="校验问题记录结构。")
    subparsers.add_parser("doctor", help="显示知识库路径、配置和运行环境。")
    return parser


def json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def emit_text(result: Mapping[str, Any]) -> None:
    if result.get("message"):
        print(result["message"])
    if result.get("context"):
        print()
        print(result["context"])
        return
    issues = result.get("issues")
    if isinstance(issues, list) and issues and isinstance(issues[0], dict) and "id" in issues[0]:
        print()
        print("ID | 状态 | 项目 | 标题 | 更新时间")
        print("---|---|---|---|---")
        for issue in issues:
            print(
                f"{issue.get('id')} | {issue.get('statusLabel', issue.get('status'))} | "
                f"{issue.get('project')} | {issue.get('title')} | {issue.get('updated')}"
            )
    for key in ("id", "project", "title", "status", "updated", "resolved", "path", "root"):
        if key in result and result[key] is not None:
            print(f"{key}: {result[key]}")
    if result.get("checkpointRecommended"):
        print(
            f"提醒：距上次保存约 {result.get('minutesSinceCheckpoint')} 分钟，"
            "建议在合适的停顿点询问是否记录检查点。"
        )
    errors = result.get("errors") or result.get("warnings")
    if errors:
        print("\n警告：", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    json_output = False
    if "--json" in arguments:
        json_output = True
        arguments = [argument for argument in arguments if argument != "--json"]
    parser = build_parser()
    args = parser.parse_args(arguments)
    try:
        if args.command == "init":
            result = initialize(Path(args.path), not args.no_set_default, args.reminder_minutes)
        else:
            root = find_knowledge_root(args.root, args.workspace)
            kb = KnowledgeBase(root, workspace=args.workspace)
            if args.command == "configure":
                result = configure(kb, args.reminder_minutes, args.set_default)
            elif args.command == "start":
                payload = load_json_file(args.input)
                project = args.project or sanitize_markdown(payload.pop("project", ""))
                title = args.title or sanitize_markdown(payload.pop("title", ""))
                result = kb.create_issue(project, title, payload)
            elif args.command == "checkpoint":
                payload = load_json_file(args.input)
                if args.title:
                    payload["title"] = args.title
                if args.result:
                    payload["result"] = args.result
                result = kb.checkpoint(args.issue_id, payload)
            elif args.command == "pause":
                result = kb.pause(args.issue_id, load_json_file(args.input))
            elif args.command == "resume":
                result = kb.resume(args.issue_id, args.recent, record_event=not args.no_record)
            elif args.command == "context":
                result = kb.context(args.issue_id, args.recent)
            elif args.command == "solve":
                result = kb.solve(args.issue_id, load_json_file(args.input))
            elif args.command == "reopen":
                payload = load_json_file(args.input)
                if args.reason:
                    payload["reason"] = args.reason
                result = kb.reopen(args.issue_id, payload)
            elif args.command == "status":
                result = kb.status(args.issue_id)
            elif args.command == "list":
                result = kb.list_records(args.project, args.status)
            elif args.command == "search":
                result = kb.search(" ".join(args.query), args.project, args.status, args.limit)
            elif args.command == "reindex":
                result = kb.reindex()
            elif args.command == "validate":
                result = kb.validate()
            elif args.command == "doctor":
                config = kb.config()
                validation = kb.validate()
                result = {
                    "message": "BIOS worklog 运行环境正常。" if validation["valid"] else "BIOS worklog 可运行，但知识库存在校验问题。",
                    "version": VERSION,
                    "python": sys.version.split()[0],
                    "root": str(kb.root),
                    "workspace": kb.workspace,
                    "config": config,
                    "userConfig": str(user_config_path()),
                    "validation": validation,
                }
            else:  # pragma: no cover - argparse prevents this
                raise WorklogError(f"未知命令：{args.command}")
        if json_output:
            print(json.dumps(json_ready(result), ensure_ascii=False, indent=2))
        else:
            emit_text(result)
        if args.command == "validate" and not result.get("valid", True):
            return 1
        return 0
    except WorklogError as exc:
        if json_output:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        else:
            print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
