# 工作记录格式

## 知识库目录

```text
<BIOS-KnowledgeBase>/
├── README.md
├── INDEX.md                         # 自动生成
├── projects/
│   └── <project-slug>/
│       ├── .project.json            # 项目显示名称
│       ├── INDEX.md                 # 自动生成
│       └── records/
│           ├── BIOS-...-issue.md
│           └── BIOS-...-feature.md
└── .bios-worklog/
    ├── config.json
    └── state.json
```

每个问题或功能只有一个 Markdown 文件，结束后不移动文件，避免历史链接失效。

旧版 `projects/<项目>/issues/*.md` 仍可读取和更新，不要求立即迁移；新记录统一创建在 `records/`。

## Front matter

| 字段 | 说明 |
|---|---|
| `id` | 唯一 ID，如 `BIOS-20260324-001` |
| `type` | `issue` 或 `feature`；旧记录缺失时按 `issue` |
| `project` | 项目显示名称 |
| `title` | 简短标题 |
| `status` | 见下方状态语义 |
| `created` / `updated` | 创建及更新时间 |
| `resolved` | 问题结案时间 |
| `completed` | 功能完成时间 |
| `reusable` | 是否包含可供其他项目参考的内容 |
| `categories` / `tags` | 分类和自由标签 |
| `confidence` | `unknown` / `hypothesis` / `probable` / `confirmed` |

## 问题记录正文

1. 问题描述
2. 环境
3. 复现步骤
4. 当前状态
5. 调查记录
6. 最终结论
   - 根因
   - 解决方法
   - 修改文件与原理
   - 验证和回归
   - 风险与经验
7. 相关记录

## 功能记录正文

1. 功能目标
2. 背景
3. 需求与约束
4. 方案设计
5. 当前状态
6. 实施记录
7. 最终成果与复用指南
   - 最终方案
   - 设计决策与原因
   - 修改内容
   - 验证结果
   - 可直接复用部分
   - 项目相关部分
   - 复用前提
   - 参考实现步骤
   - 限制、风险与经验
8. 相关记录

## 受管理区域

脚本通过 HTML 注释定位内容，例如：

```markdown
<!-- BIOS-WORKLOG:CURRENT:START -->
...
<!-- BIOS-WORKLOG:CURRENT:END -->
```

不要删除、复制或重命名这些标记。允许在受管理区域外补充人工说明。

## 状态语义

### Issue

- `investigating`：正在调查或修改。
- `paused`：已保存检查点，暂时停止。
- `verifying`：已有候选修复，验证未完成。
- `solved`：根因、解决方法和验证均明确。

### Feature

- `implementing`：正在设计或实现。
- `paused`：已保存检查点，暂时停止。
- `verifying`：实现基本完成，验证未完成。
- `completed`：最终方案、验证和复用信息已整理。

## 当前状态与历史

- 当前状态是跨会话恢复所用的最新摘要，可以更新。
- 调查/实施记录是历史，只追加。
- 旧判断或设计被推翻时，在新 checkpoint 说明原因，不删除旧记录。

检查点建议包含：目的、操作、结果、得到的信息、证据、对当前判断/方案的影响、下一步。

## 数据真实性

记录 Markdown 是唯一真实来源；`INDEX.md`、状态和配置均为辅助数据。目录可以用 `reindex` 重建。
