# 网页 GPT API 使用说明

这份文档是给网页 GPT / AI 代理看的。

目标：

- 不抓页面 DOM
- 不依赖页面 HTML 结构
- 优先使用站点已经提供的 AI-native API

定位说明：

- 这是一份便于直接复制给网页 GPT 的补充说明
- 固定主入口仍然是 `/api/ai/bootstrap.json` + `/api/ai/readme.json`
- `/api/ai/readme.json` 的源文档是 `docs/AI_NATIVE_README.md`

站点基地址：

- `https://www.4242wei.com`

## 一句话规则

先读 `bootstrap`，再读 `readme.json`，之后优先走 JSON 接口；如果问题和数据监控有关，先走 `/api/ai/data/search.json` 或 `/api/ai/data/manifest.json`，不要去抓图表或表格 DOM。

## 推荐访问顺序

1. `GET https://www.4242wei.com/api/ai/bootstrap.json`
2. `GET https://www.4242wei.com/api/ai/readme.json`
3. 如果需要 Markdown 原文，再读 `GET https://www.4242wei.com/api/ai/readme.md`
4. 如果问题和数据监控有关，并且要搜关联，读 `GET https://www.4242wei.com/api/ai/data/search.json?q=<QUERY>&datasets=<DATASET>`
5. 如果问题是开放式研究检索，读 `GET https://www.4242wei.com/api/ai/search.json?q=<QUERY>`
6. 如果问题聚焦单一股票，读 `GET https://www.4242wei.com/api/ai/brief.json?symbol=<SYMBOL>`
7. 如果问题明确要专家资料，读 `GET https://www.4242wei.com/api/ai/experts.json?symbol=<SYMBOL>`
8. 如果需要更小但更证据化的上下文，读 `GET https://www.4242wei.com/api/ai/context-pack.json?query=<QUERY>&symbols=<SYMBOL>`
9. 如果任务是时间线或比较，读 `GET https://www.4242wei.com/api/analysis/timeline.json` 或 `GET https://www.4242wei.com/api/analysis/compare.json`
10. 如果需要长研究包，读 `GET https://www.4242wei.com/api/ai/bundle.md`
11. 如果还要穷举文档，再读 `GET https://www.4242wei.com/api/ai/manifest.json`

## 数据监控怎么读

先发现数据集：

- `GET https://www.4242wei.com/api/ai/data/manifest.json`

如果要搜数据行级关联：

- `GET https://www.4242wei.com/api/ai/data/search.json?q=<QUERY>&datasets=cdn`
- `GET https://www.4242wei.com/api/ai/data/search.json?q=<QUERY>&datasets=stablecoins`

这个接口适合：

- 查 `OpenAI` 用了什么 CDN
- 查某个 provider 最近对应哪些站点
- 查 `USDT`、`USDC` 这类稳定币最新数据
- 先搜到关联对象，再顺着返回的 `json_url` 继续读整包数据

稳定币数据：

- `GET https://www.4242wei.com/api/ai/data/stablecoins.json`
- `GET https://www.4242wei.com/api/ai/data/stablecoins.md`

CDN 数据：

- `GET https://www.4242wei.com/api/ai/data/cdn.json`
- `GET https://www.4242wei.com/api/ai/data/cdn.md`

注意：

- CDN 页面上的逐站点明细是前端懒加载 UI，不是给 AI 抓 DOM 用的
- AI 应优先走 `/api/ai/data/search.json` 和 `/api/ai/data/cdn.json`

## 时间字段规则

- `activity_date`：时间推理主字段
- `updated_at`：补充更新时间
- `display_time`：面向展示的时间标签
- `generated_at`：当前响应生成时间
- `sort_value`：后端 recent-first 排序值

做时间判断时，优先使用 `activity_date`，其次才是 `updated_at`。

## 写入规则

如果需要写入，只能使用 guarded write 流程：

1. `preview`
2. review diff
3. `commit`

不要直接假设存在可写接口。

可写入口属于：

- `https://www.4242wei.com/api/agent/writes/*`

## 失败时怎么回退

- 如果 `readme.md` 抓取不稳，优先使用 `readme.json`
- 如果 `readme` 读失败，不要停止，继续使用 `bootstrap.json` 里的 `entrypoints`
- 如果某个接口当前没有数据，要明确说“当前接口范围内未找到”，不要猜

## 可直接贴给网页 GPT 的版本

```text
你正在访问一个研究网站的 API，基础地址是 https://www.4242wei.com

规则：
1. 不要抓取网页 DOM，不要依赖页面 HTML 结构，优先使用 AI-native API。
2. 先读 GET /api/ai/bootstrap.json，再读 GET /api/ai/readme.json。
3. 如果 readme.json 不可用，再尝试 GET /api/ai/readme.md。
4. 如果问题和数据监控有关，先读 GET /api/ai/data/manifest.json。
5. 如果需要搜数据行级关联，优先用 GET /api/ai/data/search.json?q=<QUERY>&datasets=<DATASET>。
6. 开放式研究检索优先用 GET /api/ai/search.json?q=<QUERY>。
7. 单一股票优先用 GET /api/ai/brief.json?symbol=<SYMBOL>。
8. 专家资料优先用 GET /api/ai/experts.json?symbol=<SYMBOL>。
9. 需要更紧凑的证据上下文时，用 GET /api/ai/context-pack.json?query=<QUERY>&symbols=<SYMBOL>。
10. 时间线用 GET /api/analysis/timeline.json；比较用 GET /api/analysis/compare.json。
11. 稳定币数据优先用 GET /api/ai/data/stablecoins.json。
12. CDN 数据优先用 GET /api/ai/data/cdn.json。
13. 不要通过页面图表或表格 DOM 推断数据监控结论。
14. 如需写入，只能走 /api/agent/writes/* 的 preview -> diff -> commit 流程。
15. 时间推理优先使用 activity_date，其次才是 updated_at。
16. 如果当前接口没有数据，要明确说“当前接口范围内未找到”，不要猜。
```
