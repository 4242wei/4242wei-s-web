---
name: security-software-research-report
description: Generate concise, investment-grade Chinese daily or weekly reports on cybersecurity software companies, including direct company catalysts, AI-era indirect impact chains, threat/regulatory events, historical delta, and optional paid X/Twitter market-view research.
---

# 安全软件投研日报 / 周报 Skill

## 0. 最高目标

生成一份**简洁、有效、不漏关键变量**的中文安全软件投研报告。

默认生成**日报**；如果用户要求周报，则生成过去 7 天的**周报**。报告不是新闻列表，也不是行业科普，而是给投资研究使用的判断材料。

每次报告必须回答：

1. 本期真正发生了什么增量变化？
2. 这些变化为什么影响安全软件公司的产品、预算、竞争格局或市场叙事？
3. 哪些公司被直接影响，哪些公司只是间接受益或承压？
4. 这与历史判断相比，是确认、削弱、反转，还是新增变量？
5. 投资者读完应该带走什么判断，以及后续看什么信号？

写作原则：**结论先行、机制清楚、公司映射明确、证据分级、少废话。**

---

## 1. 输出风格

用户偏好：

- 中文输出。
- 简洁，但不能漏重要变量。
- 先给判断，不要先堆新闻背景。
- 不要把报告写成“今天新闻 1/2/3”。
- 不要写泛泛的“AI agent 很重要”。必须说明影响链。
- 不要复读公司营销话术。
- 区分：事实、解释、推测、市场观点。
- 如果没有强催化，也要明确说“本期无强催化”，不要硬凑。

长度控制：

- 日报目标：约 800-1500 中文字。
- 周报目标：约 1500-2500 中文字。
- 如出现财报、重大攻击、监管、并购、重大产品发布，可适度加长，但不要为了完整而啰嗦。

---

## 2. 报告类型

### Daily Mode（日报）

覆盖 report_date 当天或上次日报之后的新信息。

重点是：

- 今天有什么新变量。
- 是否影响重点公司。
- 是否改变已有主线。
- 是否需要 X/Twitter 看市场温度。

### Weekly Mode（周报）

覆盖最近 7 天，优先读取过去一周的日报和原始证据。

重点是：

- 本周最重要的 3-5 条主线。
- 哪些公司叙事增强，哪些削弱。
- 本周 AI / 威胁 / 监管 / 公司公告中，哪些真的改变判断。
- 下周需要继续跟踪什么。

周报不是把 7 篇日报拼起来，必须重新筛选和压缩。

---

## 3. 必扫信息层

每次生成报告前，按以下层级扫描。新闻源可以帮助发现事件，但核心判断必须尽量回到一手或近一手来源。

### Layer 1：公司与财务硬证据

- 公司官方博客、产品公告、客户案例。
- IR、SEC filings、8-K、10-Q、10-K、财报电话会、投资者日。
- 管理层采访、行业会议发言、合作伙伴公告。

### Layer 2：威胁、漏洞、监管

- CISA KEV、NVD、CVE、MSRC。
- Google/Mandiant、Microsoft Security、CrowdStrike、Palo Alto Unit 42、Cloudflare、Zscaler、Okta、GitHub Security 等威胁情报。
- 勒索软件、供应链攻击、云安全事故、身份攻击、数据泄露。
- SEC cyber disclosure、NIST、CISA、EU AI Act、关键基础设施安全要求。

### Layer 3：AI 与非安全平台的间接变量

每天必须扫描会改变安全软件需求结构的非安全源，尤其是：

- Anthropic / Claude / Claude Code / MCP。
- OpenAI / Codex / ChatGPT Enterprise / agents / connectors。
- Microsoft Copilot / GitHub Copilot / Azure AI。
- Google Gemini / Google Cloud AI。
- Cursor、Replit、Cognition、LangChain、LlamaIndex、CrewAI。
- GitHub、GitLab、JFrog、npm、PyPI、Docker、Kubernetes、CI/CD、IaC。
- AWS、Azure、Google Cloud、Cloudflare、Akamai。
- Microsoft 365、Google Workspace、Slack、Salesforce、ServiceNow、Snowflake、Databricks。

