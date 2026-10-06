"""Curated, versioned prerequisites and scoring points; no generated edges."""

RUBRIC_VERSION = "growth-rubric-v1"
GROUPS = ["开发基础", "AI 应用", "Agent 工程"]
LEVELS = [
    "识别概念并说明用途", "独立解释核心概念和链路", "应用场景、解释代码并跨日复测",
    "提交实现和运行记录并通过追问", "迁移新场景并解释取舍、边界和排障",
]


def skill(identifier, name, group, dependencies, points, practice, aliases=()):
    return {
        "id": identifier, "name": name, "group": group, "dependencies": dependencies,
        "points": [{"id": key, "name": label} for key, label in points],
        "practice": practice, "aliases": [name, *aliases], "rubricVersion": RUBRIC_VERSION,
    }


CATALOG = [
    skill("python", "Python", GROUPS[0], [], [("types", "数据类型与函数"), ("errors", "异常处理"), ("async", "异步与阻塞")], "为 Career Radar 的输入转换写一个小函数，覆盖正常输入、空值和异常，并解释返回值。"),
    skill("http", "HTTP", GROUPS[0], [], [("request", "Request / Response"), ("methods", "GET / POST"), ("status", "400 / 500"), ("headers", "Headers"), ("session", "Cookie / Session")], "阅读 Career Radar 的一个 API route，画出请求、参数校验、业务处理、JSON 响应和前端错误处理链路。", ("HTTP API", "网络协议")),
    skill("sql", "SQL / SQLite", GROUPS[0], ["python"], [("query", "查询与参数绑定"), ("transaction", "事务与一致性"), ("index", "索引与迁移")], "为 Career Radar 一个查询解释参数绑定与事务边界，提交查询示例及测试结果。", ("SQL", "SQLite", "MySQL", "PostgreSQL")),
    skill("api", "API 开发", GROUPS[0], ["python", "http"], [("validation", "请求与响应校验"), ("errors", "错误与幂等"), ("testing", "接口契约与测试")], "为 Career Radar 的一个 FastAPI 接口补一个正常场景和一个非法输入场景，解释状态码与结构化响应。", ("FastAPI", "Flask", "后端开发")),
    skill("frontend", "前端交互", GROUPS[0], ["http"], [("state", "状态与数据流"), ("fetch", "请求与异步状态"), ("a11y", "可访问性与窄屏")], "检查 Career Radar 一个 React 页面，补齐加载、空数据、错误和键盘操作中的一个缺口。", ("React", "TypeScript", "前端")),
    skill("llm", "模型调用", GROUPS[1], ["api"], [("context", "上下文与提示词"), ("schema", "结构化输出"), ("failure", "超时、重试与成本")], "追踪 Career Radar 的结构化模型调用，解释输入、Schema 校验与失败重试，并提交一个假模型测试。", ("LLM", "大模型", "OpenAI", "结构化输出", "Prompt")),
    skill("rag", "RAG", GROUPS[1], ["llm", "sql"], [("retrieve", "切分、检索与召回"), ("ground", "引用与事实依据"), ("evaluate", "检索与回答评估")], "从 Career Radar 的 JD 中构造三条检索样例，给出预期引用和一个错误召回案例，解释如何评估。", ("检索增强生成", "Embedding", "向量检索")),
    skill("evaluation", "评估与测试", GROUPS[1], ["llm"], [("rubric", "评分标准与样例"), ("regression", "离线回归"), ("limits", "偏差与证据边界")], "为 Career Radar 一次模型判断准备正确、错误和证据不足三种固定样例，提交评分依据。", ("Eval", "Evals", "评估体系")),
    skill("tools", "工具调用", GROUPS[2], ["llm"], [("contract", "工具接口与参数"), ("permission", "权限与输入边界"), ("recovery", "调用失败与恢复")], "为 Career Radar 一个只读工具定义输入输出和错误分支，用假工具验证失败恢复。", ("Function Calling", "Tool Calling", "MCP")),
    skill("memory", "状态与 Memory", GROUPS[2], ["llm", "sql"], [("state", "会话与持久状态"), ("memory", "记忆更新与失效"), ("replay", "幂等与恢复")], "解释 Career Radar 一项状态如何持久化，补一个重复提交或重启恢复测试。", ("Memory", "状态管理", "记忆")),
    skill("agent", "Agent 规划", GROUPS[2], ["tools", "memory", "evaluation"], [("plan", "任务分解与停止条件"), ("feedback", "反馈与重新规划"), ("trace", "执行轨迹与评估")], "为 Career Radar 的两步任务写清状态转换、停止条件和失败恢复，并用假模型验证轨迹。", ("AI Agent", "Agent", "LangGraph", "LangChain")),
]

