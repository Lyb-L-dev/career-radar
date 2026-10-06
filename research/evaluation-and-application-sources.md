# 评测、申请材料与中文检索：GitHub 源码核查

核查日期：2026-09-24。只读取公开上游源码和本地产品源码、测试；未读取私有画像或配置，未调用付费 LLM，未安装上游项目、下载模型或修改产品实现。

## 结论

近期最值得做两件事：

1. **借鉴 Reactive Resume 的“导出后重新提取”测试方法，把 PDF 文本完整性纳入本地申请材料验收。** 当前 DOCX 已核对正文，PDF 只检查文件头、可解析性和页数，转换后丢字/空白页可能漏过。直接复用已有 `pypdf` 即可开始，无需迁移整个简历系统。
2. **把现有 promptfoo 式评测升级成逐岗位结构断言和失败样例集。** 当前已有 3 个内置样例，不应把“引入 promptfoo 思路”重复算成新工作；新增价值是验证标题、地点、技能属于同一岗位、岗位集合完整性、申请材料事实约束。需要模型/提示词矩阵和报告界面时，再把 promptfoo 作为开发工具接入 Python provider。

Sentence Transformers 值得做隔离试验，但目前没有中文招聘数据上的效果证据，**不建议立刻替换默认 hash 检索或重复岗位判定**。

## 核查范围与固定版本

