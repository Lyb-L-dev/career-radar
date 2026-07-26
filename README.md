# Career Radar：企业官网招聘信息自动监控与完整 JD 提取

Career Radar 面向校招求职者：每天访问你配置的企业公开官网，智能寻找招聘入口和职位详情页，用 LLM 提取完整 JD，利用 SQLite 去重/检测变化，并输出 Markdown、CSV 和可选邮件提醒。项目同时提供本地 FastAPI 与 React 管理端，可直接查看真实画像、岗位、企业、运行、日报和通知数据。

它只访问无需登录的公开 HTTP(S) 页面；每个站点都会检查 `robots.txt`，同一域名默认间隔 5～10 秒。单个页面或单家公司失败不会中断整批任务。

## 已实现能力

- YAML 自定义企业列表；输入招聘专栏或官网首页均可。
- 支持央企、地方国企、民营、外资、合资等公司类型分类，并可在管理端按类型筛选或批量扫描。
- 所有制与行业分类分开：互联网、游戏、宠物、企业软件、AI 与数据、物联网、金融科技、通信、能源、制造、消费品等可独立筛选。
- 支持 `job`（具体岗位）与 `notice`（官方招聘通知）两类记录；央国企没有网申入口时仍保存公告全文、报名时间、邮箱和申请方式。
- 支持省份、城市、推荐优先级、政府公示荣誉及证据链接；默认公司池优先补充福建本地企业。
- 内置 3295 家多来源优质企业候选库（其中福建 468 家），覆盖重点“小巨人”、国家企业技术中心、央企和福建数字经济创新企业；支持规模证据、画像初筛、收藏/淘汰和官网自动发现，候选库本身不参加每日扫描。
- 候选企业支持独立记录“未找到官网、官网无招聘渠道、集团统一招聘、官方公告、仅人工维护、第三方待核验、当前未招聘”等渠道状态；缺少官网不是抓取故障。已核验官方 PDF/图片/公众号文字可人工登记并导入招聘通知，第三方链接不能直接成为岗位事实。
- 官网首页智能发现“招聘、校招、加入我们、Careers、Jobs”等入口。
- `requests + BeautifulSoup` 静态抓取；可配置 Playwright 自动回退/始终渲染/完全禁用。
- DeepSeek JSON Output（默认）、OpenAI Responses API Pydantic 结构化输出，以及 Anthropic 官方 SDK 适配。
- 列表页自动跟踪职位详情、岗位列表和分页链接；详情页不自动进入登录或申请表。
- 提取职位名称、地点、JD 全文、任职资格、招聘类型、2026 届标识、目标届别、发布时间、有效期和申请链接。
- 分开评估“是否面向 2026 届”和“与个人能力画像是否匹配”，并给出 1～10 投递难度、等级与理由。
- 长页面按重叠切片分析并合并，避免简单截断；模型输出 URL 必须来自当前页面候选链接。
- SQLite 保存岗位当前版本和变化历史；同时使用需求指定指纹与完整内容哈希。
- 只把新增/变化岗位写入按日期归档的 Markdown/CSV；不变岗位只更新 `last_seen_at`。
- CSV 使用 UTF-8 BOM，方便 Excel 直接打开，并防护公式注入。
- 可选 SMTP 邮件只发送指定匹配等级，正文包含 JD 摘要，完整 JD 保留在本地日报。
- 日志按大小滚动，API Key 和 SMTP 密码只从环境变量读取。
- FastAPI 默认只监听 `127.0.0.1`，提供真实扫描任务、配置安全写回和 Web 静态资源托管；密钥接口只返回“是否已配置”。
- React 管理端默认调用真实 `/api`，只有显式设置 `VITE_USE_MOCK=true` 才进入演示模式。
- JD 完整的具体岗位可在网页发起 AI 申请任务：DeepSeek 先做五维匹配和硬性资格评估，人工批准后再生成简历/求职信、完成事实与招聘视角双审，并提供经过路径和哈希校验的本地文件下载。
- 岗位详情页可手动发起“小红书、知乎、微博、牛客”公开口碑调查：由本机 Agent Reach/OpenCLI 只读搜索，DeepSeek 生成带证据编号的风险归纳，原始线索与报告持久化到 SQLite。
- 候选企业可登记并人工核验招聘公众号，再由 OpenCLI 搜索和下载公开文章。账号身份、招聘语义和集团子公司归属均由本地规则校验；官方文章导入招聘通知，转载或未核验账号只保存为线索，整个公众号扫描不调用 DeepSeek。

## 目录结构

