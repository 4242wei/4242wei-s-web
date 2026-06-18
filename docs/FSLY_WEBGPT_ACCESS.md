# FSLY API 访问文档

这份文档是给网页 GPT / Web GPT 用的。

验证时间：2026-04-10

目标：

- 直接通过 API 读取 `FSLY` 相关专家资料、会议转录、财报电话会
- 不抓网页 DOM
- 不依赖页面 HTML 结构

## 基础地址

如果你在本机访问：

- `http://127.0.0.1:5000`

如果你在外网访问部署站点：

- `https://www.4242wei.com`

下面示例默认用相对路径写法。

## 先读这两个入口

1. `GET /api/ai/bootstrap.json`
2. `GET /api/ai/readme.json`

## FSLY 快速入口

先看单股票摘要：

- `GET /api/ai/brief/FSLY.json`

这条接口会返回：

- `latest_by_kind`
- `experts`
- 最近材料统计

## FSLY 专家资料

先列专家目录：

- `GET /api/ai/experts/FSLY.json`

2026-04-10 实测返回：

- `filtered_experts = 1`
- 当前命中的专家 `doc_id = 4351b7f0a8`
- 标题 `庄申秋`

读取该专家全文：

- `GET /api/ai/documents/expert/4351b7f0a8.json`
- `GET /api/ai/documents/expert/4351b7f0a8.md`

也可以用等价别名：

- `GET /api/ai/json/expert/4351b7f0a8`
- `GET /api/ai/md/expert/4351b7f0a8`

## FSLY 会议内容

### 最新会议转录

- `GET /api/ai/latest/FSLY/transcript.json`
- `GET /api/ai/latest/FSLY/transcript.md`

2026-04-10 实测当前最新 transcript：

- 标题：`CLoudflare国内专家_20260409`
- `doc_id = 44fcf2fca3`

如果要直接读这个具体文档：

- `GET /api/ai/documents/transcript/44fcf2fca3.json`
- `GET /api/ai/documents/transcript/44fcf2fca3.md`

### 最新财报电话会

- `GET /api/ai/latest/FSLY/earnings_call.json`
- `GET /api/ai/latest/FSLY/earnings_call.md`

2026-04-10 实测当前最新 earnings call：

- 标题：`FSLY FY2025 Q4 财报电话会议记录`
- `doc_id = FSLY--87b172ad50bf`

如果要直接读这条电话会全文：

- `GET /api/ai/documents/earnings_call/FSLY--87b172ad50bf.json`
- `GET /api/ai/documents/earnings_call/FSLY--87b172ad50bf.md`

## FSLY 所有可读 transcript / 电话会 / 专家资料

先列 FSLY 全部文档：

- `GET /api/ai/manifest.json?symbol=FSLY`

如果只想看 transcript：

- `GET /api/ai/manifest.json?symbol=FSLY&kind=transcript`

如果只想看专家：

- `GET /api/ai/manifest.json?symbol=FSLY&kind=expert`

## 搜索怎么用

开放检索：

- `GET /api/ai/search.json?q=<QUERY>&symbols=FSLY`

只搜专家：

- `GET /api/ai/search.json?q=<QUERY>&symbols=FSLY&kinds=expert`

只搜会议转录：

- `GET /api/ai/search.json?q=<QUERY>&symbols=FSLY&kinds=transcript`

只搜财报电话会：

- `GET /api/ai/search.json?q=<QUERY>&symbols=FSLY&kinds=earnings_call`

证据块压缩：

- `GET /api/ai/context-pack.json?query=<QUERY>&symbols=FSLY`

## 已验证可命中的查询

专家资料：

- `庄申秋`
- `CDN`
- `Cloudflare`
- `FSLY`

财报电话会：

- `Kip Compton`
- `accelerate our growth`
- `CEO 7 months ago`

## 搜索边界

当前搜索更接近关键词检索，不是强语义联想搜索。

这意味着：

- 如果关键词明确出现在专家资料或电话会里，命中通常正常
- 对 transcript，很多时候更稳的方法不是先搜索，而是先拿 `latest` 或 `manifest`，再直接读取全文

因此网页 GPT 读取 FSLY 会议内容时，推荐顺序是：

1. `GET /api/ai/brief/FSLY.json`
2. 优先读 `latest`：
   - `GET /api/ai/latest/FSLY/transcript.json`
   - `GET /api/ai/latest/FSLY/earnings_call.json`
3. 如果要更多材料，再读：
   - `GET /api/ai/manifest.json?symbol=FSLY&kind=transcript`
   - `GET /api/ai/manifest.json?symbol=FSLY&kind=earnings_call`
4. 拿到 `doc_id` 后再读具体全文

## 推荐给网页 GPT 的最短说明

```text
你现在读取的是一个研究网站的 AI-native API，不要抓网页 DOM。

先读：
1. GET /api/ai/bootstrap.json
2. GET /api/ai/readme.json

本次任务只看 FSLY。

优先顺序：
1. GET /api/ai/brief/FSLY.json
2. GET /api/ai/experts/FSLY.json
3. GET /api/ai/latest/FSLY/transcript.json
4. GET /api/ai/latest/FSLY/earnings_call.json

如果 experts 返回 doc_id=4351b7f0a8，则读取：
- /api/ai/documents/expert/4351b7f0a8.md

如果要读取当前最新 transcript，则读取：
- /api/ai/latest/FSLY/transcript.md

如果要读取当前最新 earnings call，则读取：
- /api/ai/latest/FSLY/earnings_call.md

如果需要更多 FSLY 文档，再读：
- /api/ai/manifest.json?symbol=FSLY

如果需要搜索，只用：
- /api/ai/search.json?q=<QUERY>&symbols=FSLY

注意：当前搜索偏关键词匹配，不是强语义联想；对会议转录，优先直接读 latest 或 manifest 返回的具体文档。
```
