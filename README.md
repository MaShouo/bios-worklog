# BIOS Worklog Agent Skill

一个用于记录、恢复和检索 BIOS **问题调查**与**功能实现方案**的可移植 [Agent Skill](https://agentskills.io/)，同时作为 Pi Package 提供可自动注册的快捷命令。

每个工作项始终对应同一个 Markdown 文件：

- `start-issue`：创建问题调查记录；
- `start-feature`：创建功能方案/实现记录；
- `checkpoint`：记录成功或失败实验、排除路径、设计决策和实现进展；
- `pause` / `resume`：跨 AI 会话暂停并恢复；
- `solve`：问题结案；
- `complete`：完成功能并整理跨项目复用指南；
- `context` / `search`：只读参考历史问题和历史方案。

用户触发两个 start 动作时不需要在命令后写完整描述，Agent 会优先从当前会话提取项目、标题和内容。

Skill 使用 Python 标准库脚本执行确定性文件操作，不依赖 Pi Extension，也不需要第三方 Python 包。Pi 快捷命令通过 Prompt Templates 注册；其他兼容 Agent Skills 的工具仍可只安装 Skill 本体。

## 仓库结构

```text
repository-root/
├── package.json                  # Pi Package 清单
├── README.md
├── LICENSE
├── .gitignore
├── prompts/                      # Pi 快捷命令（/bios-*）
│   ├── bios-issue.md
│   ├── bios-feature.md
│   └── ...
└── bios-worklog/                 # 可单独复制的标准 Agent Skill
    ├── SKILL.md
    ├── scripts/
    │   └── bios_worklog.py
    ├── references/
    │   ├── bios-categories.md
    │   ├── record-format.md
    │   └── workflow.md
    └── tests/
        └── test_bios_worklog.py
```

## 安装

### Pi（推荐，自动注册快捷命令）

直接把本仓库安装为 Pi Package：

```bash
pi install git:github.com/MaShouo/bios-worklog
```

重启 Pi 或开启新会话后，将同时加载：

- `bios-worklog` Skill，对应 `/skill:bios-worklog`；
- `prompts/` 中的 `/bios-*` 快捷命令。

Pi 默认启用 Skill 命令。如果 `/skill:bios-worklog` 没有出现在补全列表，请在 `/settings` 中启用 **Skill commands**，或在 `~/.pi/agent/settings.json` 中设置：

```json
{
  "enableSkillCommands": true
}
```

### 手工安装或其他 Agent Harness

只需要标准 Skill 时，克隆仓库后把内层 **`bios-worklog/`** 复制到 Agent 的 Skills 目录。例如 Pi：

```text
<本仓库>/bios-worklog/  →  ~/.pi/agent/skills/bios-worklog/
```

这种安装方式只注册 `/skill:bios-worklog`，不会自动安装独立的 `/bios-*` 快捷命令。若要在 Pi 中同时手工安装快捷命令，再把 `prompts/*.md` 复制到 `~/.pi/agent/prompts/`。随后重启 Pi 或开启新会话。

## 初始化记录目录

让 Agent 执行：

```text
使用 bios-worklog，将记录目录初始化为 D:\BIOS-KnowledgeBase
```

或直接运行：

```bash
python bios-worklog/scripts/bios_worklog.py init "D:\BIOS-KnowledgeBase"
```

默认目录保存在 `~/.bios-worklog/config.json`。

## 使用示例

Pi Package 会注册以下快捷命令，输入 `/bios-` 即可在补全列表中选择：

```text
/bios-init D:\BIOS-KnowledgeBase
/bios-issue [简短标题或补充说明]
/bios-feature [简短标题或补充说明]
/bios-checkpoint [进展摘要]
/bios-pause [交接说明]
/bios-resume [记录 ID]
/bios-context <记录 ID>
/bios-solve [根因、方案或验证补充]
/bios-complete [最终方案或验证补充]
/bios-reopen <记录 ID> [复现补充]
/bios-status
/bios-list [筛选条件]
/bios-search <关键词或筛选表达式>
/bios-reindex
/bios-validate
/bios-doctor
```

标准 Skill 命令仍然可用：

```text
/skill:bios-worklog start-issue
/skill:bios-worklog start-feature
/skill:bios-worklog checkpoint
/skill:bios-worklog pause
/skill:bios-worklog resume BIOS-20260324-001
/skill:bios-worklog solve
/skill:bios-worklog complete
/skill:bios-worklog search type:feature Event Log Export
```

自然语言也可以：

```text
使用 bios-worklog 创建一个功能实现记录。
使用 bios-worklog 记录当前工作的检查点。
参考 BIOS-20260325-001 的方案，但不要改变原记录。
```

## 知识库结构

```text
BIOS-KnowledgeBase/
├── README.md
├── INDEX.md
├── projects/
│   └── Project-A/
│       ├── INDEX.md
│       └── records/
│           ├── BIOS-20260324-001-s3-resume-black-screen.md
│           └── BIOS-20260325-001-event-log-export.md
└── .bios-worklog/
    ├── config.json
    └── state.json
```

旧版 `issues/` 目录仍然兼容；新记录统一写到 `records/`。Markdown 记录是唯一真实来源，`INDEX.md` 可以随时重建。

## 直接使用 CLI

```bash
python bios-worklog/scripts/bios_worklog.py --help
python bios-worklog/scripts/bios_worklog.py --json status
python bios-worklog/scripts/bios_worklog.py --json list --type feature
python bios-worklog/scripts/bios_worklog.py --json search "type:feature Event Log Export"
python bios-worklog/scripts/bios_worklog.py --json validate
```

支持 Python 3.9+，只使用标准库。

## 测试

```bash
python -m unittest discover -s bios-worklog/tests -v
```

## 安全说明

BIOS 项目可能包含内部或敏感信息。不要记录密码、Token、签名密钥、私钥、客户身份、设备序列号或不必要的内部地址；使用时遵守所在组织的数据分类和保密要求。

## License

[MIT](LICENSE)
