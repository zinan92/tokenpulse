# tokenpulse

## 要去哪里
把本地 Claude/Codex token 用量日志变成桌面鞭策 widget、Telegram 推送、CLI 状态与可分享 QR 战绩卡——用可视化压力驱动 AI 工时产出。

## 现在在哪里(2026-07-22)
- 产品运行中;Codex 今日 token/成本与已安装 CodexBar 的本地扫描口径对齐，避免当前累计/forked 日志导致的虚高。
- widget 可在设置中切换为一行紧凑模式；紧凑行右侧常驻 ⚙，可立即回到完整面板继续改设置。也可切到经真实 macOS 启动验证的菜单栏状态项（点开可临时查看完整面板）。
- 展开的明细/设置面板在浮窗内可滚动；`保存并重启` 会先持久化配置，再自动重启本地 launchd widget。
- 菜单栏的打开/刷新/退出均使用已验证的 Objective-C action selector；Codex 本地扫描短暂失败时保留上次可信值或明确不可用，绝不回退到会虚高的原始累计日志求和。
- 体系角色:loop 全周期演练与 claimer 冒烟的**指定沙盒仓**,share 测试已 sandbox-hermetic。
- 无排队任务。

## 下一步
- 按晨会需求排;继续担任流水线演练沙盒。