HTTP_REFERENCE_NOTES = """官方规则边界（用于校准题目和讲解，只解释当前题目相关部分）：
HTTP/1.1 有文本起始行、头部和空行；HTTP/2、HTTP/3 使用帧和伪头部，不要把 HTTP/1.1 报文格式泛称所有 HTTP。
GET 安全指请求不期望修改状态，允许日志等附带行为；幂等指预期服务端效果，不代表响应字节永远相同。
POST 是资源按自身语义处理内容，不仅创建；可以有查询参数，也能由应用实现幂等。满足显式新鲜度等规定时 POST 响应可缓存，不能说 POST 一律不能缓存。
浏览器 fetch 禁止脚本直接设置 Cookie 请求头：使用浏览器已有 Cookie、Set-Cookie、credentials 并遵守 Cookie/CORS 规则。GET 参数不等于协议层强制只能 URL，需区别浏览器 Fetch 的限制。
Cookie 在客户端；Session 存储取决于实现。Flask 默认 Session 是签名客户端 Cookie，签名不等于加密，也不隐藏内容。不要假定所有 Session 位于服务器。
FastAPI 注入的 Response 头部适用于返回普通数据；若返回另一份 JSONResponse，应把头部设在实际返回的对象上，不会自动合并注入对象的头部。
JSONResponse 自动设置 JSON 的 Content-Type，本身就是响应头的例子；材料明确解释媒体类型时不能仅因没有其他头部例子判为无证据。
参考 RFC 9110/9112/9113/9114、WHATWG Fetch、FastAPI Response Headers/Return a Response Directly、Flask Quickstart Sessions。"""
for _entry in CATALOG:
    if _entry["id"] in {"http", "api", "frontend"}:
        _entry["referenceNotes"] = HTTP_REFERENCE_NOTES
    if _entry["id"] == "http":
        _project_criteria = {
            "request": "材料具体展示或解释接收请求及返回响应，不要求列出所有线格式。",
            "methods": "材料对所用方法有具体、正确的用途说明即可；单一POST接口不要求凭空补一个GET接口。",
            "status": "至少一个材料中实际出现的状态码及其含义解释正确；不要求覆盖所有未出现的状态码。",
            "headers": "解释Content-Type/媒体类型的用途就是Headers证据。‘JSONResponse设置JSON媒体类型’说明响应类型，应该通过本项目点；不要再强求额外Set-Cookie/Cache-Control或手工设置头部。",
            "session": "必须有Cookie/Session机制的真实材料或具体解释；明确未实现不是通过证据。",
        }
        for _point in _entry["points"]:
            _point["projectCriterion"] = _project_criteria[_point["id"]]
        _entry["questionExamples"] = [
            "GET /api/jobs?limit=-1 HTTP/1.1\nHost: career.example\nAccept: application/json\nCookie: session_id=example1\n\nHTTP/1.1 400 Bad Request\nContent-Type: application/json\nSet-Cookie: session_id=example2; HttpOnly; Path=/\n\n{\"error\": \"limit must be positive\"}",
            "POST /api/messages HTTP/1.1\nHost: career.example\nContent-Type: application/json\nCookie: session_id=example1\n\n{\"message\": \"hello\"}\n\nHTTP/1.1 500 Internal Server Error\nContent-Type: application/json\n\n{\"error\": \"database unavailable\"}",
        ]