这类来源不是因为它们本身是安全公司，而是因为它们可能改变：

- 企业数据流。
- 身份与权限边界。
- AI agent 可调用的工具。
- 代码生产方式。
- 云控制面风险。
- SOC 自动化。
- 软件供应链风险。

### Layer 4：市场观点与 X/Twitter

X/Twitter 只用于理解市场温度、争议、投资者叙事和从业者反馈。不要把 X 当作事实源。

---

## 4. 重点公司池

不要每天机械覆盖所有公司。只有当公司有实质影响时才写入报告；但扫描时必须覆盖这些公司和赛道。

| 赛道 | 重点公司 |
|---|---|
| 身份 / PAM / 非人类身份 | OKTA, CYBR, SAIL, MSFT, PANW |
| SASE / Zero Trust / Edge | ZS, NET, PANW, FTNT, CHKP, CSCO |
| Endpoint / XDR / Workload | CRWD, MSFT, S, PANW, FTNT |
| Cloud / CNAPP / AppSec | PANW, CRWD, MSFT, DDOG, TENB, QLYS, RPD |
| Code / DevSecOps / Supply Chain | GTLB, FROG, MSFT/GitHub, PANW, CRWD, TENB, QLYS, RPD |
| Data Security / DLP / DSPM | MSFT, ZS, NET, VRNS, PANW |
| SOC / SIEM / Security Operations | CRWD, PANW, MSFT, S, RPD, CSCO |
| Resilience / Backup / Recovery | RBRK, MSFT, PANW, CRWD, TENB, QLYS |
| Exposure / Vulnerability Management | TENB, QLYS, RPD, PANW, CRWD, MSFT |

---

## 5. AI 时代间接影响框架

凡是非安全公司新闻，必须用下面链条判断，不能直接写“利好某某安全公司”。

```text
Event
→ Behavior Change
→ New Attack Surface / Budget Need
→ Required Security Control
→ Company Exposure
→ Evidence Strength
→ Investment Relevance
```

### 判断模板

1. **Event**：本期发生了什么？
2. **Behavior Change**：企业用户、开发者、攻击者或 AI agent 的行为是否变化？
3. **Attack Surface**：新增或放大的攻击面是什么？
4. **Control Point**：企业需要什么安全控制？
5. **Company Map**：哪些上市安全软件公司相关？直接还是间接？
6. **Evidence Gap**：缺少什么证据才能升级为强催化？

### 控制点映射

| 控制点 | 看什么变化 | 相关公司 |
|---|---|---|
| Agent Identity / PAM | agent、service account、API token、MCP 权限、OAuth、secrets | CYBR, OKTA, SAIL, MSFT, PANW |
| Data Security / DLP / DSPM | connector、RAG、prompt context、敏感数据暴露、shadow AI | MSFT, ZS, NET, VRNS, PANW |
| Code / AppSec / Supply Chain | AI 生成代码、依赖包、CI/CD、SBOM、MCP server、IaC | GTLB, FROG, MSFT, PANW, CRWD, TENB, QLYS, RPD |
| Cloud / Workload / CNAPP | 云权限、Kubernetes、runtime、misconfiguration、workload identity | PANW, CRWD, MSFT, DDOG, TENB, QLYS, RPD |
| SOC / XDR / SIEM | agentic SOC、autonomous investigation、detection engineering、threat hunting | CRWD, PANW, MSFT, S, RPD, CSCO |
| Resilience / Recovery | ransomware recovery、immutable backup、clean room recovery、business continuity | RBRK, MSFT, PANW, CRWD, TENB, QLYS |
| SASE / Browser / API / Edge | secure browser、API security、SaaS access、remote browser isolation | ZS, NET, PANW, FTNT, CHKP, CSCO |

### 间接影响强度

- Level 0：泛 AI 新闻，和安全软件链条弱。不写。
- Level 1：有安全含义，但公司映射弱。只作内部观察。
- Level 2：能映射到明确控制点。可写入“简短观察”。
- Level 3：影响多个控制点，并能映射重点公司。可进入主文。
- Level 4：有一手源、市场讨论、公司产品/财报呼应。可作为标题主线。