```text
career-radar/
├─ config.yaml                 # 企业、候选人画像、抓取、LLM、邮件设置
├─ COMPANY_SELECTION.md       # 已核验正式监控公司的证据与投递策略
├─ CANDIDATE_CATALOG.md       # 3295 家多来源候选库、规模证据与背调流程
├─ config.example.yaml        # 可公开提交的脱敏配置模板
├─ application_profile.example.yaml # 私有申请画像模板
├─ .env.example               # 密钥模板
├─ pyproject.toml             # 包与依赖声明
├─ requirements.txt           # 传统 pip 安装依赖
├─ scripts/
│  ├─ run_windows.ps1         # Windows 任务计划入口
│  └─ run_linux.sh            # Linux cron 入口
├─ src/career_radar/
│  ├─ cli.py                  # 命令行
│  ├─ api.py                  # 本地 FastAPI、静态前端托管与接口校验
│  ├─ api_companies.py        # 企业 CRUD、批量操作、连接测试与审计接口
│  ├─ api_candidates.py       # 候选企业筛选、审批、官网发现与转监控接口
│  ├─ api_wechat.py           # 公众号绑定、公开文章扫描与摘要接口
│  ├─ web_repository.py       # SQLite 到前端字段的真实数据适配
│  ├─ run_manager.py          # 单进程串行真实扫描任务
│  ├─ reputation.py           # OpenCLI 只读社交搜索、证据清洗与口碑后台任务
│  ├─ wechat_recruitment.py   # 公众号搜索、正文读取、身份核验与通知导入
│  ├─ config_editor.py        # YAML 局部校验、备份和原子写回
│  ├─ config.py               # YAML/.env 加载与严格校验
│  ├─ company_catalog.py      # 千家候选库筛选、画像初筛与审批状态合并
│  ├─ crawler.py              # robots、限速、HTTP、Playwright
│  ├─ discovery.py            # HTML 清洗和招聘链接发现
│  ├─ llm.py                  # DeepSeek/OpenAI/Anthropic、切片与合并
│  ├─ prompts.py              # 完整 JD、能力匹配与难度评分提示词
│  ├─ application/            # DeepSeek 申请评估、正文生成、双审、修订和断点恢复
│  ├─ storage.py              # SQLite 去重与变化历史
│  ├─ output.py               # Markdown/CSV 日报
│  ├─ mailer.py               # SMTP 通知
│  └─ pipeline.py             # 跨公司运行流程
├─ web/                        # React/TypeScript 管理端源码（与后端同仓库）
├─ tests/                     # 离线单元测试与 API 契约测试
├─ data/                      # 运行后生成 SQLite（Git 忽略）
├─ output/                    # 日报（Git 忽略）
└─ logs/                      # 滚动日志（Git 忽略）
```

## 一、在 Windows 本地安装

项目支持 Python 3.10+，并已验证 Python 3.13。先用 `python --version` 确认当前
PowerShell 能找到 Python；下面直接使用电脑现有的默认版本，不要求必须安装 3.11。

打开 PowerShell，逐条执行：

```powershell
cd E:\AIProjects\work\career-radar
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
Copy-Item config.example.yaml config.yaml
```

以上命令不需要激活虚拟环境，也不会受 PowerShell 脚本执行策略影响。如果你希望在
当前窗口使用简短的 `python` 命令，可选执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

如果 `python --version` 本身失败，再安装 Python 3.11～3.13，并在安装界面勾选
“Add Python to PATH”。仅使用静态抓取且 `render_mode: never` 时，可以不安装
Chromium；Python 包本身仍会安装，只有实际启用渲染时才启动浏览器。

用记事本或 VS Code 打开 `.env`。项目已经按你拥有的 DeepSeek API 配好，至少把这一行的占位符替换为真实 Key：

```dotenv
DEEPSEEK_API_KEY=sk-你的真实DeepSeek密钥
```

若以后切换供应商，再填写 `OPENAI_API_KEY` 或 `ANTHROPIC_API_KEY`。不要把 `.env` 上传到 GitHub；项目已经在 `.gitignore` 中忽略它。

## 二、本地 Web 管理端

前端已经并入本仓库的 `web/` 目录。首次安装或前端代码变化后构建一次：
需要 Node.js 22（本项目已用 `v22.14.0` 验证）；先运行 `node --version` 确认。

```powershell
cd E:\AIProjects\work\career-radar\web
node --version
npm ci
npm run test
npm run lint
npm run build
```

然后只需启动一个本地服务：

