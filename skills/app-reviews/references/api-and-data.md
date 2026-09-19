# reference — 文件、接口契约与数据格式

## 文件清单

下表 `<skill目录>` 指本 Skill 所在目录（SKILL.md 的同级目录）。Skill 完全自包含，与任何仓库解耦。

| 文件 | 角色 |
|------|------|
| `<skill目录>/scripts/serve_reviews.py` | 本地服务：静态托管 `assets/` + `GET /api/scrape` 抓取接口（Android/iOS 双平台）；页面「拉取最新」按钮调它。看板/数据路径全部由脚本自身位置解析，任意目录启动均可 |
| `<skill目录>/scripts/scrape_play_reviews.py` | Android CLI 抓取（产出 CSV）；`T1/T2/T3_MARKETS` 与 `MARKET_TIERS` 定义市场层级，增删市场改这里（两平台共用） |
| `<skill目录>/scripts/scrape_app_store.py` | iOS CLI 抓取（iTunes RSS，产出同格式 CSV）；bundleId 自动解析为数字 id |
| `<skill目录>/scripts/csv_to_reviews_js.py` | CSV → data.js 转换 |
| `<skill目录>/assets/dashboard/index.html` + `app.js` | 看板前端（纯 HTML/JS，零依赖，筛选/排序/搜索均为前端行为） |
| `<skill目录>/assets/dashboard/apps/index.json` | 应用索引：多包切换器的数据源，最近更新在前 |
| `<skill目录>/assets/dashboard/apps/<app_id>.json` | 每个应用的完整评论数据（互不覆盖） |
| `<skill目录>/assets/dashboard/data.js` | 全部应用的**内联镜像**（`window.REVIEWS_APPS`）；`file://` 双击打开亦可切包/筛选/导出（顶部显示离线横幅），仅「拉取最新」需服务器 |
| `<skill目录>/assets/csv/<app>.csv` | 原始持久层（每包一个文件） |

服务器 URL：`http://localhost:<port>/dashboard/index.html`（静态根 = `assets/`）。

## /api/scrape 契约

- 请求：`GET /api/scrape?app=<标识>[&platform=<android|ios>][&tier=<t1|t2|t3>][&count=<每国上限，默认 3000>]`
- `platform`：默认 `android`。iOS 时 `app` 传数字 App id 或 bundleId（bundleId 自动经 lookup 解析，落盘统一用数字 id）
- `tier` 市场层级（累积语义，默认 `t1`，两平台共用同一国家表）：
  - **t1（8 国）**：us en · gb en · ca en · au en · de de · fr fr · jp ja · kr ko
  - **t2（26 国，= T1+T2）**：+ nl/be `nl` · at/ch `de` · ie/nz/sg/ae `en` · it `it` · es `es` · pt `pt` · pl `pl` · se `sv` · no `no` · dk `da` · fi `fi` · tw/hk `zh-tw`
  - **t3（43 国，= T1+T2+T3）**：+ br `pt` · mx/ar/cl/co `es` · in/my/ph/za/eg/ng `en` · id `id` · th `th` · vn `vi` · tr `tr` · ru `ru` · sa `ar`
- 响应：NDJSON 流，逐行 JSON：
  - `{"type":"start","tier":"t2","markets":26,"platform":"ios"}`
  - `{"type":"progress","country":"de","got":54,"new":54,"total":926}`（`error` 字段出现表示该国失败，继续其余国家）
  - `{"type":"fatal","message":"…"}` 整体失败（含**全部国家都抓取失败**的情况——服务器会以 fatal 报网络问题，而不是带着 0 条评论假成功）
  - `{"type":"done","payload":{"app_id","platform","title","generated_at","reviews":[…]}}` 结束（`title` 为商店应用名，拉取失败时退回标识）
- done 时服务器已持久化：per-app **upsert**——写该包 CSV + `apps/<id>.json` 并刷新 `apps/index.json`，其他已有包不受影响；另镜像一份到 data.js。payload 体积可达数百 KB，勿整行打进上下文；过滤必须用 ERE（`grep -vE '"type": ?"done"'`），BRE 下 `?` 是字面量、滤网不生效。
- 页面「拉取最新」按钮旁的市场下拉与 `tier` 参数联动，默认 T1。

## 数据格式

