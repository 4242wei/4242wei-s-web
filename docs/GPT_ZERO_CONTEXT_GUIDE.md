# GPT 零上下文使用指南

这份指南是给“第一次接触这个网页、此前什么都不知道”的 GPT / Web GPT / 外部 AI 工具用的。

目标：

- 不抓网页 DOM
- 不猜页面结构
- 不依赖人工点开页面看内容
- 直接走网页已经提供好的 AI-native API
- 在最少试错下找到日报、笔记、上传文件、专家资料、电话会议、转录、数据监控等各种资料

如果你只能记住一件事，请记住：

1. 先读 `/api/ai/bootstrap.json`
2. 再读 `/api/ai/readme.json`
3. 然后根据任务类型走 `brief / experts / search / context-pack / manifest / latest / analysis`

## 基础地址

本地：

- `http://127.0.0.1:5000`

公网：

- `https://www.4242wei.com`

下面示例默认写相对路径。

## 最重要的规则

1. 不要先抓 HTML 页面，也不要读页面 DOM。
2. 优先 JSON；只有在需要整段正文时再读 Markdown。
3. 单股票问题优先 `brief`。
4. 专家资料优先 `experts`。
5. 开放式检索优先 `search`，需要更密集证据再读 `context-pack`。
6. 如果要“最新一篇某类材料”，优先 `latest`。
7. 如果要“列出全部可用材料”，优先 `manifest`。
8. 如果要“最近发生了什么”或“两只股票怎么比较”，优先 `analysis`。
9. 上传文件类资料现在可以被 AI-native 搜索按需发现，不需要反复上传同一个文件。
10. 如果接口没数据，要明确说“当前接口范围内未找到”，不要编造。

## 第一次接入时必须怎么做

第一次访问一个站点实例时，固定按这个顺序：

1. `GET /api/ai/bootstrap.json`
2. `GET /api/ai/readme.json`
3. 如果需要 Markdown 原文，再读 `GET /api/ai/readme.md`

为什么必须这样做：

- `bootstrap.json` 会告诉你当前系统暴露了哪些入口、推荐访问顺序、时间字段语义、path alias 模板。
- `readme.json` 是同一份 AI-native 说明的稳定 JSON 版本，通常比直接抓 Markdown 更稳。

## 如果遇到权限问题

优先尝试：

- `GET /api/ai/bootstrap.json`
- `GET /api/ai/readme.json`

如果返回鉴权错误，说明当前站点没有给匿名 AI 直接开放读接口。

这时有两个可行办法：

1. 让管理员开启 AI 直连。
2. 让管理员提供访客只读直达链接：
   - `/visitor/<VISITOR_SHARE_TOKEN>?next=/api/ai/readme.md`

访客只读模式只能读，不会获得写权限。

## 资料类型总表

网页里的 AI-native 文档主要分这些类型：

- `report`：日报
- `signal_report`：信号报告
- `stock_setup`：单股票 setup / 观察框架
- `expert`：专家资料目录
- `note`：研究笔记
- `file`：上传文件正文
- `earnings_call`：财报电话会议
- `transcript`：会议转录
- `data_snapshot`：数据快照

怎么理解它们：

- `report` / `signal_report` 更像全站级研究材料。
- `note` / `file` / `earnings_call` 往往挂在某个股票下面。
- `expert` 是“专家档案 + 关联访谈/关联资源”的聚合入口。
- `transcript` 是上传并处理后的会议转录。
- `data_snapshot` 目前主要是稳定币和 CDN 数据监控。

## 每种常见任务应该先读什么

### 1. 我什么都不知道，只想先摸清这个站点

按顺序读：

1. `/api/ai/bootstrap.json`
2. `/api/ai/readme.json`
3. `/api/ai/manifest.json?limit=30`

这三步可以让你知道：

- 有哪些可用入口
- 支持哪些文档类型
- 当前有哪些材料
- 每种材料的 `kind / doc_id / title / symbol / json_url / markdown_url`

### 2. 我想快速研究单一股票

按顺序读：

