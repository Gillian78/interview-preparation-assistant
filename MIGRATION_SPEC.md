> 发布说明：本文记录原始MVP；个人路径与题库名已脱敏。公开副本题源改为项目内questions.md，背诵页为占位页，静态服务改为白名单。

# Interview Float 知识管理功能迁移分析

日期：2026-11-26。源项目：`<project-root>`。

目标：将五项知识准备能力迁移到 Interview Float（用户指定为 Electron + React + TypeScript），最终只运行一个桌面App，不保留Python助手作为运行时服务。

本次只新增说明文档，未修改业务代码、迁移数据、调用模型或启动服务。分析依据为源项目当前 `app.py` 与 `index.html` 的最终有效调用链；未读取凭证内容或在文档输出个人资料。**尚未检查 Interview Float 仓库，其目录、持久化方案、IPC和实时问答接口均未确认。下文所有目标文件名、类型和接口均为建议，不代表目标项目已有实现。**

## 1. 迁移边界

| 功能 | 结论 |
|---|---|
| 个人资料与简历管理 | 迁移文本保存/导入能力，补充独立简历实体；旧版并没有结构化简历管理 |
| JD拆解与岗位能力分析 | 迁移现有综合研究里的岗位分析部分，拆成独立结构化任务 |
| 公司与行业研究 | 迁移检索、摘要分析、来源展示，补证据关联 |
| 领域知识包生成 | 迁移六张图、概念、事实边界；改为可检索知识结构 |
| 知识收藏与分类管理 | 迁移收藏/类型元数据/展示；分类编辑和检索属于新增 |
| 模拟面试、单题评分、整场复盘、三天背诵、每日打卡 | 不迁移页面、任务、存储和运行依赖；旧数据原地保留 |

旧研究接口返回的 `interview_plan` 是模拟面试计划，应移除运行依赖；`jd_interview_plan()`、`question_bank()` 及目录外固定30题Markdown均不属于本次迁移。领域包中的旧 `case_card`、理解题可作为历史学习材料保留，不迁移训练、评分、题目晋升或迁移训练流程。

## 2. 源项目公共实现

源文件位置：

- [app.py](app.py)：`config()`（约224行）、`call_json_api()`（280行）、`web_search()`（312行）、`Handler.do_POST` 的 `/api/domain-pack`（411行）、`/api/research`（493行）。
- [index.html](index.html)：`saveState/load`、资料保存与导入（约39—45行）；最终生效 `#researchJd` 和 `#startJdMock`（82—83行）；知识收藏和领域包（159—180行）。较早同名事件被覆盖，不能按第一次定义迁移。
- `data/state.json`：资料、当前JD、知识收藏的持久化载体；`read_json/write_json` 读取或整体写入。研究/领域包后端仅返回结果，前端随后POST `/api/state` 才保存。

### 模型公共适配器

`config()` 选择DeepSeek或豆包配置；请求provider优先于默认provider。UI请求实际取模拟页 `#provider` 的值，不能把设置页默认值视为所有调用的保证。

`call_json_api(base_url, api_key, model, messages, json_mode, max_tokens)`：

- 请求 `{base_url}/chat/completions`，Bearer鉴权；默认DeepSeek模型名 `deepseek-chat`，豆包模型/接入点由用户填写。实际保存的选择本次未核验。
- `temperature=0.65`，`stream=False`，`urlopen(timeout=90)`；读取 `choices[0].message.content`。
- 研究输出上限3000 token；领域包4200 token并要求 `response_format: {type:'json_object'}`。
- 支持HTTP/网络异常信息和不完整响应的部分内容处理；没有通用schema校验、自动重试或任务恢复。

目标建议：在Electron主进程或目标项目现有受控服务层实现 `ModelClient.generate()`；React只接收业务DTO，不接触凭证。沿用Interview Float现有模型配置（待核验），不要为了复用功能复制旧Key文件或新开Python/HTTP服务。准备任务可保留非流式生成；实时问答的流式渲染与延迟策略由目标项目单独处理。

