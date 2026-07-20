# Milestone: 战绩卡 Builder CTA + HTTPS QR 分享页

## Objective

把 TokenPulse 的战绩卡从“本地生成 PNG、手动拖去平台”升级成两个增长能力：

1. 每张公开传播的战绩卡都能让别人识别 Wendy / Zinan 是 builder。
2. 点击“分享战绩卡”后，用户拿手机扫码进入一个 HTTPS 分享页，在手机上完成保存或分享。

这不是“扫码后静默代发”。正确产品承诺是：扫码进入手机端分享页，用户再用系统分享、保存图片、或平台入口完成发布。

## Scope

### In

- 在现有 1080 x 1440 Card 2.0 页脚增加 builder CTA。
- 生成一个可扫描 QR，指向稳定 HTTPS builder / share URL。
- Widget 的“分享战绩卡”从 Finder-only 反馈升级为 QR 分享入口。
- HTTPS 分享页原型支持展示战绩卡图片、保存图片、系统分享、平台入口。
- 平台入口先做诚实 fallback：X intent / 系统分享 / 保存图片；Douyin 和 Xiaohongshu 不承诺自动带图，除非真机验证通过。

### Out

- 不做平台静默发布。
- 不接入账号密码、OAuth、平台 token 或用户授权发布。
- 不把生成的卡片公开上传到永久不可控位置，除非另有隐私/保留策略。
- 不改 token 统计、等级、徽章算法。
- 不改 launchd、cron、furnace 自动执行行为。

## Product Principles

- **Owner vs builder 分离**：卡片顶部继续代表卡片主人；页脚 CTA 代表 TokenPulse builder。
- **二维码只承诺 URL**：QR 内容是 HTTPS 页面链接，不是假装携带图片文件本身。
- **分享页讲真话**：能系统分享就系统分享，不能就保存图片；平台按钮不承诺平台不支持的能力。
- **先传播，再自动化**：先让卡片带 attribution 并容易从手机分享，官方平台深接入放 Phase 2。

## User Journey 1: Builder CTA

### Primary actor

未来安装 TokenPulse 的用户，以及看到用户战绩卡的外部观众。

### Journey

1. 用户在 TokenPulse widget 展开面板。
2. 用户配置自己的 X / 小红书号，这些仍显示在卡片顶部，代表“这张战绩是谁的”。
3. 用户点击“分享战绩卡”。
4. TokenPulse 生成战绩卡 PNG。
5. 卡片页脚出现低干扰 builder CTA：
   - `Made with TokenPulse by @zinan92`
   - 小红书 / 抖音的 builder 标识优先显示
   - 一个小 QR 指向 builder landing page
6. 用户把卡片发到 X / 小红书 / 抖音 / 微信等任意渠道。
7. 观众看到卡片后，能在不混淆卡片主人身份的情况下识别 TokenPulse builder，并可扫码访问 builder 页面。

### Success criteria

- [ ] 卡片顶部仍只表达卡片主人身份：`handle` / `xhs_id` 不被 builder 信息覆盖。
- [ ] 页脚新增 builder CTA，文案清楚但不抢主视觉：`Made with TokenPulse by @zinan92`。
- [ ] 页脚优先包含 builder 的小红书和抖音标识；X 可作为 landing page 次级链接或短文本补充。
- [ ] 页脚 QR 可被 iPhone 相机和微信/抖音/小红书扫码识别。
- [ ] QR 指向 HTTPS URL，不使用脆弱 app scheme。
- [ ] CTA 不遮挡现有成本、核验、日期、水印信息；卡片在 1080 x 1440 下无文字重叠。
- [ ] PNG 转发、截图、压缩后仍保留可读 CTA；至少在 50% 尺寸预览下能识别 `TokenPulse` 和 builder handle。
- [ ] Builder credentials 独立配置，不污染用户自己的 `handle` / `xhs_id` 设置。
- [ ] 缺少 builder 抖音号时，卡片仍能生成，并以 landing page QR 兜底。
- [ ] `python3 card.py` 能生成含 CTA 的 `.card-out/tokenpulse-card.png`。

## User Journey 2: HTTPS QR 分享页

### Primary actor

