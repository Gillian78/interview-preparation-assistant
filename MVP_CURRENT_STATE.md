> 发布说明：本文记录原始MVP；个人路径与题库名已脱敏。公开副本题源改为项目内questions.md，背诵页为占位页，静态服务改为白名单。

# 面试助手 MVP 现状说明

盘点日期：2026-11-26。范围：`<project-root>`。

本报告以当前 `app.py`、`index.html`、配套背诵 HTML、启动脚本及本地数据结构为依据。旧 PRD、使用说明与测试报告不作为“已实现”的证明。没有修改业务代码，没有调用付费模型、录音或修改训练数据。本次主要为静态调用链审计及数据结构核对，未重新执行真实语音、模型或搜索端到端测试。

**核心结论：现有产品是单人、本地运行的模拟面试与学习工具。AI 扮演面试官，用户回答；语音识别用于录入用户回答。它不是监听真人面试官、实时提取问题并给候选人生成答案的系统。后者需要新增音频输入、问题识别和场景上下文链路。**

文内文件路径相对本报告所在目录；链接和函数名用于定位。`index.html` 存在多次覆盖同名函数/事件的补丁，必须以最后生效的定义为准。

## 1. 产品现状

### 1.1 定位与功能边界

页面定位为“面试空窗期训练场｜项目温故 · 领域学习 · JD定向 · 陌生Case”，面向商业化产品、数据分析、产品运营训练。业务逻辑和固定母题明显偏向商业化产品，并非三套完全独立的题库。

| 功能 | 当前实际实现 | 边界 |
|---|---|---|
| 模拟面试 | 30分钟倒计时、文字回答、AI连续追问、暂停、结束复盘 | 一次会话主要保存在前端内存，结束才保存；暂停/继续存在重置风险 |
| 语音回答 | 浏览器 SpeechRecognition 将语音填入回答框，用户编辑后发送 | 无真人面试官监听、无系统音频采集、无说话人区分 |
| 问题朗读 | 后端豆包 TTS，失败或未配置时浏览器 SpeechSynthesis 回退 | 整段音频返回后播放，没有边生成边播放 |
| 课程训练 | 高频母题、项目温故、错题复练、陌生Case；分类/优先级筛选 | 固定题库来自上级目录 Markdown，不来自运行目录中的 JSON 快照 |
| 单题教练 | 评分、最小提示、补答、推理地图、参考表达、追问 | 每次评分只发送当前题卡和本次回答，无完整多轮课程上下文 |
| JD研究 | 公司/行业/岗位搜索摘要、AI简报、预设20题计划 | 当前仅保留一个 `profile.jd`；比例是计划构成，不是运行时强制控制 |
| 领域学习 | 六张领域图、概念、理解检查、Case | “图”实际是文字列表；理解检查是展开答案，不是自动评估作答 |
| 知识收藏 | 整包、领域图、概念、理解题、Case收藏 | 有公司等元信息，但调用时不按公司隔离 |
| 迁移训练 | 从评分结果生成跨场景题和项目回看题 | 保存生成结果，暂无专用迁移历史浏览页 |
| 市场题管理 | 生成候选题、标记有价值、淘汰、满足条件后晋升 | 精确文本归一化去重；不保证语义去重 |
| 复盘 | 保存会话、AI评分、逐题建议、失败重试 | 页面只展示最近8场，未直接展示全部原始问答 |
| 背诵 | 内嵌独立三天背诵器、遮挡、朗读、抽问、进度 | 内容硬编码，不会随资料库自动重新生成 |
| 每日打卡 | 投递/商业项目/阅读/健身/模拟面试五项、连续天数、近7天 | 手动勾选，无训练完成自动勾选；无午夜定时刷新 |
| 资料与设置 | 文本资料导入保存、模型设置、考官静态图上传、JSON导出 | 无完整简历解析、无账号系统、无完整数据恢复导入 |

主要依据：[index.html](index.html) 的 `startMock`、`finish`、课程训练 IIFE、`renderDomainPack`、`saveKnowledge`、`renderCheckin`；[app.py](app.py) 的 `Handler.do_POST`。

### 1.2 UI页面结构

