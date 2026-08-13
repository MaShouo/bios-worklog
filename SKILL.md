---
name: bios-worklog
description: Manages a local Markdown knowledge base for BIOS debugging issues. Use when the user wants to create a BIOS issue record, save any investigation checkpoint (including failed experiments and eliminated paths), pause or resume work across AI sessions, search historical issues, close or reopen an issue, rebuild indexes, or inspect the active BIOS problem.
compatibility: Requires Python 3.9+ and permission to read and write the user-selected local knowledge-base directory. Uses only the Python standard library.
---

# BIOS Worklog

使用本 Skill 管理本地 BIOS 调试知识库。一个问题从创建到结案始终对应**同一个 Markdown 文件**：

- `start` 创建该文件并设为当前活动问题。
- `checkpoint`、`pause`、`resume`、`solve`、`reopen` 编辑该文件。
- 历史检查点只追加；“当前状态”和最终结论可以更新。
- 成功尝试、失败尝试、排除路径、缩小范围、发现新现象、代码修改和验证结果都属于进展，统一记录为 `checkpoint`。

实际文件操作必须通过 `scripts/bios_worklog.py` 完成，不要直接维护索引或 `.bios-worklog/state.json`。

## 执行约定

1. 将本 `SKILL.md` 所在目录记为 `SKILL_DIR`，脚本路径为：

   ```text
   <SKILL_DIR>/scripts/bios_worklog.py
   ```

2. 使用当前环境可用的 Python 3 解释器。示例统一写成：

   ```bash
   python "<SKILL_DIR>/scripts/bios_worklog.py" --json <action> ...
   ```

   Windows 上如果 `python` 不可用，可用 `py -3`；其他平台可用 `python3`。

3. 需要传递多行或结构化内容时：
   - 在系统临时目录创建 UTF-8 JSON 临时文件；
   - 调用脚本的 `--input <file>`；
   - 调用后删除临时文件；
   - 不要把临时输入文件放进用户源码仓库。

4. 命令成功后，向用户清楚报告问题 ID、状态和问题 Markdown 路径。

5. 用户显式调用 `start`、`checkpoint`、`pause`、`resume`、`solve` 或 `reopen`，即表示授权执行对应写入；不要再增加没有价值的二次确认。仅在以下情况询问：
   - `start` 缺少项目或无法判断问题标题；
   - 当前有多个候选问题，无法确定要编辑哪一个；
   - `solve` 的根因、解决方法或验证结果缺失/仍互相矛盾；
   - 写入会覆盖用户明确表达的判断，或涉及敏感信息。

6. 不要把模型推测写成已确认事实。保留“已确认事实 / 当前判断 / 尚未确认”的边界。

7. 当本 Skill 因 BIOS 调试任务被加载、但用户没有明确指定动作时，先运行一次 `status`：
   - 有活动问题时，把它视为当前问题；
   - `checkpointRecommended: true` 时，在当前工作自然停顿后询问是否保存检查点；
   - 没有活动问题时继续协助调试，不要擅自 `start`；只有出现值得长期跟踪的问题时才询问是否创建记录；
   - 任何提醒都不能自动写文件，写入必须由用户触发或确认。

## 首次使用与知识库定位

脚本按以下优先级寻找知识库：

1. 命令行 `--root <path>`；
2. 环境变量 `BIOS_WORKLOG_ROOT`；
3. 当前目录或祖先目录中的 `.bios-worklog/config.json`；
4. 用户级 `~/.bios-worklog/config.json` 中的默认路径。

若脚本提示尚未配置知识库，询问用户目标“大文件夹”，然后执行：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json init "<知识库目录>"
```

`init` 默认把该目录设为当前用户的默认知识库，不会删除已有文件。目录结构见 [references/record-format.md](references/record-format.md)。

如果用户希望改变提醒间隔：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json configure --reminder-minutes 45
```

## 动作路由

将用户自然语言或 Skill 参数映射为下列动作：