- CSV 列：`reviewId, countries(|分隔), primary_country, score, content, reviewCreatedVersion, at, thumbsUpCount, userName, replyContent, repliedAt`
- payload/apps JSON：`{ app_id, platform, title, source_csv, generated_at, reviews:[同 CSV 列的 JSON] }`
- data.js：`window.REVIEWS_APPS = { apps:[{app_id, platform, title, total, generated_at, data:<同 payload>}] }`（内联多包镜像）

## iOS (App Store) 机制

- 数据源为苹果官方 iTunes RSS：`https://itunes.apple.com/{country}/rss/customerreviews/page={n}/id={appid}/sortby=mostrecent/json`，免登录。
- 应用解析：`https://itunes.apple.com/lookup?id=<数字id>`（或 `?bundleId=`）；名称搜索 `https://itunes.apple.com/search?term=…&entity=software&country=us`。
- **各国 storefront 真实隔离**：每个国家 feed 独立，不存在安卓的同语言池现象，`countries` 通常是单值。
- **每国上限 500 条**（RSS 仅暴露 10 页 × 50 条，`count` 再大也取不满）。
- 无开发者回复、无点赞数（`replyContent`/`thumbsUpCount` 恒空/0）；评论标题与正文合并进 `content`（换行分隔）。
- 小众应用可能全商店零评论（各国空返回且无 error）——用 lookup 确认应用存在后如实告知，不算失败。

## 备用抓取（服务器起不来时）

```bash
# Android
python3 <skill目录>/scripts/scrape_play_reviews.py <包名> 3000 [--tier t2]   # → <skill目录>/assets/csv/<app>.csv, 默认 tier=t1
# iOS
python3 <skill目录>/scripts/scrape_app_store.py <App数字id或bundleId> 500 [--tier t2]
# 转 data.js（离线镜像；服务器模式下 persist 已自动做）
python3 <skill目录>/scripts/csv_to_reviews_js.py <上述csv> <skill目录>/assets/dashboard/data.js --app <标识>
```

完成后仍执行步骤 4 的前端验证。

## 行为与坑

- **范围边界**：支持 Android（Google Play）与 iOS（App Store）。命令链（`lsof`/`ps`/`nohup`/`curl`）为 macOS/Linux 语法，Windows 需 WSL 或等效命令。
- **数据不入库**：抓取产生的 `assets/csv/`、`assets/dashboard/apps/`、`assets/dashboard/data.js` 均为运行时状态，已 gitignore；新克隆里首次抓取（或拖入 CSV）后自动生成，之前看板显示空状态引导。
- **网络前提**：抓取需可访问 play.google.com（Android）/ itunes.apple.com（iOS，国内通常可直连）；前者不可达时全部国家报错、服务器返回 fatal。
- **多包并存**：抓新包 upsert 自己的数据，不覆盖其他包；页面顶部下拉可切换，报告头大标题为应用名称（包名退到小字），地区口径显示"语言池 N · M 国"。层级选择按应用记忆在浏览器 localStorage。
- **看板筛选**：时间快捷档（近7/30/90天 + 自定义起止）与星级/地区/搜索/仅看回复叠加；评分条与地区面板计数为**上下文统计**（排除自身维度、应用其余筛选），报告头五格恒为全量。
- **导出**：工具栏「导出 CSV」（带 BOM，Excel 直开）与「复制文本」（纯文本可直接粘贴到 IM），均为当前筛选所见，文件名带应用名+筛选条件+日期。
- **评论池按语言切分（仅 Android）**：同语言国家返回完全相同的评论集合（如 t1 的 us/gb/ca/au，t2 里 at/ch 与 de 也同池），页面以 ≈ 标注同池；区分地区靠 `lang` 而非 `country`。iOS 无此现象（见 iOS 机制节）。
- 每国间隔 2 秒防限流，约 5 秒/国；T3 新兴市场评论池普遍很浅（几十条即见底）。`count` 超过实际池深时返回该池全部。
- 页面支持拖入 CSV 直接加载（仅内存，不落盘）；`file://` 双击打开走内联 data.js 离线模式（顶部横幅提示），「拉取最新」自动禁用。
- 端口 4318 被非本服务占用：换端口跑 `python3 <skill目录>/scripts/serve_reviews.py <port>`，探活与页面 URL 随之替换。