1. `/api/ai/brief.json?symbol=<SYMBOL>`
2. `/api/ai/experts.json?symbol=<SYMBOL>`
3. `/api/ai/latest/<SYMBOL>/transcript.json`
4. `/api/ai/latest/<SYMBOL>/earnings_call.json`
5. `/api/ai/manifest.json?symbol=<SYMBOL>`
6. 如需长上下文，再读 `/api/ai/bundle.md?symbols=<SYMBOL>&include_setups=1`

适合的问题：

- “帮我快速看下 NET 最近有哪些材料”
- “FSLY 最近有什么值得注意的资料”
- “AKAM 近期有哪些专家会、电话会、笔记和文件”

### 3. 我想按主题找资料

按顺序读：

1. `/api/ai/search.json?q=<QUERY>`
2. `/api/ai/context-pack.json?query=<QUERY>`
3. 如果要限制股票，追加 `&symbols=<SYMBOL>`
4. 如果要限制类型，追加 `&kinds=<KIND>`
5. 如果想穷举，再读 `/api/ai/manifest.json?q=<QUERY>`

适合的问题：

- “帮我找最近关于 edge / CDN 的材料”
- “找所有和 AI bot 流量相关的资料”
- “找和 pricing power 有关的内容”

### 4. 我想直接拿最新资料

优先用：

- `/api/ai/latest/<SYMBOL>/note.json`
- `/api/ai/latest/<SYMBOL>/file.json`
- `/api/ai/latest/<SYMBOL>/transcript.json`
- `/api/ai/latest/<SYMBOL>/earnings_call.json`

这适合：

- “给我最新一篇文件资料”
- “给我这个股票最新的会议转录”
- “给我这个股票最近的研究笔记”

### 5. 我想知道某类资料到底有哪些

用：

- `/api/ai/manifest.json?symbol=<SYMBOL>&kind=<KIND>`

例子：

- 某股票全部上传文件：`/api/ai/manifest.json?symbol=NET&kind=file`
- 某股票全部转录：`/api/ai/manifest.json?symbol=NET&kind=transcript`
- 某股票全部电话会：`/api/ai/manifest.json?symbol=NET&kind=earnings_call`
- 某股票全部专家资料：`/api/ai/manifest.json?symbol=NET&kind=expert`

## 各类资料怎么找

### A. 日报 / 信号报告怎么找

如果是主题检索：

1. `/api/ai/search.json?q=<QUERY>&kinds=report,signal_report`
2. 对命中的文档再读 `/api/ai/json/<kind>/<doc_id>`

如果是想看当前都有哪些：

1. `/api/ai/manifest.json?kind=report`
2. `/api/ai/manifest.json?kind=signal_report`

### B. 股票笔记怎么找

单股票优先：

1. `/api/ai/brief.json?symbol=<SYMBOL>`
2. `/api/ai/latest/<SYMBOL>/note.json`
3. `/api/ai/manifest.json?symbol=<SYMBOL>&kind=note`

如果是主题检索：

1. `/api/ai/search.json?q=<QUERY>&kinds=note`
2. 需要正文证据时再读 `/api/ai/context-pack.json?query=<QUERY>&kinds=note`

### C. 上传文件怎么找

这是最关键的一类。

优先路径：

1. 单股票全部文件：`/api/ai/manifest.json?symbol=<SYMBOL>&kind=file`
2. 某股票最新文件：`/api/ai/latest/<SYMBOL>/file.json`
3. 主题搜文件：`/api/ai/search.json?q=<QUERY>&kinds=file`
4. 需要更密集正文证据：`/api/ai/context-pack.json?query=<QUERY>&kinds=file`
5. 读取具体文件全文：`/api/ai/json/file/<doc_id>`

拿到文件后，不要只停在文件名：

1. 先通过 `search` / `manifest` / `latest` 找到目标文件的 `doc_id` 或 `json_url`
2. 再读 `/api/ai/json/file/<doc_id>`
3. 从返回的 `document.extra` 中读取：
   - `download_url`：下载原始文件
   - `inline_url`：浏览器内联打开原始文件
   - `preview_url`：人类页面完整预览
   - `preview_fragment_url`：人类页面预览片段
   - `is_previewable` / `is_text_previewable` / `is_image_previewable`