```powershell
cd E:\AIProjects\work\career-radar
.\.venv\Scripts\python.exe -m career_radar serve -c config.yaml
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。接口文档位于 [http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)。也可以执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\AIProjects\work\career-radar\scripts\run_web_windows.ps1"
```

开发前端时使用两个 PowerShell 窗口：后端运行上面的 `serve` 命令；`web/` 目录运行 `npm run dev`，再访问 `http://127.0.0.1:7100`。Vite 会把 `/api` 代理到 8000 端口。FastAPI 优先托管 `web/dist`；仅为兼容旧本地目录，找不到时才回退到同级 `career-radar-web/dist`。

安全说明：`serve` 会拒绝绑定公网地址，表单也会拒绝 `localhost`、私网和保留 IP，避免把本地管理端变成内网请求代理。Web 不返回 DeepSeek/SMTP 密钥；密钥仍只从 `.env` 或系统环境变量读取。健康检查不返回配置文件或数据库绝对路径，设置页也只展示和接受项目目录内的相对数据路径。若以后部署到服务器并允许远程访问，必须另外配置反向代理认证和 HTTPS。

### 岗位口碑调查（Agent Reach/OpenCLI）

这个功能不是每天批量扫描所有岗位，而是由你在“岗位详情 → 岗位口碑调查”中手动触发。系统会串行查询小红书、知乎、微博和牛客，每个平台读取少量公开搜索结果和有限详情。平台可能模糊召回只包含岗位名的通用内容，因此后端会再次校验标题/正文：没有明确命中目标公司全称或可复核品牌简称的结果一律丢弃；保留结果再分为“公司+岗位相关”和“仅公司相关”。最后由当前配置的 DeepSeek 归纳工作强度、单双休、福利、管理、成长、岗位边界和面试体验。结论会显示原始证据链接和置信度；没有结果、连接中断或单个平台失败时会如实显示，不会伪造评价。

你这台 Windows 电脑的示例配置已经指向 Agent Reach 安装目录：

```yaml
reputation:
  enabled: true
  opencli_command: ${USERPROFILE}\.agent-reach\node-global\opencli.cmd
  platforms: [xiaohongshu, zhihu, weibo, nowcoder]
  results_per_query: 5
  detail_results_per_platform: 2
  command_timeout_seconds: 90
  max_evidence_items: 40
  max_evidence_chars: 4000
```

使用前需要：

1. 保持 Chrome 开启，OpenCLI Browser Bridge 显示已连接。
2. 在同一个 Chrome Profile 中登录这四个平台；不要把账号密码填进 Career Radar。
3. 重启 `career_radar serve`，打开任一岗位详情页，点击“开始调查”。调查期间不要关闭 Chrome。

也可访问 `GET /api/reputation/health` 检查本机连接状态。系统只调用固定白名单中的搜索/详情命令，不提供发帖、评论、点赞、收藏或私信入口；岗位名和 URL 作为独立进程参数传递，不进入 shell。为减少隐私风险，数据库不保存作者账号，只保存平台、标题、必要摘要、公开链接、时间和互动数。社交内容可能主观、过时、营销或无法核实，只适合生成面试核实清单，不应当作公司存在某种事实的认定。