| 候选 | 实际核查 commit | 许可证 / 依赖边界 | 采用结论 |
| --- | --- | --- | --- |
| [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | `69aa57e7b45de53ab4770bcf178ba39fbe95db02`，提交日期 2026-09-24 | [MIT](https://github.com/promptfoo/promptfoo/blob/69aa57e7b45de53ab4770bcf178ba39fbe95db02/LICENSE)；[package.json](https://github.com/promptfoo/promptfoo/blob/69aa57e7b45de53ab4770bcf178ba39fbe95db02/package.json) 为 0.123.1，Node >=22.22.0 | 先借鉴断言和评测组织；可作为开发依赖，无需加入 Python 生产服务 |
| [reactive-resume/reactive-resume](https://github.com/reactive-resume/reactive-resume) | `73ed3f9b0331d9ae4f97040d2684d06d0357e1ff`，提交日期 2026-09-22 | [MIT](https://github.com/reactive-resume/reactive-resume/blob/73ed3f9b0331d9ae4f97040d2684d06d0357e1ff/LICENSE)；[package.json](https://github.com/reactive-resume/reactive-resume/blob/73ed3f9b0331d9ae4f97040d2684d06d0357e1ff/package.json) 为 5.3.1，Node >=24、pnpm 12.4.2、TS monorepo | 借鉴导出验收和导入映射，整套迁移不匹配 |
| [huggingface/sentence-transformers](https://github.com/huggingface/sentence-transformers) | `4a3b5cd6ec718e421f57e824a41ed3fd99595df6`，提交日期 2026-09-21 | [Apache-2.0](https://github.com/huggingface/sentence-transformers/blob/4a3b5cd6ec718e421f57e824a41ed3fd99595df6/LICENSE)；[pyproject.toml](https://github.com/huggingface/sentence-transformers/blob/4a3b5cd6ec718e421f57e824a41ed3fd99595df6/pyproject.toml) 为 6.2.0.dev0，Python >=3.10、torch >=2.2、transformers >=5,<6 等 | 中文语义模型试验候选，评测后才能决定上线；不直接依赖开发 HEAD |

旧名称 `AmruthPillai/Reactive-Resume`、`UKPLab/sentence-transformers` 的 GitHub API 返回迁移，已搜索并改用上述实际维护仓库。版本是本次读到的源码快照，不代表推荐安装开发分支。复制 MIT 代码须保留版权和许可；分发 Apache 代码应保留相应许可、声明并标记修改。模型权重的许可必须另行核查，库许可不能代替模型许可。

## 1. promptfoo：已有雏形，缺的是更严谨的判定

### 已查看的实质内容

- [`src/assertions/json.ts`](https://github.com/promptfoo/promptfoo/blob/69aa57e7b45de53ab4770bcf178ba39fbe95db02/src/assertions/json.ts)：`handleIsJson` 先解析 JSON，再用 AJV 验证内联或文件中的 schema，返回通过与否、分数、失败原因；不是只检查关键词。
- [`test/assertions/json.test.ts`](https://github.com/promptfoo/promptfoo/blob/69aa57e7b45de53ab4770bcf178ba39fbe95db02/test/assertions/json.test.ts)：覆盖 schema 符合/不符合、文件 schema、无效断言参数等边界。只阅读，未运行上游 Vitest。
- [`examples/eval-python-assert/assert.py`](https://github.com/promptfoo/promptfoo/blob/69aa57e7b45de53ab4770bcf178ba39fbe95db02/examples/eval-python-assert/assert.py)：Python 断言可返回布尔、分数、带原因及 named scores/component results 的结构。适合把“岗位数”“逐岗位字段”“事实来源”分项呈现。
- [`examples/provider-python/provider.py`](https://github.com/promptfoo/promptfoo/blob/69aa57e7b45de53ab4770bcf178ba39fbe95db02/examples/provider-python/provider.py)：`call_api(prompt, options, context)` 返回 `output`、`tokenUsage`，可适配本地 `PageAnalyzer`。**样例自身会真实调用 OpenAI，不能原样作为离线测试运行**，应替换成当前应用调用或录制输出 provider。
- [`test/evaluator/repeatCache.test.ts`](https://github.com/promptfoo/promptfoo/blob/69aa57e7b45de53ab4770bcf178ba39fbe95db02/test/evaluator/repeatCache.test.ts)：有 repeat index 缓存隔离和重跑缓存测试；说明评测重复次数与缓存要一起设计，不能把命中同一个缓存误认为多次独立模型验证。

### 与当前代码的对应关系

本地 `src/career_radar/prompt_eval.py:1` 已明确参考 promptfoo；`EvalCase`（第 21 行）及 3 个 `BUILTIN_CASES`（第 33 行）支持页面类型、标题、地点、关键词。`_check_case`（第 111 行）分别在所有岗位上查标题和地点，再拼接所有岗位正文查关键词，因此字段错配也可能通过。

本次离线构造两个岗位：后端开发 / 北京 / 数据处理，前端开发 / 福州 / React Python；要求“后端开发、福州、Python”，`_check_case` 实际返回 `[]`，即通过。这个结果只证明断言存在盲点，不是实际 LLM 已发生该错误。

建议把期望值改为逐岗位对象并匹配同一条 job，增加最少/精确岗位数、必需字段、禁止捏造项。测试集应加入列表页缺岗位、正文与福利混淆、过期招聘、含恶意指令的 JD、来源不存在的简历事实等真实失败样例。Pydantic 已负责基础结构验证，无需再写一套 schema 引擎；采用 promptfoo 时可导出已有 Pydantic JSON schema，再用 Python 断言补业务约束。

申请模块已有事实来源 ID、五个固定评分维度、确定性权重及状态机（`application/models.py`、`application/evaluator.py`），这些应保留。评测应断言来源引用合法、不得增添画像没有的量化成果、硬性不合格不被总分覆盖。源码测试不能代替人工判断模型输出的招聘合理性。

### 为什么不立即整体接入

当前只有很小的评测集合，直接加入 Node 评测栈会增加环境与升级成本。先修正本地断言、积累脱敏样本收益更直接；一旦需要多模型/多提示词比较和历史结果浏览，再复用 promptfoo 的运行器和报告，避免继续自制通用评测平台。上游 JSON 断言及测试已核查，Python 桥接尚未在本项目运行，不能声称已经集成可用。

## 2. Reactive Resume：优先借鉴真实导出物的可提取性检查

### 与当前缺口高度匹配的代码

[`packages/pdf/src/ats-extraction.integration.test.tsx`](https://github.com/reactive-resume/reactive-resume/blob/73ed3f9b0331d9ae4f97040d2684d06d0357e1ff/packages/pdf/src/ats-extraction.integration.test.tsx) 的流程是实际 `renderToBuffer` → PDF.js 读取 → `harvestPdfDocument` → `analyzePdfResume`，覆盖文本层、联系方式、日期、章节标题、扫描件、文字转轮廓及 Type 3 字体；还验证 PDF.js 运算符常量的兼容性。它没有把“能生成 PDF”当成“导出可用”。

[`packages/resume/src/ats-pdf/harvest.ts`](https://github.com/reactive-resume/reactive-resume/blob/73ed3f9b0331d9ae4f97040d2684d06d0357e1ff/packages/resume/src/ats-pdf/harvest.ts) 读取真实文本项、坐标和字体对象；第 154 行附近明确区分嵌入字体信息与合成 CSS 字体名，防止无依据的字体判断。代码分离了提取和规则分析，适合借鉴这种接口边界。

本地 `application/document_verifier.py:258` 只对 DOCX 提取文本并核对 `expected_texts`；PDF 分支（第 273 行起）检查文件、`%PDF-`、页数和哈希，未检查提取正文。**首个可执行改进**：通过现有 `pypdf.PdfReader` 提取每页文本，检查空白/无文本层、关键联系方式和最终稿字段缺失，输出独立 `pdf_text_missing` 等原因；准备含中文、英文技术词、长链接的合成简历以及空白/乱码 PDF 反例。文本检查不能证明视觉无裁切，仍需保留渲染预览检查。

不建议复制它的 0–100 ATS 总分作为本产品“通过 ATS 概率”。源码中的启发式评分不是任何招聘系统的录取或解析承诺；本地更适合具体可复查的问题列表。

### 可借鉴但优先级较低的导入互通

[`packages/import/src/json-resume.tsx`](https://github.com/reactive-resume/reactive-resume/blob/73ed3f9b0331d9ae4f97040d2684d06d0357e1ff/packages/import/src/json-resume.tsx) 有 JSON Resume → 内部领域模型的明确映射；[对应测试](https://github.com/reactive-resume/reactive-resume/blob/73ed3f9b0331d9ae4f97040d2684d06d0357e1ff/packages/import/src/json-resume.test.ts) 检查无效 JSON/email/date、基本信息、经历、教育、技能、项目等。若需要导入外部简历，可借鉴映射和错误定位，但必须补全本地 `ApplicationProfile.sources/source_ids/verification_status`，不能把普通简历内容自动视为用户已核实事实。

已发现不能照搬的细节：日期 regex 接受年、年月、年月日，并限制月/日数字范围，但不是完整日历有效性检查；导入日期还应按真实日历验证。上游数据以展示字段、HTML 正文为中心，本地以可追溯事实和去身份 LLM 上下文为中心，领域模型不等价。

### 依赖与中文适配限制

PDF 包使用 [`@react-pdf/renderer` 等依赖](https://github.com/reactive-resume/reactive-resume/blob/73ed3f9b0331d9ae4f97040d2684d06d0357e1ff/packages/pdf/package.json)，与现有 python-docx + LibreOffice 输出路径不同。整体引入会重写已有文档、隐私和审批工作流。

也不能断言上游 ATS 对中文已经适配充分：[`jd/tokenize.ts`](https://github.com/reactive-resume/reactive-resume/blob/73ed3f9b0331d9ae4f97040d2684d06d0357e1ff/packages/resume/src/ats-pdf/jd/tokenize.ts) 使用 `Intl.Segmenter("en")` 并保留 C++、C#、Node.js 等技术词；[`analyze/text-quality.ts`](https://github.com/reactive-resume/reactive-resume/blob/73ed3f9b0331d9ae4f97040d2684d06d0357e1ff/packages/resume/src/ats-pdf/analyze/text-quality.ts) 有英语词表和拉丁字符检测。无文本层、替代字符等检查可借鉴，章节别名、中文分词、日期和评分阈值需要本地样本验证。未运行该项目或其上游导出测试。

## 3. Sentence Transformers：候选库可用，中文岗位效果尚待证实

### 实际实现与测试

- [`sentence_transformers/util/retrieval.py:162`](https://github.com/huggingface/sentence-transformers/blob/4a3b5cd6ec718e421f57e824a41ed3fd99595df6/sentence_transformers/util/retrieval.py#L162) 的 `semantic_search` 分块计算 query/corpus 相似度，用 `torch.topk` 和堆合并结果，不需要先部署向量数据库。
- [`tests/util/test_retrieval.py`](https://github.com/huggingface/sentence-transformers/blob/4a3b5cd6ec718e421f57e824a41ed3fd99595df6/tests/util/test_retrieval.py) 的 `test_semantic_search` 将分块结果与直接余弦矩阵 top-k 对比，检查 ID 和数值误差；这能证明检索实现的一致性，不能证明中文岗位语义质量。
- [`sentence_transformers/sentence_transformer/evaluation/information_retrieval.py`](https://github.com/huggingface/sentence-transformers/blob/4a3b5cd6ec718e421f57e824a41ed3fd99595df6/sentence_transformers/sentence_transformer/evaluation/information_retrieval.py) 已实现 Recall、MRR、NDCG 等；应直接利用评测器，不重造指标代码。
- [官方预训练模型列表第 131 行起](https://github.com/huggingface/sentence-transformers/blob/4a3b5cd6ec718e421f57e824a41ed3fd99595df6/docs/sentence_transformer/pretrained_models.md#L131) 明确多语言包含 `zh-cn`、`zh-tw`，候选 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 用于同语言/跨语言语义相似。它是岗位到岗位相似度的合理试验候选，但不能凭文档就认定招聘任务效果合格。
- [检索样例](https://github.com/huggingface/sentence-transformers/blob/4a3b5cd6ec718e421f57e824a41ed3fd99595df6/examples/sentence_transformer/applications/semantic-search/semantic_search.py) 区分 `encode_query` 与 `encode_document`；若模型需要不同 query/document 指令，应遵循模型卡，不能不加区分地照抄英语 `all-MiniLM-L6-v2` 样例。

### 当前代码的实际限制

`embeddings.py` 的 `char-hash-v1` 是字符特征哈希，不是训练过的语义模型。离线小例：

| 文本对 | 当前余弦相似度 |
| --- | ---: |
| 后端研发 / 服务端开发（常见近义表达） | 0.223607 |
| 后端研发 / 前端研发（不同方向但词面相似） | 0.750000 |

这是词面偏差的示例，不是完整 benchmark，也未在本次运行任何神经嵌入模型。当前 `job_embedding_text`（第 92 行）拼接公司、标题、地点、description 前 4000 字，没有独立加入 requirements；若换模型，还要考虑模型 token 上限、JD 分块、字段权重，不能按字符长度推断模型没有截断。

存储更是前置条件：`storage.py:1006` 的 `ensure_job_embeddings` 仅检查 `entity_key` 是否存在，虽然表里保存 provider/dimension，但不会依据模型变化重算；`load_job_embeddings`（第 1047 行）也不筛 provider。上线前必须按模型 ID、revision、维度、文本构造版本隔离或重建索引，防止不同向量空间混用；当前 `0.12` 阈值不可照搬到新模型。

### 建议的试验边界

先以独立可选依赖试验：保留 hash 基线，对脱敏中文岗位构建人工相关性标注，包含同义改写、同词不同方向、同公司福利模板、城市/届别冲突。比较 Recall@5、MRR@10、错误推荐比例，以及 CPU 耗时、内存、模型下载体积；硬性城市/届别规则不能交给相似度代替。模型 commit、权重许可、校验和、离线加载与首次下载行为需在采用前确认。

只有检索效果和资源成本均满足本项目才替换推荐排序；重复岗位归并仍应用本地保守规则，不能因语义相似自动合并不同职位。本次没有核查具体权重模型卡和运行模型，因此候选停留在“值得试验”，不标为“已验证上线可用”。

## 本次验证记录

- 用本项目 `.venv/Scripts/python.exe` 运行 `tests/test_prompt_eval.py` 和 `tests/test_embeddings.py`：**10 项通过**，无真实 LLM 调用。
- 通过 Python 直接调用 `_check_case`，复现跨岗位错配返回空失败列表；直接调用 `feature_hash_vector/cosine_similarity` 得到上述两组数值。没有更改产品代码或测试文件。
- 阅读三个候选的实际源码、许可证、依赖和相关测试；**未运行上游测试套件、未安装候选、未验证模型准确率/性能、未验证本地 PDF 转换效果**。上游有测试不等于本地已经兼容。
- 本地已有 LiteLLM 可选依赖和 trafilatura 正式依赖，本报告不重复把它们列为新引入项。
