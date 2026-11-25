#!/usr/bin/env python3
"""本地 AI 面试模拟助手。仅使用 Python 标准库。"""
from __future__ import annotations

import base64
import html
import json
import os
import re
from urllib.parse import quote_plus, unquote
import secrets
import threading
import time
import uuid
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
CONFIG = DATA / "config.json"
STATE = DATA / "state.json"
PORT = int(os.environ.get("INTERVIEW_PORT", "8765"))
DOTENV = ROOT / ".env"
QUESTION_SOURCE = ROOT / "questions.md"
MARKET_QUESTIONS = DATA / "market_questions.json"
PROMOTED_QUESTIONS = DATA / "promoted_questions.json"
DATA_LOCK = threading.Lock()

DEFAULT_STATE = {
    "profile": {"job": "商业化产品经理", "mode": "business", "materials": ""},
    "sessions": [],
    "cards": [],
    "stats": {"totalMinutes": 0, "completedSessions": 0, "streak": 0},
}


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def write_json(path: Path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def mask_unverified_numbers(text, source):
    """参考答案不得发明数字；未在题目、回答或资料中出现的数字统一遮蔽。"""
    if not isinstance(text, str):
        return text
    allowed = set(re.findall(r"\d+(?:\.\d+)?", str(source or "")))
    return re.sub(
        r"\d+(?:\.\d+)?",
        lambda match: match.group(0) if match.group(0) in allowed else "[需要补充]",
        text,
    )


def mask_unverified_responsibility(text, candidate_answer):
    """阻止参考答案把“参与/协作”擅自升级为“主导/拍板”。"""
    if not isinstance(text, str):
        return text
    source = str(candidate_answer or "")
    for claim in ("主导", "独立负责", "全权负责", "牵头", "拍板", "最终决策"):
        if claim not in source:
            text = text.replace(claim, "[需要补充职责边界]")
    for action in ("协调", "搭建", "制定", "推动", "上线", "发现", "优化", "确保", "拍板"):
        if action not in source:
            text = text.replace(action, "[需要补充具体动作]")
    while "[需要补充具体动作][需要补充具体动作]" in text:
        text = text.replace(
            "[需要补充具体动作][需要补充具体动作]", "[需要补充具体动作]"
        )
    return text


def question_bank():
    """把人工维护的30题Markdown转换成结构化题库。"""
    try: text = QUESTION_SOURCE.read_text(encoding="utf-8")
    except FileNotFoundError: return []
    items = []
    special = {
        10: {"evidence":["本人负责的分析环节","团队共同决策环节","上线执行责任人"],"followups":["哪些工作由你独立完成？","哪个文档是你产出的？","谁做最终决策？"],"risks":["把团队成果说成个人成果","职责边界模糊"]},
        14: {"evidence":["业务范围与时间","GMV下降口径","漏斗拆解","维度下钻","策略与实验","个人职责与复盘"],"followups":["异常是谁发现的？","为什么按这个顺序拆解？","如果重做会改什么？"],"risks":["数字口径冲突","项目主线不完整","职责夸大"]},
        16: {"evidence":["异常与竞品活动时间重合","受影响用户与价格带匹配","内部因素排查","实验或其他验证"],"followups":["如何排除内部资源变化？","相关性为什么不等于因果？","竞品是唯一原因吗？"],"risks":["把假设直接说成事实","缺少排除性证据"]},
        17: {"evidence":["用户价格带","购物篮金额","商品毛利","替代方案比较","实验验证"],"followups":["满减门槛依据是什么？","为什么不用直降？","如何防止凑单后退款？"],"risks":["策略依据不足","忽略毛利和退款","币种口径错误"]},
        18: {"evidence":["实验组和对照组","下单率","客单价","增量GMV","交互效应"],"followups":["客单价提升是否来自凑单？","如何计算交互项？","下单率显著但ROI不达标怎么办？"],"risks":["把相关性说成因果","没有增量口径","忽略指标交互"]},
        19: {"evidence":["核心指标与目标对应","业务结果指标","策略风险对应的护栏指标"],"followups":["为什么ROI是护栏而非核心？","退款率恶化怎么办？","护栏阈值怎么定？"],"risks":["机械罗列指标","指标与目标不匹配"]},
        20: {"evidence":["增量GMV","毛利率","退款成本","实际核销补贴","对照组自然成交"],"followups":["为什么不能用全量GMV？","优惠券未核销是否算成本？","首月ROI不足怎么办？"],"risks":["使用全量GMV","忽略退款和自然成交","LTV/CAC与活动ROI混淆"]},
        21: {"evidence":["可证伪假设","核心与护栏指标","A/A和随机分流","样本量与周期","显著性与推全条件"],"followups":["为什么先做A/A？","什么是SRM？","何时提前停止实验？"],"risks":["缺少基线检查","只看P值","实验污染"]},
        22: {"evidence":["基准率","MDE","显著性水平alpha","Power","实验流量与周期"],"followups":["MDE为什么这样定？","样本不足怎么办？","两千万是用户还是曝光？"],"risks":["只说软件计算","参数无法解释","样本口径不明"]},
        23: {"evidence":["P值或置信区间","增量收益","成本与护栏","上线阈值"],"followups":["P值小于0.05是什么意思？","统计显著但业务不显著怎么办？"],"risks":["把P值解释为策略有效概率","忽略业务价值"]},
        24: {"evidence":["业务口径","表结构与JOIN","去重和粒度","分步查询","看板核对","明细抽样"],"followups":["如何发现一对多JOIN放大GMV？","AI与看板结果不一致怎么办？","如何保护公司数据？"],"risks":["直接相信AI代码","无法解释SQL","未验证结果"]},
        26: {"evidence":["具体业务场景","AI执行动作","人工验证方法","实际产出","安全边界"],"followups":["AI具体帮你节省哪一步？","如何验证AI结论？","哪些决策不能交给AI？"],"risks":["只说提高效率","编造量化收益","把判断交给AI"]},
        27: {"evidence":["来源核验","事实与推断分开","敏感数据脱敏","企业批准工具"],"followups":["哪些数据绝不能上传？","如何处理模型幻觉？"],"risks":["泄露敏感数据","无来源引用"]}
    }
    pattern = re.compile(r'^###\s+(\d+)\.【([SAB])】(.+?)\n([\s\S]*?)(?=^###\s+\d+\.【[SAB]】|^##\s+|\Z)', re.M)
    for number, priority, title, block in pattern.findall(text):
        def field(label):
            m = re.search(r'^-\s+' + re.escape(label) + r'：(.+)$', block, re.M)
            return m.group(1).strip() if m else ""
        qid = int(number); extra = special.get(qid, {})
        split = lambda value: [x.strip(" `。；") for x in re.split(r'\s*(?:→|；|、|，|\+|\|)\s*', value) if x.strip(" `。；")]
        framework = split(field("回答骨架")) or ["直接回答问题","说明判断依据","给出具体行动和结果","明确职责与复盘"]
        evidence = extra.get("evidence") or split(field("关键证据")) or ["具体场景","个人行动","可核验结果"]
        followups = extra.get("followups") or split(field("风险追问")) or ["你具体负责哪一步？","证据和数据口径是什么？","如果重做会如何优化？"]
        risks = extra.get("risks") or split(field("风险")) or (["答非所问","缺少真实证据"] if priority == "S" else ["回答模板化","缺少岗位变量"])
        items.append({"id": qid, "priority": priority, "question": title.strip(),
                      "category": "商业化项目深挖" if 14 <= int(number) <= 20 else "数据与实验" if 21 <= int(number) <= 25 else "AI与产品" if 26 <= int(number) <= 27 else "产品协作" if int(number) >= 28 else "经历与动机",
                      "intent": field("面试官意图") or "判断候选人是否理解问题、能提供证据并承担职责",
                      "answer_framework": framework, "required_evidence": evidence,
                      "followups": followups, "risk_points": risks, "raw": block.strip()})
    promoted = read_json(PROMOTED_QUESTIONS, [])
    return items + [q for q in promoted if isinstance(q, dict) and q.get("status") == "promoted"]


def jd_interview_plan(company: str, job: str):
    """20题综合面试：4公司行业+4动机匹配+8项目深挖+3基本功+1反问。"""
    bank = {q["id"]: q for q in question_bank()}
    custom = [
        {"id":"jd-c1","category":"公司与行业","priority":"S","question":f"你如何理解{company or '目标公司'}的核心业务和商业模式？","intent":"判断候选人是否做过公司研究","answer_framework":["核心用户","价值主张","收入来源","竞争位置"],"required_evidence":["公开业务事实","产品或服务","商业模式","信息来源"],"followups":["主要竞争对手是谁？","当前增长瓶颈可能是什么？"],"risk_points":["泛泛而谈","把推断说成事实"]},
        {"id":"jd-c2","category":"公司与行业","priority":"A","question":f"你如何看待{company or '目标公司'}所在行业未来两三年的机会与风险？","intent":"判断行业框架和商业判断","answer_framework":["市场驱动","竞争格局","用户变化","机会与风险"],"required_evidence":["行业趋势","竞争变化","与岗位关系"],"followups":["这个趋势如何影响产品策略？"],"risk_points":["只谈宏观趋势","没有岗位落点"]},
        {"id":"jd-c3","category":"公司与行业","priority":"A","question":f"如果让你分析{company or '目标公司'}的一个核心产品，你会从哪些指标开始？","intent":"判断业务拆解能力","answer_framework":["业务目标","用户路径","核心指标","护栏指标"],"required_evidence":["目标用户","业务漏斗","指标口径"],"followups":["为什么选择这个核心指标？"],"risk_points":["机械罗列指标"]},
        {"id":"jd-c4","category":"公司与行业","priority":"A","question":f"与主要竞品相比，你认为{company or '目标公司'}可能有哪些差异化机会？","intent":"判断竞品研究和策略能力","answer_framework":["竞品选择","用户场景","差异证据","机会假设"],"required_evidence":["竞品事实","用户场景","可验证机会"],"followups":["你会如何验证这个机会？"],"risk_points":["功能罗列","无来源推断"]},
        {"id":"jd-r1","category":"反问面试官","priority":"A","question":"现在请你反问面试官一个最有价值的问题，并说明为什么问。","intent":"判断候选人关注点和信息获取能力","answer_framework":["岗位核心目标","当前业务瓶颈","成功标准"],"required_evidence":["问题与岗位相关","能帮助判断工作重点"],"followups":["得到答案后你会如何调整入职计划？"],"risk_points":["只问薪资福利","问题官网可查"]}
    ]
    ids = [1,4,5,7,10,14,15,16,17,18,19,20,21,23,24]
    selected = [bank[i] for i in ids if i in bank]
    motivation = [{**q,"category":"求职动机与岗位匹配"} for q in selected if q["id"] in (1,4,5,7)][:4]
    deep = [{**q,"category":"项目深挖"} for q in selected if q["id"] in (10,14,15,16,17,18,19,20)][:8]
    basics = [{**q,"category":"产品和商业基本功"} for q in selected if q["id"] in (21,23,24)][:3]
    return custom[:4] + motivation + deep + basics + custom[4:]


def normalize_market_question(q, index=0):
    as_list = lambda v: v if isinstance(v, list) else ([str(v)] if v else [])
    priority = str(q.get("priority") or "A").upper()
    priority = {"高":"S", "中":"A", "低":"B", "HIGH":"S", "MEDIUM":"A", "LOW":"B"}.get(priority, priority)
    if priority not in ("S", "A", "B"): priority = "A"
    return {
        "id": str(q.get("id") or f"market-{int(time.time())}-{index}"),
        "category": str(q.get("category") or "市场衍生题"),
        "priority": priority,
        "question": str(q.get("question") or "").strip(),
        "intent": str(q.get("intent") or "检验是否能处理市场变化中的新问题"),
        "market_context": str(q.get("market_context") or ""),
        "answer_framework": as_list(q.get("answer_framework")),
        "required_evidence": as_list(q.get("required_evidence")),
        "followups": as_list(q.get("followups")),
        "risk_points": as_list(q.get("risk_points")),
        "source_refs": as_list(q.get("source_refs")),
        "freshness": str(q.get("freshness") or time.strftime("%Y-%m")),
        "novelty_reason": str(q.get("novelty_reason") or "补充固定题库之外的现实业务变化"),
        "work_skill": str(q.get("work_skill") or "业务判断"),
        "status": str(q.get("status") or "candidate"),
        "generated_at": str(q.get("generated_at") or time.strftime("%Y-%m-%dT%H:%M:%S%z")),
        "practice_count": int(q.get("practice_count") or 0),
        "useful_votes": int(q.get("useful_votes") or 0),
        "last_scores": q.get("last_scores") if isinstance(q.get("last_scores"), dict) else {},
    }


def save_market_questions(questions):
    with DATA_LOCK:
        write_json(MARKET_QUESTIONS, questions)


def update_market_question(qid, updater):
    with DATA_LOCK:
        rows = read_json(MARKET_QUESTIONS, [])
        target = None
        for row in rows:
            if str(row.get("id")) == str(qid):
                updater(row); target = row; break
        write_json(MARKET_QUESTIONS, rows)
        return target


def sanitize_domain_pack(payload):
    """修正常见公式性错误，并明确领域包只是学习导航而非企业内部事实。"""
    if not isinstance(payload, dict):
        return {}
    domain_map = payload.get("domain_map") if isinstance(payload.get("domain_map"), dict) else {}
    metrics = domain_map.get("指标树", [])
    if not isinstance(metrics, list):
        metrics = [str(metrics)] if metrics else []
    cleaned = []
    for item in metrics:
        text = str(item)
        if "GMV" in text and "=" in text and "复购率" in text:
            text = "单周期GMV = 有效流量 × 点击后下单率 × 支付率 × 客单价；复购率用于衡量跨周期用户价值，不应在同一漏斗中重复相乘"
        cleaned.append(text)
    domain_map["指标树"] = cleaned
    payload["domain_map"] = domain_map
    payload["verification_note"] = "本知识包是基于JD与公开资料生成的学习导航；公司内部指标口径、组织流程和策略效果必须在面试或权威资料中核实。"
    return payload


def dotenv_values():
    values = {}
    try:
        for line in DOTENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    values.update({k: v for k, v in os.environ.items() if k.startswith("VOLCENGINE_")})
    return values


def config():
    env = dotenv_values()
    saved = read_json(CONFIG, {
        "deepseek": {"api_key": "", "model": "deepseek-chat", "base_url": "https://api.deepseek.com"},
        "doubao": {"api_key": "", "model": "", "base_url": "https://ark.cn-beijing.volces.com/api/v3"},
        "doubao_tts": {"api_key": "", "resource_id": "seed-tts-2.0", "speaker_id": "zh_female_tvbnv_uranus_bigtts", "speech_rate": 25, "silence_duration": 250},
        "provider": "deepseek",
    })
    # 新版豆包TTS优先从 .env/环境变量读取密钥与可复用配置；兼容旧配置但不再调用旧接口。
    tts = saved.setdefault("doubao_tts", {})
    tts["api_key"] = env.get("VOLCENGINE_API_KEY", tts.get("api_key", ""))
    tts["resource_id"] = env.get("VOLCENGINE_TTS_RESOURCE_ID", tts.get("resource_id", "seed-tts-2.0"))
    tts["speaker_id"] = env.get("VOLCENGINE_SPEAKER_ID", tts.get("speaker_id", "zh_female_tvbnv_uranus_bigtts"))
    return saved


def write_dotenv(values):
    lines = [
        "# 本地语音配置，不要提交到GitHub",
        f"VOLCENGINE_API_KEY={values.get('api_key', '')}",
        f"VOLCENGINE_SPEAKER_ID={values.get('speaker_id', 'zh_female_tvbnv_uranus_bigtts')}",
        f"VOLCENGINE_TTS_RESOURCE_ID={values.get('resource_id', 'seed-tts-2.0')}",
    ]
    DOTENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try: DOTENV.chmod(0o600)
    except OSError: pass


def parse_tts_response(raw: bytes):
    """V3 HTTP接口返回chunked JSON：每行一个JSON，不能整体json.loads。"""
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        one = json.loads(text)
        return one.get("data") or one.get("audio") or one.get("audio_data"), one
    except json.JSONDecodeError:
        chunks, last = [], {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(":") or line.startswith("data:"):
                line = line.removeprefix("data:").strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            last = item
            chunk = item.get("data") or item.get("audio") or item.get("audio_data")
            if isinstance(chunk, dict): chunk = chunk.get("data") or chunk.get("audio")
            if chunk:
                try: chunks.append(base64.b64decode(chunk))
                except (ValueError, base64.binascii.Error): pass
            if str(item.get("code", "")) == "20000000": break
        return base64.b64encode(b"".join(chunks)).decode() if chunks else "", last


def call_json_api(base_url: str, api_key: str, model: str, messages: list, json_mode=False, max_tokens=1800):
    if not api_key:
        raise ValueError("尚未配置 API Key")
    if not model:
        raise ValueError("尚未配置模型名称，请在API设置中填写模型")
    endpoint = base_url.rstrip("/") + "/chat/completions"
    body = {"model": model, "messages": messages, "temperature": 0.65, "stream": False, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    request = Request(endpoint, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"
    })
    try:
        with urlopen(request, timeout=90) as response:
            try:
                raw = response.read()
            except IncompleteRead as exc:
                raw = exc.partial or b""
            if not raw:
                raise RuntimeError("模型接口连接被提前关闭，未返回内容；请稍后重试")
            payload = json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"模型接口返回 {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"无法连接模型接口：{exc.reason}") from exc
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("模型返回格式无法解析") from exc


def web_search(query: str, limit=5):
    """从公开搜索页获取标题、摘要与链接；网络失败时安全降级为空结果。"""
    req = Request("https://html.duckduckgo.com/html/?q=" + quote_plus(query), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=15) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception:
        return []
    rows = []
    for block in re.findall(r'<div class="result[^"]*"[\s\S]*?</div>\s*</div>', text)[:limit]:
        link = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', block)
        if not link: continue
        snippet = re.search(r'class="result__snippet"[^>]*>([\s\S]*?)</', block)
        clean = lambda value: html.unescape(re.sub(r'<[^>]+>', '', value or '')).strip()
        rows.append({"title": clean(link.group(2)), "url": html.unescape(link.group(1)), "snippet": clean(snippet.group(1) if snippet else '')})
    return rows


def interviewer_prompt(body):
    profile = body.get("profile") or {}
    mode = profile.get("mode", "business")
    role_map = {"business": "商业化产品/增长产品业务面试官", "data": "数据分析与实验面试官", "ops": "产品运营面试官"}
    return f"""你是{role_map.get(mode, role_map['business'])}。你正在对候选人进行真实、克制、连续追问式模拟面试。
一次只问一个问题，不要先给答案，不要连续抛多个问题。优先追问：职责边界、指标口径、原因证据、实验设计、业务价值、协作冲突。
自适应规则：每次先判断候选人是否直接回答、覆盖了哪些证据、缺少哪些关键证据、命中了什么风险；下一问必须针对最重要的证据缺口或风险，而不是机械进入新题。一个母题最多连续追问3层，证据闭环后再进入计划中的下一题。若资料中包含“本场20题计划”，按其顺序和类别比例推进。
候选人的资料可能包含“待确认”数据或训练案例：不要替候选人编造事实；发现数字冲突时，追问统计范围和计算口径，并标记需要确认。
当前目标岗位：{profile.get('job', '商业化产品经理')}
当前资料：
{profile.get('materials', '')[:12000]}
JD定制研究简报：
{profile.get('research', '')[:8000]}
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalInterview/0.1"

    def log_message(self, *_):
        return

    def send_json(self, value, status=200):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_GET(self):
        if self.path == "/api/config":
            c = config()
            safe = {k: dict(v) if isinstance(v, dict) else v for k, v in c.items()}
            for provider in ("deepseek", "doubao"):
                if provider in safe:
                    safe[provider]["api_key"] = "" if not safe[provider].get("api_key") else "••••••••"
            safe["doubao_tts"]["api_key"] = "" if not safe["doubao_tts"].get("api_key") else "••••••••"
            return self.send_json(safe)
        if self.path == "/api/state":
            return self.send_json(read_json(STATE, DEFAULT_STATE))
        if self.path == "/api/questions":
            return self.send_json({"ok": True, "questions": question_bank()})
        if self.path == "/api/market-questions":
            return self.send_json({"ok": True, "questions": read_json(MARKET_QUESTIONS, []), "promoted": read_json(PROMOTED_QUESTIONS, [])})
        request_path = unquote(self.path.split("?", 1)[0])
        path = ROOT / ("index.html" if request_path in ("", "/") else request_path.lstrip("/"))
        if request_path in ("", "/", "/index.html", "/三天背诵训练器-商业化产品面试.html") and path.exists() and path.is_file():
            mime = "text/html; charset=utf-8" if path.suffix == ".html" else "text/plain; charset=utf-8"
            raw = path.read_bytes()
            self.send_response(200); self.send_header("Content-Type", mime); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        else:
            self.send_error(404)

    def do_POST(self):
        try:
            body = self.body()
            if self.path == "/api/config":
                old = config()
                for key in ("deepseek", "doubao", "doubao_tts"):
                    if key in body:
                        updates = {k: v for k, v in body[key].items() if v != "••••••••"}
                        # 空白API Key代表“保持原配置”，避免刷新页面后测试按钮清空密钥。
                        if "api_key" in updates and not updates["api_key"]:
                            updates.pop("api_key")
                        # 语音密钥单独写入本地.env，不进入config.json。
                        if key == "doubao_tts" and "api_key" in updates:
                            write_dotenv({**old.get(key, {}), **updates})
                            updates.pop("api_key", None)
                        old.setdefault(key, {}).update(updates)
                old["provider"] = body.get("provider", old.get("provider", "deepseek"))
                write_json(CONFIG, old)
                return self.send_json({"ok": True})
            if self.path == "/api/state":
                state = body.get("state", DEFAULT_STATE)
                write_json(STATE, state)
                return self.send_json({"ok": True})
            if self.path == "/api/domain-pack":
                c = config(); provider = body.get("provider") or c.get("provider", "deepseek"); p = c.get(provider, {})
                company = str(body.get("company", "")).strip(); job = str(body.get("job", "商业化产品经理")).strip()
                jd = str(body.get("jd", ""))[:12000]; report = str(body.get("report", ""))[:10000]
                sources = body.get("sources", [])[:20] if isinstance(body.get("sources"), list) else []
                saved_knowledge = body.get("knowledge_library", [])[:30] if isinstance(body.get("knowledge_library"), list) else []
                if not jd: raise ValueError("请先粘贴JD并生成岗位简报")
                messages = [{"role":"system","content":"""你是产品经理领域知识教练。请根据JD、研究简报和公开来源，生成面试前可学习的最小领域知识包。目的不是堆术语，而是让学习者理解业务系统后再做Case。严格区分：JD明示、公开事实、合理推断；不确定内容标记“待核实”。用户收藏的知识仅是学习笔记：相关时可复用其框架，不得将其当成目标公司的内部事实，发现冲突时以JD与可靠公开来源为准。所有业务公式必须做量纲和重复计算检查；尤其不得把复购率直接乘入单周期GMV漏斗，复购属于跨周期价值指标。输出严格JSON：
domain_name；scope_note（事实边界）；
domain_map对象，必须包含价值链图、用户场景图、业务流程图、指标树、策略杠杆图、风险约束图，每项为3—7条字符串数组；
must_know数组5—10项，每项包含term、plain_explanation、why_it_matters、common_mistake；
understanding_checks数组3项，每项包含question、answer_points数组；
case_card对象，字段包含category、priority、question、intent、market_context、answer_framework数组、required_evidence数组、followups数组、risk_points数组、source_refs数组、novelty_reason、work_skill；
case_card必须是一个有真实目标、约束和取舍的陌生业务Case，不能要求候选人声称做过；只能基于现有资料推演，不能虚构公司内部数据。"""},{"role":"user","content":json.dumps({"company":company,"job":job,"jd":jd,"research_report":report,"sources":sources,"saved_knowledge_notes":saved_knowledge,"current_date":time.strftime("%Y-%m-%d")},ensure_ascii=False)}]
                content = call_json_api(p.get("base_url", ""), p.get("api_key", ""), p.get("model", ""), messages, json_mode=True, max_tokens=4200)
                try: payload = json.loads(content)
                except json.JSONDecodeError: raise RuntimeError("领域知识包返回格式无法解析，请重试")
                payload = sanitize_domain_pack(payload)
                domain_map = payload.get("domain_map") if isinstance(payload.get("domain_map"), dict) else {}
                for key in ("价值链图","用户场景图","业务流程图","指标树","策略杠杆图","风险约束图"):
                    value = domain_map.get(key, [])
                    domain_map[key] = value if isinstance(value, list) else ([str(value)] if value else [])
                payload["domain_map"] = domain_map
                payload["must_know"] = payload.get("must_know") if isinstance(payload.get("must_know"), list) else []
                payload["understanding_checks"] = payload.get("understanding_checks") if isinstance(payload.get("understanding_checks"), list) else []
                case_card = normalize_market_question(payload.get("case_card", {}))
                case_card.update({"id":f"domain-case-{int(time.time())}","status":"training","source_type":"JD领域知识包","domain_name":payload.get("domain_name", "")})
                payload["case_card"] = case_card
                payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                return self.send_json({"ok":True,"domain_pack":payload})
            if self.path == "/api/generate-transfer":
                c = config(); provider = body.get("provider") or c.get("provider", "deepseek"); p = c.get(provider, {})
                original = body.get("original_question", {}) if isinstance(body.get("original_question"), dict) else {}
                diagnosis = body.get("diagnosis", {}) if isinstance(body.get("diagnosis"), dict) else {}
                domain_pack = body.get("domain_pack", {}) if isinstance(body.get("domain_pack"), dict) else {}
                materials = str(body.get("materials", ""))[:6000]
                saved_knowledge = body.get("knowledge_library", [])[:30] if isinstance(body.get("knowledge_library"), list) else []
                messages = [{"role":"system","content":"""你是迁移学习教练。根据原题和本轮最薄弱的思维能力，生成：1）底层能力相同、表面业务场景不同的变式Case；2）一道回看候选人旧项目的问题，用来区分“当时实际做过”与“现在如果重做会怎样优化”。用户收藏的知识是学习笔记，只能用于启发框架和追问，不得当作候选人的真实经历或公司的内部事实。输出严格JSON：variant_case、project_reflection_question、transfer_focus、why_this_tests_transfer。variant_case字段与训练题卡一致：category、priority、question、intent、market_context、answer_framework数组、required_evidence数组、followups数组、risk_points数组、source_refs数组、novelty_reason、work_skill。变式题必须跨越行业或根本业务机制，禁止使用原题的同一行业、同一平台类型或相邻品类；例如原题是电商农产品，不得改成生鲜、水产或其他电商品类，应迁移到SaaS续费、广告竞价、内容生态、出行调度、AI产品质量等不同机制。保持同一底层能力，但重新定义业务目标、约束、指标和风险；不得只改名换皮，不得要求候选人编造经历。项目回看问题不得把后来学到的知识写成过去做过。"""},{"role":"user","content":json.dumps({"original_question":original,"diagnosis":diagnosis,"domain_name":domain_pack.get("domain_name"),"domain_map":domain_pack.get("domain_map"),"saved_knowledge_notes":saved_knowledge,"personal_materials":materials},ensure_ascii=False)}]
                content = call_json_api(p.get("base_url", ""), p.get("api_key", ""), p.get("model", ""), messages, json_mode=True, max_tokens=2400)
                try: payload = json.loads(content)
                except json.JSONDecodeError: raise RuntimeError("迁移题返回格式无法解析，请重试")
                card = normalize_market_question(payload.get("variant_case", {}))
                card.update({"id":f"transfer-case-{int(time.time())}","status":"training","source_type":"跨场景变式","transfer_focus":payload.get("transfer_focus", "")})
                return self.send_json({"ok":True,"variant_case":card,"project_reflection_question":str(payload.get("project_reflection_question", "")),"transfer_focus":str(payload.get("transfer_focus", "")),"why_this_tests_transfer":str(payload.get("why_this_tests_transfer", ""))})
            if self.path == "/api/generate-market-questions":
                c = config(); provider = body.get("provider") or c.get("provider", "deepseek"); p = c.get(provider, {})
                company = str(body.get("company", "")).strip(); job = str(body.get("job", "商业化产品经理")).strip()
                jd = str(body.get("jd", ""))[:10000]; weaknesses = body.get("weaknesses", {})
                queries = [f"{job} 2026 招聘 JD AI 数据 商业化", f"{company} 行业 2026 趋势 竞争 商业模式", f"AI 产品经理 商业化 增长 风险 治理 2026"]
                sources = []
                for query in queries: sources.extend(web_search(query, 5))
                base_titles = [q["question"] for q in question_bank()[:30]]
                messages = [{"role":"system","content":"你是产品经理能力训练设计师。结合近期公开搜索摘要、目标JD和个人能力短板，生成8道固定30题之外的现实业务衍生题。题目必须训练真实工作判断，不是换皮概念题；至少包含AI落地、商业策略、数据归因、组织协作和市场变化。严格区分公开事实与合理推断，不确定时标记待核实。输出严格JSON对象，字段questions为数组；每题字段：category、priority、question、intent、market_context、answer_framework数组、required_evidence数组、followups数组、risk_points数组、source_refs数组、freshness、novelty_reason、work_skill。不得与existing_questions语义重复。source_refs使用搜索结果标题或URL；没有可靠来源时写“基于JD与业务场景推演”。"},{"role":"user","content":json.dumps({"company":company,"job":job,"jd":jd,"weaknesses":weaknesses,"existing_questions":base_titles,"search_results":sources,"current_date":"2026-08-27"},ensure_ascii=False)}]
                content = call_json_api(p.get("base_url", ""), p.get("api_key", ""), p.get("model", ""), messages, json_mode=True, max_tokens=3500)
                try: payload = json.loads(content)
                except json.JSONDecodeError: raise RuntimeError("市场衍生题返回格式无法解析，请重试")
                generated = [normalize_market_question(q, i) for i,q in enumerate(payload.get("questions", [])) if str(q.get("question", "")).strip()]
                old = read_json(MARKET_QUESTIONS, []); seen = {re.sub(r'\W+', '', str(q.get("question", "")).lower()) for q in old}
                fresh = []
                for q in generated:
                    key = re.sub(r'\W+', '', q["question"].lower())
                    if key and key not in seen: seen.add(key); fresh.append(q)
                save_market_questions((old + fresh)[-100:])
                return self.send_json({"ok":True,"questions":fresh,"sources":sources,"skipped_duplicates":len(generated)-len(fresh)})
            if self.path == "/api/market-question-feedback":
                qid = str(body.get("question_id", "")); action = str(body.get("action", ""))
                if not qid: raise ValueError("缺少题目ID")
                def apply(row):
                    if action == "useful": row["useful_votes"] = int(row.get("useful_votes",0)) + 1
                    elif action == "reject": row["status"] = "rejected"
                    elif action == "restore": row["status"] = "candidate"
                    row["eligible"] = int(row.get("practice_count",0)) >= 2 and int(row.get("useful_votes",0)) >= 1 and row.get("status") != "rejected"
                target = update_market_question(qid, apply)
                if not target: raise ValueError("未找到衍生题")
                if action == "promote":
                    eligible = int(target.get("practice_count",0)) >= 2 and int(target.get("useful_votes",0)) >= 1 and target.get("status") != "rejected"
                    if not eligible: raise ValueError("尚未满足晋升条件：至少练习2次并标记1次有价值")
                    def mark(row): row.update({"status":"promoted","eligible":True,"promoted_at":time.strftime("%Y-%m-%dT%H:%M:%S%z")})
                    target = update_market_question(qid, mark)
                    promoted = read_json(PROMOTED_QUESTIONS, [])
                    if not any(str(x.get("id")) == qid for x in promoted): promoted.append(target); write_json(PROMOTED_QUESTIONS, promoted)
                return self.send_json({"ok":True,"question":target})
            if self.path == "/api/research":
                c = config(); provider = body.get("provider") or c.get("provider", "deepseek"); p = c.get(provider, {})
                company = str(body.get("company", "")).strip(); job = str(body.get("job", "")).strip(); jd = str(body.get("jd", ""))[:12000]
                if not jd: raise ValueError("请先粘贴JD")
                queries = [f"{company} 公司 业务 产品 竞争对手", f"{company} 所在行业 市场 趋势", f"{job} 岗位职责 面试问题"]
                sources = []
                for query in queries: sources.extend(web_search(query, 4))
                messages = [{"role":"system","content":"你是求职研究员和业务面试官。必须区分JD明示、搜索资料和合理推断；资料不足要写待核实。输出中文Markdown简报，包含：公司业务与商业模式、行业趋势、主要竞品、岗位核心任务、能力矩阵、候选人可能被追问的20个问题、反问面试官的5个问题、面试准备重点。问题要覆盖公司/行业/岗位匹配以及项目数据、职责和因果深挖。"},{"role":"user","content":json.dumps({"company":company,"job":job,"jd":jd,"search_results":sources},ensure_ascii=False)}]
                report = call_json_api(p.get("base_url", ""), p.get("api_key", ""), p.get("model", ""), messages, max_tokens=3000)
                return self.send_json({"ok":True,"report":report,"sources":sources,"interview_plan":jd_interview_plan(company, job)})
            if self.path == "/api/question-score":
                c = config(); provider = body.get("provider") or c.get("provider", "deepseek"); p = c.get(provider, {})
                q = body.get("question", {}); answer = str(body.get("answer", ""))[:8000]
                prompt = [{"role":"system","content":"""你是严格、自适应的产品经理面试教练。目标不是给出漂亮模板，而是帮助候选人形成面对陌生问题也能迁移的第一性原理思考路径。先识别题型，再使用最合适的子路径；通用内核是：目标→现状→差距→机制→杠杆→验证→决策→反馈。\n逐项检查题卡要求和候选人回答，不要求逐字一致。严格区分已知事实、待验证假设、关键未知、必须由候选人补充的个人证据，绝不能替候选人编造经历或数据。\n输出严格JSON，字段：\n- total_score(0-25)、passed；\n- scores对象：直接回答、逻辑结构、数据证据、职责边界、业务判断，各0-5；\n- reasoning_scores对象：问题定义、机制拆解、假设与证据、验证与归因、权衡与决策、行动闭环、表达清晰，各0-5；\n- question_type；thinking_breakpoint（最关键的思维断点）；minimal_hint（只提示下一步，不泄露完整答案）；\n- strengths、gaps、covered_evidence、missing_evidence、hit_risks、weak_capabilities数组；\n- first_principles_map对象，必须包含目标、现状、差距、机制、杠杆、验证、决策、反馈；每项是针对本题的简洁分析，不是复述模板；\n- information_types对象，包含已知事实、合理假设、关键未知、个人证据，值均为数组；\n- alternatives数组，每项包含方案、适用前提、主要代价；change_conditions数组，说明什么证据出现时应改变结论；\n- better_answer：基于上述推理压缩出的60—120秒自然口语答案，不逐项念八步；未知事实用[需要补充]标记；\n- next_followup、followup_reason。\nnext_followup优先攻击最重要的思维断点、缺失证据或命中风险。18分通过；关键能力低于3分或存在严重数据/职责风险不得稳定掌握。"""},{"role":"user","content":json.dumps({"question":q,"candidate_answer":answer},ensure_ascii=False)}]
                prompt.insert(1, {"role": "system", "content": "证据边界：题卡中的raw、required_evidence、answer_framework只是评分标准，不是已经证实的候选人事实。better_answer中的个人经历、公司、学历、职责、动作、结果和数字，只能来自candidate_answer明确陈述的内容；未陈述的信息必须写成[需要补充经历/职责/数据]，严禁把评分标准改写成候选人的事实，也严禁擅自把参与改成负责或主导。"})
                content = call_json_api(p.get("base_url", ""), p.get("api_key", ""), p.get("model", ""), prompt, json_mode=True, max_tokens=2800)
                try: result = json.loads(content)
                except json.JSONDecodeError: result = {"total_score":0,"passed":False,"gaps":["模型返回无法解析"],"better_answer":content}
                scores = result.get("scores") if isinstance(result.get("scores"), dict) else {}
                result["weak_capabilities"] = result.get("weak_capabilities") or [k for k,v in scores.items() if isinstance(v,(int,float)) and v < 3]
                result["covered_evidence"] = result.get("covered_evidence") or []
                result["missing_evidence"] = result.get("missing_evidence") or q.get("required_evidence", [])
                result["hit_risks"] = result.get("hit_risks") or []
                result["followup_reason"] = result.get("followup_reason") or "继续核实回答中最重要的证据缺口"
                result["reasoning_scores"] = result.get("reasoning_scores") if isinstance(result.get("reasoning_scores"), dict) else {}
                result["thinking_breakpoint"] = result.get("thinking_breakpoint") or "尚未明确问题的目标、形成机制与验证路径"
                result["minimal_hint"] = result.get("minimal_hint") or "先不要给方案：明确目标和口径，再解释结果是怎样产生的。"
                result["first_principles_map"] = result.get("first_principles_map") if isinstance(result.get("first_principles_map"), dict) else {}
                result["information_types"] = result.get("information_types") if isinstance(result.get("information_types"), dict) else {}
                result["alternatives"] = result.get("alternatives") if isinstance(result.get("alternatives"), list) else []
                result["change_conditions"] = result.get("change_conditions") if isinstance(result.get("change_conditions"), list) else []
                result["better_answer"] = mask_unverified_numbers(
                    result.get("better_answer", ""),
                    json.dumps({"question": q, "answer": answer}, ensure_ascii=False),
                )
                result["better_answer"] = mask_unverified_responsibility(
                    result.get("better_answer", ""), answer
                )
                qid = str(q.get("id", ""))
                if qid.startswith("market-"):
                    def record(row):
                        row["practice_count"] = int(row.get("practice_count",0)) + 1
                        row["last_score"] = int(result.get("total_score",0) or 0)
                        row["last_scores"] = scores
                        row["last_missing_evidence"] = result.get("missing_evidence", [])
                        row["last_practiced_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                        row["eligible"] = row["practice_count"] >= 2 and int(row.get("useful_votes",0)) >= 1 and row.get("status") != "rejected"
                    update_market_question(qid, record)
                return self.send_json({"ok":True,"result":result})
            if self.path == "/api/chat":
                c = config(); provider = body.get("provider") or c.get("provider", "deepseek")
                p = c.get(provider, {})
                messages = body.get("messages", [])
                system = interviewer_prompt(body)
                if not messages or messages[0].get("role") != "system":
                    messages = [{"role": "system", "content": system}] + messages
                text = call_json_api(p.get("base_url", ""), p.get("api_key", ""), p.get("model", ""), messages)
                return self.send_json({"ok": True, "content": text, "provider": provider})
            if self.path == "/api/review":
                c = config(); provider = body.get("provider") or c.get("provider", "deepseek"); p = c.get(provider, {})
                # 复盘只发送必要字段，避免长资料和重复上下文导致响应过慢。
                compact_session = dict(body.get("session", {}))
                compact_session["turns"] = compact_session.get("turns", [])[-24:]
                compact_profile = dict(body.get("profile", {}))
                compact_profile["materials"] = compact_profile.get("materials", "")[:6000]
                compact_bank = [{"id":q["id"],"question":q["question"],"category":q["category"],"required_evidence":q["required_evidence"],"risk_points":q["risk_points"]} for q in question_bank()]
                compact_body = {"provider": body.get("provider"), "profile": compact_profile, "session": compact_session, "question_bank": compact_bank}
                prompt = """请根据这场模拟面试输出严格JSON，不要Markdown代码围栏：\n""" + json.dumps(compact_body, ensure_ascii=False)
                review_messages = [
                    {"role": "system", "content": "你是面试复盘教练。目标不只是润色表达，而是训练候选人用第一性原理解决陌生问题。通用内核：目标→现状→差距→机制→杠杆→验证→决策→反馈；根据题型选择重点，不机械念八步。overall_score为0-100整数。输出严格JSON，包含overall_score、scores、overall_summary、evidence、improvement_suggestions、question_feedback、wrong_questions。question_feedback每项必须包含question、risks、question_type、thinking_breakpoint、minimal_hint、first_principles_map（目标/现状/差距/机制/杠杆/验证/决策/反馈）、information_types（已知事实/合理假设/关键未知/个人证据，均为数组）、alternatives（方案/适用前提/主要代价）、change_conditions数组、better_answer。better_answer是60—120秒自然口语答案，必须从推理地图压缩而来，不得替候选人编造事实，未知处用[需要补充]。wrong_questions只收录本场实际涉及且需要复练的母题，匹配题库id；包含question_id、reason、ability_scores（直接回答、逻辑结构、数据证据、职责边界、业务判断，各0-5）、missing_evidence、hit_risks、next_variant_question。任何能力低于3分必须收录；不能匹配时不要编造ID。"},
                    {"role": "user", "content": prompt}]
                review_messages.insert(1, {"role": "system", "content": "严禁新增资料和回答中没有出现的数字、项目动作、职责或结果；缺失处必须写[需要补充]，不能为了示范而编造。"})
                try:
                    content = call_json_api(p.get("base_url", ""), p.get("api_key", ""), p.get("model", ""), review_messages, json_mode=True)
                except RuntimeError as exc:
                    # 仅在明确是不支持 response_format 时降级；超时/断连不能再发第二次请求，避免复盘耗时翻倍。
                    msg = str(exc).lower()
                    if "response_format" not in msg and "json_object" not in msg:
                        raise
                    content = call_json_api(p.get("base_url", ""), p.get("api_key", ""), p.get("model", ""), review_messages, json_mode=False)
                try: result = json.loads(content)
                except json.JSONDecodeError:
                    # 有些模型未严格遵守JSON模式：保留原文，前端仍可查看复盘而不是直接判定失败。
                    cleaned = content.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.strip("`").replace("json\n", "", 1).strip()
                    try: result = json.loads(cleaned)
                    except json.JSONDecodeError: result = {"raw": content, "parse_error": True}
                review_source = json.dumps(compact_body, ensure_ascii=False)
                review_candidate_source = compact_profile.get("materials", "") + "\n" + "\n".join(
                    str(turn.get("content", ""))
                    for turn in compact_session.get("turns", [])
                    if turn.get("role") == "user"
                )
                for feedback in result.get("question_feedback", []) if isinstance(result, dict) else []:
                    if isinstance(feedback, dict):
                        feedback["better_answer"] = mask_unverified_numbers(
                            feedback.get("better_answer", ""), review_source
                        )
                        feedback["better_answer"] = mask_unverified_responsibility(
                            feedback.get("better_answer", ""), review_candidate_source
                        )
                return self.send_json({"ok": True, "review": result})
            if self.path == "/api/tts":
                c = config(); t = c.get("doubao_tts", {}); text = str(body.get("text", ""))[:1000]
                if not t.get("api_key"):
                    return self.send_json({"ok": False, "fallback": True, "message": "未配置豆包语音凭证"})
                payload = {"req_params": {"text": text, "model": "seed-tts-2.0-standard", "speaker": t.get("speaker_id", "zh_female_tvbnv_uranus_bigtts"), "audio_params": {"format": "mp3", "sample_rate": 24000, "bit_rate": 128000, "speech_rate": int(t.get("speech_rate", 25)), "loudness_rate": 0}, "additions": json.dumps({"silence_duration": int(t.get("silence_duration", 250)), "disable_markdown_filter": True}, ensure_ascii=False)}}
                req = Request("https://openspeech.bytedance.com/api/v3/tts/unidirectional", data=json.dumps(payload, ensure_ascii=False).encode(), method="POST", headers={"Content-Type": "application/json", "X-Api-Key": t["api_key"], "X-Api-Resource-Id": t.get("resource_id", "seed-tts-2.0"), "X-Api-Request-Id": str(uuid.uuid4())})
                with urlopen(req, timeout=30) as response:
                    try:
                        raw = response.read()
                    except IncompleteRead as exc:
                        raw = exc.partial or b""
                audio, result = parse_tts_response(raw)
                if not audio: raise RuntimeError(result.get("message", result.get("msg", "豆包TTS未返回音频")))
                return self.send_json({"ok": True, "audio": "data:audio/mp3;base64," + audio})
            if self.path == "/api/export":
                export = DATA / f"interview-export-{time.strftime('%Y%m%d-%H%M%S')}.json"
                write_json(export, body.get("state", read_json(STATE, DEFAULT_STATE)))
                return self.send_json({"ok": True, "path": str(export)})
            self.send_error(404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, 400)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"AI面试模拟助手已启动：http://127.0.0.1:{PORT}")
    print("资料和配置保存在：", DATA)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__":
    main()