### 搜索公共实现

`web_search(query, limit)` 访问DuckDuckGo HTML搜索页，15秒请求超时，正则解析标题/链接/摘要，返回 `{title,url,snippet}[]`。异常直接返回空数组。没有正文抓取、发布/抓取时间、来源ID、搜索状态、去重、可信度排序或逐结论引用。

目标建议：封装 `SearchProvider.search()`，可先保持返回内容兼容，但增加查询、状态、时间及稳定来源ID。搜索失败与“成功但零结果”必须分开。网页内容视为证据材料，不作为系统指令。暂不把替换搜索服务商当成本次迁移前提。

## 3. 五项功能逐项分析

### 3.1 个人资料与简历管理

**原有业务流程与UI**：资料库填写目标岗位及长文本；导入按钮接受 `.md/.txt/.json`，`f.text()` 只把全文填入编辑框，需要再点保存。JSON未解析为简历实体。保存后展示纯文本预览。没有PDF/Word解析、多份简历、结构化履历、版本或独立个人资料页。

**调用关系**：`#saveMaterial.onclick` → 更新 `state.profile.job/materials` → `saveState()` → POST `/api/state` → `write_json(STATE, state)`；加载时 `load()` → GET `/api/state` → `read_json()` → 填表。

**当前结构**：`profile: {job:string, mode:string, materials:string, jd?:object, examinerImage?:string}`。materials是混合文本，并不保证只含简历。**此功能没有专用模型、Prompt或联网搜索。**

**TypeScript建议**：独立 `PersonalProfile` 与 `ResumeDocument`，支持命名、版本及原文；岗位选择迁往Job，不写回简历。提供 `resumeRepository.save/list/getVersion` 和 `ResumeEditor`。第一版保留纯文本/Markdown导入；PDF/Word支持若需要应另列功能，不能声称是迁移已有能力。

**保留规则**：导入先预览再保存；保存失败显示错误；不得把AI生成研究内容当成候选人真实经历。

**迁移风险**：旧materials可能已被 `#startJdMock.onclick` 覆盖为JD/简报/计划。导入时标记 `legacyMixed/unclassified`，保留原文并提示确认类型；不要自动认定为简历，也不能恢复已被覆盖且无备份的旧资料。移除旧的整个profile覆写入口。

### 3.2 JD拆解与岗位能力分析

**原有业务流程与UI**：JD页填写公司、岗位、JD → 点击生成简报 → 返回综合Markdown与来源 → 保存到 `profile.jd` → 显示结果。岗位任务、能力矩阵只是Markdown章节，没有独立可操作的能力字段或简历匹配分数。

**调用关系**：最终 `#researchJd.onclick` → POST `/api/research` → `config()` → 三次 `web_search()` → `call_json_api(..., max_tokens=3000)` → `jd_interview_plan()` → 前端保存state。后者仅服务旧模拟计划，应拆除，不迁移固定题库依赖。

**当前结构**：`profile.jd={company,job,text,report,sources,interviewPlan,domainPack?}`。生成新简报时直接赋新对象，旧JD/知识包被替换。JD输入截断到12000字符，未提示截断。

**模型与Prompt**：共用配置模型。完整原始system Prompt见第5节；要求输出岗位核心任务、能力矩阵等，但不使用JSON输出。user内容为 `{company,job,jd,search_results}`。

**联网及来源**：与公司研究共用同一次请求，不是独立JD拆解；岗位搜索词为“岗位名 岗位职责 面试问题”。输出sources独立于Markdown，没有把JD原句与能力结论建立对应关系。

**TypeScript建议**：建立 `JobDescription` 和版本化 `JobAnalysis`；`analyzeJob()` 默认先基于JD，返回 responsibilities、competencies、businessGoals、requirements、unknowns，能力项关联JD原句。外部岗位资料仅作补充。React用 `JobEditor`、`CompetencyPanel` 展示，用户可查看推断依据。