| 用户意图 | 动作 |
|---|---|
| 创建、开始记录问题 | `start` |
| 保存进展、尝试、实验、排除路径 | `checkpoint` |
| 暂停、下班、切换工作前保存 | `pause` |
| 恢复当前/指定问题 | `resume` |
| 只读取上下文，不改变状态 | `context` |
| 解决、结案 | `solve` |
| 已解决问题再次出现 | `reopen` |
| 查看当前问题 | `status` |
| 查看未解决/项目问题 | `list` |
| 查找历史问题 | `search` |
| 重建目录 | `reindex` |
| 检查知识库 | `validate` / `doctor` |

如果参数为空且用户只加载了本 Skill，简短询问希望执行哪个动作；不要擅自创建记录。

## `start`：立即创建项目问题文件

从当前对话提取初始内容，但只使用有证据的信息。至少需要：

- `project`：对应的项目名称；
- `title`：问题标题。

推荐 JSON 结构：

```json
{
  "project": "Project-A",
  "title": "S3 Resume 后黑屏",
  "description": "系统从 S3 唤醒后仍在运行，但内外屏无输出。",
  "environment": {
    "platform": "待补充",
    "bios_version": "V1.08",
    "os": "Windows 11"
  },
  "reproduction_steps": [
    "进入操作系统并执行睡眠",
    "使用电源键唤醒",
    "观察内屏和外接显示器"
  ],
  "confirmed_facts": [
    "串口日志继续输出",
    "问题复现率为 10/10"
  ],
  "current_assessment": "怀疑 Graphics PCI 配置恢复顺序异常，尚未确认。",
  "unknowns": ["BAR 和 Command Register 的恢复顺序是否为直接根因"],
  "next_steps": ["对比正常和异常版本的 PCI Configuration Dump"],
  "categories": ["S3", "Display"],
  "tags": ["PCI", "Graphics"],
  "confidence": "hypothesis"
}
```

调用：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json start --input "<start.json>"
```

行为必须是：在 `projects/<项目>/issues/` 下创建单一问题 Markdown，设为当前工作区的活动问题，并更新顶层及项目 `INDEX.md`。

## `checkpoint`：编辑当前记录

用户要求记录任何调查进展时，从**上次检查点之后的相关对话**提取内容；不要重复抄写全部历史。即使实验失败，也记录它带来的信息，而不是称为“没有进展”。

推荐 JSON：

```json
{
  "title": "对比 PCI Restore 顺序",
  "purpose": "检查 Graphics Device 的 PCI 配置恢复时序。",
  "actions": ["比较正常版本和异常版本的恢复日志及源码"],
  "result": "异常版本先恢复 Command Register，再恢复 BAR。",
  "findings": ["Graphics Device 可能在 BAR 有效前被提前 Enable"],
  "evidence": ["PciRestore.c 中的调用顺序", "两版串口日志"],
  "impact": "PCI Restore 顺序成为当前最高优先级假设，尚未最终确认。",
  "confirmed_facts": ["异常版本的 Command Register 早于 BAR 恢复"],
  "current_assessment": "PCI Restore 顺序很可能导致黑屏。",
  "unknowns": ["修改后能否通过长时间 S3 循环"],
  "next_steps": ["调整恢复顺序", "执行 100 次 S3 循环"],
  "confidence": "probable"
}
```

调用：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json checkpoint --input "<checkpoint.json>"
```

可用 `--id BIOS-...` 临时指定问题；否则脚本编辑当前工作区的活动问题。该动作同时：

- 向 `调查记录` 追加带时间的检查点；
- 更新顶部“当前状态”；
- 更新 front matter 的 `updated/status/confidence/categories/tags`；
- 重建索引。

不要删除或改写旧检查点。旧判断后来被推翻时，在新检查点中说明证据和影响。

## `pause`：保存可恢复状态

暂停前重点整理：当前事实、当前判断、未确认项、最近操作、下一步和“恢复后首先执行什么”。调用：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json pause --input "<pause.json>"
```

它编辑同一问题文件，追加暂停检查点并把状态设为 `paused`。

## `resume`：跨会话恢复

指定 ID：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json resume BIOS-20260324-001 --recent 3
```

