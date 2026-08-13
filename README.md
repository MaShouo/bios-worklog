# BIOS Worklog Agent Skill

一个用于记录、恢复和检索 BIOS **问题调查**与**功能实现方案**的可移植 [Agent Skill](https://agentskills.io/)。

每个工作项始终对应同一个 Markdown 文件：

- `start-issue`：创建问题调查记录；
- `start-feature`：创建功能方案/实现记录；
- `checkpoint`：记录成功或失败实验、排除路径、设计决策和实现进展；
- `pause` / `resume`：跨 AI 会话暂停并恢复；
- `solve`：问题结案；
- `complete`：完成功能并整理跨项目复用指南；
- `context` / `search`：只读参考历史问题和历史方案。

用户触发两个 start 动作时不需要在命令后写完整描述，Agent 会优先从当前会话提取项目、标题和内容。

Skill 使用 Python 标准库脚本执行确定性文件操作，不依赖 Pi Extension，也不需要第三方 Python 包。

## 仓库结构

```text
repository-root/
├── README.md
├── LICENSE
├── .gitignore
└── bios-worklog/                 # 可直接复制安装的 Skill 目录
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

下载或克隆后，只复制内层 **`bios-worklog/`** 到 Agent 的 Skills 目录。例如 Pi：

```text
<本仓库>/bios-worklog/  →  ~/.pi/agent/skills/bios-worklog/
```

```bash
git clone https://github.com/MaShouo/bios-worklog.git
```

随后重新加载 Skills 或重启 Agent。仓库根目录的文件不需要复制。

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
