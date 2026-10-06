# 招聘结构化提取与正文提取：GitHub 源码核查

核查日期：2026-09-24。范围：extruct、JobSpy、trafilatura。阅读本项目 discovery.py、ats_source.py、crawler.py 及对应测试；未读取 private、环境密钥或真实用户配置，未修改产品代码。

## 结论

1. **优先修正已经接入的 trafilatura 使用方式。** 当前关闭表格；已在本机复现招聘资格条件丢失，即使输出保留 97% 字符也会通过现有 50% 长度门槛。库本身提供保留表格能力，无需另造正文提取器。
2. **extruct 值得做结构化提取试点，但不能直接视为可用的 JobPosting 适配器。** 它解决 JSON-LD / microdata 的语法提取；岗位选择、图展开、字段映射、单块异常隔离与真实性核验仍属本项目职责。本机未安装 extruct，尚未完成其运行验证。
3. **不整体引入 JobSpy。** 核查版本只适配 LinkedIn、Indeed、ZipRecruiter、Glassdoor、Google、Bayt、Naukri、BDJobs 八类招聘聚合站，不能替代中国企业官网或国内 ATS 适配器。可借鉴模型中的字段来源与适配器接口；当前项目已有同类结构，收益有限。

## 项目匹配依据

- discovery.py:121 的 _clean_visible_text 删除全部 script；parse_html:213 没有在删除前把 JSON-LD 转成岗位。本次离线实验确认仅存于 JSON-LD 的“算法工程师”标题不会出现在输出正文。
- discovery.py:142 的 _preferred_visible_text 已使用 trafilatura，并在异常/过短时回退 BeautifulSoup；不应把“接入 trafilatura”当成新增工作。
- ats_source.py 已有 Greenhouse、Lever、Ashby、JSON Feed 映射、公开地址校验和错误封装；无需复制另一套同名适配器。
- crawler.py 已具备 robots、请求节流、响应体大小限制、重定向目标校验及 Playwright 回退。新解析库应只消费已获取 HTML，继续复用这一边界。
- 项目要求 Python >=3.10；本次实际运行环境为 Windows x64 / Python 3.13.3，并非已测试所有 3.10+ 版本。

## 1. extruct：可复用语法解析，不等于岗位语义解析