4. 如果任务是“让 GPT 理解内容”，优先使用 `markdown` 和 `chunks`
5. 如果任务是“保留原件、下载源文件、给出原始资料链接”，使用 `document.extra.download_url`

重要说明：

- 文件正文现在支持按需抽取和本地缓存。
- 对支持类型的文件，GPT 首次命中后就可以走缓存，不需要你反复手动上传。
- 常见支持类型包括 `txt/md/json/pdf/docx`。
- 如果文件过大或类型不支持，接口会返回有限信息，这时要明确说明“当前没有可直接读取的正文”。

### D. 专家资料怎么找

始终先走：

1. `/api/ai/experts.json?symbol=<SYMBOL>`

然后：

2. 从结果里拿 `doc_id`
3. 读 `/api/ai/json/expert/<doc_id>`

为什么不要先从 `manifest` 猜：

- `experts.json` 是专门的专家目录入口，里面通常有更适合 GPT 使用的专家信息、访谈信息、关联资源链接。

### E. 电话会议怎么找

优先：

1. `/api/ai/latest/<SYMBOL>/earnings_call.json`

如果要全部：

2. `/api/ai/manifest.json?symbol=<SYMBOL>&kind=earnings_call`

如果要全文：

3. `/api/ai/json/earnings_call/<doc_id>`

### F. 会议转录怎么找

优先：

1. `/api/ai/latest/<SYMBOL>/transcript.json`

如果要全部：

2. `/api/ai/manifest.json?symbol=<SYMBOL>&kind=transcript`

如果要全文：

3. `/api/ai/json/transcript/<doc_id>`

### G. 股票 setup 怎么找

优先：

1. `/api/ai/manifest.json?symbol=<SYMBOL>&kind=stock_setup`

如果知道文档 id：

2. `/api/ai/json/stock_setup/<doc_id>`

### H. 长研究包怎么找

如果想把多个材料一次性预装到上下文：