**保留规则**：JD不能为空；区分明示与推断；输入长度限制须可见；生成失败不得覆盖上一个成功版本。

**风险**：把综合Markdown直接正则拆成能力矩阵会丢失语义。历史report保留为legacy报告，不冒充结构化事实。当前函数没有候选人匹配分析，迁移后若增加匹配，需要明确传入所选简历版本。

### 3.3 公司与行业研究

**原有业务流程/UI**：与3.2共用“生成岗位简报”按钮；右侧显示公司、商业模式、趋势、竞品等文字，另列检索来源链接。没有独立公司列表、研究历史或行业资料仓库。

**Python调用关系**：`/api/research` → `config()` → 依次搜索：

1. `{company} 公司 业务 产品 竞争对手`
2. `{company} 所在行业 市场 趋势`
3. `{job} 岗位职责 面试问题`

每次 `web_search(query,4)`，合并结果供 `call_json_api()`，并原样返回给前端。正则解析可能获得少于预期的结果，不能保证12条。

**当前结构/模型/Prompt**：与3.2完全共用 `profile.jd.report/sources` 和模型调用。没有单独Python“公司分析函数”；业务代码在 `Handler.do_POST` 分支里。不能把它描述成两个独立研究服务。

**来源处理**：只保存 `{title,url,snippet}`；资料为空仍调用模型，前端显示“公开搜索未取得结果；公司事实需进一步核实”。Prompt要求区分证据，但程序不校验引用，也不抓正文。公司名可以为空，只有JD强制非空。

**TypeScript建议**：新增 `Company`、`ResearchRun`、`EvidenceSource`、`ResearchClaim`。`researchCompany(companyId,jobId?)` 收集来源、生成结构化结论、绑定sourceId并保留原报告；React在公司研究页呈现结论与证据抽屉。公司别名和同名实体需确认，不能仅用字符串作身份。

**保留规则**：资料不足明确待核实；搜索失败可降级为JD推断，但状态必须可见；不得把搜索摘要升级为公司内部事实。

**风险**：摘要时效不明、跳转URL未规范化、同名公司混淆、模型虚构来源、重新研究覆盖旧结论。旧数据缺少真实抓取时间，不得用导入时间冒充；建议 `retrievedAt=null, importedAt=...`。

### 3.4 领域知识包生成

**原有业务流程/UI**：已有简报 → 点击生成知识包 → 六张图（文字列表）、概念、可展开理解题、Case → 可收藏整包或子项。前端要求 `profile.jd.report`；后端只校验JD非空，两端前置条件不完全一致。

**调用关系**：`#generateDomainPack.onclick` → `/api/domain-pack` → `config()` → `call_json_api(json_mode=True,max_tokens=4200)` → JSON解析 → `sanitize_domain_pack()` → 列表字段规范化 → `normalize_market_question(case_card)` → 返回 → `d.domainPack=...` → `saveState()` → `renderDomainPack()`。

**当前输入**：JD前12000字符、report前10000字符、sources前20项、全局knowledge_library前30项、当天日期。**此接口不执行新搜索**，复用客户端传入的研究来源。

**当前输出**：

```ts
// 源结构描述；不是目标项目现有类型
interface LegacyDomainPack {
  domain_name: string;
  scope_note: string;
  domain_map: Record<string, string[]>; // 价值链图/用户场景图/业务流程图/指标树/策略杠杆图/风险约束图
  must_know: Array<{term: string; plain_explanation: string; why_it_matters: string; common_mistake: string}>;
  understanding_checks: Array<{question: string; answer_points: string[]}>;
  case_card: Record<string, unknown>;
  verification_note: string;
  generated_at: string;
}
```

**模型/Prompt**：共用所选模型；要求六图每项3—7条、5—10概念、3道理解题、Case，以及来源边界和量纲检查。数组数量只是Prompt要求，代码没有强制校验。原文在 `app.py:418—424`。