主界面是原生单页切换，`page(id)` 控制 `.page.active`，没有前端路由框架。

| 导航 | section ID | 页面内容 |
|---|---|---|
| 训练首页 | `home` | 累计时长/完成次数/连续训练、入口、三类岗位说明、学习路径 |
| 课程训练 | `course` | 题库筛选与掌握进度、题卡、回答框、评分与推理结果、Case生成/晋升 |
| JD定制面试 | `jdresearch` | 公司/岗位/JD输入、简报、来源链接、知识包、Case及模拟入口 |
| 开始面试 | `mock` | 静态考官图、聊天、倒计时、语音和发送按钮、岗位/模型/强度配置、目标勾选、每日打卡 |
| 三天背诵 | `memorize` | iframe 加载 `/三天背诵训练器-商业化产品面试.html` |
| 资料库 | `materials` | 岗位与资料文本、文件导入、预览、JSON导出、清空、领域知识收藏 |
| 复盘记录 | `review` | 通过标准说明、最近8场复盘及重试按钮 |
| API设置 | `settings` | DeepSeek/豆包模型、Base URL、Key；TTS音色、资源、语速和停顿 |

CSS 使用12列 Grid，800px以下主要栏位变为单列。因此窄窗口下打卡在长页面底部，容易找不到。`追问强度` 和“本轮目标”可见，但未发现它们被发送到后端或用于提问决策。

### 1.3 完整使用流程与交互关系

1. 双击 `启动面试助手.command`，脚本检查8765端口；已有服务则打开浏览器，否则启动Python并打开页面。
2. `load()` 拉取 `/api/state`、`/api/config`。在设置页保存模型/TTS配置；在资料库保存岗位及个人资料。
3. 选择训练路线：
   - 课程：加载题库 → 筛题 → 回答 → 单题评分 → 首次不达标时最小提示 → 补答 → 完整推理/参考表达 → 追问或迁移题。
   - JD：研究简报 → 领域知识包 → 理解检查/收藏 → 领域Case → JD模拟。UI给出顺序，但不强制完成每一步。
   - 直接模拟：固定自我介绍开场 → 用户手动发送回答 → AI生成下一问 → 自动尝试朗读 → 重复 → 结束保存 → 复盘。
4. 复盘接口返回的 `wrong_questions` 经前端 `api` 包装器写入题目/能力进度，课程“错题复练”读取这些进度。
5. JD知识收藏写入全局 `knowledgeLibrary`；生成知识包和迁移题时取前30条传给模型。
6. 背诵器通过iframe独立使用；打卡通过全局 `state` 保存，与课程成绩、背诵进度没有统一联动。

注意：`startJdMock` 会把JD、简报、计划写进 `profile.materials`，替换现有个人资料文本。它不是只给当前场次附加JD上下文。

## 2. 技术架构

### 2.1 技术栈

- 前端：单文件 HTML、内联 CSS、原生 JavaScript、DOM事件、Fetch API；无 React/Vue、构建器、npm依赖或组件框架。
- 后端：Python标准库，`ThreadingHTTPServer` + `BaseHTTPRequestHandler`，`urllib.request` 调第三方HTTP接口；无Flask/FastAPI、数据库或任务队列。
- 服务：`main()` 绑定 `127.0.0.1`，端口由 `INTERVIEW_PORT` 指定，默认8765。当前是本地单用户服务，没有鉴权、用户隔离、TLS或生产部署配置。
- 浏览器能力：SpeechRecognition、SpeechSynthesis、FileReader、Canvas、localStorage、Blob下载。

### 2.2 目录与依赖

```text
找工作资料包/
├── questions.md  # 运行时固定题源
└── ai面试模拟助手/
    ├── app.py                         # 全部HTTP接口/AI/搜索/TTS/文件存储
    ├── index.html                     # 页面、状态、训练与渲染逻辑
    ├── 三天背诵训练器-商业化产品面试.html # 独立静态背诵器
    ├── start.sh                       # exec python3 app.py
    ├── 启动面试助手.command             # 端口检查、启动、打开浏览器
    ├── .env                           # 语音配置，含敏感凭证，不在报告展示
    ├── .gitignore
    ├── data/
    │   ├── config.json                # 模型和语音配置
    │   ├── state.json                 # 主状态
    │   ├── market_questions.json      # 市场候选题
    │   ├── promoted_questions.json    # 晋升题
    │   └── question_bank.json         # 文件存在，但当前代码未读取
    └── README、使用说明、测试清单及历史报告等.md
```

