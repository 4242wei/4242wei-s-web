# AI Native Layer / 网页 GPT 访问方法说明

这份说明是给读取本网页内容的 AI / GPT 用的。

目标只有一个：不要抓人类页面 DOM，不要猜页面结构，优先走网页已经提供好的 AI 原生接口。

## 访问原则

- 先读 `/api/ai/bootstrap.json`，先知道入口、时间字段和可用能力，再决定下一跳。
- 如果调用方对 Markdown 抓取不稳定，优先读 `/api/ai/readme.json`，把其中 `content` 当作同一份说明文本。
- 固定入口保持为 `/api/ai/bootstrap.json` + `/api/ai/readme.json` + `docs/AI_NATIVE_README.md`；`docs/WEBGPT_API_USAGE.md` 只是便于复制给网页 GPT 的补充文档，不替代主入口。
- 优先读 JSON 接口；只有在需要直接引用整段机器正文时，再读 Markdown 版本。
- 研究类问题优先用 `search -> brief / experts / context-pack -> bundle / 单文档`。
- 对于股票上传文件，AI-native 检索会对支持的本地文件类型做按需正文抽取并写入本地缓存；同一文件命中后后续优先走缓存，不需要反复上传。
- 时间推理优先使用 `activity_date`，`updated_at` 只作为补充时间锚点。
- 需要可复用分析结果时，优先用 `artifacts + jobs`，不要每次都临时重算。
- 需要写入时，只能走 `preview -> diff -> commit` 的 guarded write 流程。
- 当站点开启 AI 直连时，匿名 GPT 可直接读取只读 GET 路由：`/api/ai/*`、`/api/analysis/*`、`/api/agent/bootstrap.json`、`/api/agent/tools/*`、`/api/artifacts/*`、`/api/jobs/*`。
- `POST /api/jobs/artifacts/*` 和 `/api/agent/writes/*` 仍然需要已认证的管理员权限。
- 如果权限不足，API 会返回 JSON 鉴权错误，不再把模型重定向到 HTML 密码页。
- 如果浏览器/GPT 工具对 query string 不稳定，优先改走 path 别名：
  - `/api/ai/latest/<SYMBOL>/<KIND>.json`
  - `/api/ai/latest/<SYMBOL>/<KIND>.md`
  - `/api/ai/brief/<SYMBOL>.json`
  - `/api/ai/experts/<SYMBOL>.json`
  - `/api/ai/stock/<SYMBOL>.json`
  - `/api/ai/stock/<SYMBOL>.md`
  - `/api/ai/search/<URL_ENCODED_QUERY>.json`
  - `/api/ai/context-pack/<URL_ENCODED_QUERY>/symbols/<SYMBOLS>.json`
  - `/api/analysis/timeline/<SYMBOLS>.json`
  - `/api/analysis/compare/<SYMBOL1,SYMBOL2>.json`

## 首次接入

固定按下面顺序工作：

1. 读 `/api/ai/bootstrap.json`
2. 优先读 `/api/ai/readme.json`
3. 如果需要 Markdown 原文，再读 `/api/ai/readme.md`
4. 如果问题和数据监测有关，先读 `/api/ai/data/manifest.json`
5. 如果需要搜数据行级关联，读 `/api/ai/data/search.json?q=<QUERY>&datasets=<DATASET>`
6. 如果问题是开放式检索，读 `/api/ai/search.json?q=<QUERY>`
7. 如果问题聚焦单一股票，优先读 `/api/ai/brief.json?symbol=<SYMBOL>`
8. 如果问题明确要专家资料，读 `/api/ai/experts.json?symbol=<SYMBOL>`
9. 如果需要更小但更“证据化”的上下文，读 `/api/ai/context-pack.json?query=<QUERY>&symbols=<SYMBOL>`
10. 如果任务是时间线或多股票比较，读 `/api/analysis/timeline.json` 或 `/api/analysis/compare.json`
11. 如果需要更长的研究上下文，再读 `/api/ai/bundle.md`
12. 如果还要穷举可用文档，再回退到 `/api/ai/manifest.json`

