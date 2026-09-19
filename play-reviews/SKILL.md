---
name: play-reviews
description: 抓取 Google Play 应用评论并展示到本地评论看板（前后端联动）。当用户想抓取/爬取/更新某应用或某包名的评论、查看某 app 的评论数据或评分时使用。
---

# Play 评论抓取 + 看板展示

把任意 Android 包名的评论抓取落盘，并让本地评论看板展示它。本 Skill **完全自包含**：脚本在 `<skill目录>/scripts/`、看板与全部数据在 `<skill目录>/assets/`（`<skill目录>` = 本 SKILL.md 所在目录），与任何仓库解耦，命令可在任意工作目录执行。文件清单、接口契约、备用路径与坑见 [references/api-and-data.md](references/api-and-data.md)。

## 步骤

### 1. 确定包名

从用户请求中提取 Android 包名（形如 `com.company.app`；也接受 Play 商店链接，取 `/store/apps/details?id=` 的参数值）。**用户只给了应用名**（既无链接也无包名）时，用商店搜索解析再让用户确认：

```bash
python3 -c "
from google_play_scraper import search
for r in search('<应用名>')[:8]:
    print(r['appId'], '|', r['title'], '|', r['developer'])
"
```

**完成判据**：包名合法且无歧义；搜索出多个候选时把列表给用户选，用户确认前不进入下一步。

### 2. 后端就位

先查依赖（缺失则装，一次性）：

```bash
python3 -c "import google_play_scraper" 2>/dev/null || pip3 install google-play-scraper
```

再探活两项检查：

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:4318/dashboard/index.html   # 期望 200
ps -p "$(lsof -ti:4318)" -o command= | grep serve_reviews    # 期望有输出
```

任一不通过则后台启动：`nohup python3 "<skill目录>/scripts/serve_reviews.py" 4318 >/tmp/reviews-server.log 2>&1 &`，一秒后重查。重查仍失败时看 `/tmp/reviews-server.log`：报 `Address already in use` 说明 4318 被非本服务进程占用——`kill "$(lsof -ti:4318)"` 后重试，或换端口启动（后续 URL 同步替换）。

**完成判据**：两项检查同时通过。

### 3. 抓取并落盘

市场层级 `tier`：`t1`（默认，8 国）/ `t2`（T1+T2，26 国）/ `t3`（T1~T3 全部，43 国），累积语义。用户没提层级就用 t1；明确要"更多国家/新兴市场"时按需升到 t2/t3。耗时约 5 秒/国（t1≈40s，t2≈2 分钟，t3≈4 分钟），`--max-time` 相应放大。

```bash
curl -sN --max-time 600 "http://localhost:4318/api/scrape?app=<包名>[&tier=t2]" | grep --line-buffered -vE '"type": ?"done"'
```

流式返回逐国 progress 行，把进展转述给用户；grep 滤掉 done 行以避免巨量 payload 涌入上下文（必须用 `-E`：`?` 只有在 ERE 里才是量词，BRE 下它是字面量、滤网失效）。done 触发时服务器已自动落盘该包的 CSV 与看板数据（多包 upsert，不影响已有包）——无需再手动转换。

**完成判据**：`grep -o '"app_id": "[^"]*"' "<skill目录>/assets/dashboard/apps/index.json" | head -1` 含新包名，progress 累计总数 **> 0**，且流中无 `fatal`。总数为 0 或出现 `fatal` 即为失败：`fatal` 报网络问题时告知用户需可访问 play.google.com（国内网络通常需要代理），不要交付空结果。服务器不可用时改走备用抓取（见 [references/api-and-data.md](references/api-and-data.md) → 备用抓取）。

### 4. 前端展示验证 + 给出本地链接

浏览器经 HTTP 打开（必须走服务器，`file://` 拿不到数据）`http://localhost:4318/dashboard/index.html`，刷新页面，切换到刚抓取的应用。

**完成判据**：页面报告头大标题为该应用的商店名称（包名在小字行）、顶部切换器里含该应用、去重评论总数与 progress 累计一致。最终回复**必须**附上可点击的本地链接（markdown 格式，如 `http://localhost:4318/dashboard/index.html`；换过端口则用实际端口），并汇报总数、平均分、各地区条数（标注 ≈ 同池关系）与评分分布——使用者不该自己去猜看板在哪。