不能仅复制应用目录就假设题库完整：`QUESTION_SOURCE = ROOT.parent / ...md` 是目录外依赖。缺失时 `question_bank()` 返回空数组，且会提前返回，连晋升题也不会合并。

### 2.3 核心模块职责

| 文件/函数 | 职责 |
|---|---|
| `app.py: read_json / write_json` | JSON读写；临时文件加 `os.replace`；文件权限尝试设0600 |
| `config / dotenv_values / write_dotenv` | 读取配置、环境变量覆盖TTS、保存语音配置 |
| `question_bank / jd_interview_plan` | 解析Markdown、补充题卡字段、组合JD计划 |
| `normalize_market_question / update_market_question` | 生成题统一结构、状态及练习次数管理 |
| `web_search` | 获取并正则解析DuckDuckGo HTML搜索页 |
| `call_json_api / interviewer_prompt` | 模型请求及模拟面试系统指令 |
| `sanitize_domain_pack` | 规范领域包，并替换一种GMV复购公式错误 |
| `mask_unverified_numbers / mask_unverified_responsibility` | 对参考答案数字/职责做字符串级约束 |
| `parse_tts_response` | 解析整包JSON或逐行JSON音频并拼接 |
| `Handler.do_GET / do_POST` | 全部API及静态文件处理 |
| `index.html: api / load / saveState` | 前端请求、恢复、整份状态提交 |
| `startMock / finish / retryReview` | 模拟会话和复盘生命周期 |
| `buildCourseQueue / nextCourseQuestion / updateLearning` | 课程抽题与最新成绩汇总 |
| `renderOneReview / fpMap / renderDomainPack` | 复盘、思考地图、领域包渲染 |
| `saveKnowledge / hydratePersistedLearning` | 收藏与JD/领域包恢复 |

### 2.4 当前接口清单

| 方法/路径 | 主要输入与输出 |
|---|---|
| GET `/api/config` | 返回配置，三个提供方Key脱敏 |
| POST `/api/config` | 保存模型/TTS设置；空Key表示不修改 |
| GET、POST `/api/state` | 读取或整体替换主状态 |
| GET `/api/questions` | Markdown母题 + 已晋升题 |
| GET `/api/market-questions` | 候选题和晋升题 |
| POST `/api/research` | company/job/jd → 简报、来源、计划 |
| POST `/api/domain-pack` | JD/简报/来源/收藏 → 领域包 |
| POST `/api/generate-transfer` | 原题/诊断/领域包/资料/收藏 → 迁移题和项目回看题 |
| POST `/api/generate-market-questions` | JD/公司/岗位/短板 → 衍生题，并写候选题文件 |
| POST `/api/market-question-feedback` | question_id/action → 有价值、淘汰、恢复、晋升 |
| POST `/api/question-score` | 当前question/answer → 结构化评分与参考表达 |
| POST `/api/chat` | profile/messages/provider → 下一轮AI文本 |
| POST `/api/review` | session/profile → 整场复盘JSON或原始文本兜底 |
| POST `/api/tts` | text → MP3 data URL |
| POST `/api/export` | state → 本地导出文件路径；当前UI导出按钮未使用此接口 |

### 2.5 数据存储

`state.json` 实际顶层键为：`profile`、`sessions`、`cards`、`stats`、`questionProgress`、`abilityProgress`、`reasoningProgress`、`knowledgeLibrary`、`learningTransfers`、`checkIns`。初始化默认状态只包含前四项，其余运行时按需创建。

本次结构核对发现3场会话，分别30/10/2条turn；前两场有不同结构的复盘，第三场尚无复盘；5项题目进度、1项知识收藏、2项迁移记录。此处只统计结构，没有在报告复制用户答案或密钥。

背诵器单独使用 `localStorage['ckl-interview-memory-v1']`，保存 `tasks`、`known`；受浏览器和origin影响。`file://` 与 `http://127.0.0.1:8765` 的进度不应假设相同。主应用JSON导出不包含该localStorage，也不包含独立候选题、晋升题及模型配置文件。