**业务规则**：区分JD明示、公开事实、推断；收藏笔记不能充当公司内部事实；不编造公司数据或候选人经历；检查公式重复计算。`sanitize_domain_pack()` 只检测同时含“GMV”“=”“复购率”的字符串并替换为固定公式，不能证明所有公式正确。

**TypeScript建议**：`generateDomainPack()` 输出可验证schema和版本；六图/概念保留，训练用题目不是必填。新增 `KnowledgeUnit`：每个概念、业务机制、指标定义、策略或风险独立成单元，记录适用场景、假设、来源、公司/岗位归属。生成完成后后台建立本地检索索引，实时问答按当前场景检索，不整包塞入Prompt。

**风险**：旧六图字符串没有逐条来源；不能自动补造引用。旧固定公式替换可能把适用口径不同的公式改错；新实现保留检查意图，输出告警和明确单位/分母，慎用无条件替换。生成任务可能在用户切换公司后返回，需用请求捕获的companyId/jobId/version写入，不能读取“当前选中公司”。

### 3.5 知识收藏与分类管理

**原有流程/UI**：领域包的整包/图/概念/理解题/Case收藏按钮 → 元数据+内容 → 查重 → unshift到知识库 → 保存 → 资料库全列表展示。没有分类编辑、标签筛选、搜索、单条删除或来源核验入口；现有“分类”是type/company/domain/job标签。

**函数关系**：`renderDomainPack()` 绑定按钮 → `saveKnowledge(type,title,content)` → `libraryMeta()` → `knowledgeSignature()` → `saveState()` → `/api/state` → `write_json()`。收藏本身没有独立模型或Prompt，也没有搜索；AI只参与上游知识包生成。

**当前数据**：

```ts
interface LegacyKnowledgeItem {
  id: string; type: string; title: string; content: unknown;
  domain: string; company: string; job: string;
  source: string; // 固定描述“JD定制AI生成”，不是证据URL
  savedAt: string;
}
```

签名是 `type + title + JSON.stringify(content)`，**未包含company/job**；相同内容在不同公司下可能被当作重复而无法分别收藏。元数据在点击时从当前 `profile.jd` 获取。独立收藏子项通常不携带sources；整包Case可能有自由文本source_refs，但不是强关联证据ID。

**TypeScript建议**：知识内容与收藏状态分离，收藏记录指向 `knowledgeUnitId`；分类支持type/domain/tags，企业事实必须带companyId。`favoriteKnowledge()` 不再复制一份失去来源的内容，去重键至少包括scope/companyId/jobId/内容哈希，并保留版本和来源链接。

**保留规则**：防重复收藏、明确AI生成属性、持久化后反馈成功；公司事实和通用方法论边界保持可见。

**风险**：跨公司误去重、标签错挂、无来源条目被当作事实；React重构时不能将历史content对象直接渲染，需按类型展示并为未知结构提供文本兜底。

## 4. profile/state 拆分及建议数据结构

以下均为目标建议，可映射到Interview Float已有存储，不要求照搬字段命名。

| 实体 | 建议核心字段 | 约束 |
|---|---|---|
| PersonalProfile | id、用户维护的基本资料 | 与目标公司、岗位分离 |
| ResumeDocument/ResumeVersion | id、profileId、title、version、text、origin、updatedAt | 所选版本不可被研究任务改写 |
| Company | id、name、aliases、website? | name不是主键，别名不自动确认同一公司 |
| JobDescription/JobVersion | id、companyId、title、jdText、version | 必须绑定公司或显式待归属 |
| JobAnalysis | id、jobId、jdVersion、tasks、competencies、assumptions、promptVersion | 每项保留JD原句依据 |
| ResearchRun | id、companyId、jobId?、querySet、status、report、modelId、promptVersion、createdAt | 成功版本不被失败任务覆盖 |
| EvidenceSource | id、researchRunId、url、title、snippet、publishedAt?、retrievedAt?、contentHash? | 区分摘要与正文；来源缺失允许null |
| ResearchClaim | id、researchRunId、text、evidenceType、sourceIds、verificationStatus | AI推断不能标记已验证事实 |
| DomainPack | id、companyId、jobId、jobVersion、researchRunId、version、payload | 保留来源链及生成版本 |
| KnowledgeUnit | id、packId?、companyId?、jobId?、scope、type、title、text、tags、sourceIds、assumptions、version | scope为company/industry/general/unassigned；行业项需industry标签 |
| Favorite | id、knowledgeUnitId、createdAt | 收藏不复制并丢失知识来源 |
| InterviewContext | id、companyId、jobId、resumeVersionId、packVersionIds、selectedKnowledgeIds | 仅描述知识绑定；复用目标实时会话，不迁移旧模拟会话 |

