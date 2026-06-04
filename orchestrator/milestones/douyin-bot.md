# Milestone: 抖音 Newsletter 机器人

> ① 这是你的活 —— 下面是我的草稿，**请直接改**：success criteria 是否够准、
> 博主列表、产物落哪、用什么转录。改完它就是 GSD 分解的输入。

## Objective
自动监控我关注的抖音博主，新视频发布后自动下载、转录、用 AI 处理成 newsletter
素材，无人工干预。

## Success criteria（什么时候算 done）
- [ ] 配置 3–4 个博主，系统每 N 小时检查更新（N 可配）
- [ ] 检测到**新**视频（不重复处理旧的）
- [ ] 自动下载视频 + 抽取音频
- [ ] 转录成带时间戳的文字
- [ ] AI 把转录处理成结构化 newsletter 条目（摘要 / 要点 / why it matters）
- [ ] 产物落到指定位置（_待定：文件 / Lark / Notion？_）+ Telegram 通知
- [ ] 端到端跑通**至少一轮真实更新**，全程无人工

## 待你拍板的空白
- 博主列表（ID / 主页链接）：______
- 转录用什么：本地 whisper / 云 API（哪家）：______
- newsletter 产物落哪、什么格式：______
- 抓取方式偏好：官方/第三方 API、还是浏览器自动化（你有 lark/chrome 工具）：______

---

## 草稿分解（第一版 atomic-unit DAG —— GSD 会正式化+验证）

```
         U1 抓取博主视频列表
            ├──────────────┐
            ▼              ▼
      U2 更新检测      U3 视频下载+抽音频     ← U2 与 U3 可并行
                          ▼
                   U4 转录(带时间戳)
                          ▼
                   U5 AI 内容处理→newsletter条目
                          ▼
                   U6 产物落地 + Telegram 通知
                          ▼
      U7 编排成定时流水线 + 错误处理   ← 依赖 U2 与 U6
```

| Unit | agent | 依赖 | 验收标准（一轮干完） |
|---|---|---|---|
| **U1** 视频列表抓取 | codex | — | 输入博主ID/链接，输出最新N条视频 `{id,title,url,publish_time}` JSON |
| **U2** 更新检测+状态库 | codex | U1 | 第二次运行只返回**新**视频；已处理的存档 |
| **U3** 下载+抽音频 | codex | U1 | 给视频URL，落地 `mp4`+`wav` |
| **U4** 转录 | codex | U3 | 给 `wav`，输出转录文本+时间戳 |
| **U5** AI 内容处理 | claude | U4 | 给转录，输出结构化 markdown 条目（摘要/要点/why matters）|
| **U6** 落地+通知 | either | U5 | 条目写入指定目录 + 推 Telegram |
| **U7** 编排+调度 | codex | U2,U6 | 一条命令/cron 跑通端到端：新视频→newsletter |

**并行 vs 串行一目了然**：U1 之后 U2 与 U3 分叉并行；U3→U4→U5→U6 是串行链；
U7 最后整合。这正是 threads 的 lane map 要吃的东西（每条 lane 写不同文件，互不冲突）。

> 改完这份文档、确认博主列表和产物去向，我就：建 repo → 跑 GSD 分解 → 同步成
> GitHub Issues → 拿 U1 用 threads 跑通第一个闭环。
