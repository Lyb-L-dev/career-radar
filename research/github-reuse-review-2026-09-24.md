# Career Radar 开源复用研究与采用建议

研究日期：2026-09-24。已核查 **9 个 GitHub 项目**的具体实现、许可证、依赖与相关测试；固定提交证据见下方专项报告。判断基于当前工作树，不沿用根目录旧代码审查报告中的历史结论。

## 最值得采用的结论

先修正已有库的使用方式，再接入小组件。当前最有证据支持的顺序是：

1. **用好 trafilatura 的表格保留能力。** 已复现当前正文仍保留 97% 字符，却丢失“统计学硕士”资格要求。库的 include_tables=True 在同一中文样本中保留了要求。字符比例不能保证 JD 完整。
2. **用 Protego 替换 robots 规则解析部分。** 当前 Python 3.13.3 标准库对通配符禁用与更具体的 Allow 规则有反例；Protego 对照通过，上游相关 66 个测试通过。保留现有下载、限速、公网校验和失败处理。
3. **借鉴 promptfoo，加强逐岗位评测。** 已有的 3 个评测样例不足；当前标题、地点、技能分别来自不同岗位，也能判“通过”。先改业务断言，规模扩大后直接用 promptfoo 管多模型对比和报告。
4. **借鉴 Reactive Resume，检查最终 PDF 是否能完整提取文字。** 当前验证 DOCX 正文，但 PDF 只检查签名、解析和页数。可以直接复用已安装 pypdf 做导出后文本回读，不需要替换整个简历系统。
5. **借鉴 changedetection.io 的招聘区域过滤与失效识别。** 当前缓存已有，不再重做；新增价值是消除导航噪声，并把选择器失效与“没有岗位”区分开。

这五项均能指出本地落点和验收方法。只有第 1、2 项的特定机制和第 3 项的现有盲点经过本机实验；PDF 改进是源码核查结论，尚未验证转换后的真实材料。不能把所有建议概括为“已经集成可用”。

## 候选对照