## 3. 实时语音识别机制

依据：`index.html` 的 `$('#listen').onclick`、`speak()`；`app.py` 的 `/api/tts`。

| 用户关注的问题 | 实际实现 |
|---|---|
| 如何获取面试官语音 | 没有该链路。AI文本通过TTS播放；语音输入按钮面向候选人回答。未发现 `getDisplayMedia`、系统回环录音、会议音轨接入或说话人分离 |
| 如何转文字 | `window.SpeechRecognition || window.webkitSpeechRecognition`，`lang='zh-CN'`，`interimResults=true`；`onresult` 拼接 `e.results` 中的首个候选文本写入回答框 |
| 如何判断一句话结束 | 交给浏览器识别会话的 `onend`；没有业务层VAD/静音阈值/语义断句；未设置 `continuous=true`，未检查 `isFinal` |
| 如何识别最新问题 | 无问题抽取。当前AI问题只是聊天中的assistant文本；朗读按钮取最后一个AI气泡 |
| 是否有去重 | 语音转录/问题级去重不存在；候选题去重和收藏去重是其他功能，不适用于ASR |
| 是否保留历史转录 | 没有原始音频、转录片段、时间戳或临时结果历史；仅手动发送后的文本进入 `messages`，结束会话后落盘 |

按第二次语音按钮会调用 `recognition.stop()`；结束后 `recognition=null`，再次点击新建实例。新一轮识别结果直接覆盖 `#answer.value`，没有把前一段作为前缀合并。不存在自动识别完就提交的问题处理流程。

浏览器识别的底层引擎、是否经远程服务处理、支持的系统/浏览器及识别效果，本仓库无法确认；没有自建ASR服务或可配置ASR供应商。未实现 `onerror` 提示处理，也未协调TTS播放与ASR监听，扬声器串音属于待实测风险。

## 4. AI回答机制

### 4.1 调用方式和流式输出

`call_json_api()` 请求 `base_url + '/chat/completions'`，Bearer Key鉴权。默认DeepSeek配置为 `deepseek-chat`；豆包支持用户填写模型/接入点。具体生效模型以本地配置为准，本报告不输出配置内容。

请求包含 `temperature=0.65`、`stream=False`、`max_tokens`；JSON任务增加 `response_format={type:'json_object'}`。默认输出上限1800，单题2800、研究3000、市场题3500、领域包4200、迁移2400。`urlopen(timeout=90)` 后整包读取 `choices[0].message.content`。

**没有SSE、WebSocket或前端增量token渲染。** TTS也先读取并拼接全部音频，再返回Base64播放；接口名称里的单向流不代表当前产品实现了实时播放。

### 4.2 当前Prompt及任务分工

完整Prompt原文均在 [app.py](app.py) 中，可按下列函数/路由定位；以下为代码中的关键原文和实际输入。

| 任务 | 当前Prompt关键内容 | 输入边界 |
|---|---|---|
| 模拟面试 `interviewer_prompt` | “一次只问一个问题，不要先给答案”“下一问必须针对最重要的证据缺口或风险”“一个母题最多连续追问3层” | 角色映射、目标岗位、materials前12000字符、research前8000字符及messages |
| 单题 `/api/question-score` | “通用内核是：目标→现状→差距→机制→杠杆→验证→决策→反馈”；要求思维断点、最小提示、推理地图、事实/假设/未知、替代方案和60—120秒 `better_answer` | 当前题卡及candidate_answer，没有前一问答、简历或收藏 |
| 整场 `/api/review` | “目标不只是润色表达，而是训练候选人用第一性原理解决陌生问题”；要求逐题反馈和匹配母题ID的错题 | 最后24条turn、资料前6000字符、精简题库 |
| 研究 `/api/research` | “必须区分JD明示、搜索资料和合理推断”；输出公司/商业模式/竞品/岗位/问题/准备重点 | 当前公司、岗位、JD及搜索摘要 |
| 领域包 `/api/domain-pack` | “最小领域知识包”；收藏只作学习笔记，不可视为公司内部事实；检查公式量纲 | JD、简报、来源前20项、知识收藏前30项 |
| 迁移 `/api/generate-transfer` | “底层能力相同、表面业务场景不同”；禁止同一行业或相邻品类换皮；区分实际做过与如果重做 | 当前题、诊断、领域图、个人资料前6000字符、收藏前30项 |
| 市场衍生 `/api/generate-market-questions` | 生成8道现实业务题，含AI落地/商业策略/归因/协作/市场变化，要求来源与待核实标记 | JD、短板、固定题标题、搜索摘要；`current_date` 硬编码2026-08-27 |

