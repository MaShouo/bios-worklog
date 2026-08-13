---
name: bios-worklog
description: Manages a local Markdown knowledge base for BIOS issue investigations and feature implementations. Use to start an issue or feature record, save checkpoints including failed experiments and design decisions, pause or resume work across AI sessions, search reusable historical records, solve issues, complete features, reopen issues, or rebuild indexes.
compatibility: Requires Python 3.9+ and permission to read and write the user-selected local knowledge-base directory. Uses only the Python standard library.
---

# BIOS Worklog

管理本地 BIOS 工程知识库，支持两种记录：

- **问题记录 (`issue`)**：异常现象、排查、根因、解决方法与验证。
- **功能记录 (`feature`)**：功能目标、方案设计、实现过程、验证和跨项目复用指南。

一个工作项从创建到结束始终对应**同一个 Markdown 文件**：

- `start-issue` 创建问题记录。
- `start-feature` 创建功能方案/实现记录。
- `checkpoint`、`pause`、`resume` 编辑当前记录。
- 问题使用 `solve` 结案，功能使用 `complete` 完成。
- 只有已解决的问题支持 `reopen`。
- 历史检查点只追加；当前状态和最终内容可以更新。

成功尝试、失败尝试、排除路径、设计决策、方案调整、代码实现和验证结果都属于进展，统一记录为 `checkpoint`。

实际文件操作必须通过 `scripts/bios_worklog.py` 完成。不要直接维护索引或 `.bios-worklog/state.json`。

## 执行约定

1. 将本文件所在目录记为 `SKILL_DIR`，脚本为：

   ```text
   <SKILL_DIR>/scripts/bios_worklog.py
   ```

2. 使用可用的 Python 3：

   ```bash
   python "<SKILL_DIR>/scripts/bios_worklog.py" --json <action> ...
   ```

   Windows 可回退到 `py -3`，其他平台可用 `python3`。

3. 多行或结构化内容应写入系统临时目录中的 UTF-8 JSON 文件，再通过 `--input <file>` 传入；执行后删除临时文件。不要在源码仓库留下输入文件。

4. 成功后报告记录 ID、类型、状态和 Markdown 路径。

5. 用户显式调用动作即授权对应写入，不要无意义地二次确认。仅在以下情况询问：
   - 无法从当前对话确定项目或简短标题；
   - 存在多个候选活动记录；
   - `solve` 缺少根因、解决方法或验证结果；
   - `complete` 缺少最终方案、验证结果或可复用部分；
   - 内容涉及敏感信息或明显互相矛盾。

6. 用户不需要在命令后输入长描述。`start-issue` / `start-feature` 应优先从当前对话提取标题与正文；只补问确实缺失的信息。

7. 不要把模型推测写成已确认事实，不要虚构平台、版本、文件、测试次数或验证结果。

8. 本 Skill 因 BIOS 工作被加载但用户未指定动作时，可先运行一次 `status`：
   - 有活动记录时把它视为当前工作项；
   - `checkpointRecommended: true` 时只在自然停顿点询问是否保存检查点；
   - 没有活动记录时继续工作，不擅自创建记录；
   - 纯 Skill 不运行后台计时器。

## 首次使用

知识库定位优先级：

1. `--root <path>`；
2. `BIOS_WORKLOG_ROOT` 环境变量；
3. 当前目录或祖先目录中的 `.bios-worklog/config.json`；
4. `~/.bios-worklog/config.json` 中的默认目录。

尚未配置时询问目标大文件夹，然后执行：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json init "<知识库目录>"
```

修改提醒间隔：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json configure --reminder-minutes 45
```

结构见 [references/record-format.md](references/record-format.md)。

## 动作路由