---

## 6. 候选事件打分

每条候选事件按 0-5 分打分。

| 维度 | 问题 |
|---|---|
| importance | 是否影响行业主线、客户预算、竞争格局？ |
| novelty | 是否是本期真实增量，而不是旧闻转发？ |
| evidence | 是否来自一手或近一手来源？ |
| company_relevance | 是否影响重点公司池？ |
| market_attention | X、投资者、分析师、股价或从业者讨论是否升温？ |
| architecture_shift | 是否改变 AI agent、身份、数据、代码、云、SOC、恢复等架构？ |
| investment_actionability | 是否足以改变 watchlist、财报问题清单、估值叙事或风险判断？ |

简化筛选规则：

- 4.0+：主线。
- 3.2-3.9：次要主题。
- 2.5-3.1：只进“简短观察”或内部记录。
- 低于 2.5：不写，除非和历史主线强相关。

必须剔除：

- 没有增量的新闻转载。
- 只有“AI-powered / agentic / unified platform”但没有产品、客户、技术或商业证据的公告。
- 和安全软件公司影响链很弱的泛 AI 新闻。
- 只有股价波动、没有事实或叙事增量的内容。

---

## 7. X/Twitter 使用规则

先读取本地系统的“使用推特 / 使用付费 X”开关，再决定 `x_mode`。

本地适配规则：

- 如果安全软件监控配置里的 `x_monitor.enabled` 为 `false`，或前端“使用推特”未打开：强制 `x_mode = off`，不得发起任何 USDC 付费请求。
- 如果 `x_monitor.enabled` 为 `true`，默认 `x_mode = light`；只有满足触发条件时才升级到 `focused` 或 `debate`。
- 如果用户在当次任务里明确要求“启用推特 / 买 X 上下文 / 付费看全文”，视为临时打开付费 X，但仍要记录 raw JSON 和成本。
- 报告正文只写市场观点结论；原始 X 数据、endpoint、query、cost、raw_json_path 放入来源或内部记录。

### x_mode

- `off`：不使用付费 X。
- `light`：只搜索 ticker、公司名、主题词，用于判断是否有明显市场讨论。
- `focused`：针对 1-2 个高分事件拉 tweet 原文、thread、X Article。
- `debate`：拉 quotes/replies 和重点账号近期发言，只在争议本身是主题时使用。

### 触发 focused / debate

满足任一条件即可：

- final score >= 3.8 且市场关注明显。
- 某家公司被长文集中讨论。
- 公司出现财报、事故、重大产品、并购、监管、股价异常。
- 新闻事实不复杂，但市场叙事变化明显。
- 用户手动指定启用 X。

### X 抓取顺序

1. `advanced_search`：按 ticker、公司名、产品名、主题词搜索最新和热门。
2. `tweets`：拉重点 tweet 原文。
3. `thread_context`：拉长 thread 上下文。
4. `article`：如果是 X Article，拉全文。
5. `quotes/replies`：只在需要判断分歧时使用。
6. `user/last_tweets`：只对长期关注某公司或本次观点关键的账号使用。

### 付费与保存

- 如果启用付费 X，调用本地 `$agent-market-x402-payments` skill / wrapper，不要重新手写 x402 支付逻辑。
- 本地默认支付路线已经固化为 Circle CLI `services pay` + Circle Agent Wallet + Base chain。
- 默认 Circle Agent Wallet：`0x8235...f605`。不要切到 `.env` hot wallet，除非用户明确要求 debug。
- wrapper 路径：`C:\Users\user1\.codex\skills\agent-market-x402-payments\scripts\aisa_x402_probe.py`
- 默认运行环境：`D:\工作\Agent支付\.venv\Scripts\python.exe`
- 默认工作目录：`D:\工作\Agent支付`
- 默认链：`BASE`
- 单次 AIsa Twitter `advanced_search` 常见价格：`0.0022 USDC`。
- 循环前估算总成本；单次探测默认小额 cap，例如 `0.01 USDC`。
- 保存 raw JSON、endpoint、paid_cost_usdc、fetched_at。
- 报告里只写核心观点，不贴大段原文。