单题和复盘额外约束不得编造个人事实；`mask_unverified_numbers`、`mask_unverified_responsibility` 进一步做字符串替换。这些是启发式处理，不是证据验证系统：题卡里的数字也可能进入允许集合，职责关键词替换还可能误伤正常方法论表述。

模拟接口的职责是提问；参考答案主要在单题评分和整场复盘生成，不存在监听外部问题后自动回答的接口链。

### 4.3 问题传递和上下文记忆

- 模拟：`#send` 将用户文本追加到 `messages`，发送整个数组；AI返回后追加assistant消息。当前会话内有文本上下文，但未结束前仅在内存中。
- 开场自我介绍只调用 `bubble()`，未写入messages；存档和模型上下文缺少这一条assistant开场。
- `startMock()` 清空messages；新场不会自动读取历史sessions或相关旧问题。
- 课程：`#fpFollowup` 把新追问覆盖到当前题卡，保留 `baseId`；评分请求仍然只有新题卡+新回答，未传上一轮问答及诊断。
- 后端Prompt读取 `profile.research`，常规发送请求未提供该字段；JD研究通过改写materials进入上下文。
- “追问最多3层”“按20题比例”靠Prompt约束；未实现显式计数器、问答树或配额调度。

### 4.4 联网与渲染

支持有限联网：`web_search()` 使用 DuckDuckGo HTML页，提取标题/URL/摘要；研究和市场题生成调用它。无正文抓取、引用真实性校验、搜索缓存、时效筛选或向量检索。网络失败返回空列表，模型仍可按JD推演。普通聊天、评分、复盘不主动搜索。

AI聊天使用文本节点，保留换行；JD简报以 `textContent` 显示，Markdown不会完整解析成富文本。评分、领域包和复盘经 `esc()` 后拼装HTML卡片。复盘有JSON解析和字段兼容兜底，但不是完整schema校验；`raw/parse_error` 返回并不保证一定正确展示原文。

## 5. 历史记录机制

| 数据 | 如何保存 | 回看/关联能力 |
|---|---|---|
| 模拟问题、用户回答 | `finish()` 把 `{role,content}` 数组写入 `sessions[].turns` | 有顺序，没有turn ID、父问题ID、时间戳、说话人/音频字段 |
| AI复盘/参考答案 | `sessions[].review`；失败信息 `reviewError` | `renderReviews()` 最近8场；支持重试；无全部历史分页/搜索 |
| 当前未结束模拟 | 全局 `messages`、计时器、DOM | 刷新丢失，没有自动保存草稿/恢复会话 |
| 单题训练 | `questionProgress[id]` 保存次数、最新分数、缺口、风险、连续通过 | 不保存每次完整问题、回答和参考答案；追问共享母题ID |
| 能力汇总 | `abilityProgress`、`reasoningProgress` | 保存最新得分和连续表现；无逐次时间序列 |
| JD | 单个 `profile.jd`，含report/sources/interviewPlan/domainPack | 再生成覆盖旧JD，不绑定场次 |
| 收藏 | `knowledgeLibrary[]` | 全列表回看，有company/domain/job标签，无公司过滤检索 |
| 迁移题 | `learningTransfers[]`，保留最近50条 | 有originalId，但不是通用问题树；无独立历史入口 |
| 打卡 | `checkIns[本地日期]` | 展示近7天，历史键仍在状态内 |

会话结束时先保存turn，再调用复盘，因此复盘失败一般不影响这场turn的落盘。但重新生成复盘使用当前profile资料，而非场次开始时的资料快照，存在旧场次被新资料影响的风险。页面没有原始turn完整回放入口，不能把“JSON中存在”称为“UI可逐问回看”。