| 用户意图 | 动作 |
|---|---|
| 创建问题调查记录 | `start-issue` |
| 创建功能方案/实现记录 | `start-feature` |
| 保存任何工作进展 | `checkpoint` |
| 暂停或切换工作前保存 | `pause` |
| 恢复当前或指定记录 | `resume` |
| 只读引用历史记录 | `context` |
| 问题解决并结案 | `solve` |
| 功能实现完成 | `complete` |
| 已解决问题再次出现 | `reopen` |
| 查看当前记录 | `status` |
| 列出记录 | `list` |
| 搜索历史方案或问题 | `search` |
| 重建目录 | `reindex` |
| 校验知识库 | `validate` / `doctor` |

没有 `adapt` 动作。跨项目参考时用 `context` 读取旧记录，再用 `start-feature` 创建目标项目自己的功能记录，并通过 `related_records` 关联来源。

## `start-issue`

用户只需简短触发，例如：

```text
/skill:bios-worklog start-issue
```

从当前会话提取 `project`、简短 `title` 及初始上下文。JSON 示例：

```json
{
  "project": "Project-A",
  "title": "S3 Resume 后黑屏",
  "description": "系统从 S3 唤醒后仍运行，但内外屏无输出。",
  "environment": {"bios_version": "V1.08", "os": "Windows 11"},
  "reproduction_steps": ["进入睡眠", "按电源键唤醒"],
  "confirmed_facts": ["串口日志继续输出", "复现率 10/10"],
  "current_assessment": "怀疑 Graphics PCI 配置恢复顺序异常，尚未确认。",
  "unknowns": ["BAR 与 Command Register 的顺序是否为直接根因"],
  "next_steps": ["对比正常和异常版本的 PCI Dump"],
  "categories": ["S3", "Display"],
  "tags": ["PCI", "Graphics"],
  "confidence": "hypothesis"
}
```

调用：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json start-issue --input "<start-issue.json>"
```

## `start-feature`

用户只需触发：

```text
/skill:bios-worklog start-feature
```

从当前会话提取功能目标、背景、要求、候选/选定方案和初始下一步。JSON 示例：

```json
{
  "project": "Project-A",
  "title": "实现 BIOS Event Log 导出",
  "objective": "在 BIOS Setup 中把 Event Log 导出到 USB。",
  "background": "现有日志只能逐项查看，不便于提供给其他团队分析。",
  "requirements": ["支持 FAT32", "输出 UTF-8", "不阻塞 Setup"],
  "design": {
    "selected": "独立 Export Protocol + 项目数据适配层",
    "reason": "隔离通用文件写入逻辑与项目数据源"
  },
  "confirmed_facts": ["不同项目的 Event Log 数据结构不同"],
  "current_assessment": "公共导出模块应与 HII Callback 解耦。",
  "unknowns": ["多分区 USB 的筛选策略"],
  "next_steps": ["定义 Protocol", "验证文件系统枚举"],
  "categories": ["Setup", "Logging"],
  "tags": ["HII", "USB"],
  "reusable": true
}
```

调用：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json start-feature --input "<start-feature.json>"
```

两种 start 都会在 `projects/<项目>/records/` 立即创建记录并设为活动记录。

## `checkpoint`

从上次检查点之后的相关对话提取信息，不重复整个历史。问题和功能共用：

```json
{
  "title": "完成文件系统 Handle 筛选",
  "purpose": "避免把内部文件系统误识别为用户 USB。",
  "actions": ["比较设备路径并验证 5 种 USB"],
  "result": "能够稳定筛选 FAT32 USB。",
  "findings": ["不能假设第一个 Simple File System Handle 就是 USB"],
  "evidence": ["设备路径 dump", "测试结果"],
  "impact": "公共模块增加可替换的设备筛选策略。",
  "current_assessment": "文件写入路径已稳定。",
  "unknowns": ["只读介质错误提示"],
  "next_steps": ["验证只读和空间不足场景"]
}
```

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json checkpoint --input "<checkpoint.json>"
```

`--id BIOS-...` 可临时指定记录，否则编辑活动记录。历史只追加；当前状态会同步更新。

## `pause`、`resume` 与 `context`

暂停：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json pause --input "<pause.json>"
```

恢复并设为活动记录：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json resume BIOS-20260324-001 --recent 3
```

只读参考旧问题或旧方案，不改变状态：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json context BIOS-20260324-001 --recent 3
```