如果浏览器工具不会提交密码表单，可以让管理员直接提供一个只读访客直达链接：

- `/visitor/<VISITOR_SHARE_TOKEN>?next=/api/ai/readme.md`

这个链接只会进入访客只读模式，不会获得上传、删除、修改或后台管理能力。

## 时间字段

- `activity_date`: 做时间线推理时的主字段。
- `display_time`: 给人看的时间标签。
- `updated_at`: 内容源或系统更新时间；当 `activity_date` 不完整时再用。
- `generated_at`: 当前响应生成时间。
- `sort_value`: 后端内部的 recent-first 排序值。

## 核心入口

### 1. Bootstrap

- `/api/ai/bootstrap.json`
- `/api/ai/readme.json`
- `/api/ai/readme.md`

用途：

- 发现当前系统暴露了哪些 AI 入口
- 读取推荐访问顺序
- 读取时间字段语义
- 读取支持的文档类型和能力边界

这是网页 GPT 的第一跳，不要跳过。

### 2. 检索与上下文压缩

- `/api/ai/search.json?q=<QUERY>&symbols=<SYMBOL>&kinds=<KIND1,KIND2>`
- `/api/ai/context-pack.json?query=<QUERY>&symbols=<SYMBOL>&kinds=<KIND1,KIND2>`

怎么选：

- `search.json` 用于轻量检索、列结果、看候选文档。
- `context-pack.json` 用于拿较少但更密集的正文证据块，适合 GPT 继续推理。

常用参数：

- `q` / `query`
- `symbols` / `symbol`
- `kinds` / `kind`
- `limit`
- `document_limit`
- `chunk_limit`
- `per_document_chunk_limit`
- `refresh=1`

### 3. 单股票快读

- `/api/ai/brief.json?symbol=<SYMBOL>`

适用场景：

- “给我快速过一下 FSLY 最近有什么材料”
- “先给我这个股票的摘要入口，再决定是否深挖”

返回内容会偏向：

- 单股票最近材料
- 按 kind 的最新文档
- 对应搜索、专家、bundle、timeline 的下一跳链接

### 4. 专家资料

- `/api/ai/experts.json?symbol=<SYMBOL>`
- `/api/ai/experts.md?symbol=<SYMBOL>`

这是“帮我看现有专家资料”的第一入口，不要直接从 manifest 猜。

重点字段：

- `doc_id`
- `markdown_url`
- `json_url`
- `detail_url`
- `document.extra.interviews`
- `document.extra.related_resources`

如果要继续深挖具体专家，再读：

- `/api/ai/json/expert/<doc_id>`

### 5. 范围研究包

- `/api/ai/bundle.md?symbols=<SYMBOL>&include_setups=1`

可选参数：

- `symbols`
- `content_kinds=report,note,file,earnings_call,transcript`
- `start_date=YYYY-MM-DD`
- `end_date=YYYY-MM-DD`
- `include_setups=1`
- `per_kind_limit=<N>`

适用场景：

- 单股复盘
- 一段时间内的催化剂回顾
- 导图 / 比较 / 长答案前的预装上下文

### 6. 全量文档索引与单文档

- `/api/ai/manifest.json`
- `/api/ai/manifest.md`
- `/api/ai/md/<kind>/<doc_id>`
- `/api/ai/json/<kind>/<doc_id>`

`manifest.json` 用来：

- 看有哪些可读文档
- 按 `kind / symbol / q / limit` 过滤
- 在明确需要落地缓存时，使用 `materialize=1`

`/api/ai/json/<kind>/<doc_id>` 会返回：

- `document`
- `markdown`
- `chunks`

对于 `file` 文档，`document.extra` 还会提供原件相关链接与能力字段，例如：

- `download_url`
- `inline_url`
- `preview_url`
- `preview_fragment_url`
- `is_previewable`
- `is_text_previewable`
- `is_image_previewable`