## 6. 已确认问题与潜在风险

### 6.1 针对指定五项问题

| 问题 | 结论 | 依据及影响 |
|---|---|---|
| 被打断后重新识别成独立问题 | **不能认定此现象已发生；当前没有自动问题识别功能。已确认输入分段续接缺失。** | 新建recognition后结果覆盖回答框，没有segment合并；若直接扩成面试官监听，会成为断句问题的根源 |
| 无法继承前置问题 | **课程追问链已确认缺上下文；模拟整场不能一概而论。** | 课程评分只传当前question/answer；模拟传messages，可继承当前场历史，但遗漏固定开场 |
| 历史问题不能有效辅助新问题 | **已确认部分缺失。** | 跨场历史未检索注入；课程只复用最新成绩/缺失证据，不复用历史回答全文；同场模拟存在基础上下文 |
| AI答案缺乏专业分析框架 | **不能直接判定“没有框架”。** | 现有Prompt已包含八步推理、事实/假设/未知、取舍、验证与参考表达；领域资料未接入单题评分，框架专业深度和效果仍待评测 |
| 公司知识无法隔离调用 | **已确认。** | company只作元数据；生成领域包/迁移题直接发送全局最近30条收藏；没有companyId和服务端过滤 |

### 6.2 代码确认的其他缺口

1. **个人资料被JD替换**：最终生效的 `#startJdMock.onclick` 重写 `profile.materials`；简历和JD没有分离。
2. **暂停后可能清空会话**：暂停设置 `running=false`；“开始/继续”调用 `startMock()` 会清空messages和重置计时；暂停状态发送也会触发重开。
3. **复盘上下文截断**：只保留最后24条turn。实际存在30条turn会话，重试复盘会丢掉前6条；输出1800 token还要容纳丰富逐题结构，有截断风险。
4. **评分显示与口径不一致**：整场Prompt未固定 `scores` 的具体键；UI却硬查“职责边界”“数据口径”，缺键按0处理。说明要求各项≥3，但实现还使用均分判断；课程使用更严格4分连续两次口径。
5. **课程覆盖层较多**：`#courseScore`、`buildCourseQueue`、`renderOneReview` 等多次赋值；旧代码仍在文件中，阅读较早定义容易误判有效行为。
6. **历史内容不完整可见**：复盘只展示8场，无turn全文；单题只存最新摘要；`cards` 未形成主应用完整独立卡片管理链。
7. **配置控件未贯通**：追问强度和目标勾选未进入请求；默认provider加载到设置控件，但未同步模拟页provider；岗位选择未在发送时同步持久化mode。
8. **统计与打卡分离**：首页 `stats.streak` 未发现更新计算；首页进度用完成次数 `%1`，整数时为0；打卡连续天数另算。
9. **打卡跨日无主动刷新**：日期在渲染/勾选时计算，没有午夜刷新机制；保存失败没有专门回滚反馈。
10. **清空/导出命名超出真实范围**：清空主state不清候选/晋升题和背诵localStorage；“导出全部数据”仅下载state。
11. **搜索时间过期**：市场题搜索词写死2026，输入日期写死2026-08-27，不是真正动态“当前市场”。

### 6.3 潜在风险及上线阻碍

- **静态文件暴露（代码确认）**：`Handler.do_GET` 未设静态文件白名单，存在的ROOT内文件可读，包括 `.env`、`data/config.json`、训练数据。API脱敏不能保护这些静态路径。路径判断也未先resolve再校验。当前绑定回环；改公网监听/加代理之前必须修复。未在本次请求敏感URL进行验证。
- **整份state覆盖与并发写（风险）**：客户端整体POST，无版本号/合并；多个标签页可能最后写覆盖。`write_json`使用固定`.tmp`文件，state保存未使用DATA_LOCK，线程并发可能冲突。
- **异步场次串写（风险）**：`finish` 完成复盘后写 `state.sessions[0]`，不按场次ID定位；进行中新开场、重复结束或未完成请求返回可能造成重复记录或错挂结果。
- **加载竞态（风险）**：JD/知识包已有加载事件，但其他模块仍用300/350/400ms定时器；接口慢时可能未正确恢复。
- **字段/类型不稳定（风险）**：JSON模式不等于业务schema；多个数组、分数和对象依赖模型正确输出，异常结构可能导致渲染错误或误评分。
- **转录质量（待实测）**：浏览器识别兼容性、长句截断、串音、权限失败和实际断句效果未在本次复测。
- **长请求体验（风险）**：同步等待搜索/LLM；无取消、后台job状态和持久化任务，刷新可能只留下未复盘记录。
- **来源可信度（风险）**：只有搜索摘要，无正文证据校验；公司标签和Prompt声明不能替代隔离与引用验证。