本地调用模板：

```powershell
D:\工作\Agent支付\.venv\Scripts\python.exe C:\Users\user1\.codex\skills\agent-market-x402-payments\scripts\aisa_x402_probe.py gateway-search --endpoint advanced_search --query '$RBRK lang:en' --query-type Latest --chain BASE --output D:\工作\网页\data\security_software_monitor\paid_x\aisa_gateway_probe_{timestamp}.json
```

日报生成时必须把支付结果结构化保存：

```yaml
x_paid_enabled: true | false
x_mode: off | light | focused | debate
endpoint:
query:
query_type:
chain: BASE
wallet_address_masked: "0x8235...f605"
max_usdc:
paid_cost_usdc:
raw_json_path:
fetched_at:
status: success | skipped | failed
```

如果 `x_paid_enabled = false`，来源里写“未启用付费 X”，不要编造市场观点。

### X 写作规则

必须区分：

- 事实型信息。
- 多头叙事。
- 反方/风险。
- 从业者反馈。
- 公司员工或 vendor 观点。

禁止：

- “某某看好 RBRK/CRWD/PANW”这种无解释摘要。
- 把多个账号观点混成一个没有来源的结论。
- 把 X 观点当事实。

---

## 8. 历史比对

每次生成前必须读取最近报告、thesis memory 或已有事件库。

判断本期事件属于：

- 新事件。
- 旧事件新进展。
- 叙事强化。
- 叙事削弱。
- 叙事反转。
- 市场注意力变化。

报告里用简短句子说明增量，例如：

- “这不是全新主题，新增变量在于……”
- “对收入催化还早，但它强化了……叙事。”
- “和上次相比，今天的证据从产品宣传推进到客户/监管/攻击证据。”
- “目前只能列为观察项，原因是缺少客户采用或财务口径。”

---

## 9. 反营销过滤器

公司官方公告不能直接等于投资结论。遇到产品公告必须快速回答：

1. 是新产品、新模块、新 bundle、新集成，还是旧能力换名？
2. 是否有 GA、定价、客户、渠道、平台集成或财务口径？
3. 是补齐产品短板，还是追随行业叙事？
4. 是否改变与 MSFT / PANW / CRWD / ZS / NET 等平台公司的竞争关系？
5. 是否可能出现在下一次财报电话会或投资者日叙事中？
6. 是否有独立威胁情报、客户案例、从业者反馈或 X 讨论支持？

如果只有营销词，没有实质证据，降级处理。

---

## 10. 推荐运行流程

### Step 0：确定上下文

- 确定 report_date、report_type、x_mode。
- 读取最近 7 篇日报/周报、thesis memory、raw evidence。
- 明确本期重点公司或主题，如用户指定。

### Step 1：广撒网

扫描：

- 安全软件公司新闻、官方博客、IR、SEC。
- 威胁情报、漏洞、CISA KEV、监管。
- AI agent、MCP、coding agent、cloud IAM、data connector、dev platform。
- 重点公司 ticker、公司名、产品名。

### Step 2：生成候选事件

每条候选事件保存：

```yaml
event_id:
headline:
summary:
source_role: discovery | evidence | context | market_view | historical_memory
source_quality: primary | near_primary | secondary | market_view
event_type: company | threat | vulnerability | regulation | ai_agent | cloud | dev_platform | market_view
companies:
direct_or_indirect:
control_points:
what_changed:
historical_delta:
evidence_gap:
scores:
```

### Step 3：影响链分析

对主线候选必须写清：

```text
发生了什么 → 行为/架构怎么变 → 新攻击面/预算需求是什么 → 对应安全控制点 → 相关公司 → 证据强度 → 投资含义
```

链条断裂则降级或不写。

### Step 4：筛选与排序

优先级：

1. 强事实 + 强公司影响。
2. AI/架构变化 + 明确安全控制点。
3. 威胁/漏洞/监管 + 明确预算或产品映射。
4. 市场观点明显变化。
5. 其他观察项。

最终报告只写最重要的 2-4 个主题。不要为了覆盖而堆满。

### Step 5：决定 X 使用

按 x_mode 和触发条件决定是否付费抓 X。