实现依据与安装说明见 [Agent Reach](https://github.com/Panniantong/Agent-Reach)、[OpenCLI](https://github.com/jackwener/OpenCLI) 和 [OpenCLI Browser Bridge](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk)。若部署到纯命令行云服务器而没有可保持登录的 Chrome 与 Browser Bridge，这个口碑功能会不可用，但企业官网监控仍可正常运行。

### 微信公众号招聘

在“优质企业候选库”中点击企业卡片的“公众号招聘”即可使用。先登记公众号名称；如果能从公众号主页或公开文章确认微信号、文章链接中的 `__biz`，建议一并填写。只有人工确认主体后才能选择“已人工核验”。集团统一招聘公众号还必须填写母集团和目标子公司的归属关键词，正文未命中归属词时不会作为该子公司的官方招聘导入。

扫描会调用 OpenCLI 的 `weixin search` 和 `weixin download`，只读取公开文章，不登录微信、不保存账号密码、不发布内容，也不调用 DeepSeek。系统按文章 URL 去重并检测正文变化：

- 已核验账号、招聘正文和归属范围全部命中：保存为官方公众号来源，并导入“招聘通知”。
- 未核验账号、转载账号或集团归属不明确：只保存为第三方待核验线索，不导入岗位事实。
- 录用公示、成绩公示等没有开放报名机会的文章：保留扫描记录，但不导入招聘通知。

Windows 示例配置：

```yaml
wechat_recruitment:
  enabled: true
  opencli_command: ${USERPROFILE}\.agent-reach\node-global\opencli.cmd
  results_per_query: 10
  max_articles_per_scan: 20
  command_timeout_seconds: 90
  max_article_chars: 100000
  search_terms: [招聘, 校招, 实习, 社会招聘]
```

使用前保持 Chrome 开启且 OpenCLI Browser Bridge 已连接。公众号搜索依赖搜索引擎索引，可能有收录延迟、漏检或临时限流，不能保证覆盖公众号全部历史文章；系统遇到失败会保留错误并显示“部分完成”，不会把搜索摘要直接当成官方身份。服务重启时，未完成任务会标记为“扫描中断”，可在管理端重新发起。

## 三、配置企业与 LLM

`config.yaml` 的正式监控公司/官方公告源与 3295 家候选企业严格分离；候选库存放在 `data/company_candidates.json`，不会自动参加扫描。请先按 [候选库说明](CANDIDATE_CATALOG.md) 收藏、背调并通过官网自动发现分批加入。现有正式公司的筛选依据、官方来源和局限见 [COMPANY_SELECTION.md](COMPANY_SELECTION.md)。每家公司最少需要 `name` 和 `url`：

```yaml
companies:
  - name: 某科技公司
    url: https://company.example/campus
    company_type: private
    industry_category: internet
    province: 福建
    city: 厦门
    priority: high
    monitor_mode: jobs
    government_honors:
      - 某政府部门公开名单
    evidence_urls:
      - https://government.example/official-list
    enabled: true
    discover_from_homepage: false
    max_pages: 20
    recruitment_channel: official_careers

  - name: 某集团官网
    url: https://group.example/
    company_type: central_soe
    industry_category: telecom
    monitor_mode: both
    recruitment_channel: official_homepage
    enabled: true
    discover_from_homepage: auto
```

`company_type` 可选值：`central_soe`（央企）、`local_soe`（地方国企）、
`private`（民营）、`foreign`（外资）、`joint_venture`（合资）、`other`（其他）。
旧配置不填写时默认按民营企业处理。`max_pages` 是单家公司覆盖全局
`crawler.max_pages_per_company` 的扫描上限，适合限制栏目庞大的集团招聘站；按上限正常停止不会被记为失败。

`industry_category` 可选值：`internet`、`gaming`、`pet`、`enterprise_software`、
`ai_data`、`iot`、`fintech`、`telecom`、`energy`、`manufacturing`、`consumer`、
`other`。`monitor_mode` 可选 `jobs`（具体岗位）、`notices`（官方招聘通知）或
`both`（两者都要）。`government_honors` 只保存政府公示原文，`evidence_urls`
保存对应政府页面；荣誉用于公司池推荐依据，不会被当作岗位事实发送通知。

`discover_from_homepage`：

- `auto`：URL 是根路径、`/index`、`/index.html` 或 `/home` 时自动发现招聘入口。
- `true`：无论 URL 路径如何都允许智能寻找招聘入口。
- `false`：把 URL 当成明确招聘页；LLM 仍可跟踪页面明确给出的职位详情/列表链接。

`recruitment_channel` 用于说明当前 URL 的来源边界，可选 `official_careers`（官方招聘页）、
`official_homepage`（企业官网首页）、`official_notice_source`（政府/国资或企业官方公告）
和 `group_recruitment`（母集团统一招聘）。集团平台必须同时填写 `parent_company` 与
`attribution_keywords`；只有页面正文明确命中子公司全称或品牌归属词时，系统才会把本页
岗位归给该子公司。候选库中的第三方招聘平台链接只保存为待核验线索，不能直接写入正式
监控配置或岗位事实。

DeepSeek 默认配置：

```yaml
llm:
  provider: deepseek
  model: deepseek-v4-flash
  base_url: https://api.deepseek.com
  request_timeout_seconds: 120
  max_output_tokens: 30000
  max_input_chars: 140000
  chunk_overlap_chars: 4000
  max_retries: 3
```

DeepSeek 提供 OpenAI 兼容接口。本工具启用官方要求的 JSON Output，再用 Pydantic 做本地严格校验。`deepseek-v4-flash` 适合高频结构化抽取；模型是否对你的账号开放以模型列表为准。官方已说明旧的 `deepseek-chat` / `deepseek-reasoner` 别名将在 2026-07-24 停用，因此示例不再使用旧别名：

- [DeepSeek 快速开始与 OpenAI 兼容说明](https://api-docs.deepseek.com/)
- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- [DeepSeek 模型更新记录](https://api-docs.deepseek.com/updates/)

切换 OpenAI：

```yaml
llm:
  provider: openai
  model: 你的 OpenAI 模型 ID
  base_url: null
```

同时在 `.env` 填写 `OPENAI_API_KEY`。模型名应使用账号当前可用、支持足够长文本与结构化输出的型号。

切换 Anthropic：

```yaml
llm:
  provider: anthropic
  model: 你的 Claude 模型 ID
  base_url: null
  request_timeout_seconds: 120
  max_output_tokens: 30000
  max_input_chars: 140000
  chunk_overlap_chars: 4000
  max_retries: 3
```

同时在 `.env` 填写 `ANTHROPIC_API_KEY`。Claude 模型 ID 会随账号和版本变化，所以示例不把某个版本写死。

### 填写个人能力画像

岗位难度不能只根据“二本”判断。请在 `config.yaml` 中填写与求职有关的非敏感信息：

```yaml
candidate:
  graduation_year: 2026
  education_level: 普通本科
  school_background: 非 985/211 的普通本科（二本）
  major: 软件工程
  skills: [Python, FastAPI, MySQL, Git]
  projects:
    - 独立完成一个 FastAPI + Vue 的课程项目并部署
  internships: []
  target_roles: [Python 后端, 测试开发, AI 应用开发]
  preferred_locations: [杭州, 上海, 南京]
  constraints:
    - 优先校招、应届生、实习转正或 0-1 年经验岗位
  notes: 英语四级，能接受中小型技术团队
```

这部分会随网页正文发送给 DeepSeek。不要填写姓名、电话、身份证号、学校学号或精确住址。资料空缺时，能力匹配会标记为 `unknown`，难度评分也会更保守。

### 私有申请画像、AI 双审与本地文档生成

申请材料需要姓名、联系方式和可追溯的简历事实，因此与上述非敏感 `candidate`
画像严格分开，保存在 Git 已忽略的 `private/` 目录：

```powershell
New-Item -ItemType Directory -Force private
Copy-Item application_profile.example.yaml private\application_profile.yaml
```

编辑完成后校验。命令只输出项目、技能等数量，不返回姓名、电话或邮箱：

```powershell
.\.venv\Scripts\python.exe -m career_radar check-application-profile -c config.yaml
```

确认所有事实以后，把私有画像中的 `verification_status` 从 `needs_review` 改为
`confirmed`。未确认画像不能创建任务。创建任务会冻结当时的完整 JD 和私有画像，
再调用一次 DeepSeek 完成岗位评估，最后停在人工批准节点：

```powershell
.\.venv\Scripts\python.exe -m career_radar apply -c config.yaml --job-id 岗位ID
.\.venv\Scripts\python.exe -m career_radar apply -c config.yaml --status 申请任务ID
```

状态结果中的 `evaluation` 包含：硬条件、五维匹配分、1～10 投递难度、逐项要求覆盖
和申请建议。确认评估后才能批准继续：

```powershell
.\.venv\Scripts\python.exe -m career_radar apply -c config.yaml --approve 申请任务ID
```

批准后会依次生成简历正文、按策略生成求职信、执行独立事实审查、执行独立招聘官/ATS
审查、根据两份审查生成终稿，再把终稿渲染为 ATS 友好的 A4 DOCX。检测到 LibreOffice
时还会导出 PDF 并验证页数。每一步先写入 SQLite 再推进状态；中途失败时使用：

```powershell
.\.venv\Scripts\python.exe -m career_radar apply -c config.yaml --resume 申请任务ID
```

已经完成的步骤会直接复用，不会重复调用 DeepSeek。若只想冻结任务、不立即评估：

```powershell
.\.venv\Scripts\python.exe -m career_radar apply -c config.yaml --job-id 岗位ID --prepare-only
.\.venv\Scripts\python.exe -m career_radar apply -c config.yaml --evaluate 申请任务ID
```

旧任务如果已经停在 `rendering`，无需重新生成正文，直接执行：

```powershell
.\.venv\Scripts\python.exe -m career_radar apply -c config.yaml --render 申请任务ID
```

安全边界：发送给 DeepSeek 的画像不含姓名、电话、邮箱、个人主页、来源文件路径和自由
备注；联系方式只在本机 DOCX 渲染时确定性注入。JD 被当作不可信数据，Prompt 会拒绝
执行其中的指令。生成器还会清理 Word 作者、自定义属性和修订会话元数据，并核对终稿
是否完整写入文档。成功状态为 `ready`，文件位于
`private/application_outputs/<申请任务ID>/`；CLI 只返回文件名和哈希，不公开绝对路径。
当前版本不会自动投递。

网页操作不需要复制岗位 ID：启动 FastAPI 并打开管理端后，进入“岗位中心 → 岗位详情”，
点击“AI 定制申请材料”。招聘通知或已标记为 `JD 不完整` 的记录会禁用该按钮，避免根据
摘要生成失真的材料。任务页会自动轮询真实进度：

1. `evaluating`：DeepSeek 正在评估岗位与私有画像。
2. `waiting_for_approval`：查看五维评分、硬性资格和逐项 JD 覆盖后，决定是否批准。
3. `drafting` 到 `verifying`：后台串行生成、双审、修订、渲染和校验；请勿重复点击。
4. `ready`：下载 DOCX/PDF，人工逐页确认后再到企业官网投递。
5. `failed`：公开页面只显示脱敏错误；查看本机日志修复原因后点击“恢复任务”，从失败步骤继续。

左侧“AI 申请材料”会保存所有任务。API 与网页只返回岗位摘要、评估、任务状态、文件名、
SHA-256 和受控下载地址，不返回联系方式、私有画像正文、来源文件路径或生成文件绝对路径。
下载时后端还会验证文件位于 `application.output_dir` 内且哈希未变化。

更新本阶段代码后需要安装新增的 Word/PDF 依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

PDF 策略在 `config.yaml` 配置：

```yaml
application:
  pdf_mode: auto             # auto / always / never
  libreoffice_command: soffice
```

- `auto`：检测到 LibreOffice 就生成 PDF；没有时仍生成并验证 DOCX，报告中记录警告。
- `always`：PDF 是硬要求；缺少 LibreOffice 或页数超限都会让任务进入可恢复的失败状态。
- `never`：只生成 DOCX，不尝试转换 PDF。

Windows 如需自动 PDF，可安装 LibreOffice，并确保 `soffice.exe` 在 `PATH` 中；程序也会
自动检查标准安装目录。没有 LibreOffice 时可以在 Word/WPS 中手动“另存为 PDF”。

一次完整流程通常使用 5 次 DeepSeek 调用（评估、简历、事实审查、招聘官/ATS 审查、
修订）；当 `cover_letter_mode: always`，或 `auto` 检测到 JD 明确要求求职信时，再增加
1 次求职信调用。`never` 永不生成求职信。

### 控制成本与抓取范围

一次 LLM 请求通常对应一个页面；很长的页面会产生多个切片请求。示例已启用 15 家公司，为了先确认 API 成本和官网兼容性，建议首次只跑一家或一个公司类型，再逐步扩大：

```yaml
crawler:
  max_pages_per_company: 120
  max_follow_links_per_page: 100
```

如果日志提示达到 `max_pages_per_company` 且官网确实有更多职位，可以逐步提高；不要一开始设成数千。详情页越多，运行时间和 API 成本越高。默认的 5～10 秒域名间隔意味着 100 个同域页面至少需要数分钟，这是合规和稳定性设计的一部分。

### Playwright 模式

```yaml
crawler:
  render_mode: auto  # never / auto / always
```

- `never`：只用 requests，速度快、资源少，适合静态官网。
- `auto`：静态正文太少或像 SPA 空壳时回退 Chromium，推荐。
- `always`：所有页面都用 Chromium；更慢，只有确认站点必须 JS 渲染时使用。

## 四、首次运行

先做不访问网络的配置检查：

```powershell
.\.venv\Scripts\python.exe -m career_radar check-config --config config.yaml
.\.venv\Scripts\python.exe -m career_radar init-db --config config.yaml
```

执行一次完整监控：

```powershell
.\.venv\Scripts\python.exe -m career_radar run --config config.yaml
```

常用参数：

```powershell
# 只跑一家；--company 可以重复传入
.\.venv\Scripts\python.exe -m career_radar run -c config.yaml --company "FIT2CLOUD 飞致云"

# 完整抓取和 LLM 分析，但不写数据库、日报或邮件
.\.venv\Scripts\python.exe -m career_radar run -c config.yaml --dry-run

# 本次不发邮件
.\.venv\Scripts\python.exe -m career_radar run -c config.yaml --no-email

# 排查页面发现逻辑
.\.venv\Scripts\python.exe -m career_radar run -c config.yaml --log-level DEBUG
```

正常完成后，命令行会输出 JSON 统计。日报文件示例：

```text
data/career_radar.db
output/2026-07-17-jobs.md
output/2026-07-17-jobs.csv
logs/career_radar.log
```

同一天重复运行会在同一 Markdown/CSV 里追加批次；SQLite 判断为 `unchanged` 的岗位不会重复输出。

## 五、配置邮件通知（可选）

邮件发送同时受三道筛选控制：应届届别匹配、个人能力匹配、最大难度。以 QQ 邮箱 SSL 为例：

```yaml
app:
  notify_match_levels: [high]
  notify_profile_fit_levels: [high, medium]
  notify_max_difficulty_score: 7

smtp:
  enabled: true
  host: smtp.qq.com
  port: 465
  use_ssl: true
  use_starttls: false
  username: your_account@qq.com
  password_env: SMTP_PASSWORD
  from_address: your_account@qq.com
  to_addresses:
    - your_account@qq.com
  subject_prefix: "[Career Radar]"
  jd_summary_chars: 500
```

`.env`：

```dotenv
SMTP_PASSWORD=邮箱后台生成的授权码或应用专用密码
```

不同邮箱常见组合：

- SSL：端口通常为 465，`use_ssl: true`。
- STARTTLS：端口通常为 587，`use_ssl: false`、`use_starttls: true`。

不要填写邮箱登录密码，优先使用授权码。程序不会在日志中打印密码。

## 六、Windows 每天 08:00 自动运行

先手工执行一次 `scripts\run_windows.ps1`，确认成功：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\AIProjects\work\career-radar\scripts\run_windows.ps1"
```

然后打开“任务计划程序” → “创建基本任务”：

1. 名称：`Career Radar 每日招聘监控`。
2. 触发器：每天，开始时间 `08:00:00`。
3. 操作：启动程序。
4. 程序或脚本：`powershell.exe`。
5. 添加参数：

   ```text
   -NoProfile -ExecutionPolicy Bypass -File "E:\AIProjects\work\career-radar\scripts\run_windows.ps1"
   ```

6. “起始于”填写项目目录：

   ```text
   E:\AIProjects\work\career-radar
   ```

7. 笔记本建议在任务属性中取消“只有在计算机使用交流电源时才启动”。
8. 右键任务 → “运行”，再检查 `logs/career_radar.log`。

电脑在 08:00 关机或休眠时无法抓取；可以在设置中勾选“错过计划开始后尽快运行”，或部署到常在线服务器。

## 七、Linux/阿里云/腾讯云轻量服务器部署

以下以 Ubuntu 22.04/24.04 为例。若要使用 Web 管理端，请先按 Node.js 官方方式安装
Node.js 22；系统仓库里的旧版 Node 可能无法构建 Vite 7：

```bash
sudo apt update
sudo apt install -y python3 python3-venv git
cd /opt
sudo mkdir -p career-radar
sudo chown "$USER":"$USER" career-radar
cd career-radar
# 把本项目文件上传到此目录后继续
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install --with-deps chromium
cd web
node --version
npm ci
npm run build
cd ..
cp .env.example .env
cp config.example.yaml config.yaml
chmod 600 .env
chmod 600 config.yaml
chmod +x scripts/run_linux.sh
```

编辑 `.env` 与 `config.yaml`，然后验证：

```bash
.venv/bin/python -m career_radar check-config -c config.yaml
.venv/bin/python -m career_radar init-db -c config.yaml
./scripts/run_linux.sh
tail -n 100 logs/career_radar.log
```

添加 cron：

```bash
crontab -e
```

追加以下内容（每天北京时间 08:00）：

```cron
CRON_TZ=Asia/Shanghai
0 8 * * * /opt/career-radar/scripts/run_linux.sh >> /opt/career-radar/logs/cron.log 2>&1
```

注意：部分旧版 cron 不支持 `CRON_TZ`。执行 `timedatectl` 检查服务器时区；必要时使用 `sudo timedatectl set-timezone Asia/Shanghai`，或把 cron 时间换算成服务器本地时间。

云服务器还应做到：

- `.env` 权限为 `600`，不放在 Web 可访问目录。
- 不需要为本工具开放任何入站端口；它只发起 HTTPS/SMTP 出站连接。
- 定期备份 `data/career_radar.db` 和 `output/`。
- 若内存较小且官网均为静态页，把 `render_mode` 设为 `never`，无需 Chromium。

## 八、运行测试

开发环境安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check src tests --no-cache
cd web
npm run test
npm run lint
```

测试完全离线，不会调用真实官网、LLM 或邮箱。

## 数据库去重与变化检测说明

每个岗位保存四个关键值：

1. `entity_key`：公司 + 职位 + 地点 + 稳定申请/来源 URL，用于识别“同一个岗位”。
2. `jd_prefix_hash`：规范化 JD 前 100 字的 SHA-256。
3. `fingerprint`：公司 + 职位名 + 发布时间 + `jd_prefix_hash` 的 SHA-256，符合需求中的建议规则。
4. `content_hash`：全部结构化字段的 SHA-256，可检测前 100 字不变但后文更新。

状态含义：

- `new`：第一次看到该实体，写 `jobs` 和 `job_history`，进入日报。
- `updated`：实体相同但任意字段变化，更新 `jobs`、追加历史，默认进入日报。
- `unchanged`：只更新 `last_seen_at`，不进入日报和邮件。

SQLite 使用 WAL 模式；请勿同时启动多个相同任务。偶尔误启动时会等待数据库锁，长期并发运行没有必要。

## 合规与已知边界

- `robots.txt` 返回明确禁止时跳过；401/403、5xx 或网络失败时采取保守策略，本轮不抓该站点；404 等“没有规则文件”状态允许访问公开页。
- 不登录、不输入账号密码、不绕过验证码、不破解反爬策略。
- 仅跟踪当前页面真实存在的 HTTP(S) 链接；如果正文明确提供简历邮箱，会保留经正文核验的 `mailto:` 投递地址但不会访问它。LLM 虚构的链接或邮箱会被丢弃。
- Playwright 会加载浏览器正常渲染所需的公开静态资源/XHR；页面发生跨域跳转后会再次检查最终顶层 URL 的 robots 规则。
- PDF、图片招聘海报、需要登录的职位、验证码和只在私有 API 返回的数据不在当前版本范围内。
- 社交口碑是用户手动触发的辅助背调，依赖本机已登录的 Chrome Profile；它不绕过登录、验证码或平台限制，不进行大规模抓取，也不保证每个平台都有相关结果。
- robots 或站点条款允许访问不等于允许高频或商业复用；如企业条款另有要求，应以条款为准。
- 官网结构可能变化。先看日志中的页面类型、候选链接和错误；必要时调整 URL、Playwright 模式或页面上限。

## 常见问题

### `py -3.11 -m venv .venv` 提示 `No suitable Python runtime found`

这表示电脑没有安装指定的 3.11，不代表项目不支持你现有的 Python。先运行：

```powershell
python --version
python -m venv .venv
```

只要版本为 3.10 或更高即可继续。第一条创建虚拟环境的命令失败时，
`.venv\Scripts\Activate.ps1` 尚不存在，后续“无法识别 Activate.ps1”只是连带结果。

### 配置有效，但运行提示缺少 API Key

确认项目根目录存在 `.env` 而不是 `.env.txt`，变量名与 `llm.provider` 对应。任务计划必须通过项目脚本启动，脚本会固定工作目录。

### Playwright 提示找不到浏览器

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Linux 使用：

```bash
.venv/bin/python -m playwright install --with-deps chromium
```

### 官网浏览器能看到岗位，但程序静态抓不到

把 `render_mode` 从 `never` 改为 `auto`；仍无效时改成 `always` 跑单家公司，并查看日志。若 robots 禁止、需要登录/验证码，程序会按设计跳过。

### 第一次运行为什么会通知很多岗位

SQLite 还没有历史记录，所以第一次看到的岗位都是 `new`。建议首次使用 `--no-email` 建立基线，确认日报正确后再启用 SMTP。

### 如何只通知“2026 届匹配 + 能力不低 + 难度可接受”的岗位

保持：

```yaml
app:
  output_match_levels: [high, medium, low]
  notify_match_levels: [high]
  notify_profile_fit_levels: [high, medium]
  notify_max_difficulty_score: 7
```

所有职位仍会进 SQLite；日报由 `output_match_levels` 控制，邮件必须同时通过上述三项条件。

## 安全建议

- API Key、邮箱授权码只放 `.env`，并定期轮换。
- 如果误把 `.env` 提交到 Git，立即在供应商后台撤销旧 Key，仅删除 Git 文件并不足够。
- CSV 已防护以 `= + - @` 开头的公式文本，但打开任何来自网页的数据时仍不要点击可疑链接。
- 更新依赖前先在测试环境运行 `pytest`；生产服务器建议保留可回滚的虚拟环境和数据库备份。

## License

MIT。使用者需自行遵守目标网站 robots.txt、服务条款、著作权和当地法律法规。
