# 通用 API 访问文档

这份文档给网页 GPT / Web GPT / 其他外部 AI 工具使用。

用途：

- 不抓网页 DOM
- 不依赖页面 HTML 结构
- 直接通过 AI-native API 读取内容
- 适用于任意股票、任意主题、专家资料、会议转录、财报电话会、时间线、比较分析、数据监控

验证时间：2026-04-10

## 基础地址

本地：

- `http://127.0.0.1:5000`

公网：

- `https://www.4242wei.com`

下面示例默认使用相对路径。

## 总原则

1. 先读 `bootstrap`
2. 再读 `readme`
3. 优先 JSON
4. 需要整段正文时再读 Markdown
5. 单股票优先 `brief`
6. 专家资料优先 `experts`
7. 会议内容优先 `latest` 或 `manifest`
8. 搜索适合找候选文档，不保证强语义联想
9. 需要更密集证据块时用 `context-pack`
10. 需要时间线或比较时用 `analysis`

## 第一次访问时怎么读

固定顺序：

1. `GET /api/ai/bootstrap.json`
2. `GET /api/ai/readme.json`
3. 如需 Markdown 原文：`GET /api/ai/readme.md`

## 常用入口

### 1. 通用搜索

- `GET /api/ai/search.json?q=<QUERY>`
- `GET /api/ai/search.json?q=<QUERY>&symbols=<SYMBOL>`
- `GET /api/ai/search.json?q=<QUERY>&symbols=<SYMBOL>&kinds=<KIND>`

适用：

- 先找候选文档
- 先看有哪些笔记、文件、专家、电话会、转录和报告命中

支持常见 `kinds`：

- `report`
- `signal_report`
- `stock_setup`
- `expert`
- `note`
- `file`
- `earnings_call`
- `transcript`
- `data_snapshot`

### 2. 单股票入口

- `GET /api/ai/brief.json?symbol=<SYMBOL>`
- `GET /api/ai/brief/<SYMBOL>.json`

适用：

- 快速看一个股票最近有什么材料
- 找这个股票各类材料的最新文档
- 找下一跳链接

### 3. 专家资料

- `GET /api/ai/experts.json?symbol=<SYMBOL>`
- `GET /api/ai/experts/<SYMBOL>.json`

拿到专家 `doc_id` 后继续读：

- `GET /api/ai/documents/expert/<DOC_ID>.json`
- `GET /api/ai/documents/expert/<DOC_ID>.md`

等价别名：

- `GET /api/ai/json/expert/<DOC_ID>`
- `GET /api/ai/md/expert/<DOC_ID>`

### 4. 最新会议内容

最新某股票某类型材料：

- `GET /api/ai/latest/<SYMBOL>/transcript.json`
- `GET /api/ai/latest/<SYMBOL>/transcript.md`
- `GET /api/ai/latest/<SYMBOL>/earnings_call.json`
- `GET /api/ai/latest/<SYMBOL>/earnings_call.md`
- `GET /api/ai/latest/<SYMBOL>/note.json`
- `GET /api/ai/latest/<SYMBOL>/file.json`

适用：

- 直接读取该股票最新会议转录
- 直接读取该股票最新财报电话会
- 不想先搜索，直接拿最新文档

### 5. 读取具体文档全文

如果已经知道 `kind` 和 `doc_id`：

- `GET /api/ai/documents/<KIND>/<DOC_ID>.json`
- `GET /api/ai/documents/<KIND>/<DOC_ID>.md`

等价别名：

- `GET /api/ai/json/<KIND>/<DOC_ID>`
- `GET /api/ai/md/<KIND>/<DOC_ID>`

JSON 一般会返回：

- `document`
- `markdown`
- `chunks`

如果文档类型是 `file`，继续看 `document.extra`：

- `download_url`：下载原始文件
- `inline_url`：内联打开原始文件
- `preview_url`：完整预览页
- `preview_fragment_url`：预览片段

所以 GPT 找到文件后，不要只停在文件名；应继续读取 `/api/ai/documents/file/<DOC_ID>.json`，先用 `markdown` / `chunks` 理解内容，再在需要原件时使用 `download_url`。

### 6. 全量文档目录

- `GET /api/ai/manifest.json`
- `GET /api/ai/manifest.json?symbol=<SYMBOL>`
- `GET /api/ai/manifest.json?kind=<KIND>`
- `GET /api/ai/manifest.json?symbol=<SYMBOL>&kind=<KIND>`

适用：

- 穷举当前可读文档
- 获取 `doc_id`
- 找某股票全部 transcript / earnings_call / expert / note / file

### 7. 证据块压缩

- `GET /api/ai/context-pack.json?query=<QUERY>&symbols=<SYMBOL>`
- `GET /api/ai/context-pack.json?query=<QUERY>&symbols=<SYMBOL>&kinds=<KIND>`

适用：

- 已经有问题，要拿小而密集的证据块
- 想让 GPT 在更短上下文里推理

### 8. 时间线与比较

- `GET /api/analysis/timeline.json?symbols=<SYMBOL>`
- `GET /api/analysis/timeline/<SYMBOLS>.json`
- `GET /api/analysis/compare.json?symbols=<SYMBOL1,SYMBOL2>&q=<QUERY>`
- `GET /api/analysis/compare/<SYMBOL1,SYMBOL2>.json?q=<QUERY>`

适用：