所以 AI 找到文件后，不要只停在文件名；如果需要读取正文，优先使用 `markdown` / `chunks`，如果需要原始资料链接，再使用 `document.extra.download_url`。

## 分析接口

- `/api/analysis/timeline.json?symbols=<SYMBOL>&kinds=<KIND1,KIND2>`
- `/api/analysis/compare.json?symbols=<SYMBOL1,SYMBOL2>&q=<QUERY>&kinds=<KIND1,KIND2>`

怎么选：

- `timeline.json` 适合 chronology-first 任务，例如“最近发生了什么”。
- `compare.json` 适合比较任务，例如“NET 和 FSLY 近期材料有什么共性和差异”。

如果希望分析结果可以被反复读取，而不是每次都即时重算，请看下面的 artifact / job 机制。

## Artifact Store 与后台队列

- `GET /api/artifacts/bootstrap.json`
- `GET /api/artifacts/list.json?kinds=<KIND>&symbols=<SYMBOL>`
- `GET /api/artifacts/<ARTIFACT_ID>.json`
- `GET /api/artifacts/<ARTIFACT_ID>.md`
- `GET /api/jobs/list.json?statuses=<STATUS>`
- `GET /api/jobs/<JOB_ID>.json`
- `POST /api/jobs/artifacts/timeline.json`
- `POST /api/jobs/artifacts/compare.json`

用途：

- 持久保存 timeline / compare 结果
- 查看最近后台任务状态
- 把重分析改成“入队 -> 轮询 -> 读取产物”

推荐心智模型：

- 即时问答：`search / context-pack / timeline / compare`
- 可复用分析：`artifacts / jobs`

## Agent Tool Layer 与 Guarded Writes

- `GET /api/agent/bootstrap.json`
- `GET /api/agent/tools/search.json`
- `GET /api/agent/tools/context-pack.json`
- `GET /api/agent/tools/artifacts.json`
- `GET /api/agent/tools/jobs.json`

如果网页 GPT 运行在 tool-calling / agent 模式，优先从这里拿稳定的工具封装。

写入相关接口：

- `POST /api/agent/writes/clipboard/preview.json`
- `POST /api/agent/writes/stock-note/preview.json`
- `GET /api/agent/writes/operations.json`
- `POST /api/agent/writes/operations/<OP_ID>/commit.json`
- `POST /api/agent/writes/operations/<OP_ID>/discard.json`

规则：

- 写入是 admin-only。
- 必须走 `preview -> review diff -> commit`。
- 不存在直接暴露的 destructive write 接口。
- stock note 写入会校验源 note fingerprint，避免静默覆盖新改动。

## 数据监测

### 稳定币

如果问题和稳定币监测有关，优先读：

- `/api/ai/data/manifest.json`
- `/api/ai/data/search.json?q=<QUERY>&datasets=stablecoins`
- `/api/ai/data/stablecoins.json`
- `/api/ai/data/stablecoins.md`

这里会提供：

- 市值历史覆盖区间
- 成交量覆盖区间
- 最新快照
- 月度汇总
- 各稳定币最新权重
- 可被 AI 搜索的 coin 级关联结果
- 对应 `data-monitor` 页面入口

这部分已经进入 AI-native contract，可以直接给网页 GPT 使用。

### CDN 追踪

如果问题和 CDN 追踪有关，优先读：

- `/api/ai/data/manifest.json`
- `/api/ai/data/search.json?q=<QUERY>&datasets=cdn`
- `/api/ai/data/cdn.json`
- `/api/ai/data/cdn.md`

注意：

- `/api/ai/data/search.json` 会返回更细粒度的 `site / provider / change / snapshot` 结果，适合 AI 先查关联再决定是否继续读取整包数据。
- `/api/ai/data/cdn.json` 默认返回摘要、provider 分布、可比时间序列、近期变化，以及受限站点明细。
- 如果需要更具体的站点筛选，可加 `provider=<PROVIDER>`、`category=<CATEGORY>`、`q=<QUERY>`、`site_limit=<N>`。
- `/api/ai/data/cdn.md` 提供引用友好的文字快照。
- 人类页面入口仍在 `/data-monitor?tab=cdn`；网页 GPT 不需要依赖抓图表 DOM。