核查提交：[a31daaadb82ec684b7d468d3b15734b8ae3b7265](https://github.com/scrapinghub/extruct/commit/a31daaadb82ec684b7d468d3b15734b8ae3b7265)，提交日期 2025-03-24。固定提交是本次取证快照，不能把仓库 pushed_at 当成已审计代码更新时间。

### 看过的源文件与可利用内容

- [extruct/jsonld.py](https://github.com/scrapinghub/extruct/blob/a31daaadb82ec684b7d468d3b15734b8ae3b7265/extruct/jsonld.py)：JsonLdExtractor 用 XPath 找 application/ld+json；跳过空 script；先 json.loads(strict=False)，失败时以 jstyleson 处理注释；接受顶层对象和数组。
- [extruct/_extruct.py](https://github.com/scrapinghub/extruct/blob/a31daaadb82ec684b7d468d3b15734b8ae3b7265/extruct/_extruct.py)：公开 extract 支持 syntaxes 限制和 errors=strict/log/ignore；适合限定 json-ld/microdata，不必运行全部六种语法。
- [tests/test_jsonld.py](https://github.com/scrapinghub/extruct/blob/a31daaadb82ec684b7d468d3b15734b8ae3b7265/tests/test_jsonld.py)：覆盖空值、空 script、控制字符、JavaScript/HTML 注释等，值得借鉴测试夹具设计。**本次阅读了测试，未执行上游测试。**

### 不能直接采用的地方

这是从源码得到的结论：

- 不筛选 @type=JobPosting，也不递归展开 @graph；一个图对象会原样返回，需要本项目识别对象/数组类型、图内节点和必要的 @id 引用。
- JSON-LD 提取没有基于 base_url 归一化字段 URL。职位 URL、申请 URL 仍需走项目已有 URL 校验，不自动访问 @context/@id。
- 一个 script 无法解析会抛错，中断 extract_items；公开 extract 的错误处理在“整种语法”层，不是逐 script 层。即便 errors=ignore，坏块也可能使同页有效 JSON-LD 全部丢失。不能简单调用一次后声称有容错。
- 它解析站方声明，并不保证 description 完整、validThrough 未过期、公司正确或元数据与可见页面一致。尤其不能把“存在描述”直接等同“完整 JD”。
- 没有证据证明中国官网普遍提供 JSON-LD；只对确实含结构化标记的页面增益，不能替代 SPA 渲染、招聘公告/附件解析。

### 兼容性和许可

[setup.py](https://github.com/scrapinghub/extruct/blob/a31daaadb82ec684b7d468d3b15734b8ae3b7265/setup.py) 声明 Python >=3.8、OS Independent，依赖 lxml、lxml-html-clean、rdflib、pyrdfa3、mf2py、w3lib、html-text、jstyleson；不是只加一个零依赖 JSON 函数。[CI](https://github.com/scrapinghub/extruct/blob/a31daaadb82ec684b7d468d3b15734b8ae3b7265/.github/workflows/python-package.yml) 在 Ubuntu 运行 3.8–3.12，未见 Windows job，故 Windows 可用性尚需安装及 smoke test，不能用声明代替实测。

[BSD-3-Clause 许可原文](https://github.com/scrapinghub/extruct/blob/a31daaadb82ec684b7d468d3b15734b8ae3b7265/LICENSE)：可复用，但分发需保留版权、条件及免责声明，不得借贡献者名义背书。建议依赖调用，不复制整个包；若局部移植则保留相应声明。

### 最小落地方式与验收

在 parse_html 清除 script **之前**增加一个独立结构化数据入口，保持 PageDocument 可见文本逻辑；逐 script 隔离异常，按需调用 extruct，映射并保留来源证据。不建议顺带引入整个抓取框架。

验收至少包括：中文对象/数组、@graph、@type 数组、同页有效块+坏块、空块、相对 URL、过期岗位、结构化摘要与可见详细 JD 冲突、多岗位公告、无 JSON-LD 回退。运行真实目标网站的脱敏固定 HTML 样本，统计新增有效岗位率、完整 JD 召回和误识别率之后再进入默认路径。

## 2. JobSpy：海外聚合站工具，与官网监控的主要任务不匹配

核查提交：[fda080a373e8226f3fd60635323f5da9af9892b1](https://github.com/speedyapply/JobSpy/commit/fda080a373e8226f3fd60635323f5da9af9892b1)，提交日期 2026-02-18。

### 看过的源文件

- [jobspy/__init__.py](https://github.com/speedyapply/JobSpy/blob/fda080a373e8226f3fd60635323f5da9af9892b1/jobspy/__init__.py)：scrape_jobs 中 SCRAPER_MAPPING 列出上述八类站点，返回 Pandas DataFrame；默认会遍历所有 Site。不是输入任意企业官网 URL 的通用爬虫。
- [jobspy/model.py](https://github.com/speedyapply/JobSpy/blob/fda080a373e8226f3fd60635323f5da9af9892b1/jobspy/model.py)：Scraper 抽象接口、ScraperInput、JobResponse、JobPost 和 SalarySource；可借鉴区分 DIRECT_DATA 与 DESCRIPTION 推断的来源设计，避免把工资推断当原始字段。Career Radar 已有 ATSJob 和统一转换入口，没必要为了这个思想加入 Pandas。
- Country.CHINA 只配置了 Indeed 的国家/子域信息，**不代表支持中国企业官网或北森/Moka/飞书 ATS**；从模型和映射可直接确认无这些适配器。
- JobPost 将 job_url 和 job_url_direct 分开，值得保留“聚合站链接”和“官方申请链接”的区别；未来若用户明确增加海外聚合招聘源，宜单独做可选接入，不改变官网真实性规则。

### 质量与兼容性

[pyproject.toml](https://github.com/speedyapply/JobSpy/blob/fda080a373e8226f3fd60635323f5da9af9892b1/pyproject.toml) 声明 Python ^3.10，依赖 pandas、numpy、tls-client、markdownify 等。语法版本范围匹配，但并未在本机安装或运行，Windows 二进制依赖和目标站可访问性未验证。

通过该提交的[完整 Git tree](https://api.github.com/repos/speedyapply/JobSpy/git/trees/036c9d084650f2bd5bf80aa9f7a39a1b4384ec85?recursive=1)检查，未发现测试文件或 tests 目录，workflow 仅 publish-to-pypi。最新提交修复 LinkedIn 新职位日期 CSS class 变更，说明依赖页面结构需要持续维护，不能把当前源码可读等同所有站点当前可爬。

scrape_jobs 的 future.result() 在该层没有逐站异常捕获，不能直接照搬来取代本项目按公司隔离失败的处理；这里仅指顶层代码，不推断所有适配器内部都没有错误处理。

[MIT 许可原文](https://github.com/speedyapply/JobSpy/blob/fda080a373e8226f3fd60635323f5da9af9892b1/LICENSE) 允许复用，复制实质代码时须保留版权和许可。**本次建议仅借鉴来源建模思路，不新增依赖。**

## 3. trafilatura：已有依赖应继续用，需修正文保留策略

核查上游提交：[c852cae9708a59f04521b19395d8ed49771a5c78](https://github.com/adbar/trafilatura/commit/c852cae9708a59f04521b19395d8ed49771a5c78)，提交日期 2026-09-21。注意：本机实验使用已安装的 **2.2.0**，不声称运行了该 master 提交。

- [trafilatura/core.py](https://github.com/adbar/trafilatura/blob/c852cae9708a59f04521b19395d8ed49771a5c78/trafilatura/core.py) 的 extract 提供 include_tables=True、favor_precision/favor_recall、include_links；可直接使用成熟正文提取能力，不需重写类似 Readability 的算法。
- [tests/unit_tests.py](https://github.com/adbar/trafilatura/blob/c852cae9708a59f04521b19395d8ed49771a5c78/tests/unit_tests.py) 实际断言 include_tables=True/False 时表格内容出现/消失，并有 colspan、表格注释节点和链接等测试；已阅读相关部分，未运行上游整套测试。
- [pyproject.toml](https://github.com/adbar/trafilatura/blob/c852cae9708a59f04521b19395d8ed49771a5c78/pyproject.toml) 要求 Python >=3.10；[CI](https://github.com/adbar/trafilatura/blob/c852cae9708a59f04521b19395d8ed49771a5c78/.github/workflows/tests.yml) 配置含 Windows 3.11 及 Linux 3.10/3.12/3.14。这是覆盖配置证据，本次没有检查 CI run 成败。
- [Apache-2.0 许可](https://github.com/adbar/trafilatura/blob/c852cae9708a59f04521b19395d8ed49771a5c78/LICENSE) 可用于本项目；分发库/派生代码应附许可，保留归属信息，修改上游文件需标明修改，并按存在情况保留 NOTICE。

### 已运行：中文招聘表格边界复现

复现脚本：[research/verify_extraction_reuse.py](verify_extraction_reuse.py)（合成 HTML，无网络、无用户数据）。

运行命令：

~~~powershell
.\.venv\Scripts\python.exe research/verify_extraction_reuse.py
~~~

实际结果：

| 检查 | 结果 |
|---|---|
| Python / trafilatura | 3.13.3 / 2.2.0 |
| BeautifulSoup 原清洗正文长度 | 690 |
| 当前 parse_html 输出长度 | 670 |
| 原清洗正文含“统计学硕士” | 是 |
| 当前 parse_html 含“统计学硕士” | **否** |
| 单独调用 include_tables=True 保留该条件 | 是 |
| 单独调用 include_tables=False 保留该条件 | 否 |
| 仅在 JSON-LD 内的“算法工程师”进入当前正文 | 否 |

690 → 670 远高于当前 50% 回退阈值，但关键岗位/学历要求已经丢失。因此“字数保留一半即可保证不会更差”的注释与实际行为不符。下一步应保留招聘表格，并以岗位标题、学历/专业、截止时间、申请方式等关键信息做保留验证；不能仅依赖字符比率。这里只证明这一合成样本的问题和库选项有效，未声称所有中国公告页面均已验证。

### 已运行：本项目现有回归

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_discovery.py tests/test_ats_source.py tests/test_crawler.py -q
~~~

结果：**26 个通过**，无跳过。本项目测试覆盖当前 HTML 处理、ATS 解析、JSON Feed 公网 URL 拒绝、SPA 回退和请求校验器；尚未覆盖上述“短但关键的表格被裁掉”场景。这说明现有测试通过并不能证明所有正文完整性要求都得到满足。

## 验证范围与实施顺序

本次 GitHub 源码通过连接器读取；shell 直接访问 GitHub 443 失败，所以没有 git clone 或在线目标网站验证。未安装 extruct / JobSpy，也未声称已跑上游全套测试。固定 SHA、源码判断和本机运行结果已分别标注。

建议顺序：

1. 优先保留 trafilatura 已有能力，修表格保留和完整性判定，增加上述关键内容回归样本。
2. 用少量明确含 schema.org JobPosting 的真实官网 HTML 做 extruct 隔离原型，先验证有效块不受坏块影响，再判断是否引入依赖。
3. 国内 ATS 按目标公司的公开接口证据增量扩展既有 ats_source；这三项研究没有发现可以直接照搬的国内 ATS 成品。
4. JobSpy 暂不进入核心依赖；只有新增海外聚合招聘源需求时再单独评估。