- `/api/ai/bundle.md?symbols=<SYMBOL>`
- `/api/ai/bundle.md?symbols=<SYMBOL>&include_setups=1`
- `/api/ai/bundle.md?symbols=<SYMBOL>&content_kinds=report,note,file,earnings_call,transcript`
- `/api/ai/bundle.md?symbols=<SYMBOL>&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

适合：

- 单股深度复盘
- 一段时间的催化剂梳理
- 做导图前的长上下文预装

## 开放式研究和单股研究的标准路径

### 路径 1：开放式研究

目标例子：

- “帮我找最近关于 edge CDN 的所有材料”

推荐动作：

1. 读 `/api/ai/bootstrap.json`
2. 读 `/api/ai/readme.json`
3. 读 `/api/ai/search.json?q=edge%20cdn`
4. 对高相关结果读 `/api/ai/context-pack.json?query=edge%20cdn`
5. 如有必要，读 `/api/ai/manifest.json?q=edge%20cdn`
6. 再按需逐篇读 `/api/ai/json/<kind>/<doc_id>`

### 路径 2：单股票研究

目标例子：

- “帮我快速看下 NET 最近有哪些核心资料”

推荐动作：

1. 读 `/api/ai/brief.json?symbol=NET`
2. 读 `/api/ai/experts.json?symbol=NET`
3. 读 `/api/ai/latest/NET/transcript.json`
4. 读 `/api/ai/latest/NET/earnings_call.json`
5. 读 `/api/ai/manifest.json?symbol=NET`
6. 如需长文，读 `/api/ai/bundle.md?symbols=NET&include_setups=1`

### 路径 3：股票之间比较

目标例子：

- “对比 NET 和 FSLY 最近三个月的材料重心”

推荐动作：

1. 读 `/api/analysis/compare.json?symbols=NET,FSLY`
2. 如果问题很具体，再加 `&q=<QUERY>`
3. 必要时再补读两个股票各自的 `brief` 和 `bundle`

### 路径 4：按时间线梳理

目标例子：

- “FSLY 最近三个月发生了什么”

推荐动作：

1. 读 `/api/analysis/timeline.json?symbols=FSLY`
2. 如果需要原文，再补读 timeline 结果中提到的具体文档

## 数据监控怎么找

这部分不要抓人类页面图表。

### 稳定币

先读：

1. `/api/ai/data/manifest.json`
2. `/api/ai/data/stablecoins.json`

如果是找行级关联：

3. `/api/ai/data/search.json?q=<QUERY>&datasets=stablecoins`

如果需要引用友好的文本：

4. `/api/ai/data/stablecoins.md`

### CDN

先读：

1. `/api/ai/data/manifest.json`
2. `/api/ai/data/cdn.json`

如果是找站点、provider、变化等细粒度关联：

3. `/api/ai/data/search.json?q=<QUERY>&datasets=cdn`

可选筛选：

- `provider=<PROVIDER>`
- `category=<CATEGORY>`
- `q=<QUERY>`
- `site_limit=<N>`

如需文本版本：

4. `/api/ai/data/cdn.md`

## 什么时候用 search，什么时候用 manifest，什么时候用 context-pack

用 `search`：

- 你还不知道有哪些资料
- 你想先拿候选文档
- 你是“按主题”找内容

用 `manifest`：

- 你想穷举某股票/某类型的全部资料
- 你需要拿到完整文档列表和 `doc_id`
- 你已经知道要按 `symbol / kind` 过滤

用 `context-pack`：

- 你已经有明确问题
- 你需要较少但更密集的正文证据块
- 你想让 GPT 在更短上下文里推理

简单理解：

- `search`：找候选
- `manifest`：看清单
- `context-pack`：拿证据

## 什么时候直接读单文档

如果你已经拿到 `doc_id`，直接读：

- `/api/ai/json/<kind>/<doc_id>`
- `/api/ai/md/<kind>/<doc_id>`

这适合：

- 你已经知道要读哪一篇
- 你需要完整正文
- 你要引用这篇材料的具体表述

返回结构通常包括：

- `document`
- `markdown`
- `chunks`

## 时间字段怎么理解

优先级：

1. `activity_date`
2. `display_time`
3. `updated_at`

建议：

- 做时间线推理时优先用 `activity_date`
- 回答里尽量写清具体日期范围
- 如果 `activity_date` 缺失，再退回 `updated_at`

## 路由不稳定时怎么办

如果 GPT 工具对 query string 支持不好，改用 path alias：

- `/api/ai/brief/<SYMBOL>.json`
- `/api/ai/experts/<SYMBOL>.json`
- `/api/ai/latest/<SYMBOL>/<KIND>.json`
- `/api/ai/search/<URL_ENCODED_QUERY>.json`
- `/api/ai/context-pack/<URL_ENCODED_QUERY>/symbols/<SYMBOLS>.json`
- `/api/analysis/timeline/<SYMBOLS>.json`
- `/api/analysis/compare/<SYMBOL1,SYMBOL2>.json`

## 回答时应该怎么组织

推荐做法：

1. 先说结论
2. 再列出主要证据来源
3. 涉及时间时明确时间范围
4. 涉及专家/文件/会议时尽量带上 `kind + title + doc_id`

如果没找到：

- 明确说“当前接口范围内未找到”

如果只有部分资料：

- 明确说“目前仅检索到这些类型，未看到更多匹配材料”

## 不要这样做

- 不要先打开首页再靠页面结构猜内容
- 不要抓图表截图推导数据
- 不要默认把整个 manifest 全量拉满
- 不要一上来读取所有 Markdown 全文
- 不要把没有数据说成有数据

## 最推荐的几个起手模板

### 模板 1：我想研究一只股票

1. `GET /api/ai/bootstrap.json`
2. `GET /api/ai/readme.json`
3. `GET /api/ai/brief/<SYMBOL>.json`
4. `GET /api/ai/experts/<SYMBOL>.json`
5. `GET /api/ai/manifest.json?symbol=<SYMBOL>`
6. 按需读取 `latest / bundle / documents`

### 模板 2：我想找某个主题

1. `GET /api/ai/bootstrap.json`
2. `GET /api/ai/readme.json`
3. `GET /api/ai/search.json?q=<QUERY>`
4. `GET /api/ai/context-pack.json?query=<QUERY>`
5. 如需穷举，再读 `GET /api/ai/manifest.json?q=<QUERY>`

### 模板 3：我只想要上传文件

1. `GET /api/ai/manifest.json?symbol=<SYMBOL>&kind=file`
2. `GET /api/ai/latest/<SYMBOL>/file.json`
3. 如需搜索文件主题，`GET /api/ai/search.json?q=<QUERY>&kinds=file`
4. 如需正文证据，`GET /api/ai/context-pack.json?query=<QUERY>&kinds=file`
5. 如需原始文件下载链接，`GET /api/ai/json/file/<DOC_ID>`，然后读取 `document.extra.download_url`

### 模板 4：我只想要会议材料

1. `GET /api/ai/latest/<SYMBOL>/transcript.json`
2. `GET /api/ai/latest/<SYMBOL>/earnings_call.json`
3. `GET /api/ai/manifest.json?symbol=<SYMBOL>&kind=transcript`
4. `GET /api/ai/manifest.json?symbol=<SYMBOL>&kind=earnings_call`

## 可直接复制给 GPT 的提示词

```text
你正在访问一个研究网站的 AI-native API。不要抓网页 DOM，不要依赖页面 HTML 结构，优先使用网站已经提供的 JSON / Markdown 接口。