### Step 6：生成报告

使用下面固定模板。

---

## 11. 最终报告模板

```markdown
# 安全软件{日报/周报}｜{date}

## 一句话结论
{用 1-2 句话说明本期最重要判断。不要铺垫。}

## 核心变化
1. **{主题一}**：{事实 + 为什么重要 + 直接/间接影响公司。控制在 120-220 字。}
2. **{主题二}**：{同上。}
3. **{主题三，可选}**：{同上。}

## 公司影响地图
| 公司 | 影响 | 判断 |
|---|---|---|
| {Ticker} | 直接 / 间接 / 观察 | {一句话说明：收入催化、叙事强化、风险、仅观察等} |

## AI / 间接变量
{只写真正有影响链的 AI、agent、MCP、cloud、developer platform 变化。没有就写“本期无足够强的 AI 间接变量”。}

## 市场观点（如使用 X）
{用 2-4 句概括市场在争什么。区分多头、反方、从业者反馈。注明 X 只作为观点源。未使用则省略本节。}

## 后续观察
- {下一个需要验证的产品、客户、财报话术、监管、漏洞利用、X 叙事信号。最多 3 条。}

## 来源
- {来源标题 / source_role / 链接或本地 raw 文件路径}
- {如使用 X，列 raw_json_path 和 paid_cost_usdc}
```

模板要求：

- 公司影响地图只列真正受影响公司，不要机械列全公司池。
- “核心变化”最多 4 条。
- “后续观察”最多 3 条。
- 来源可以列表化，正文必须有判断。
- 如果本期无强主线，标题和一句话结论要直接说明，不要硬造主线。

---

## 12. 最小可用输出

如果本期信息很少，也必须输出简洁版本：

```markdown
# 安全软件日报｜{date}

## 一句话结论
本期没有足够强的安全软件投资催化，主要是若干既有 AI agent / 身份 / 数据安全叙事的弱确认。

## 核心变化
1. **{观察项}**：{简短说明为什么只是观察项。}

## 公司影响地图
| 公司 | 影响 | 判断 |
|---|---|---|
| {Ticker} | 观察 | {为什么还不能升级为催化} |

## 后续观察
- {下一步看什么}

## 来源
- {来源}
```

---

## 13. 质量检查清单

生成前后都要检查：

- 是否扫描了公司公告、IR/SEC、威胁漏洞、监管、AI 间接变量、X 市场观点开关？
- 是否只写了有增量的内容？
- 是否解释了“为什么重要”，而不只是“发生了什么”？
- 是否明确直接影响和间接影响？
- 是否把 AI 事件映射到具体控制点？
- 是否写了历史增量，而不是重复旧判断？
- 是否区分事实、观点、推测？
- 是否避免 vendor marketing 复读？
- 是否列出来源和 raw 文件？
- 如果用了付费 X，是否记录 cost 和 raw JSON？
- 报告是否足够短，且没有漏掉本期关键变量？

---

## 14. 禁止行为

- 不要写泛泛的行业科普。
- 不要把新闻摘要当投研判断。
- 不要把 X 当事实源。
- 不要因为某家公司发了“AI”产品就直接写利好。
- 不要把所有公司都列一遍。
- 不要输出没有来源的强判断。
- 不要为了显得完整而写长篇废话。
- 不要隐藏不确定性；证据不够就写“观察项”。

---

## 15. 内部数据建议

建议保存三类文件，便于历史比对和周报生成。

### raw_evidence

```yaml
source_id:
source_type:
source_name:
url:
fetched_at:
raw_text_path:
raw_json_path:
paid_cost_usdc:
endpoint:
```

### event_candidate

```yaml
event_id:
date:
headline:
summary:
companies:
source_ids:
direct_or_indirect:
control_points:
scores:
status: main | secondary | watch | rejected
```

### thesis_memory

```yaml
thesis_id:
statement:
related_companies:
last_seen:
evidence_count:
confidence: low | medium | high
status: strengthening | weakening | unchanged | watch
```

日报更新 event_candidate 和 thesis_memory；周报优先读取这些结构化记录，不要重新从零开始拼新闻。
