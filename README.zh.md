# linversion/skills

[English](README.md) | 简体中文

[![skills.sh](https://skills.sh/b/linversion/skills)](https://skills.sh/linversion/skills)

面向 Codex 等 AI Agent 的个人技能集合，覆盖日常效率工具与 AI 生图评估。每个技能都可以单独安装和使用。

## 前置要求

- 安装 [Node.js](https://nodejs.org/)，以便使用 `npx` 安装技能。
- 个别技能有额外运行环境要求，详见对应说明。

## 安装

安装整个技能集合：

```bash
npx skills add linversion/skills
```

也可以只安装需要的技能：

```bash
npx skills add linversion/skills --skill when-will-tibo-reset
npx skills add linversion/skills --skill app-reviews
npx skills add linversion/skills --skill image-score
```

`npx skills` 会发现本机已安装的 Agent，并将技能链接到相应目录，方便后续更新。更多安装选项见 [Skills CLI](https://github.com/vercel-labs/skills)。

## 更新

更新已安装的技能：

```bash
npx skills update
```

也可以只更新单个技能，例如：

```bash
npx skills update app-reviews
```

## 可用技能

### Productivity

#### When will Tibo reset

每小时检查 AIHot 的 Codex 重置动态，发现新事件或已有事件状态更新时，通过来源名为 **When will Tibo reset** 的 macOS 原生通知提醒；也可选择转发到飞书、钉钉或企业微信。首次配置会引导选择中文或英文，以及是否启用 webhook。

- macOS 11+ 和 Python 3；通用版通知辅助 App 已随技能分发，无需安装 Xcode 或 Command Line Tools。首次启动可能需要按 Gatekeeper 提示手动放行并授予通知权限。
- 通知支持持久样式和声音提醒，需在 macOS「系统设置 → 通知」中启用。
- 技能：[`skills/productivity/when-will-tibo-reset`](skills/productivity/when-will-tibo-reset/)

**通知效果**

<p align="center">
  <img src="screenshots/aihot-notification-example.png" alt="When will Tibo reset 的 macOS 通知效果" width="640">
</p>

**macOS 通知设置**

<p align="center">
  <img src="screenshots/tibo-reset-notification-settings.png" alt="When will Tibo reset 的持久通知与声音设置" width="520">
</p>

#### App Reviews

抓取 Google Play 和 iOS App Store 应用评论，并汇总到本地评论看板，适合跟踪多个应用的用户反馈。

- 按应用切换，查看评分、评论总量、地区和语言分布。
- 支持 T1/T2/T3 市场层级，以及时间、星级和地区筛选。
- 支持 CSV 或文本导出，也可查看已保存的离线数据。
- 技能：[`skills/productivity/app-reviews`](skills/productivity/app-reviews/)

**评论看板**

<p align="center">
  <img src="screenshots/app-reviews-dashboard.png" alt="App Reviews 本地评论看板" width="1000">
</p>

### Engineering

#### Image Score

用大语言模型对 AI 生成图片做结构化评估，帮助比较不同模型或提示词的生成结果，并定位可改进之处。

- 按 5 个维度、17 个子项评分：质量、审美、提示词一致性、现实可信度和创意表现。
- 每项评分附理由，输出摘要和完整 JSON，方便复查及对比。
- 支持 OpenAI 兼容接口和 Gemini。
- 技能：[`skills/engineering/image-score`](skills/engineering/image-score/)

在技能目录中运行示例：

```bash
python scripts/judge.py --image output.png --prompt "a cat wearing a spacesuit on Mars"
```