使用返回的 `context` 作为权威摘要，不凭空补回旧会话。

## `solve`：问题结案

仅用于 `issue`，至少需要 `root_cause`、`solution`、`validation`：

```json
{
  "root_cause": "S3 Resume 时先恢复 Command Register，设备在 BAR 有效前被使能。",
  "solution": "先恢复 BAR，再恢复 Command Register。",
  "changed_files": ["Platform/PciRestore/PciRestore.c"],
  "validation": ["S3 循环 500 次通过"],
  "regression_scope": ["冷启动", "暖启动"],
  "reusable_lessons": ["Resume 调试需要比较寄存器值和恢复时序"]
}
```

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json solve --input "<solve.json>"
```

验证未完成时用 `checkpoint` 设置 `status: verifying`，不要提前 `solve`。

## `complete`：功能完成

仅用于 `feature`，至少需要：

- `final_design`：最终实现方案；
- `validation`：验证结果；
- `reusable_parts`：可直接供其他项目复用的部分。

推荐同时整理项目相关部分、复用前提和参考实现步骤：

```json
{
  "final_design": "独立 Export Protocol，项目适配层提供 Event Log 数据。",
  "design_decisions": ["Setup Callback 只发起请求，不执行长时间文件操作"],
  "changed_files": ["Common/EventLogExport/", "Platform/EventLogAdapter.c"],
  "validation": ["5 种 FAT32 USB 通过", "5000 条日志导出通过"],
  "reusable_parts": ["文件系统枚举", "UTF-8 格式化", "错误处理"],
  "project_specific": ["Event Log 数据适配器", "HII Form ID 和字符串资源"],
  "prerequisites": ["DXE 阶段可用 Simple File System Protocol"],
  "reference_steps": ["引入公共模块", "实现项目适配器", "接入入口", "完成异常场景验证"],
  "known_risks": ["部分项目安全策略禁止向外部介质写入"],
  "reusable_lessons": ["项目数据源应与通用导出流程分离"]
}
```

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json complete --input "<complete.json>"
```

完成后状态为 `completed`，同一文件中保留全部方案与实现过程。

## `reopen`

仅用于已 `solved` 的问题记录：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json reopen BIOS-20260324-001 --input "<reopen.json>"
```

已完成的功能在另一个项目参考实现时，不修改源记录；使用 `context` 读取，再为目标项目 `start-feature`。

## 搜索、列表和提醒

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json status
python "<SKILL_DIR>/scripts/bios_worklog.py" --json list --type feature
python "<SKILL_DIR>/scripts/bios_worklog.py" --json search "type:feature Event Log Export"
python "<SKILL_DIR>/scripts/bios_worklog.py" --json search "project:Project-A category:S3 resume"
```

搜索支持 `type:`、`project:`、`status:`、`category:`、`tag:`。旧版没有 `type` 的问题记录按 `issue` 处理。

`checkpointRecommended: true` 只表示距上次保存超过阈值，不代表用户没有进展。用户拒绝提醒后，本次会话不要反复询问。

重建与校验：

```bash
python "<SKILL_DIR>/scripts/bios_worklog.py" --json reindex
python "<SKILL_DIR>/scripts/bios_worklog.py" --json validate
python "<SKILL_DIR>/scripts/bios_worklog.py" --json doctor
```

## 内容质量和安全

详细规则见：

- [references/record-format.md](references/record-format.md)
- [references/workflow.md](references/workflow.md)
- [references/bios-categories.md](references/bios-categories.md)

始终遵守：

- 清楚区分事实、假设、未知和最终结论。
- 失败实验应说明验证了什么、影响了哪个判断、何时值得重试。
- 功能记录应说明候选/最终方案、设计原因、模块边界和跨项目复用条件。
- 大日志只记录关键摘录或附件路径，不复制完整聊天。
- 不保存密码、Token、签名密钥、私钥、个人数据或不必要的内部地址。
- 问题/功能 Markdown 是唯一真实来源；INDEX 可重建。
