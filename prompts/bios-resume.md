---
description: 恢复 BIOS 工作记录
argument-hint: "[记录 ID]"
---
使用 `bios-worklog` skill 执行 `resume`。目标记录：${ARGUMENTS:-当前活动记录}。返回并采用脚本提供的权威上下文，不凭空补回旧会话。