桌面端 TokenPulse 用户，使用手机把战绩卡发到 X / 小红书 / 抖音。

### Journey

1. 用户在 Mac 上打开 TokenPulse widget 的展开面板。
2. 用户点击“分享战绩卡”。
3. TokenPulse 生成最新战绩卡 PNG。
4. Widget 弹出一个 QR 分享面板，而不是只打开 Finder。
5. 用户用手机相机或任意 App 扫码。
6. 手机打开 HTTPS 分享页。
7. 分享页显示：
   - 战绩卡预览
   - 主按钮：分享图片
   - 次按钮：保存图片
   - 平台入口：X、小红书、抖音
8. 如果手机浏览器支持 `navigator.share({ files })`，点击“分享图片”打开系统分享面板并带上 PNG。
9. 如果不支持文件分享，页面清楚降级为“长按保存图片 / 下载图片”。
10. 用户选择平台并完成发布；平台发布动作必须由用户自己确认。

### Success criteria

- [ ] 点击 widget 的“分享战绩卡”后，用户不再被迫去 Finder 找文件；默认看到 QR 分享入口。
- [ ] 分享入口明确显示当前卡片已生成成功，并能展示本地路径或错误原因。
- [ ] QR 指向 HTTPS URL；非 HTTPS 只允许作为开发模式，不作为默认体验。
- [ ] 手机打开分享页后，首屏能看到卡片预览和“分享图片 / 保存图片”主操作。
- [ ] 分享页在 iPhone Safari、Android Chrome 的基础路径可用。
- [ ] 支持 Web Share 文件分享时，`navigator.canShare({ files })` 通过后才调用 `navigator.share({ files })`。
- [ ] 不支持 Web Share 文件分享时，有可执行 fallback：下载、长按保存、复制文案。
- [ ] X 入口使用 X Web Intent 预填文字、链接和 via，不声称能通过 intent 附图。
- [ ] 小红书入口不声称网页能直接打开带图发布器；默认指引为保存图片后打开小红书发布。
- [ ] 抖音入口不声称普通二维码/相机扫码能带图发布；只有配置官方 H5 分享能力、签名、素材 HTTPS URL 后才显示“抖音发布”深入口。
- [ ] 生成的分享页链接有合理生命周期和隐私边界：默认短期有效或本地开发模式清楚标识。
- [ ] 失败状态可理解：上传失败、QR 生成失败、分享页不可达、浏览器不支持文件分享都要有明确提示。
- [ ] 不需要用户配置平台账号或授权 TokenPulse 代发内容。

## Non-goals / Rejection tests

- 如果用户扫码后页面只打开一张裸 PNG，没有主操作按钮，不算完成。
- 如果 X 按钮让用户以为图片已附上，但实际只带链接，不算完成。
- 如果小红书/抖音按钮在未接入官方能力时承诺“直接发布”，不算完成。
- 如果 builder CTA 和卡片主人账号混在一起，让观众分不清谁是卡片主人、谁是产品作者，不算完成。
- 如果分享流程依赖 `http://192.168.*` 作为默认体验，不算完成。

## Implementation hints

- `card.py` 是 Builder CTA 的主入口。
- `badges.card_data()` 已经提供用户卡片身份；builder identity 应该单独配置，不能复用用户身份字段。
- `webwidget.Api.share_card()` 当前只生成 PNG 并 `open -R`，这里应改成返回 QR/share payload。
- `web/widget.html` 当前按钮文案是 `分享战绩卡 ↗`，后续应打开 modal/panel，而不是只改按钮文本。
- `requirements.txt` 当前没有 Pillow/qrcode；若 QR 成为正式功能，需要补齐运行依赖或使用已有可控实现。
- HTTPS 原型可以先用明确的 provider abstraction：`local_dev`, `static_hosted`, `cloudflare_r2_worker`，避免把上传逻辑写死。

## Open decisions

- Builder landing page 的最终 URL 是什么？
- Builder 抖音号 / 主页链接是什么？
- 分享页图片保存期限默认多久？
- Phase 1 是否允许使用 Cloudflare R2 + Worker，还是先用静态 HTTPS 原型验证手机体验？