### 防止研究覆盖简历

删除迁移链上的 `startJdMock` 语义；用 `bindInterviewContext()` 返回ID组合，不拼接改写materials。`saveResume()` 和 `saveResearchResult()` 使用独立repository与输入schema，研究写操作没有简历字段。上下文仅在读取时拼装，并在场次启动固定版本。

### 公司隔离

检索前做权限式范围过滤：当前公司 + 当前岗位 + 用户明确选中的通用/同领域知识。其他公司的条目默认不可进入结果；不能先全库召回再让LLM自行分辨。companyId由主进程根据绑定场景解析；公司空值不能自动升级为通用知识。通用化必须为显式动作，并移除/改写公司特定事实。

### 来源与证据

研究生成时给来源分配稳定sourceId；Prompt输出claim→sourceIds，程序验证ID属于本次sources。领域单元继续引用同一来源；收藏保留引用；实时答案可展示支持片段和来源链接。ID有效只证明引用存在，不证明内容支持结论，仍需保留待核实状态。

旧report只有一个来源列表，导入后保持“报告级来源”，不要强行把每条结论与每个URL关联。没有来源的旧条目标记 `legacy_unverified`。

## 5. Prompt迁移策略

### 5.1 原研究Prompt原文

源：`app.py` `/api/research`。

> 你是求职研究员和业务面试官。必须区分JD明示、搜索资料和合理推断；资料不足要写待核实。输出中文Markdown简报，包含：公司业务与商业模式、行业趋势、主要竞品、岗位核心任务、能力矩阵、候选人可能被追问的20个问题、反问面试官的5个问题、面试准备重点。问题要覆盖公司/行业/岗位匹配以及项目数据、职责和因果深挖。

可作为第一阶段对照基线原样运行，但最终建议拆成 `analyzeJob` 与 `researchCompany` 两个Prompt，输出结构化字段及证据ID。删除固定20题/5反问的硬性要求，避免将准备研究变成模拟训练任务。

### 5.2 领域包Prompt可保留部分

下列规则可以原文保留：

> 严格区分：JD明示、公开事实、合理推断；不确定内容标记“待核实”。
>
> 用户收藏的知识仅是学习笔记：相关时可复用其框架，不得将其当成目标公司的内部事实，发现冲突时以JD与可靠公开来源为准。
>
> 所有业务公式必须做量纲和重复计算检查；尤其不得把复购率直接乘入单周期GMV漏斗，复购属于跨周期价值指标。

六图与概念解释逻辑可以保留。完整旧Prompt不能无修改作为目标终版：其目标是“理解业务系统后再做Case”，要求必出理解题和case_card；新目标需要可检索单元、适用条件、事实类型、来源ID及口径，而非训练评分字段。

### 5.3 必须新设计的实时检索/回答Prompt

源项目没有知识检索Prompt；`interviewer_prompt` 是扮演面试官提问，不能迁来充当答题助手。评分/复盘Prompt也不迁移。

目标实时流程建议分为“查询意图/题型识别”和“基于所选证据生成回答”两步，允许简单问题跳过额外模型路由以控制延迟：