## 支持的文档类型

- `report`: 日报
- `signal_report`: 信号报告
- `stock_setup`: 股票 Setup
- `expert`: 专家资料
- `note`: 笔记
- `file`: 文件正文
- `earnings_call`: 电话会议
- `transcript`: 转录
- `data_snapshot`: 数据快照

## 推荐工作流

### 场景 A：开放式找资料

用户例子：

- “帮我找最近关于 edge / CDN 的材料”

推荐步骤：

1. 读 `/api/ai/bootstrap.json`
2. 读 `/api/ai/search.json?q=edge%20cdn`
3. 对重点结果再读 `/api/ai/context-pack.json?query=edge%20cdn`
4. 如果需要穷举，再读 `/api/ai/manifest.json?q=edge%20cdn`

### 场景 B：快速研究单一股票

用户例子：

- “帮我快速看下 NET 最近都有什么研究材料”

推荐步骤：

1. 读 `/api/ai/brief.json?symbol=NET`
2. 读 `/api/ai/experts.json?symbol=NET`
3. 读 `/api/ai/bundle.md?symbols=NET&include_setups=1`
4. 再按需读取关键单文档

### 场景 C：做时间线或比较

用户例子：

- “FSLY 最近三个月发生了什么”
- “对比 NET 和 FSLY 最近的资料重心”

推荐步骤：

1. 读 `/api/analysis/timeline.json?symbols=FSLY`
2. 或读 `/api/analysis/compare.json?symbols=NET,FSLY`
3. 如果结果需要长期复用，再走 `/api/jobs/artifacts/*.json`

### 场景 D：做稳定币问答

用户例子：

- “稳定币总市值最近怎么变的”

推荐步骤：

1. 读 `/api/ai/data/stablecoins.json`
2. 如需引用文本，再读 `/api/ai/data/stablecoins.md`
3. 回答时注明时间点和覆盖区间

### 场景 E：需要写回剪贴板或股票笔记

推荐步骤：

1. 调 `preview`
2. 看 diff / operation
3. 明确确认后再 `commit`
4. 不需要保留时 `discard`

## 本地缓存位置

后端会按需生成：

```text
data/ai_native/
  README.md
  manifest.json
  file-text-cache/
    <symbol-file>.json
  documents/
    <kind>/
      <doc-slug>/
        document.md
        meta.json
        chunks.jsonl
```

此外：

- `file-text-cache/` 会缓存支持类型文件的抽取正文，供 `search.json` / `context-pack.json` / 文件单文档读取复用。
- 搜索 sidecar、artifact store、job queue、agent write operation log 也都在 `data/ai_native/` 下。

## 回答规则

- 先基于 AI-native 接口返回的结构化内容回答，不要先抓页面。
- 能用 `brief / experts / context-pack / timeline / compare` 解决时，不要一上来就拉整个 manifest。
- 引用结论时尽量带上 `kind`、`title`、`doc_id` 或来源接口。
- 涉及时间判断时，优先用 `activity_date`，并明确时间范围。
- 如果专家目录里没有匹配结果，明确说“当前专家目录中未找到”。
- 如果某类数据还没有 AI-native 读接口，明确说“当前仅有人类页面入口，尚未暴露给 AI-native API”。
- 除非明确需要刷新缓存，否则不要默认加 `materialize=1` 或 `refresh=1`。


## Data Search Addendum

For data-monitor questions that need row-level associations, use:

- /api/ai/data/search.json?q=<QUERY>&datasets=<DATASET> 

Notes:

- This endpoint is for granular data entities, not whole documents.
- It can return cdn results such as site, provider, change, and snapshot.
- It can return stablecoins results such as coin and snapshot.
- Use it when the AI needs associations like OpenAI -> Cloudflare or USDT -> latest market cap.
- After finding a match, follow the returned json_url to read the full dataset payload.
