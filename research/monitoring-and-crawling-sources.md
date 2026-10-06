# 监控与抓取组件：GitHub 核查及离线验证

核查日期：2026-09-24。研究对象为当前 Career Radar 工作树，实际环境 Windows / Python 3.13.3。未修改生产代码、依赖或用户配置。

## 1. Protego：适合优先接入的小组件

仓库：[scrapy/protego](https://github.com/scrapy/protego)。核查提交 [2aab3bcd464ca022f6f6a120b6e4201426c2782b](https://github.com/scrapy/protego/commit/2aab3bcd464ca022f6f6a120b6e4201426c2782b)，提交日期 2026-09-22。

**解决实际缺口：** 本项目 crawler.py 的 RobotsPolicy 使用 urllib.robotparser.RobotFileParser，当前 Python 3.13.3 对下面两种规则与预期存在差异：

| robots 规则与目标 | 标准库实际允许 | Protego 实际允许 | 预期允许 |
|---|---|---|---|
| Disallow: /*.pdf$；访问 /jobs.pdf | 是 | 否 | 否 |
| Disallow: / + Allow: /jobs/；访问 /jobs/1 | 否 | 是 | 是 |

两次均使用新建解析器，避免复用 parse 导致旧规则残留。复现脚本 [verify_robots_reuse.py](verify_robots_reuse.py)，调用的 Protego 源码就是上述固定提交；未安装到项目虚拟环境。

### 实际核查的实现

- [_urlpattern.py](https://github.com/scrapy/protego/blob/2aab3bcd464ca022f6f6a120b6e4201426c2782b/src/protego/_urlpattern.py)：通配符分段匹配和末尾 $ 锚定，不依赖自制正则补丁。
- [_ruleset.py](https://github.com/scrapy/protego/blob/2aab3bcd464ca022f6f6a120b6e4201426c2782b/src/protego/_ruleset.py)：finalize_rules 按规则长度与 Allow 优先排序；规则组还提供 crawl_delay/request_rate。
- [_protego.py](https://github.com/scrapy/protego/blob/2aab3bcd464ca022f6f6a120b6e4201426c2782b/src/protego/_protego.py)：parse 接收已有 robots 文本，can_fetch(url, user_agent) 判断；不负责下载页面。参数顺序与标准库 can_fetch(user_agent, url) 相反，接入时必须明确适配。
- [_utils.py](https://github.com/scrapy/protego/blob/2aab3bcd464ca022f6f6a120b6e4201426c2782b/src/protego/_utils.py)：路径/查询编码归一化。
- [pyproject.toml](https://github.com/scrapy/protego/blob/2aab3bcd464ca022f6f6a120b6e4201426c2782b/pyproject.toml)：Python >=3.10，版本字段 0.7.0，未声明运行依赖。此为源码快照，未验证 0.7.0 是否已发布到 PyPI，采用时应选择经过验证的发布包。
- [LICENSE](https://github.com/scrapy/protego/blob/2aab3bcd464ca022f6f6a120b6e4201426c2782b/LICENSE)：BSD-3-Clause，分发需保留版权、许可条件和免责声明。

### 已运行的上游验证

将已检查的五个模块、许可证与 [tests/test_on_google_spec.py](https://github.com/scrapy/protego/blob/2aab3bcd464ca022f6f6a120b6e4201426c2782b/tests/test_on_google_spec.py) 放入忽略目录 tmp/reuse-research，仅运行离线测试：

~~~powershell
.\.venv\Scripts\python.exe -B -m pytest tmp/reuse-research/test_protego_google_spec.py -q -o addopts='' -p no:cacheprovider
.\.venv\Scripts\python.exe -B research/verify_robots_reuse.py
~~~

**66 passed in 0.08s**；两个对照样例均符合预期。测试覆盖组匹配、通配符和路径优先级等，未运行整个上游测试库或真实站点扫描，不能据此声称完全覆盖所有 robots 情形。

### 接入边界

仅替换规则解析层，继续复用现有 robots 下载、重定向安全校验、失败保守拒绝和域名限速。不要引入整个 Scrapy。不要改成解析失败默认放行。crawl_delay 的采用需要与当前限速策略整合；读出值并不等于已经执行限速。

采用前再跑本项目 test_robots、test_crawler、test_network_policy 并补充上述两个反例。这是本次证据最充分的新依赖候选，仍需正式集成回归。

## 2. changedetection.io：借鉴过滤与失败语义，不整体嵌入

仓库：[dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io)，核查提交 [fd7c9db23e371803bf1892b827b03d9c9c946bcd](https://github.com/dgtlmoon/changedetection.io/commit/fd7c9db23e371803bf1892b827b03d9c9c946bcd)，提交日期 2026-09-21。API 显示未归档；这只证明仓库状态，不证明全部功能可靠。

[processor.py](https://github.com/dgtlmoon/changedetection.io/blob/fd7c9db23e371803bf1892b827b03d9c9c946bcd/changedetectionio/processors/text_json_diff/processor.py) 实际阅读的部分：

- FilterConfig.get_filter_config_hash（108 行起）：合并全局、标签、页面过滤规则后求哈希，规则变化会使“内容未变”的快捷路径失效。
- ContentProcessor.apply_include_filters（342 行起）：CSS/XPath/JSON 选择；结果全空抛 FilterNotFoundInResponse，防止把选择器失效当成无内容。
- run_changedetection（496 行附近）：先执行排除选择器，再执行包含选择器，保留祖先上下文，避免排除条件失效。
- ContentTransformer：独立的文本变换组件，便于测试每种降噪是否改变含义。

对应测试已阅读：
[test_filter_exist_changes.py](https://github.com/dgtlmoon/changedetection.io/blob/fd7c9db23e371803bf1892b827b03d9c9c946bcd/changedetectionio/tests/test_filter_exist_changes.py) 验证过滤目标从不存在到出现的通知行为；
[test_ignore_text.py](https://github.com/dgtlmoon/changedetection.io/blob/fd7c9db23e371803bf1892b827b03d9c9c946bcd/changedetectionio/tests/test_ignore_text.py) 验证忽略规则、全局规则与变更通知。

### 对本项目真正新增的价值

本地 pipeline.py 已经有 context_hash、正文 hash、304 缓存和模型/画像/提示词变更失效。因此不再把“增加内容缓存”列为建议。

缺少的是**每站可配置招聘区域和排除区域**，以及选择器失效的明确状态。可在现有 BeautifulSoup 上使用成熟 CSS 选择器能力，不需要移植 Flask 应用。修改抓取范围后，选择器、正文提取选项和提取器版本也应纳入分析 context hash；继续保存原始证据，避免丢失申请入口。

### 已验证有效与已验证不适合的部分

[verify_monitoring_reuse.py](verify_monitoring_reuse.py) 仅通过 AST 加载已检查的 FilterConfig、ContentTransformer 两个类，未执行上游应用导入和网络代码。结果见 [monitoring-probe-results.json](monitoring-probe-results.json)。

- 相同规则生成相同哈希；变更全局忽略规则会改变哈希。
- 合成中文 HTML 使用现有 BeautifulSoup 提取 .job，能移除访问量并保留表格内学历、截止日期。只是局部机制可行性实验，不代表所有官网都适用。
- **不能照搬全文排序：** 两个岗位交换 Python/Java 要求后，全文排序结果完全相同，会隐藏真实变更。
- **不能照搬全局去重：** 两个岗位共同的“任职要求”标签被压成一个，可能破坏岗位边界。项目当前仅去除连续重复短行，不能擅自改成全局去重。

### 为什么不直接安装整个项目

[setup.py](https://github.com/dgtlmoon/changedetection.io/blob/fd7c9db23e371803bf1892b827b03d9c9c946bcd/setup.py) 要求 Python >=3.11，与本项目声明的 3.10 最低支持不同。
[requirements.txt](https://github.com/dgtlmoon/changedetection.io/blob/fd7c9db23e371803bf1892b827b03d9c9c946bcd/requirements.txt) 包括 Flask、SocketIO、Selenium、pyppeteer 等整套应用依赖；其中 pytest ~=9.0 与本项目 dev 的 pytest <9 不可同时满足，BeautifulSoup <=4.14.3 也将要求降级当前 4.15.0。项目还有部分 jq 平台约束。无需为过滤功能承担这些依赖。

[Apache-2.0 LICENSE](https://github.com/dgtlmoon/changedetection.io/blob/fd7c9db23e371803bf1892b827b03d9c9c946bcd/LICENSE) 允许按条件复用代码：保留版权和许可证、标记修改，并检查上游 NOTICE。当前仅在忽略目录保存研究快照及许可，没有把其实现复制进产品。

## 3. Crawl4AI：定向借鉴等待与结构化选择，不替换现有爬虫

仓库：[unclecode/crawl4ai](https://github.com/unclecode/crawl4ai)，核查提交 [86e6464f6db215e0d608f6aa1da41e8505636ede](https://github.com/unclecode/crawl4ai/commit/86e6464f6db215e0d608f6aa1da41e8505636ede)，提交日期 2026-09-23。

### 有价值的具体实现

- [async_configs.py](https://github.com/unclecode/crawl4ai/blob/86e6464f6db215e0d608f6aa1da41e8505636ede/crawl4ai/async_configs.py)：wait_for 与独立 timeout、css_selector、excluded_selector。当前本地 renderer 是 domcontentloaded 后固定等待毫秒数，适合借鉴“每站等待招聘节点出现 + 超时反馈”，用已有 Playwright 即可实现。
- [extraction_strategy.py](https://github.com/unclecode/crawl4ai/blob/86e6464f6db215e0d608f6aa1da41e8505636ede/crawl4ai/extraction_strategy.py) 的 JsonElementExtractionStrategy（1043 行起）：baseSelector → 每条记录的字段 → 嵌套列表。可参考配置格式，为稳定站点提供确定性提取，LLM 仅处理未知结构和业务判断。
- 同文件的字段异常处理常返回 default，部分字段存在即可形成结果。不能把“返回了非空 JSON”当成完整 JD 成功，仍须本地必需字段/完整性校验。
- [test_robots_query_rules.py](https://github.com/unclecode/crawl4ai/blob/86e6464f6db215e0d608f6aa1da41e8505636ede/tests/unit/test_robots_query_rules.py) 有裸问号、通配符、不同 Python 版本的 robots 回归案例。值得参考输入边界，但不建议复制其标准库 monkey patch；优先独立成熟解析库。

### 不建议整体替换的实证依据

[pyproject.toml](https://github.com/unclecode/crawl4ai/blob/86e6464f6db215e0d608f6aa1da41e8505636ede/pyproject.toml) 支持 Python >=3.10，但默认依赖包含 aiohttp、aiosqlite、numpy、nltk、playwright-stealth 和固定 unclecode-litellm；会扩大现有同步 requests/Playwright 管线的运行依赖。其 Torch/transformer 是可选依赖，不应错误地称为默认必须安装。

async_configs.py 的 check_robots_txt **默认 False**，不符合本项目每站检查的默认约定。整合必须显式启用，并验证公网目标、跳转、子请求限制和任务取消等既有保证；框架的能力列表不是兼容证明。

[LICENSE 原文](https://github.com/unclecode/crawl4ai/blob/86e6464f6db215e0d608f6aa1da41e8505636ede/LICENSE) 在 Apache-2.0 文本之后另有 Attribution Requirement，要求显著署名，Web 应用举例为 About/Credits。不能只看 GitHub 的 Apache 标签就忽略附加原文。若直接用代码，应满足原文或先厘清许可；仅借鉴等待策略无需复制其实现。

本次未安装 Crawl4AI、未跑上游测试或真实浏览器流程；结论是“具体机制可借鉴、整套替换缺乏必要性”，不是断言框架不能用。