- 输入：当前问题、目标项目提供的必要前置问题上下文、当前场景绑定、选定简历证据和召回知识片段。
- 输出：问题意图、适用分析框架、简洁结论、论据/步骤、关键假设或待补信息、sourceIds。
- 约束：只能用选定简历中的内容描述个人经历；公司事实来自本公司证据；通用框架不是个人业绩；无依据时明确未知；不同题型选择框架而非机械套八步。

当前源项目不存在上述实时功能；目标Interview Float如何识别问题和传入连续上下文需对接核验，本次不设计或实现其音频采集/评分系统。

## 6. 领域知识包如何服务实时检索

建议离线准备完成后入库索引，实时仅召回已准备内容：

1. 按六图条目、概念、指标定义等语义边界切成KnowledgeUnit，附带口径、假设和来源，避免拆散公式及条件。
2. 用场景companyId/jobId/resumeVersion确定范围，再按问题关键词、标签、题型做本地全文搜索；可优先采用目标现有数据库全文索引。SQLite FTS只是建议，尚未确认目标使用SQLite。
3. 同一公司内按相关性、来源状态、版本和时间排序，合并重复片段，限定上下文预算。向量召回不是首版必要条件。
4. 构建 `RetrievalHit {unitId, version, text, sourceIds, evidenceType, scope, score}`，供实时回答器使用。简历证据单独标记，不混作公司研究资料。
5. 检索零命中时返回明确状态；可给通用框架并提示缺信息，不临时混入其他公司知识。联网补充作为用户可控的慢路径，不阻塞基础实时回答。
6. 记录本次选用的unit/version/source ID，便于回看答案依据；索引可从内容重新生成，不迁移旧模型配置或训练记录。

## 7. TypeScript模块和接口建议

以下路径是**逻辑模块示例**，实施前须对照Interview Float现有结构映射；不能据此认定这些文件已存在。

```text
src/shared/knowledge/types.ts          # 实体及IPC DTO
src/shared/knowledge/schemas.ts        # 运行时输入/模型输出校验
src/main/knowledge/repositories.ts    # 独立实体持久化、版本与事务
src/main/knowledge/legacyImport.ts    # 旧state一次性导入
src/main/knowledge/modelClient.ts     # 复用目标模型适配层
src/main/knowledge/searchProvider.ts  # 来源采集与状态
src/main/knowledge/jobAnalysis.ts     # JD拆解
src/main/knowledge/companyResearch.ts # 公司行业研究
src/main/knowledge/domainPack.ts      # 知识包生成/规范化
src/main/knowledge/retrieval.ts       # 作用域过滤/检索/上下文组装
src/main/knowledge/prompts.ts         # 带版本的Prompt
src/preload/knowledgeBridge.ts        # 白名单IPC，需适配目标现有preload
src/renderer/features/preparation/   # React简历/岗位/知识准备页
```

| 源调用 | 目标建议接口 | 说明 |
|---|---|---|
| `/api/state`全量读写 | `resume.save`、`job.save`、`knowledge.save`等 | 避免多窗口全量覆盖 |
| `/api/research` | `job.analyze(jobId)`、`company.research(companyId,jobId?)` | 从一个混合请求拆业务职责 |
| `/api/domain-pack` | `domainPack.generate(jobId,researchRunId,knowledgeIds)` | 主进程验证知识归属 |
| `saveKnowledge` | `knowledge.favorite(unitId)` | 内容与收藏状态分离 |
| 无 | `interviewContext.bind(...)` | 绑定所选资料版本，不修改实体 |
| 无 | `knowledge.retrieve(contextId,query)` | 实时问答的受控检索入口 |

生成请求返回jobId/状态，主进程执行并按固定实体ID保存；renderer接收进度或完成事件。新增任务状态和取消需复用目标已有机制（若有），不是现有Python能力。模型调用/搜索/文件写入不放React组件中；不把旧任意静态文件HTTP服务迁入桌面App。

## 8. 旧数据导入方案（规划，不在本次执行）