恢复当前问题：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json resume --recent 3
```

脚本会把原文件设为活动问题、必要时把 `paused` 改回 `investigating`、追加恢复事件，并在 JSON 的 `context` 字段返回：

- 问题描述、环境和复现步骤；
- 当前事实、判断、未知项和下一步；
- 最近若干检查点；
- 原始记录路径。

读取 `context` 后，以它作为当前工作的权威摘要继续协助用户。不要凭空补回旧会话内容。

若只需要引用历史问题而不改变其状态，使用：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json context BIOS-20260324-001 --recent 3
```

## `solve`：编辑同一文件并结案

仅在用户明确要求结案，并且至少存在以下内容时执行：

- `root_cause`：最终根因；
- `solution`：解决方法；
- `validation`：验证结果。

推荐 JSON：

```json
{
  "root_cause": "S3 Resume 时先恢复 Command Register，导致 Graphics Device 在 BAR 有效前被使能。",
  "solution": "先恢复 BAR，再恢复 Command Register，最后恢复扩展配置。",
  "changed_files": ["Platform/PciRestore/PciRestore.c"],
  "principle": "确保设备 decode enable 发生在地址窗口恢复之后。",
  "validation": ["S3 循环 500 次通过", "内屏和外接显示器通过"],
  "regression_scope": ["冷启动", "暖启动", "独显配置"],
  "known_risks": ["仍需在另一块板型验证 Thunderbolt Dock"],
  "reusable_lessons": ["检查 Resume 问题时应同时比较寄存器值与恢复时序"],
  "confidence": "confirmed"
}
```

调用：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json solve --input "<solve.json>"
```

脚本更新同一 Markdown 的最终结论和当前状态，追加结案检查点，设为 `solved`，然后更新索引。若只是补丁后暂时未复现、验证尚未完成，先用 `checkpoint` 并设置 `status: verifying`，不要强行 `solve`。

## `reopen`

问题再次出现且判断为同一问题时：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json reopen BIOS-20260324-001 --input "<reopen.json>"
```

它编辑原文件、保留上次结论、追加重新打开检查点并设回 `investigating`。如果现象相似但根因明显不同，应 `start` 新问题，并在 `related_issues` 中关联旧 ID。

## 状态、提醒、搜索和目录

查看当前问题：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json status
```

`checkpointRecommended: true` 只表示“距上次保存超过配置时间”，不表示用户没有进展。若本 Skill 正在参与当前 BIOS 调查，在自然停顿点最多提醒一次：

> 当前问题已有约 N 分钟没有保存检查点。是否把这段调查、实验结果和下一步记录下来？

纯 Skill 不运行后台定时器，也不应在用户没有发消息时承诺弹出提醒。用户拒绝后，本次会话不重复提醒，除非又发生明显的新调查阶段或用户主动询问。

列出问题：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json list --status investigating
```

搜索支持普通关键词以及 `project:`、`status:`、`category:`、`tag:`：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json search S3 Graphics PCI
python "<SKILL_DIR>/scripts/bios_worklog.py" --json search "project:Project-A category:S3 resume"
```

重建和校验：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json reindex
python "<SKILL_DIR>/scripts/bios_worklog.py" --json validate
python "<SKILL_DIR>/scripts/bios_worklog.py" --json doctor
```

## 内容质量规则

详细字段和文件结构见 [references/record-format.md](references/record-format.md)，工作方法见 [references/workflow.md](references/workflow.md)，分类建议见 [references/bios-categories.md](references/bios-categories.md)。始终遵守：

- 只记录与该问题相关的技术事实和必要上下文。
- 清楚标识“事实、假设、未知、最终根因”。
- 记录失败实验为何有价值：验证了什么、削弱/排除了什么、何时值得重试。
- 日志只摘录关键片段；大日志放附件或记录路径，不把整段会话复制进 Markdown。
- 不保存密码、令牌、签名密钥、私钥、个人数据或不必要的内部地址。
- 不虚构 BIOS 版本、硬件平台、测试次数、代码路径、提交号或验证结果；缺失时写“待补充”。
- 调查历史只追加；自动索引可重建；问题 Markdown 是唯一真实来源。
