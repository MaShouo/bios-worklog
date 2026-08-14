#!/usr/bin/env python3
"""Standard-library tests for the bios-worklog CLI.

Run with:
    python -m unittest discover -s bios-worklog/tests -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bios_worklog.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bios_worklog", SCRIPT)
assert SPEC and SPEC.loader
bios_worklog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bios_worklog
SPEC.loader.exec_module(bios_worklog)


class BiosWorklogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "knowledge"
        self.workspace = self.base / "firmware" / "ProjectA"
        self.workspace.mkdir(parents=True)
        self.user_config = self.base / "user-config.json"
        self.env_patch = mock.patch.dict(
            os.environ,
            {"BIOS_WORKLOG_CONFIG": str(self.user_config)},
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        bios_worklog.initialize(self.root, set_default=True, reminder_minutes=30)
        self.kb = bios_worklog.KnowledgeBase(self.root, workspace=str(self.workspace))

    def start_issue(self):
        return self.kb.create_issue(
            "Project-A",
            "S3 Resume 后黑屏",
            {
                "description": "系统从 S3 唤醒后仍运行，但内外屏无输出。",
                "environment": {"bios_version": "V1.08", "os": "Windows 11"},
                "reproduction_steps": ["进入系统并睡眠", "按电源键唤醒"],
                "confirmed_facts": ["串口日志继续输出", "复现率 10/10"],
                "current_assessment": "怀疑 PCI Restore 顺序异常。",
                "unknowns": ["BAR 与 Command Register 的恢复顺序"],
                "next_steps": ["对比 PCI dump"],
                "categories": ["S3", "Display"],
                "tags": ["PCI", "Graphics"],
                "confidence": "hypothesis",
            },
        )

    def start_feature(self):
        return self.kb.create_feature(
            "Project-A",
            "实现 BIOS Event Log 导出",
            {
                "objective": "在 BIOS Setup 中把 Event Log 导出到 USB。",
                "background": "现有日志只能逐项查看，不便于跨团队分析。",
                "requirements": ["支持 FAT32", "输出 UTF-8", "不阻塞 Setup"],
                "design": {
                    "selected": "独立 Export Protocol + 项目数据适配层",
                    "reason": "隔离通用文件写入与项目数据源",
                },
                "confirmed_facts": ["各项目 Event Log 数据结构不同"],
                "current_assessment": "公共导出模块应与 HII Callback 解耦。",
                "unknowns": ["多分区 USB 的选择策略"],
                "next_steps": ["定义 Protocol", "验证 Simple File System 枚举"],
                "categories": ["Setup", "Logging"],
                "tags": ["HII", "USB"],
                "reusable": True,
            },
        )

    def test_init_creates_portable_layout_and_default_config(self):
        self.assertTrue((self.root / ".bios-worklog" / "config.json").exists())
        self.assertTrue((self.root / ".bios-worklog" / "state.json").exists())
        self.assertTrue((self.root / "INDEX.md").exists())
        default = json.loads(self.user_config.read_text(encoding="utf-8"))
        self.assertEqual(Path(default["knowledgeBase"]), self.root.resolve())
        discovered = bios_worklog.find_knowledge_root(None, str(self.workspace))
        self.assertEqual(discovered, self.root.resolve())

    def test_start_creates_one_issue_file_and_indexes(self):
        result = self.start_issue()
        issue_path = Path(result["path"])
        self.assertTrue(issue_path.exists())
        self.assertEqual(len(list(self.root.glob("projects/*/records/*.md"))), 1)
        text = issue_path.read_text(encoding="utf-8")
        self.assertIn("status: \"investigating\"", text)
        self.assertIn("<!-- BIOS-WORKLOG:HISTORY:START -->", text)
        self.assertIn("S3 Resume 后黑屏", (self.root / "INDEX.md").read_text(encoding="utf-8"))
        status = self.kb.status(None)
        self.assertEqual(status["id"], result["id"])
        self.assertEqual(status["status"], "investigating")

    def test_checkpoint_appends_history_and_updates_current_state(self):
        started = self.start_issue()
        path = Path(started["path"])
        before = path.read_text(encoding="utf-8")
        result = self.kb.checkpoint(
            None,
            {
                "title": "对比 PCI Restore 顺序",
                "purpose": "确认恢复时序。",
                "actions": ["比较两版源码与日志"],
                "result": "异常版本先恢复 Command Register。",
                "findings": ["设备可能被提前 Enable"],
                "impact": "该方向成为最高优先级假设。",
                "confirmed_facts": ["Command Register 早于 BAR 恢复"],
                "current_assessment": "PCI Restore 顺序很可能是根因。",
                "unknowns": ["循环验证是否通过"],
                "next_steps": ["调整顺序", "执行 100 次 S3 循环"],
                "confidence": "probable",
            },
        )
        self.assertEqual(result["id"], started["id"])
        after = path.read_text(encoding="utf-8")
        self.assertIn("创建问题", after)
        self.assertIn("对比 PCI Restore 顺序", after)
        self.assertIn("PCI Restore 顺序很可能是根因", after)
        self.assertIn("confidence: \"probable\"", after)
        self.assertGreater(len(after), len(before))

    def test_pause_resume_edits_same_file_and_context(self):
        started = self.start_issue()
        issue_path = Path(started["path"])
        paused = self.kb.pause(
            None,
            {
                "title": "暂停并保存环境",
                "result": "当前缺少测试机器。",
                "findings": ["源码比较已完成"],
                "next_steps": ["恢复后刷写测试 BIOS"],
                "current_assessment": "等待硬件验证。",
            },
        )
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(Path(paused["path"]), issue_path)
        resumed = self.kb.resume(started["id"], recent=2, record_event=True)
        self.assertEqual(resumed["status"], "investigating")
        self.assertEqual(Path(resumed["path"]), issue_path)
        self.assertIn("恢复后刷写测试 BIOS", resumed["context"])
        self.assertIn("恢复工作", issue_path.read_text(encoding="utf-8"))
        self.assertEqual(len(list(self.root.glob("projects/*/records/*.md"))), 1)

    def test_solve_reopen_and_validation(self):
        started = self.start_issue()
        solved = self.kb.solve(
            None,
            {
                "root_cause": "Command Register 在 BAR 前恢复。",
                "solution": "先恢复 BAR，再恢复 Command Register。",
                "changed_files": ["Platform/PciRestore/PciRestore.c"],
                "validation": ["S3 循环 500 次通过", "外接显示器通过"],
                "regression_scope": ["冷启动", "暖启动"],
                "reusable_lessons": ["比较寄存器值时也要检查恢复顺序"],
            },
        )
        self.assertEqual(solved["status"], "solved")
        status = self.kb.status(None)
        self.assertFalse(status["active"])
        text = Path(started["path"]).read_text(encoding="utf-8")
        self.assertIn("status: \"solved\"", text)
        self.assertIn("S3 循环 500 次通过", text)

        reopened = self.kb.reopen(
            started["id"],
            {
                "reason": "另一板型再次复现。",
                "unknowns": ["是否为同一恢复路径"],
                "next_steps": ["收集另一板型日志"],
            },
        )
        self.assertEqual(reopened["status"], "investigating")
        reopened_text = Path(started["path"]).read_text(encoding="utf-8")
        self.assertNotIn("resolved:", reopened_text.split("---", 2)[1])
        self.assertIn("另一板型再次复现", reopened_text)
        self.assertIn("此问题已重新打开", reopened_text)
        validation = self.kb.validate()
        self.assertTrue(validation["valid"], validation)

    def test_reindex_reports_malformed_records_without_overwriting_them(self):
        self.start_issue()
        bad_dir = self.root / "projects" / "bad-project" / "issues"
        bad_dir.mkdir(parents=True)
        bad_path = bad_dir / "broken.md"
        bad_text = "# 手工损坏的记录\n\n此文件不应被 reindex 覆盖。\n"
        bad_path.write_text(bad_text, encoding="utf-8")
        result = self.kb.reindex()
        self.assertTrue(result["warnings"])
        self.assertEqual(bad_path.read_text(encoding="utf-8"), bad_text)
        validation = self.kb.validate()
        self.assertFalse(validation["valid"])

    def test_marker_like_input_is_escaped(self):
        started = self.start_issue()
        self.kb.checkpoint(
            None,
            {
                "title": "检查日志标记",
                "result": "日志包含 <!-- BIOS-WORKLOG:HISTORY:END --> 文本。",
                "next_steps": ["继续分析"],
            },
        )
        text = Path(started["path"]).read_text(encoding="utf-8")
        self.assertIn("&lt;!-- BIOS-WORKLOG:HISTORY:END -->", text)
        self.assertTrue(self.kb.validate()["valid"])

    def test_feature_lifecycle_uses_same_record_and_complete(self):
        started = self.start_feature()
        path = Path(started["path"])
        self.assertEqual(started["type"], "feature")
        self.assertEqual(started["status"], "implementing")
        self.assertIn("records", path.parts)
        text = path.read_text(encoding="utf-8")
        self.assertIn('type: "feature"', text)
        self.assertIn("## 方案设计", text)
        self.assertIn("BIOS-WORKLOG:DESIGN:START", text)

        checkpoint = self.kb.checkpoint(
            None,
            {
                "title": "完成文件系统枚举",
                "actions": ["枚举 Simple File System Protocol"],
                "result": "FAT32 USB 可以写入。",
                "findings": ["不能假设第一个文件系统就是 USB"],
                "current_assessment": "需要按设备路径筛选 Handle。",
                "next_steps": ["实现设备路径筛选"],
            },
        )
        self.assertEqual(checkpoint["path"], str(path))
        completed = self.kb.complete(
            None,
            {
                "final_design": "使用独立 Export Protocol，项目适配层提供数据。",
                "design_decisions": ["Setup Callback 只发起请求"],
                "changed_files": ["Common/EventLogExport/"],
                "validation": ["5 种 FAT32 USB 通过", "5000 条日志通过"],
                "reusable_parts": ["文件系统枚举", "UTF-8 格式化"],
                "project_specific": ["Event Log 数据适配器", "HII Form ID"],
                "prerequisites": ["DXE 可用 Simple File System Protocol"],
                "reference_steps": ["引入公共模块", "实现项目适配器", "完成异常场景验证"],
                "known_risks": ["安全策略可能禁止外部写入"],
            },
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(Path(completed["path"]), path)
        completed_text = path.read_text(encoding="utf-8")
        self.assertIn("可直接复用部分", completed_text)
        self.assertIn("5 种 FAT32 USB 通过", completed_text)
        self.assertEqual(len(list(self.root.glob("projects/*/records/*.md"))), 1)
        context = self.kb.context(started["id"], recent=2)["context"]
        self.assertIn("功能目标", context)
        self.assertIn("最终成果与复用指南", context)
        self.assertTrue(self.kb.validate()["valid"])

    def test_solve_and_complete_enforce_record_type(self):
        issue = self.start_issue()
        with self.assertRaises(bios_worklog.WorklogError):
            self.kb.complete(
                issue["id"],
                {"final_design": "x", "validation": ["y"], "reusable_parts": ["z"]},
            )
        self.kb.clear_active(issue["id"])
        feature = self.start_feature()
        with self.assertRaises(bios_worklog.WorklogError):
            self.kb.solve(
                feature["id"],
                {"root_cause": "x", "solution": "y", "validation": ["z"]},
            )

    def test_legacy_issue_directory_remains_readable(self):
        started = self.start_issue()
        current = Path(started["path"])
        legacy_dir = current.parent.parent / "issues"
        legacy_dir.mkdir()
        legacy_path = legacy_dir / current.name
        current.replace(legacy_path)
        text = legacy_path.read_text(encoding="utf-8").replace('type: "issue"\n', "")
        legacy_path.write_text(text, encoding="utf-8")
        found = self.kb.find_issue(started["id"])
        self.assertEqual(found.path, legacy_path)
        self.assertEqual(bios_worklog.record_type(found.metadata), "issue")
        self.assertTrue(self.kb.validate()["valid"])

    def test_search_can_filter_feature_type(self):
        feature = self.start_feature()
        result = self.kb.search("type:feature Event Log", None, None, 20)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["records"][0]["id"], feature["id"])
        self.assertEqual(result["records"][0]["type"], "feature")
        issue_only = self.kb.search("type:issue Event Log", None, None, 20)
        self.assertEqual(issue_only["count"], 0)

    def test_search_filters_and_keyword_matching(self):
        first = self.start_issue()
        self.kb.checkpoint(
            first["id"],
            {
                "title": "Graphics PCI 调查",
                "result": "找到 BAR 恢复顺序差异。",
                "next_steps": ["验证修复"],
            },
        )
        results = self.kb.search("category:S3 Graphics PCI", None, None, 20)
        self.assertEqual(results["count"], 1)
        self.assertEqual(results["issues"][0]["id"], first["id"])
        none = self.kb.search("category:Memory Graphics", None, None, 20)
        self.assertEqual(none["count"], 0)

    def test_solve_requires_root_cause_solution_and_validation(self):
        self.start_issue()
        with self.assertRaises(bios_worklog.WorklogError):
            self.kb.solve(None, {"root_cause": "x", "solution": "y"})

    def test_pi_package_registers_skill_and_prompt_commands(self):
        manifest = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertIn("pi-package", manifest["keywords"])
        self.assertEqual(manifest["pi"]["skills"], ["./bios-worklog"])
        self.assertEqual(manifest["pi"]["prompts"], ["./prompts"])

        expected_actions = {
            "bios-init.md": "`init`",
            "bios-issue.md": "`start-issue`",
            "bios-feature.md": "`start-feature`",
            "bios-checkpoint.md": "`checkpoint`",
            "bios-pause.md": "`pause`",
            "bios-resume.md": "`resume`",
            "bios-context.md": "`context`",
            "bios-solve.md": "`solve`",
            "bios-complete.md": "`complete`",
            "bios-reopen.md": "`reopen`",
            "bios-status.md": "`status`",
            "bios-list.md": "`list`",
            "bios-search.md": "`search`",
            "bios-reindex.md": "`reindex`",
            "bios-validate.md": "`validate`",
            "bios-doctor.md": "`doctor`",
        }
        prompt_dir = REPO_ROOT / "prompts"
        self.assertEqual({path.name for path in prompt_dir.glob("*.md")}, set(expected_actions))
        for filename, action in expected_actions.items():
            text = (prompt_dir / filename).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), filename)
            self.assertIn("description:", text, filename)
            self.assertIn("`bios-worklog` skill", text, filename)
            self.assertIn(action, text, filename)

    def test_cli_json_end_to_end(self):
        other_root = self.base / "cli-kb"
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            init_code = bios_worklog.main(
                ["--json", "init", str(other_root), "--no-set-default", "--reminder-minutes", "10"]
            )
        self.assertEqual(init_code, 0)
        input_path = self.base / "start.json"
        input_path.write_text(
            json.dumps(
                {
                    "project": "CLI-Project",
                    "title": "Memory Training Fail",
                    "description": "Cold boot training fails.",
                    "next_steps": ["Collect MRC log"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            start_code = bios_worklog.main(
                [
                    "--json",
                    "--root",
                    str(other_root),
                    "--workspace",
                    str(self.workspace),
                    "start-issue",
                    "--input",
                    str(input_path),
                ]
            )
        self.assertEqual(start_code, 0)
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            validate_code = bios_worklog.main(["--json", "--root", str(other_root), "validate"])
        self.assertEqual(validate_code, 0)


if __name__ == "__main__":
    unittest.main()