| 项目 | 复用什么 | 适配判断 | 验证与采用级别 |
|---|---|---|---|
| [trafilatura](https://github.com/adbar/trafilatura) | 正文提取、表格保留 | 已经依赖，优先改正确用法 | 本机 2.2.0 中文合成样本已实测 |
| [Protego](https://github.com/scrapy/protego) | robots 通配符和规则优先级 | 小组件、Python >=3.10、纯 Python | 固定源码 66 项上游测试及 2 项对照通过；适合优先集成 |
| [promptfoo](https://github.com/promptfoo/promptfoo) | 结构化断言、Python provider、评测矩阵 | 当前已有轻量雏形，先补同一岗位关联约束 | 已核查源码/测试；未运行上游或调用 LLM |
| [Reactive Resume](https://github.com/reactive-resume/reactive-resume) | PDF 导出回读、导入映射 | 借鉴验收思路；不迁移 TS 简历应用 | 已核查真实导出集成测试；本地 PDF 改进未实施 |
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io) | 区域过滤、过滤规则变更失效、失败状态 | 用已有 BeautifulSoup 实现所需接口；不嵌入整个 Flask 应用 | 部分上游纯逻辑已离线运行；全文排序/全局去重不适合多岗位页面 |
| [extruct](https://github.com/scrapinghub/extruct) | JSON-LD / microdata 语法提取 | 适合含结构化标记官网试点；需图展开、字段映射、坏块隔离 | 源码审查完成，未安装运行；不能标记为完整岗位提取器 |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | 等待招聘节点、按条目选择字段 | 局部机制有价值；现有 requests/Playwright 无需整体替换 | 源码审查；默认 robots 关闭、依赖和署名条款需适配 |
| [Sentence Transformers](https://github.com/huggingface/sentence-transformers) | 中文相似岗位模型、检索评测器 | 可选离线试验；先验证中文效果和资源成本 | 未下载模型或运行效果评测；不能直接替换自动合并规则 |
| [JobSpy](https://github.com/speedyapply/JobSpy) | 聚合源/官方源区分、字段来源模型 | 八类招聘聚合站与中国企业官网主需求不匹配 | 不整体采用；所查提交未发现测试文件 |

这些不是按 star 排行的推荐。每一项都检查了能否解决本项目问题、引入哪些依赖、失败时会发生什么；有测试的项目也明确区分“阅读测试”和“执行测试”。

## 与当前项目的对应关系及验收

| 优先级 | 本地位置 | 具体工作 | 采用前验收 |
|---|---|---|---|
| P0 | src/career_radar/discovery.py | 保留招聘表格，检查关键资格/报名信息未丢失 | 中文表格与段落混排、短资格条件、列表多岗位；与原始全文逐项比对 |
| P0 | src/career_radar/crawler.py / tests/test_robots.py | 接入 Protego 解析，不改变抓取安全边界 | 通配符、$、Allow 优先级、组匹配、抓取失败策略；现有 crawler/network_policy 回归 |
| P1 | src/career_radar/prompt_eval.py | 按同一 job 匹配期望字段，验证岗位数量和事实约束 | 错配的两个岗位必须失败，正确单条岗位通过；录制输出先离线，再做真实模型评测 |
| P1 | src/career_radar/application/document_verifier.py | 对最终 PDF 回读文本、检查缺字/无文本层 | 中文、技术词、长链接、联系方式；空白/文字轮廓 PDF 必须报错；另做视觉检查 |
| P1 | discovery.py / models.py / pipeline.py | 可选每站招聘区域、排除区域、失效状态，配置纳入缓存上下文 | 导航改变不触发重分析，JD/截止时间改变必须触发，选择器失效不能写成零岗位 |
| P2 | discovery.py 与岗位归一化入口 | 试点 extruct，先元数据解析再与可见正文核对 | 好坏 JSON-LD 同页、@graph、多岗位、相对 URL、过期/不一致元数据 |
| P2 | crawler.py 的 _PlaywrightRenderer | 用已有 Playwright 等待招聘节点 | 延迟加载、节点永不出现、超时、取消；不依赖统一固定 sleep |
| P2 | embeddings.py / storage.py | 试验中文模型，模型与文本版本隔离 | 人工标注集 Recall/MRR、错误推荐、CPU/内存；严禁不同向量空间混用 |

P0/P1/P2 是本次建议实施顺序，不是已完成状态。研究没有扩大到所有模块：这不是 GitHub 全量项目调查，也未找到可以直接替代国内 Moka/北森/飞书 ATS 的已验证适配器；应继续按目标公司的公开接口逐个验证。

## 避免重复建设的边界

当前代码已经使用 trafilatura、Apprise、可选 LiteLLM、React Query，并已有 Greenhouse/Lever/Ashby/JSON Feed、304 缓存、内容 hash、画像和提示词变更失效、任务协调、文档审批。因此本次不把“添加上述能力”重复列为新成果。

- 不为了 CSS 选择器安装整套 changedetection.io：其 Python >=3.11、pytest ~=9.0 等与本项目最低版本/开发依赖存在差异。
- 不把 Crawl4AI 默认参数直接套用：robots 默认关闭，许可证原文还有显著署名要求。
- 不把 JobSpy 的 China 枚举理解为国内招聘系统适配。
- 不把神经相似度当成重复岗位的充分证据，也不沿用旧 hash 向量阈值。
- 不把简历项目的启发式 ATS 得分包装成录取率或系统通过率。
- 不复制上游代码而遗漏版权、许可、NOTICE 或修改声明。源码许可证和模型权重许可证分别核查。

## 本次实际验证与限制

- 本项目 discovery、ATS、crawler 相关 **26 个测试通过**。
- 本项目 prompt_eval、embeddings 相关 **10 个测试通过**。
- Protego 固定源码的 Google 规则测试文件 **66 个测试通过**，另做两项标准库对照。
- trafilatura 表格丢失/保留、JSON-LD 标题丢弃、评测跨岗位误通过、hash 词面偏差均用合成数据离线复现。
- changedetection.io 仅运行两个经审阅类的局部逻辑，验证规则哈希与不适合照搬的文本变换；未启动上游应用。
- 未在真实招聘站点批量抓取，未发送通知/投递，未使用用户私有画像或调用付费模型。未声称所有候选在生产环境已验证。
- 本次只新增 research/ 文档与研究脚本、tmp/ 隔离源码快照；未修改产品实现、依赖或现有未提交改动。

**明确下一步：** 优先实现“表格不丢资格条件 + Protego 规则解析”，补对应回归；随后完善逐岗位评测和 PDF 文本验收。extruct 与中文模型先做小样本试验，有增益证据后才进入默认路径。

## 可复核证据

- [结构化招聘与正文提取](extraction-sources.md)：extruct、JobSpy、trafilatura 的固定 SHA、源码、许可、实测。
- [监控与抓取](monitoring-and-crawling-sources.md)：Protego、changedetection.io、Crawl4AI 的固定 SHA、源码、许可、实测。
- [评测、申请材料与中文检索](evaluation-and-application-sources.md)：promptfoo、Reactive Resume、Sentence Transformers 的固定 SHA、源码、许可及本地反例。
- [正文复现脚本](verify_extraction_reuse.py)、[robots 对照脚本](verify_robots_reuse.py)、[过滤机制验证脚本](verify_monitoring_reuse.py)、[过滤实验结果](monitoring-probe-results.json)。

Protego 和 changedetection.io 的脚本依赖 tmp/reuse-research/ 下本次保留的源码快照，该目录被 Git 忽略；复制仓库到别处时须按专项报告固定 SHA 重新取得源码及许可证，不能只运行脚本便假定依赖存在。
