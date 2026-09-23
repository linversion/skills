---
name: when-will-tibo-reset
description: 在 macOS 上安装、配置和管理 AIHot Codex 重置动态监控。每小时轮询 aihot.news API，识别新增事件和已有事件的状态更新，用 macOS 系统通知提醒，并可选转发到飞书、钉钉或企业微信机器人 webhook。用户提到 AIHot、Codex 重置动态、额度重置提醒、每小时监控、系统通知、飞书/钉钉/企业微信 webhook 通知，或希望查看、测试、停止这项监控时，都应使用此 skill。
---

# When will Tibo reset

## 首次使用引导

先从本次加载的 `SKILL.md` 文件绝对路径确定其父目录，并将它作为 `SKILL_DIR`；每次调用都应使用当前安装位置展开后的绝对脚本路径，不要假设当前工作目录，也不要把某位用户的路径写死。首次安装前运行 `python3 "$SKILL_DIR/scripts/manage.py" status` 查看是否已有初始化配置。

该技能需要 macOS 11 或更新版本和 Python 3；其余 Python 代码只使用标准库。通用版通知辅助 App 已随 skill 放在 `assets/When will Tibo reset.app`，安装时会复制到用户的 `~/Library/Application Support/AIHot Codex Reset Monitor/runtime/`，因此用户不需要安装 Xcode 或 Command Line Tools。通知来源的显示名固定为 `When will Tibo reset`。首次安装前确认这个内置 App 存在且完整；若资源缺失，提示用户重新获取完整 skill，不要改为在用户机器上编译。

此 App 当前使用 ad-hoc 签名且尚未公证。若 macOS 在首次运行时通过 Gatekeeper 拦截，说明来源并引导用户自行确认后，在“系统设置 → 隐私与安全性”中选择“仍要打开”；不要静默绕过系统安全检查。首次发送通知时还需用户单独允许通知。

若没有已初始化的基线，且用户尚未说明偏好，用一条简短提示引导用户选择：

1. 通知语言：中文或 English。macOS 通知和 webhook 正文都会使用所选语言；动态原文来自接口的 `text` / `originalText` 字段。
2. 是否启用 webhook：若用户选择启用，询问要连接飞书、钉钉、企业微信中的哪些渠道；请求用户提供url，说明默认方式是关键词Tibo。

拿到选择后再配置并安装。通过 `configure --language zh` 或 `configure --language en` 保存语言；不要在公开回复或日志里回显 webhook URL。用户已经明确提供偏好时直接使用，不要重复询问。已有监控配置时保留已保存的语言、webhook 和关键词，日常查看、测试或停止时不要重新展示首次使用引导。

首次配置会生成一个随机 actor UUID，保存在该用户的本地配置中并用于 API 请求头；它不依赖 Codex 账号，也不应复用技能作者的 actor UUID。该值不需要向用户展示。

3. (必须)配置完之后请求最新的数据，测试一次用户的通知渠道是否正常，如不正常则帮用户适配，直到测试通过才停止，必要时可通过电脑操作验证结果。

4. 提醒用户：需要通知一直保留到用户关闭时，在“系统设置 → 通知 → When will Tibo reset”中选择“持久”通知样式并开启声音。

5. 拉取一次数据建立基线，并通知最新一条让用户看到效果。

## 操作入口

先定位本 skill 目录，再运行：

```bash
python3 "$SKILL_DIR/scripts/manage.py" <command>
```

### 安装或重新启用

```bash
python3 "$SKILL_DIR/scripts/manage.py" install
python3 "$SKILL_DIR/scripts/manage.py" install --language en
```

安装会先访问一次接口建立基线，再注册每 3600 秒执行一次的 LaunchAgent。成功后告诉用户：已建立基线、定时任务是否已加载、Webhook 当前是否启用。

### 查看状态

```bash
python3 "$SKILL_DIR/scripts/manage.py" status
```

状态输出显示当前语言及各渠道是否已配置，不会显示 webhook URL。

### 立即检查

```bash
python3 "$SKILL_DIR/scripts/manage.py" check
```

### 测试通知渠道

```bash
python3 "$SKILL_DIR/scripts/manage.py" test-notification
python3 "$SKILL_DIR/scripts/manage.py" test-notification --channel feishu
```

不指定 `--channel` 时，会向所有已启用渠道发送一条明确标注为“测试”的消息；指定后只测试该渠道。测试不修改事件基线。

### 配置 webhook

Webhook URL 属于敏感信息。优先让用户把地址放入临时环境变量，再执行配置；不要在最终回复、状态输出或日志中回显完整 URL。

```bash
python3 "$SKILL_DIR/scripts/manage.py" configure --language zh
python3 "$SKILL_DIR/scripts/manage.py" configure --language en
AIHOT_FEISHU_WEBHOOK='https://...' python3 "$SKILL_DIR/scripts/manage.py" configure
AIHOT_DINGTALK_WEBHOOK='https://...' python3 "$SKILL_DIR/scripts/manage.py" configure
AIHOT_WECOM_WEBHOOK='https://...' python3 "$SKILL_DIR/scripts/manage.py" configure
```

```bash
AIHOT_FEISHU_WEBHOOK='https://...' AIHOT_FEISHU_KEYWORD='Tibo' python3 "$SKILL_DIR/scripts/manage.py" configure
```

也支持显式参数 `--feishu-webhook`、`--dingtalk-webhook`、`--wecom-webhook`，关键词参数 `--feishu-keyword`、`--dingtalk-keyword`、`--wecom-keyword`，以及清除参数 `--clear-feishu`、`--clear-dingtalk`、`--clear-wecom`。只有用户明确提供或要求启用某渠道时才配置它。

关闭或重新开启系统通知：

```bash
python3 "$SKILL_DIR/scripts/manage.py" configure --disable-macos
python3 "$SKILL_DIR/scripts/manage.py" configure --enable-macos
```

配置后建议运行 `test-notification`。第一次发送时 macOS 可能请求通知权限；应让用户允许“When will Tibo reset”。如果没有显示通知，提醒用户在“系统设置 → 通知”中检查该应用，并查看 `monitor.stderr.log`。


### 停止与卸载

```bash
python3 "$SKILL_DIR/scripts/manage.py" stop
python3 "$SKILL_DIR/scripts/manage.py" install
python3 "$SKILL_DIR/scripts/manage.py" uninstall
```

`uninstall` 只移除 LaunchAgent，保留配置和状态，便于恢复。只有用户明确要求清除本地数据时才使用：

```bash
python3 "$SKILL_DIR/scripts/manage.py" uninstall --purge
```

## 结果汇报

用简短的“已完成 / 尚未启用或需用户处理”汇报。区分以下证据：

- 脚本和配置已生成；
- 接口基线已成功获取；
- LaunchAgent 已加载；
- 测试消息已由脚本提交；
- 用户是否实际在通知中心或群聊中看到消息。

脚本返回成功只证明系统或 webhook 接受了发送请求，不能声称用户已经看到通知。
