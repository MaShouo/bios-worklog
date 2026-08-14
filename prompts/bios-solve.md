---
description: 解决并结案当前 BIOS 问题
argument-hint: "[根因、方案或验证补充]"
---
使用 `bios-worklog` skill 执行 `solve`。从当前对话提取根因、解决方法和验证结果；三项任一缺失时不要提前结案，按 skill 规则补问或改记 checkpoint。用户补充：${ARGUMENTS:-无}。
