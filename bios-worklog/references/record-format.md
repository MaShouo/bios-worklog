# 问题记录格式

## 知识库目录

```text
<BIOS-KnowledgeBase>/
├── README.md
├── INDEX.md                         # 自动生成
├── projects/
│   └── <project-slug>/
│       ├── .project.json            # 项目显示名称
│       ├── INDEX.md                 # 自动生成
│       └── issues/
│           └── BIOS-YYYYMMDD-NNN-<title>.md
└── .bios-worklog/
    ├── config.json
    └── state.json
```

每个问题只有一个 Markdown 文件。问题解决后不移动文件，避免历史链接失效。

## Front matter

脚本管理以下字段：

| 字段 | 说明 |
|---|---|
| `id` | 全局唯一 ID，如 `BIOS-20260324-001` |
| `project` | 项目显示名称 |
| `title` | 问题标题 |
| `status` | `investigating` / `paused` / `verifying` / `solved` |
| `created` | 创建时间（带时区 ISO 8601） |
| `updated` | 最后一次文件状态更新 |
| `resolved` | 结案时间，仅 solved 时存在 |
| `categories` | BIOS 分类列表 |
| `tags` | 自由标签列表 |
| `confidence` | `unknown` / `hypothesis` / `probable` / `confirmed` |

## 正文区域

问题文件固定包含：

1. `问题描述`
2. `环境`
3. `复现步骤`
4. `当前状态`
   - 已确认事实
   - 当前判断
   - 尚未确认
   - 下一步
5. `调查记录`
6. `最终结论`
   - 根因
   - 解决方法
   - 修改文件
   - 修改原理
   - 验证结果
   - 回归范围
   - 已知风险
   - 可复用经验
7. `相关记录`

脚本通过下列 HTML 注释定位受管理区域：

```markdown
<!-- BIOS-WORKLOG:CURRENT:START -->
...
<!-- BIOS-WORKLOG:CURRENT:END -->
```

不要删除、复制或重命名这些标记。允许在受管理区域外添加人工说明；重新生成 INDEX 不会覆盖问题文件。

## 当前状态与调查历史

- **当前状态**是恢复上下文时的最新摘要，可以被 checkpoint 更新。
- **调查记录**是不可变历史，只追加新检查点。
- 旧假设被推翻时不删除旧记录，而是在新检查点记录证据和判断变化。

检查点建议包含：

```markdown
### YYYY-MM-DD HH:MM — 标题

#### 目的

#### 操作

#### 结果

#### 得到的信息

#### 证据与参考

#### 对当前判断的影响

#### 下一步
```

不是每次都必须填写所有小节，但至少应有“结果”或“得到的信息”。

## 状态语义

- `investigating`：正在定位、修改或准备验证。
- `paused`：已保存可恢复检查点，暂时停止。
- `verifying`：已有候选修复，但回归验证未完成。
- `solved`：根因、解决方法和验证结果均已明确，并由用户手动结案。

## 数据真实性

Markdown 问题文件是唯一真实来源。以下文件都属于辅助数据：

- `INDEX.md`：可用 `reindex` 重建；
- `.bios-worklog/state.json`：只记录每个工作区的活动问题；
- `.bios-worklog/config.json`：知识库配置。