1. 只读旧 `data/state.json`，记录源文件摘要；目标先生成导入预览，不修改源文件。
2. `profile.materials` → 待确认个人资料文档；若含JD/简报段落，标记混合资料，用户确认后再归类。
3. `profile.jd` → Company + JobVersion + legacy ResearchRun；sources原样保留。不存在的旧版本不能恢复。
4. `profile.jd.domainPack` → DomainPack旧格式版本及子单元；来源无法逐条确认时保持包级关系。
5. `knowledgeLibrary[]` → KnowledgeUnit + Favorite；按旧标签映射公司，不确定归属放unassigned。保留原ID映射和旧savedAt，不迁移个人内容到本说明文档。
6. 不导入sessions、题目/能力成绩、迁移训练、打卡、考官图片、三天背诵localStorage、候选题、晋升题；不导入 `.env` 或 `config.json` 凭证。
7. 以 `sourceHash + legacyId/entityPath` 保证重复导入幂等；整次写入用事务或等价回滚机制。失败不留下半套公司与知识关系。

旧源是一个当前JD加全局收藏，不是完整多公司库。迁移只能保存仍然存在的内容，不能从标签推断遗失的研究历史。

## 9. 风险、实施顺序与验收标准

### 风险

- 目标架构未核验：先确认main/preload/renderer边界、现有存储、模型配置、检索与实时会话接口，避免重复造模块。
- 实体分离会改变旧资料组合方式；旧materials不能默认可信地解析为简历。
- 公司切换与后台生成并发可能写错归属；所有任务绑定请求时的ID和版本。
- 旧知识无逐条证据，不能因迁移而被标为已验证；同名公司和跨公司去重须审查。
- 直接拼接全部旧知识会增加延迟和串公司风险；必须先过滤再召回。
- 原始JSON模式不保证字段正确；运行时schema校验和失败保留旧版本必需。
- JSON导入、网页摘要和模型内容均为不可信输入；文本渲染、URL协议和IPC载荷需校验。
- 不迁移旧HTTP服务及Key管理；目标凭证方案以已有实现为准，避免renderer可读的明文密钥。

### 建议开发顺序

1. 核验Interview Float架构并确定实体/IPC契约。
2. 建立独立简历、公司、岗位、知识实体与版本，完成可回滚旧数据导入。
3. 接入JD分析和公司研究，先保留来源再生成结论。
4. 接入领域包及知识收藏分类，建立KnowledgeUnit与来源链。
5. 绑定实时面试场景，接入公司过滤与本地检索。
6. 重新设计实时回答Prompt，评估依据完整性、领域适配和延迟。
7. 完成单桌面App端到端验收后，再由用户决定归档旧应用和停用旧启动自动化；本次没有停服务或变更自动化。

### 必须通过的行为验收

- 更新JD/研究/领域包后，简历原文和版本完全不变。
- A公司与B公司切换、并发生成、重复收藏时，数据归属和检索互不混用。
- 检索结果包含可回溯的版本/来源；未知来源保持未知，不补造URL。
- 新领域包可被实时问题召回；概念、指标和适用假设一起返回。
- 简历经历与公司研究证据在回答中分开使用；未提供的个人成果不被生成。
- 搜索失败、模型超时、输出JSON损坏时保留上次成功结果并可重试。
- 重复导入不增加重复实体；旧项目数据不变；所有功能无需Python服务运行。
- 被排除的模拟、评分、复盘、背诵、打卡不进入目标导航或后台依赖。

## 10. 结论与交接边界

可复用的核心是：研究任务的输入组织、证据边界规则、六图概念结构、知识收藏粒度和模型/搜索适配逻辑。不能照搬的是单个profile/state、JD覆盖materials、全局前30条知识注入，以及扮演面试官的Prompt。

下一阶段的最小完整链路应为：**独立简历与岗位 → 公司研究及来源 → 领域知识单元 → 按公司绑定 → 实时问题检索与引用。** 本文提供源实现和目标契约建议，目标仓库具体改动点需在获准开发并读取Interview Float代码后最终确定。