- 最近发生了什么
- 两只股票材料重心有什么差异

### 9. 股票紧凑包

- `GET /api/ai/stock/<SYMBOL>.json`
- `GET /api/ai/stock/<SYMBOL>.md`

适用：

- 想拿一个更紧凑的单股票包
- 比 `brief` 更像单股资料合集

### 10. Bundle 长文研究包

- `GET /api/ai/bundle.md?symbols=<SYMBOL>`
- `GET /api/ai/bundle.md?symbols=<SYMBOL>&include_setups=1`
- `GET /api/ai/bundle.md?symbols=<SYMBOL>&content_kinds=report,note,file,earnings_call,transcript`

适用：

- 做长篇研究
- 需要把多个材料拼成一个包

## 数据监控

### 先发现数据集

- `GET /api/ai/data/manifest.json`

### 稳定币

- `GET /api/ai/data/search.json?q=<QUERY>&datasets=stablecoins`
- `GET /api/ai/data/stablecoins.json`
- `GET /api/ai/data/stablecoins.md`

### CDN

- `GET /api/ai/data/search.json?q=<QUERY>&datasets=cdn`
- `GET /api/ai/data/cdn.json`
- `GET /api/ai/data/cdn.md`

## 推荐工作流

### 场景 A：研究某个股票

1. `GET /api/ai/brief/<SYMBOL>.json`
2. `GET /api/ai/experts/<SYMBOL>.json`
3. `GET /api/ai/latest/<SYMBOL>/transcript.json`
4. `GET /api/ai/latest/<SYMBOL>/earnings_call.json`
5. 如需更多文档，再读 `GET /api/ai/manifest.json?symbol=<SYMBOL>`

### 场景 B：按主题找资料

1. `GET /api/ai/search.json?q=<QUERY>`
2. 如需更集中证据，读 `GET /api/ai/context-pack.json?query=<QUERY>`
3. 如需全文，读取返回结果中的具体 `doc_id`

### 场景 C：看专家资料

1. `GET /api/ai/experts.json?symbol=<SYMBOL>`
2. 取出 `doc_id`
3. `GET /api/ai/documents/expert/<DOC_ID>.md`

### 场景 D：看会议内容

1. 优先 `GET /api/ai/latest/<SYMBOL>/transcript.json`
2. 再看 `GET /api/ai/latest/<SYMBOL>/earnings_call.json`
3. 如果要更多会议信息，再读 `GET /api/ai/manifest.json?symbol=<SYMBOL>&kind=transcript`
4. 用 `doc_id` 读取全文

### 场景 E：做时间线或对比

1. `GET /api/analysis/timeline.json?symbols=<SYMBOL>`
2. 或 `GET /api/analysis/compare.json?symbols=<SYMBOL1,SYMBOL2>&q=<QUERY>`

## 搜索边界

当前搜索更偏关键词匹配，不是强语义联想搜索。

这意味着：

- 明确关键词通常命中正常
- 对专家资料、电话会命中率通常较好
- 对 transcript，直接读 `latest` 或 `manifest -> documents/<kind>/<doc_id>` 往往更稳

如果你已经知道要看会议内容，不建议只靠搜索。

更稳的方法是：

1. `brief`
2. `latest`
3. `manifest`
4. 具体全文文档

## 常见占位符

- `<SYMBOL>`：股票代码，例如 `FSLY`、`NET`、`AKAM`
- `<QUERY>`：搜索词，例如 `pricing power`、`CDN`、`Cloudflare`
- `<KIND>`：文档类型，例如 `expert`、`transcript`、`earnings_call`
- `<DOC_ID>`：具体文档 ID，从 `brief / experts / manifest / latest` 返回值中拿

## 推荐给网页 GPT 的通用提示词

```text
你正在访问一个研究网站的 AI-native API，不要抓网页 DOM，不要依赖页面 HTML 结构。

固定顺序：
1. GET /api/ai/bootstrap.json
2. GET /api/ai/readme.json

如果研究单个股票：
1. GET /api/ai/brief/<SYMBOL>.json
2. GET /api/ai/experts/<SYMBOL>.json
3. GET /api/ai/latest/<SYMBOL>/transcript.json
4. GET /api/ai/latest/<SYMBOL>/earnings_call.json
5. 如需更多文档，GET /api/ai/manifest.json?symbol=<SYMBOL>

如果按主题搜索：
1. GET /api/ai/search.json?q=<QUERY>
2. 如需更密集证据，GET /api/ai/context-pack.json?query=<QUERY>

如果已知 doc_id：
- GET /api/ai/documents/<KIND>/<DOC_ID>.json
- GET /api/ai/documents/<KIND>/<DOC_ID>.md

如果要看时间线或比较：
- GET /api/analysis/timeline.json?symbols=<SYMBOL>
- GET /api/analysis/compare.json?symbols=<SYMBOL1,SYMBOL2>&q=<QUERY>

注意：
1. 优先使用 JSON，只有在需要整段正文时再读取 Markdown。
2. 当前搜索偏关键词匹配，不是强语义联想。
3. 对会议转录，优先读 latest 或 manifest，再读具体全文。
4. 如果接口当前没有数据，要明确说“当前接口范围内未找到”，不要编造。
```

## 相关文档

- `docs/AI_NATIVE_README.md`
- `docs/WEBGPT_API_USAGE.md`
- `docs/FSLY_WEBGPT_ACCESS.md`