## 7. 最小改动的2.0建议（均为未来规划）

优先保留Python HTTP服务、原生页面和旧state兼容读取。先新增结构和服务端上下文组装；暂不必为了这些功能引入向量数据库或更换前端框架。

### 7.1 准备模块与场景绑定

建议新增以下字段/实体，并保留旧 `profile.materials` 作为迁移来源，不原地覆盖：

```text
schemaVersion: 2
resumes[]: {id, name, text, version, updatedAt}
companies[]: {id, name}
jobs[]: {id, companyId, title, jdText, research, sources, version}
knowledgeItems[]: {id, companyId|null, scope, title, text, sourceUrl,
                  evidenceType, updatedAt, version}
scenarios[]: {id, mode, resumeId, jobId, companyId, knowledgeIds, createdAt}
sessions[]: {原字段..., scenarioId, contextSnapshot, status, updatedAt}
```

三个准备模块分别维护简历、岗位、知识库；公司专属知识用companyId绑定，通用框架使用 `scope='general'`。场景启动时固化版本和内容快照，旧场复盘始终使用旧快照。

修改位置：`index.html` 资料库、JD页、`startJdMock`、`startMock`、`finish`；`app.py` DEFAULT_STATE、状态迁移、chat/review/score的上下文读取。

### 7.2 公司知识选择与专业框架

新增后端 `build_context(scenario_id, question, session_id)`：读取绑定简历/JD；仅取当前companyId及通用知识；按关键词、标签、来源和长度预算选取；保留证据ID。不要继续无条件取全局前30条。

先做可解释的关键词检索，数据规模增长后再考虑embedding。单题评分、聊天、领域包、迁移和整场复盘统一复用这个函数，并允许任务选择不同内容预算。

建议评分输出补充 `framework_name`、`why_this_framework`、`assumptions`、`evidence_ids`、`missing_information`、`decision_rule`，将现有八步推理按题型压缩；引用企业事实时必须关联知识条目。已有框架Prompt可以保留，不应从零另建一套无证据模板。

### 7.3 连续问题与问题树

先明确两种场景：`mock`（AI提问、用户答）与未来 `live_practice`（外部语音输入问题）。现有ASR按钮继续用于回答，不应直接改成监听器破坏模拟流程。

```text
transcriptSegments[]:
  {id, sessionId, speaker, text, isFinal, startedAt, endedAt, sequence}
questionNodes[]:
  {id, sessionId, parentQuestionId, rootQuestionId, sourceSegmentIds,
   text, kind, status, revision, createdAt}
turns[]:
  {id, sessionId, questionId, role, content, createdAt}
attempts[]:
  {id, sessionId, questionId, answer, evaluation, contextVersion, createdAt}
```

最小路径：先把现有课程母题/追问写成树，评分携带祖先问题、回答及缺失证据；再做音频连续识别。ASR临时结果仅用于预览，final结果追加片段；短停顿进入可修订候选问题；语义分类为“新问题/补充/追问/更正/非问题”，不靠每次onend创建新问题。允许用户手动合并、拆分、纠正。

去重先使用segment ID/sequence保证幂等，再在同场相邻窗口比较归一化文本；不要跨场全局去重而误删重复训练。系统音频接入及流式ASR不是已有能力，需独立选型并在目标浏览器实测。

### 7.4 历史回看

保留旧sessions展示，新增场次详情：场景快照、原始turn、问题树、每次回答和评分。列表支持分页和按公司/岗位/题型筛选。旧数据按turn顺序展示，不假造旧问题父子关系；旧课程只有汇总，无法恢复过去未保存的答案。

