# 更新日志

## 0.3.0 - 2026-09-23

### 新功能

- 新增 `When will Tibo reset` 技能：每小时监控 AIHot Codex 重置动态，发送 macOS 原生通知，并可选转发到飞书、钉钉或企业微信。
- 随技能分发通用版 macOS 通知辅助 App，用户无需安装 Xcode 或 Command Line Tools。

### 文档

- 将技能整理到 Productivity 和 Engineering 分类；README.md 默认使用英文，并新增可切换语言的中文版和效果截图。

## 0.2.0 - 2026-09-19

### 新功能

- release-skills 发布为正式技能（通用发布工作流：版本升级、双语 CHANGELOG、打标、推送）

## 0.1.0 - 2026-09-19

### 新功能

- 新增 image-score 技能：AI 生图结构化评分，5 维度 17 项
- 新增 app-reviews 技能：应用商店评论抓取（Google Play 与 iOS App Store 双平台）+ 本地看板 — 多应用存储与切换、T1/T2/T3 市场层级、iOS 按国家 storefront 独立抓取（每国上限 500 条）、语言池同池检测、时间/星级/地区/搜索筛选、CSV/文本导出、离线模式
- 仓库目录结构兼容 `npx skills add linversion/skills` 安装
