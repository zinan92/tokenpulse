<div align="center">

# ⏱ TokenPulse

**把每日 token 用量做成会"鞭策"你的桌面 widget —— 用得少时让你坐立不安，逼自己把订阅额度榨干。**

[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://python.org)
[![pywebview](https://img.shields.io/badge/UI-pywebview%20%2B%20HTML/CSS-7c3aed.svg)](https://pywebview.flowrl.com)
[![Platform](https://img.shields.io/badge/platform-macOS-black.svg)](https://www.apple.com/macos)
[![Stdlib](https://img.shields.io/badge/deps-stdlib%20only%20(core)-green.svg)](#技术栈)

</div>

---

```
in   本地日志  ~/.claude/projects/**/*.jsonl (Claude) + ~/.codex/sessions/**/*.jsonl (Codex)
   + CodexBar 落盘缓存  session/weekly 真实额度 + models.dev 单价表

out  常驻桌面 goad widget + Telegram 鞭策推送 + CLI 状态
   每项含: 今日 token vs 150M/天目标 · pace 配速 · session/weekly 剩余额度 · today/30d cost · 30d tokens

fail CodexBar 未运行 / 数据 >6h 旧  → 额度显示 "—" / ⚠stale,token 追踪照常工作
fail 模型不在价格表 (如新出的 claude-opus-4-8)  → 家族回退到最新同族费率,而非算成 $0
fail Telegram 凭证缺失  → 跳过推送,不报错
fail 在工作窗口外 (凌晨 / 09:00 前)  → 进入 early 状态,不误判 pace
```

`CodexBar 是里程表（只报原始数字）；TokenPulse 是教练 —— 把数字对着每日目标、算配速、落后时扎你一下。`

## 示例输出

桌面 widget（无边框、置顶、可拖动）。**整个表面随用量变情绪**：落后变冷蓝并扎心文案，超额变炽热发光。

![TokenPulse widget](./screenshots/widget.png)

终端状态：

```bash
$ python3 cli.py
⏱  TokenPulse · 2026-06-15 14:37 · weekday

Claude 🔥 [████████████████░░░░░░] 136M/150M  (91%)  2.41× pace
      plan: session 84%left 4h22m  ·  weekly 71%left 1d0h
Codex  🙂 [████████░░░░░░░░░░░░░░] 54M/150M   need 96M · pace 56M
      plan: session 83%left 10m  ·  weekly 76%left 2d20h

Σ  190M/300M  (63%)
```

Telegram 鞭策（落后 pace 或周额度没跟上时）：

```
⏱ TokenPulse · 20:00 · Sun
Claude 😴 25M/150M — need 125M (pace 110M)
   plan session 99% 4h · weekly 88% 6d2h ⚠落后9%
Σ 38M/300M (12%)

▶ 去把 token 用掉：
resume [codex] 整理GitHub仓库三条管线 · 6h ago
```

## 架构

```
本地日志                              CodexBar 落盘 (~/Library/.../com.steipete.codexbar)
~/.claude/projects/**/*.jsonl  ┐      history/{claude,codex}.json   (session / weekly 额度)
~/.codex/sessions/**/*.jsonl   ┤      model-pricing/models-dev-v1.json  (per-model 单价)
                               │              │
                               ▼              ▼
        ┌──────────────────────────────────────────────────┐
        │  core.py    今日 token + 目标 + pace + mood          │
        │  limits.py  真实 session/weekly 额度 (+ 周配速)        │
        │  cost.py    today/30d cost + 30d tokens (models.dev) │
        └───────────────────────┬──────────────────────────┘
                                ▼  webdata.py  (合并成一个 payload)
        ┌───────────────┬───────────────┬──────────────┬───────────────┐
        ▼               ▼               ▼              ▼
   webwidget.py      nudge.py        cli.py        furnace.py
   web/widget.html   (Telegram 推送)  (终端状态)    (可选·自动烧额度)
   常驻 goad widget                                 fuel.py (取料)
```

数据口径逐字段验证：

- **Token 计数** — Claude 按 `(message.id, requestId)` 去重（修正 transcript 重复写入导致的虚高，~485M → 真实 ~200M）；Codex 按 session UUID 去重、累加每轮 `last_token_usage`。
- **成本** — `tokens × models.dev 单价`，**直连 [models.dev](https://models.dev) 拉价格表**（每日本地缓存），新模型缺表时家族回退到最新同族费率。**不依赖 CodexBar**。
- **真实额度** — **Codex** 的 5h/周 % 直接读本地 `~/.codex` session 的 `payload.rate_limits`，无需 CodexBar。**Claude** 的 5h/周/opus % 只在 Anthropic 的 OAuth 接口里（token 需刷新、自己刷有把你登出 Claude Code 的风险），所以**当 CodexBar 在跑时**读它落盘的结果；没装也行，Claude 那两栏显示 `—`，其它全正常。**CodexBar 是可选增强，不是必需。**

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/zinan92/tokenpulse.git
cd tokenpulse

# 2. 依赖：core/cli/nudge 纯 stdlib；只有 web widget 需要 pywebview
pip3 install --user pywebview

# 3. 终端看今日状态（最轻量，零额外依赖）
python3 cli.py

# 4. 启动桌面 goad widget（无边框置顶，可拖动）
python3 webwidget.py

# 5. (可选) 装成 launchd 常驻 + Telegram 定时鞭策
#    见 com.tokenpulse.{widget,nudge} 两个 LaunchAgent
```

> **CodexBar 可选**（[steipete/codexbar](https://github.com/steipete/codexbar)）：只用于 **Claude** 的 session/weekly % 那两栏。没装也能跑——token、cost、Codex 额度全部正常，Claude 额度那两栏显示 `—`。

## 功能一览

| 功能 | 说明 | 状态 |
|------|------|------|
| 今日 token 追踪 | Claude + Codex 两 plan，去重 | ✅ |
| pace 配速 + mood | 本地 24h 为窗口算"该到哪 vs 实际到哪"，落后/达标/超额状态机 | ✅ |
| 真实 session/weekly 额度 | Codex 直读本地；Claude 经可选 CodexBar；带重置倒计时 + 周配速 | ✅ |
| today/30d cost + 30d tokens | models.dev 单价**直连**，新模型家族回退 | ✅ |
| **🥚 egg 等级 + 徽章 + 战绩卡** | 按月用量孵化等级、streak、可分享 PNG（`badges.py` / `card.py`） | ✅ |
| goad widget (web) | 暗色、drenched 状态反应、count-up、达标 flare、点开详情面板 | ✅ |
| Telegram 鞭策 | 落后 pace 或周额度没跟上时推 | ✅ |
| 终端 CLI | `--json` / `--sessions` | ✅ |
| furnace 自动烧额度 | 落后时无人值守派一个队列/循环作业给更落后的 plan | ⚙️ 默认关闭 |

## 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 引擎 | Python 3.13 **纯 stdlib** | 日志提取、目标/配速、成本计算（core/limits/cost/cli/nudge 零依赖） |
| Widget UI | `pywebview` (Cocoa WebKit) + HTML/CSS/JS | 无边框置顶 goad 窗口，~100–200MB，远轻于 Electron |
| 数据源 | CodexBar 落盘文件 | session/weekly 真实额度 + models.dev 价格缓存 |
| 常驻 | macOS `launchd` (framework python) | widget + nudge 两个 LaunchAgent |
| 通知 | Telegram Bot API (openclaw `wendy` bot) | 鞭策推送 |

## 项目结构

```
tokenpulse/
├── core.py            # 引擎：token 提取 + 每日目标 + pace + mood
├── limits.py          # 真实 session/weekly 额度（CodexBar feed）
├── cost.py            # today/30d cost + tokens（models.dev 定价 + 家族回退）
├── sessions.py        # 最近 5 天 Claude/Codex 会话 →「去 resume 这个」
├── webdata.py         # 合并 core/limits/cost → widget 的 JSON 桥
├── webwidget.py       # pywebview 宿主（无边框置顶）
├── web/widget.html    # goad UI：状态反应配色 + 动效（自包含 HTML/CSS/JS）
├── widget.py          # 旧版 Tkinter widget（已被 web 版取代）
├── nudge.py           # Telegram 鞭策（落后时）
├── furnace.py / fuel.py   # 可选：无人值守自动烧额度
├── cli.py             # 终端状态
├── config.json        # 目标 / 工作窗口 / checkpoints / 阈值 / furnace 开关
└── tests/             # pytest（42 passing）
```

## 配置

`config.json`：

| 字段 | 说明 | 默认 |
|------|------|------|
| `targets.{claude,codex}.{weekday,weekend}` | 每日 token 目标（百万） | `150` |
| `active_window` | pace 配速的"工作窗口"，窗外进 early 态 | `09:00–23:59` |
| `day_boundary` | 日界：`local`（你的时区）或 `utc`（贴 CodexBar） | `local` |
| `checkpoints` | Telegram 推送时间点 | `15:00 / 20:00 / 23:00` |
| `plan_behind_threshold` | 周额度落后多少个百分点才算"落后"并触发推送 | `10` |
| `furnace.enabled` | 自动烧额度总开关（kill switch） | `false` |

## For AI Agents

TokenPulse 是**本机 CLI / 桌面工具**，不暴露 HTTP API。要把它当数据源用，直接调 CLI 或 import 模块。

### Capability Contract

```yaml
name: tokenpulse
capability:
  summary: Track daily token usage across Claude Code + Codex subscription plans and goad the user to use more.
  in: local logs (~/.claude/projects, ~/.codex/sessions) + CodexBar's on-disk feed (plan limits + models.dev prices)
  out: always-on-top "goad" desktop widget + Telegram nudges + CLI status (today tokens vs target, pace, session/weekly %, cost)
  fail:
    - "CodexBar not running / data >6h stale → plan limits show — / ⚠stale; token tracking still works"
    - "model missing from price table → family fallback to latest sibling's rate (not $0)"
    - "Telegram creds missing → nudge skips, no error"
    - "outside active window (overnight/pre-09:00) → 'early' state, no false pace verdict"
cli_command: python3 cli.py
cli_flags:
  - name: --json
    type: boolean
    description: emit the full status payload as JSON instead of the terminal view
  - name: --sessions
    type: boolean
    description: list recent resumable Claude/Codex sessions
programmatic_entry: "import webdata; webdata.core_payload()  # merged goal/pace/limits dict; webdata.cost_payload() for cost"
install_command: "pip3 install --user pywebview   # only needed for the web widget; core/cli/nudge are stdlib"
start_command: "python3 webwidget.py   # widget  ·  python3 cli.py   # status  ·  python3 nudge.py   # telegram"
requires: "nothing external for core (tokens/cost via models.dev, Codex limits local); CodexBar optional, only for Claude's session/weekly %"
```

### Agent 调用示例

```python
import subprocess, json

# 拿今日状态的结构化数据
out = subprocess.run(["python3", "cli.py", "--json"], cwd="~/work/tokenpulse",
                     capture_output=True, text=True).stdout
status = json.loads(out)
combined = status["status"]["combined"]   # {today, target, percent, ...}
if combined["today"] < combined["expected"]:
    print(f"Behind pace: {combined['today']/1e6:.0f}M of expected {combined['expected']/1e6:.0f}M")

# 或直接 import（同目录）
import webdata
core = webdata.core_payload()             # 目标/配速/额度
cost = webdata.cost_payload()             # today/30d cost + tokens
```

## License

Private / personal use.