### 7.5 建议接口调整

| 接口（规划） | 改动 |
|---|---|
| `/api/preparation` 或分开的resumes/jobs/knowledge CRUD | 管理三个准备模块；服务端校验ID和公司归属 |
| POST `/api/scenarios` | 创建绑定并校验简历/JD/知识选择 |
| POST `/api/sessions` | 创建场次并固化快照 |
| POST `/api/sessions/{id}/turns` | 增量、幂等保存；替代逐步依赖全量state |
| POST `/api/transcripts` | 接收ASR片段，尚不等于已具备音频ASR服务 |
| POST `/api/questions/resolve` | 合并片段、去重、分类并关联父问题 |
| POST `/api/question-score` | 增加scenarioId/sessionId/questionId/祖先上下文；兼容旧question/answer请求 |
| POST `/api/chat`、`/api/review` | 按sessionId获取快照和turn；不依赖当前profile |
| GET `/api/sessions`、`/api/sessions/{id}` | 历史分页/筛选及完整详情 |

MVP最小实现可先在现有路由中加可选字段，但场次ID和版本校验应由后端负责。JSON可短期保留，至少加锁、独立临时文件和版本冲突检测；多用户服务器阶段再迁移SQLite/其他数据库。

## 8. 开发风险和建议顺序

| 顺序 | 工作 | 对现有功能的风险与控制 |
|---|---|---|
| 1 | 备份现有状态、隔离测试数据；整理最后生效的处理器 | 多次函数覆盖容易误删有效逻辑；保留课程、JD、复盘、背诵、打卡冒烟验证 |
| 2 | 修复暂停/继续、场次ID保存、复盘字段归一化 | 防止训练中断、串写；不把清理UI与数据迁移一次性混做 |
| 3 | 引入schemaVersion及简历/岗位/知识准备实体 | 不覆盖原materials；旧数据无法可靠拆分时标记待用户确认 |
| 4 | 公司隔离、场景绑定、上下文快照 | 验证切换A/B公司不串知识；旧场重试不引用新资料 |
| 5 | turns/attempts增量保存和历史详情 | 兼容旧role/content记录，确保刷新恢复和幂等写入 |
| 6 | 先在课程里实现问题树和前置上下文 | baseId继续用于母题统计，独立questionId用于追问节点，避免统计错位 |
| 7 | 将知识检索与题型框架接入评分/复盘 | 用固定样例比较有无证据时的输出，检查未知事实是否明确标记 |
| 8 | 外部音频/连续ASR试验（如2.0确认需要） | 单独入口验证长句、中断、续说、更正、串音及去重；不影响原语音回答 |
| 9 | UI调整与服务器部署 | 部署前修复静态敏感文件暴露、鉴权、用户隔离、写并发及任务恢复；浏览器语音权限/安全上下文需重新验证 |

建议优先验收的闭环：**选择简历+岗位+公司知识 → 创建场次快照 → 母题/追问继承上下文 → 保存每次回答和反馈 → 刷新恢复 → 按公司回看。** 连续音频识别建立在这个闭环上，避免只有转录更连续而上下文仍然丢失。

## 附：证据索引与盘点限制

- [后端 app.py](app.py)：`call_json_api`、`web_search`、`interviewer_prompt`、`question_bank`、`Handler.do_GET/do_POST`、`main`。
- [前端 index.html](index.html)：`load`、`saveState`、`startMock`、`finish`、`retryReview`、最终覆盖的课程评分事件、`updateLearning`、`saveKnowledge`、`renderDomainPack`、`renderCheckin`。
- [背诵器](三天背诵训练器-商业化产品面试.html)：`STORAGE`、`save`、`updateProgress`、硬编码cards。
- [启动脚本](启动面试助手.command)、[start.sh](start.sh)：启动及生命周期。
- `data/state.json` 仅用于核对字段、记录数量与结构；`data/config.json`、`.env` 未在报告展示密钥。
- 本次没有验证第三方服务可用性、模型实际质量、麦克风权限/识别精度及当前服务器运行代码是否与磁盘完全相同；这些不能由静态代码证明。
