# BIOS Worklog Agent Skill

一个用于记录、恢复和检索 BIOS 调试问题的可移植 [Agent Skill](https://agentskills.io/)。

每个问题从创建到结案始终对应同一个 Markdown 文件：

- `start`：在对应项目目录中创建问题记录；
- `checkpoint`：记录任何调查进展，包括失败实验和排除路径；
- `pause` / `resume`：跨 AI 会话暂停并恢复问题上下文；
- `solve` / `reopen`：结案或重新打开原问题；
- `search` / `reindex` / `validate`：搜索、重建目录和校验知识库。

Skill 使用 Python 标准库脚本执行确定性的文件操作，不依赖 Pi Extension，也不需要第三方 Python 包。

## 目录结构

```text
bios-worklog/
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

把整个仓库克隆或复制到 Agent 支持的 Skills 目录。例如 Pi：

```text
~/.pi/agent/skills/bios-worklog/
```

随后重新加载 Skills 或重启 Agent。

## 初始化记录目录

可以让 Agent 执行：

```text
使用 bios-worklog，将记录目录初始化为 D:\BIOS-KnowledgeBase
```

也可以直接运行：

```bash
python scripts/bios_worklog.py init "D:\BIOS-KnowledgeBase"
```

初始化后，默认目录记录在：

```text
~/.bios-worklog/config.json
```

## 使用示例

在支持 Skill 命令的 Agent 中：

```text
/skill:bios-worklog start Project-A S3 Resume 后黑屏
/skill:bios-worklog checkpoint
/skill:bios-worklog pause
/skill:bios-worklog resume BIOS-20260324-001
/skill:bios-worklog solve
/skill:bios-worklog search S3 Graphics PCI
```

也可以直接使用自然语言：

```text
使用 bios-worklog 记录当前问题的检查点。
使用 bios-worklog 恢复 BIOS-20260324-001。
```

## 知识库示例

```text
BIOS-KnowledgeBase/
├── README.md
├── INDEX.md
├── projects/
│   └── Project-A/
│       ├── INDEX.md
│       └── issues/
│           └── BIOS-20260324-001-s3-resume-black-screen.md
└── .bios-worklog/
    ├── config.json
    └── state.json
```

问题 Markdown 是唯一真实来源；`INDEX.md` 可以随时重建。

## 直接使用 CLI

```bash
python scripts/bios_worklog.py --help
python scripts/bios_worklog.py --json status
python scripts/bios_worklog.py --json list --status investigating
python scripts/bios_worklog.py --json search "project:Project-A category:S3 resume"
python scripts/bios_worklog.py --json validate
```

支持 Python 3.9 及以上版本，只使用标准库。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 安全说明

BIOS 项目可能包含内部或敏感信息。不要把密码、Token、签名密钥、私钥、客户身份、设备序列号或不必要的内部地址写入知识库。使用前请遵守所在组织的数据分类和保密要求。

## License

[MIT](LICENSE)
