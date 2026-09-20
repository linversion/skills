# Skills

我的 Agent 技能集合（OpenClaw / Claude Code / Codex 等通用）。

## 安装

```bash
npx skills add linversion/skills
```

[npx skills](https://github.com/vercel-labs/skills) 会自动检测本机已装的 Agent，并把技能以 symlink 方式装到对应目录，便于后续更新。

也可以按需手动复制或软链单个技能目录（如 `skills/app-reviews/`）到 `~/.agents/skills/` 或项目的 `.agents/skills/` 下。

## 目录

| 技能 | 说明 |
|------|------|
| [image-score](skills/image-quality/image-score/) | AI 生图结构化评分，5 维度 17 项 |
| [app-reviews](skills/app-reviews/) | 应用评论抓取 + 本地看板（Google Play / iOS App Store）：多应用切换、T1/T2/T3 市场层级、时间/星级/地区筛选、CSV/文本导出、离线模式 |

## 使用

每个技能目录下包含 `SKILL.md`（给 Agent 的说明文档）、`references/`（参考文档）和可执行脚本。