固定起手顺序：
1. GET /api/ai/bootstrap.json
2. GET /api/ai/readme.json

工作规则：
1. 优先 JSON，只有在需要整段正文时再读 Markdown。
2. 单股票问题优先 brief。
3. 专家资料优先 experts。
4. 开放式检索优先 search，需要更密集证据时再读 context-pack。
5. 如果要最新资料，优先 latest。
6. 如果要穷举资料，优先 manifest。
7. 如果要时间线或比较，优先 analysis。
8. 上传文件正文也属于可检索资料类型 file，不需要假设必须手动重新上传。
9. 找到 file 文档后，不要只报文件名；继续读取 `/api/ai/json/file/<DOC_ID>`，优先使用其中的 `markdown` / `chunks` 理解内容，并在需要原件时使用 `document.extra.download_url`。
10. 如果某接口没有数据，要明确说“当前接口范围内未找到”，不要编造。

推荐路径：

如果研究单个股票：
- GET /api/ai/brief/<SYMBOL>.json
- GET /api/ai/experts/<SYMBOL>.json
- GET /api/ai/latest/<SYMBOL>/transcript.json
- GET /api/ai/latest/<SYMBOL>/earnings_call.json
- GET /api/ai/manifest.json?symbol=<SYMBOL>

如果按主题搜索：
- GET /api/ai/search.json?q=<QUERY>
- GET /api/ai/context-pack.json?query=<QUERY>
- 如需穷举，再 GET /api/ai/manifest.json?q=<QUERY>

如果只找上传文件：
- GET /api/ai/manifest.json?symbol=<SYMBOL>&kind=file
- GET /api/ai/latest/<SYMBOL>/file.json
- GET /api/ai/search.json?q=<QUERY>&kinds=file

如果要全文：
- GET /api/ai/documents/<KIND>/<DOC_ID>.json
- GET /api/ai/documents/<KIND>/<DOC_ID>.md

如果要时间线或比较：
- GET /api/analysis/timeline.json?symbols=<SYMBOL>
- GET /api/analysis/compare.json?symbols=<SYMBOL1,SYMBOL2>&q=<QUERY>
```

## 相关文档

- `docs/AI_NATIVE_README.md`
- `docs/WEBGPT_GENERAL_ACCESS.md`
- `docs/WEBGPT_API_USAGE.md`
- `docs/FSLY_WEBGPT_ACCESS.md`
