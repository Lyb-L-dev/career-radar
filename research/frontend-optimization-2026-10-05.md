# Career Radar 前端优化：一手来源、复用判断与验收依据

调研日期：2026-10-05。本文整理本轮已经阅读的官方文档、作者文章及维护者仓库源码。网络来源用于建立设计依据，项目基线来自本轮本地审计；它们均不代表实施后的结果。

用户最终确定的方向是：**首页岗位优先，其次成长；保留现有风格，先优化核心流程。** 沿用 React 19、Tailwind 3、Radix 和 TanStack Query，不为模板更换应用框架或样式栈。成长模块的能力证据、JD 原文与任务追溯语义继续保留。

## 项目基线与采用方向

| 本轮记录的基线 | 对应优化与验收方向 |
|---|---|
| 390px 首页被“最近岗位变化”区域撑到 535px | 修复真实内容的最小宽度、换行和容器溢出；390px 下页面宽度不超视口，长岗位标题、公司名和链接仍可阅读 |
| 品牌蓝在白底的对比度约 4.1:1 | 保留品牌方向，分别调整文字、按钮与装饰用途；普通文字须达到 WCAG AA 4.5:1，不能用大文字的 3:1 门槛替代 |
| 弱灰在白底的对比度约 3.26:1 | 日期、说明、证据元信息等实际阅读文字调整至符合 AA；区分可读次要内容和纯装饰 |
| 入口 index 为 420188 raw / 129913 gzip bytes | 以此作为同构建口径的入口包基线；定位重型导入后有针对性拆分，不以体积减少冒充交互速度验证 |
| 官网岗位已有 URL 筛选状态；all/BOSS 需要补齐 | 复用现有约定，让关键筛选、分页等可恢复且可分享；返回页面保留上下文 |
| 已有 route splitting | 保留并检查边界，避免把“增加路由拆分”重复当作新成果 |

任务优先的信息架构原则在此具体解释为“当前求职操作优先”：首页首先帮助用户找到、筛选和处理岗位，其次承接今日成长任务。它不意味着把能力地图置于岗位列表之前，也不意味着删除数据来源与局限提示。

## 一手文章与官方文档

以下“采用”是面向 Career Radar 的设计决定或推断，不宣称已实施。未标发布日期的动态文档以本次读取日期为准。

| 来源 | 日期与证据类型 | 采用 | 局限与不采用 |
|---|---|---|---|
| [NNGroup：Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/) | Jakob Nielsen，2006-12-03；设计指导 | 首页突出岗位操作及今日成长摘要；原始答题、完整评分依据、目标编辑等按需展开，入口明确说明内容 | 不隐藏高频必需操作，不增加多层折叠；文章提出的经验不能代替本项目任务验证 |
| [NNGroup：8 Design Guidelines for Complex Applications](https://www.nngroup.com/articles/complex-application-design/) | Kate Kaplan，2020-11-08；复杂应用设计指导 | 保留 JD、技能、任务、证据的来回路径与上下文；模型等待时可切换视图，中断后能恢复 | 借鉴恢复上下文与减少杂乱，不继承企业软件的功能规模 |
| [Linear：A calmer interface for a product in motion](https://linear.app/now/behind-the-latest-design-refresh) | Charlie Aufmann、Maxime Heckel，2026-03-12；作者设计复盘 | 让当前内容与操作突出，降低重复图标、卡片和分割线的竞争；导航和页面操作位置一致 | 属于作者设计判断；不照搬其低调文字、小图标或深色主题，不以降低对比度换取视觉平静 |
| [W3C：中文排版需求](https://www.w3.org/TR/clreq/) | 2026-09-01 Group Note Draft；中文排版草案 | 检查中文断行、标点、中西混排、阅读宽度与行高；JD、教学和证据正文与代码区域采用不同阅读处理 | 含书刊场景，行长参考不机械变成网页硬指标；字体大小和行高是项目默认值，需实机验证 |
| [W3C：WCAG 2.2](https://www.w3.org/TR/WCAG22/)及[目标尺寸解释](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum) | 标准初版 2023-10-05；标准与解释文档 | 以 AA 对比度、键盘、焦点、重排及目标尺寸为验收依据；状态使用文字和图标，不只使用颜色 | 24×24 CSS px 是含例外条件的最低要求；移动主要操作可采用更宽裕尺寸，但不能把 44px 说成 AA 的统一强制要求 |
| [W3C：状态消息解释](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) | 动态官方解释文档，2026-10-05 读取 | 排队、成功、失败和验证结果在合适的状态区域通知辅助技术，保持焦点稳定 | 不把每次轮询和整页结果都放入 live region；解释文档辅助理解，正式要求以标准为准 |
| [web.dev：Optimize Interaction to Next Paint](https://web.dev/articles/optimize-inp) | 2023-05-19 发布，2025-09-02 更新；浏览器性能指导 | 先记录岗位筛选、节点选择、答题输入的慢交互，再减少长任务和无益渲染；按设备区分实验条件 | 良好 INP 的真实用户 75 分位目标为 ≤200ms；单用户本地实验不能冒充真实流量统计，LLM 等待也不是 INP |
| [TanStack：Background Fetching Indicators](https://tanstack.com/query/latest/docs/framework/react/guides/background-fetching-indicators)及[Important Defaults](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults) | 动态官方文档，2026-10-05 读取 | 初载用局部骨架，后台更新保留现有内容；按数据变化配置 staleTime；操作结束停止轮询 | Query 缓存不替代持久化 operation 状态；窗口聚焦刷新与请求重试需结合当前版本，不能直接照搬 latest 的新选项 |
| [React：useTransition](https://react.dev/reference/react/useTransition) | 动态官方 API 文档，2026-10-05 读取 | 测量确有必要时，让非紧急视图更新不阻塞输入 | 不把受控输入本身放进 Transition；它不缩短模型或网络耗时，不为所有状态增加 Transition |
| [Radix：Accessibility](https://www.radix-ui.com/primitives/docs/overview/accessibility) | 动态官方组件文档，2026-10-05 读取 | 复用现有 Tabs、Dialog、Select 的语义、键盘与焦点行为，补齐中文标签和应用上下文 | 采用 Radix 不等于整个页面自动符合 WCAG；对比度、标签、图形和错误恢复仍需本地验收 |

本轮优先选取一手材料，未将搜索结果摘要、模板广告或社区意见当作事实证据。中文阅读、任务层级和具体信息密度仍需通过真实流程检查，无法仅由某篇文章确定。

## GitHub 源码复用核查

两项核查均通过 GitHub API 读取元数据、固定 HEAD、完整文件树及具体文件；没有安装依赖、执行外部脚本或运行上游测试。证据层级为**源码核查**，不是集成验证。两个仓库默认分支均为 main，读取时未归档。

### shadcn-ui/ui：局部借鉴，避免照搬 Tailwind 4 模板

实际读取 HEAD：[`95efb5cd8d7f13adba70b58b1119211e8980683f`](https://github.com/shadcn-ui/ui/commit/95efb5cd8d7f13adba70b58b1119211e8980683f)，提交日期 2026-10-05。

实际阅读的源码：

- [sidebar-07 页面结构](https://github.com/shadcn-ui/ui/blob/95efb5cd8d7f13adba70b58b1119211e8980683f/apps/v4/registry/bases/radix/blocks/sidebar-07/page.tsx)
- [sidebar 组件](https://github.com/shadcn-ui/ui/blob/95efb5cd8d7f13adba70b58b1119211e8980683f/apps/v4/registry/bases/radix/ui/sidebar.tsx)
- [分组导航](https://github.com/shadcn-ui/ui/blob/95efb5cd8d7f13adba70b58b1119211e8980683f/apps/v4/registry/bases/radix/blocks/sidebar-07/components/nav-main.tsx)
- [移动断点 hook](https://github.com/shadcn-ui/ui/blob/95efb5cd8d7f13adba70b58b1119211e8980683f/apps/v4/registry/bases/radix/hooks/use-mobile.ts)
- [应用依赖声明](https://github.com/shadcn-ui/ui/blob/95efb5cd8d7f13adba70b58b1119211e8980683f/apps/v4/package.json)
- [组件转换语料测试](https://github.com/shadcn-ui/ui/blob/95efb5cd8d7f13adba70b58b1119211e8980683f/packages/registry/src/utils/transformers/transform-corpus.test.ts)

采用决定：借鉴主区域与导航对齐、桌面展开与移动抽屉状态分离、图标辅助标签等模式，用本地 React Router、Radix 包装、图标和 cn 工具实现所需部分。其 dashboard 示例可以作为容器组织参考，不整体导入 KPI、图表或组织切换功能。

适配限制：该 HEAD 的 apps/v4 声明 Tailwind ^4.3.0、Next 16.3.3、React 19.2.3；sidebar 包含 w-(--sidebar-width)、--spacing(4)、新 data/has 变体、cn 包及站点 IconPlaceholder 引用。本项目 Tailwind 3 不具备原样安装兼容性。保留技术栈，将需要的规则转为本地支持的任意值或 CSS；不执行 latest CLI 导入整个 block。

不照搬全局 Ctrl/⌘+B 快捷键：所读处理器未排除编辑输入场景，可能干扰答题和文稿操作。源码写入 sidebar cookie，恢复读取依赖调用方，也不能据此宣称复制页面就具备完整持久化。

维护与测试证据：sidebar 相关修改包括 [2026-09-04 迁移 cn](https://github.com/shadcn-ui/ui/commit/c257f688cf4de7ec10cc1be84cad29cd4631182c)；2026-03-02 为格式化，2026-02-06 添加新样式 blocks。当前 HEAD 的最新提交是 registry 配置读取修复，不能被描述为 sidebar 修复。所读转换语料测试含 v3/v4 前缀案例，但验证的是源码转换快照，不证明 Tailwind 4 sidebar 在 Tailwind 3 的视觉或交互兼容。完整树未发现以 sidebar 命名的直接交互测试；本地仍需测试移动抽屉、焦点、断点与溢出。

许可：[实际 LICENSE.md](https://github.com/shadcn-ui/ui/blob/95efb5cd8d7f13adba70b58b1119211e8980683f/LICENSE.md)为 MIT，Copyright (c) 2023 shadcn。直接复制实质代码时保留版权和许可文本；思想借鉴标明来源。许可证结论针对已读代码，不替示例图片等外部素材作额外授权判断。

### vercel-labs/web-interface-guidelines：筛选为评审清单

实际读取 HEAD：[`e3d624baaf29dc1fc645aff3e38f03e564d2d6b1`](https://github.com/vercel-labs/web-interface-guidelines/commit/e3d624baaf29dc1fc645aff3e38f03e564d2d6b1)，2026-08-18。

已读 [AGENTS 规则原文](https://github.com/vercel-labs/web-interface-guidelines/blob/e3d624baaf29dc1fc645aff3e38f03e564d2d6b1/AGENTS.md)、[command 评审模板](https://github.com/vercel-labs/web-interface-guidelines/blob/e3d624baaf29dc1fc645aff3e38f03e564d2d6b1/command.md)和[实际 LICENSE](https://github.com/vercel-labs/web-interface-guidelines/blob/e3d624baaf29dc1fc645aff3e38f03e564d2d6b1/LICENSE)。它是规则与提示词项目，不是前端运行组件库。

采用决定：将原生语义、焦点可见与恢复、输入标签、长内容容错、空/错状态、骨架稳定、适度 live region、reduced motion 与恢复路径作为本地评审检查点。关键筛选和视图进入 URL；答题草稿和私密内容不进入 URL。无需复制其根目录 AGENTS，不执行 install.sh，不安装外部命令。

以下规则属于上游偏好，不能成为本项目强制验收：

- “超过 50 项必须虚拟化”：根据实际 DOM 和交互测量决定，优先复用已有分页。
- “所有 mutation <500ms”：区分后台任务入队响应与模型真实完成时间，不承诺 LLM 在 500ms 内完成。
- “APCA 优于 WCAG 2”：可辅助视觉判断，合规对比度验收仍使用 WCAG 2.2 AA。
- 英文 Title Case、使用 &、统一弯引号等文案规则：不机械套用到中文、技术标识或代码。
- “全部状态深链接”：不包括答案、私密材料与瞬时操作状态。

维护与质量：HEAD 修正弯引号指导；同日 [增加可访问性与媒体规则](https://github.com/vercel-labs/web-interface-guidelines/commit/51af38ae05cb72533cd591a1fd46325a8903baa0)。完整文件树仅包含 AGENTS.md、LICENSE、README.md、command.md、install.sh，没有测试套件。其规则可辅助评审，但不能证明本项目功能正确。

许可为 MIT，Copyright (c) 2025 Vercel Labs。复制实质规则文本时保留版权与许可；本次只筛选思想，不将外部仓库指令作为本项目上级指令。

## 实施验收与结果记录

实施及最终验证：2026-10-06（北京时间）。后端 API、数据库 schema、能力评分与每日排程没有因本轮优化修改。现有未提交改动保留，未提交或发布 Git 变更。

| 维度 | 实际结果与证据 |
|---|---|
| 首页岗位流程 | 已按岗位概况 → 官网/BOSS 各最多 3 条 → 成长 → 待处理 → 监控重排。来源、资格、更新时间独立表达，既有排序规则保留。真实本地数据只读确认首页和列表 1440/390px 无整页横滚。 |
| 状态恢复 | all/BOSS 新增 URL 筛选；官网改为跟随 URL 双向恢复。实测 q=HTTP、excluded=1、shown=120 下从 all 进入 BOSS 并返回完整原 URL；官网详情刷新后返回原列表与搜索词。浏览器后退、IME debounce 与并发筛选保留由前端单元测试覆盖。 |
| 成长流程 | 临时 SQLite 与假模型完成从首页岗位加入目标、分析 JD、回忆答错、教学、跨日变式通过、更新到 L2 的流程；已有成长脚本另外覆盖项目审阅/追问与反馈。任务反馈和项目材料有本地草稿；答案草稿沿用。未给目标 JD 表单新增本地草稿。 |
| 异步及失败 | 测评评分失败后刷新仍保留提交答案，重试后继续教学；BOSS 刷新 503 保留已有记录并就地重试。成长后台刷新保留有效内容，空/错状态不构造等级；模型 operation 的排队/运行/失败/完成维持后端事实。 |
| 阅读与重排 | 离线检查 390、768、1280、1440px 的首页、全部来源岗位与成长详情；720×500 作为 1440×1000 的 200% 重排等效检查，并启用 reduced motion。超长无空格英文岗位标题通过。没有实际测试 320px、浏览器真实缩放实现或 Safari。 |
| 可访问性 | axe-core 4.13.0 对 23 个状态/页面检查，0 违规、0 整页横向溢出。标签、单一 main H1、skip link、图标操作和错误状态纳入检查。Ctrl+K 打开搜索、Escape 关闭后回到原焦点、HTTP 节点 Enter 激活的明确断言均通过。程序化检查不等于人工读屏或完整 WCAG 认证。 |
| 性能 | 搜索变为受控按需加载，首页不提前请求日报；场景输入→两帧绘制为本地实验室测量，不等于线上 INP。加载策略对照见下节，保留首次搜索开启的等待代价。 |
| 回归 | 前端 49 项测试、lint、build 通过；后端全量 pytest（421 项）与 Ruff 通过。既有成长、官网筛选和打包形态 E2E 均通过；纯 UI 验证真实模型调用为 0。 |

可复现命令（从项目根目录；前端 npm 命令从 web 运行）：

- `npm run test`、`npm run lint`、`npm run build`
- `.venv/Scripts/python.exe -m pytest -q`
- `.venv/Scripts/python.exe -m ruff check --no-cache src tests scripts`
- `.venv/Scripts/python.exe scripts/verify_frontend_ui.py --output <独立截图目录>`
- `.venv/Scripts/python.exe scripts/verify_growth_ui.py --output <独立截图目录>`
- `.venv/Scripts/python.exe scripts/verify_official_screening_ui.py`
- `.venv/Scripts/python.exe scripts/run_web_e2e.py`

截图及浏览器报告目录：`C:/Users/<local-user>/.codex/visualizations/2026/10/05/01a10b30-3b42-7e20-9fca-0a0e1ae8c388/frontend/`。`frontend-verification.json` 记录各场景 axe 结果；`frontend-*.png` 使用合成数据，`live-*.png` 是拦截所有写请求后的真实数据首屏确认。合成截图中的 L2 不属于用户能力记录。

独立 Impeccable finish review 初次发现 BOSS 首页资格缺少独立标签、BOSS 返回 all 列表丢失上下文，两项均已修复并复核为 RESOLVED，视觉方向 PASS。机械检测器一次运行结果为 `[]`，没有因此宣称功能或无障碍自动通过。

验证过程确实发现并修正：搜索 listbox 内装饰 separator 语义、实际 Sonner 入口未使用调色后的共享组件、对话框关闭目标尺寸、灰底错误文字对比度 4.39:1。弹层 audit 等待有限开场动画结束，避免将半透明过渡帧当作稳定色板。补充键盘断言后，修正了受控搜索弹窗没有 Radix Trigger 引用时无法回焦点的问题：关闭时显式恢复打开前元素，来源元素已离开 DOM 时回到主内容。旧成长反馈测试补了展开入口；打包 E2E 修正了已过期的“固定 DeepSeek”文案断言，保留服务商、备份与日报的实际检查。

依赖方面只增加 devDependency `axe-core` 4.13.0，不导入生产 bundle，MPL-2.0 许可记录在 THIRD_PARTY_NOTICES.md。没有安装网络上的新设计 skill，没有执行外部安装脚本，也没有引入 shadcn 整套模板或 Tailwind 4。

本地服务已确认返回最新 `web/dist/index.html`（HTTP 200），入口 `index-BMW0xH8N.js`；仅刷新页面即可使用。保留既有 Starlette/httpx 弃用与 Browserslist 数据陈旧提示，没有为本轮界面改动升级这些无关依赖。

## 隔离实测：常驻搜索与按需搜索的加载对照

固定产物复测日期：2026-10-06（北京时间，JSON 记录为 2026-10-05T16:22:13Z）。可复现脚本为 [benchmark_frontend_loading.py](../scripts/benchmark_frontend_loading.py)，完整逐次请求、资源 SHA256、运行环境和中位数见 [frontend-loading-comparison.json](frontend-loading-comparison.json)。本节数字已用共享 Toaster、对话框关闭目标及 danger 文字对比度修复后的固定产物覆盖，入口为 index-B2A8Zbre.js、样式为 index-Dg5CXtem.css。

加载对照保留其固定构建的资源 SHA；此后只增加关闭搜索的焦点恢复回调，没有改变按需加载策略。最新构建的核心流程和键盘另经上述端到端检查。

这项实验比较的是**同一新界面下“常驻搜索”与“按需搜索”**。它不是原始全站与优化后全站的速度对比，也没有测量线上 INP。

方法：冻结当前 web 源码和 dist，在临时目录重建 optimized，要求产物与冻结的当前 dist 逐文件 SHA256 完全一致。然后只将 AppLayout 的 `commandOpen && <Suspense>...<CommandPalette open={commandOpen}>` 改为始终挂载同一个受控组件（初始 open=false），构建 resident 版本。没有修改生产 web/src、配置、数据库或 dist；脚本结束再次核对生产 dist 未变。

两版分别使用临时配置与 SQLite 的 create_app 实例，空岗位、运行与日报数据，以及配置校验所需的一条静态虚构企业。API 只允许 GET，浏览器屏蔽外网和 mutation，成长模型 factory 禁用；真实模型调用为 0，临时服务均正常停止。每版 3 次，交错顺序，每次新浏览器 context 且路由拦截禁用 HTTP 缓存。环境为 Windows 11、Python 3.13.3、Chromium 149.0.7827.55、1440×1000、本地网络、未限速。

首页阶段为首页主标题可见、networkidle 后再等 250ms，尚未打开搜索。下表字节数是实际请求的唯一 JS 文件在构建目录中的原始大小，gzip 为 Python level 9、mtime=0 的估算总和，**不是实际 HTTP 传输字节数**。

| 每版 3 次的中位数 | 常驻搜索 | 按需搜索 | 按需版首页减少 |
|---|---:|---:|---:|
| 初次首页 JS 文件数 | 19 | 18 | 1 |
| 初次首页 JS raw bytes | 590570 | 570219 | 20351（约 3.45%） |
| 初次首页 JS gzip bytes | 188880 | 181931 | 6949（约 3.68%） |
| 初次首页 API 请求数 | 9 | 8 | 1 |

两版首页共有的 API 每次各调用 1 次：`/api/applications`、`/api/companies`、`/api/dashboard`、`/api/growth`、`/api/jobs`、`/api/notifications`、`/api/platform-leads`、`/api/runs`。常驻搜索额外提前调用 `/api/reports` 1 次；按需版首次打开搜索时才调用它。

首次打开搜索后，按需版新增 CommandPalette JS（20355 raw / 6945 gzip bytes）与 `/api/reports` 1 次；常驻版没有新增 JS 或 API。打开后的总资源几乎相同：常驻版 590570 raw / 188880 gzip bytes，按需版 590574 raw / 188876 gzip bytes，API 均为 9 次。少量字节差异来自条件包装与构建压缩；这里的收益是延后首页不需要的加载，并未消除搜索功能的资源成本。

自动化点击至搜索输入可见的实验室中位数为常驻版 58.719ms、按需版 394.275ms，显示首次开启需要支付延迟加载成本；这包含 Playwright 操作和可见性等待，不是 INP 或纯浏览器输入到绘制时延。首页就绪墙钟中位数为 1490.543ms 与 1612.928ms，包含 networkidle 和固定等待且只有 3 次样本，**不足以证明按需版首页更快**。

结论与局限：已经证明此加载策略在本地相同新界面下减少首页初次 JS 和一次日报请求，并将成本转移到首次打开搜索。空数据没有覆盖真实列表规模、慢网络、移动设备或模型耗时；共享浏览器进程与本地服务也不等同于独立真实用户。原有 420188/129913 bytes 基线是单个入口 index，而本节是首页全部实际加载 JS，不能混用口径宣称全站体积或速度提升。

复现条件：使用现有已安装 Node/web/node_modules、Python 依赖与 Playwright Chromium，不安装新生产依赖；当前源码必须与当前 dist 对应。仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_frontend_loading.py --repetitions 3
```

本轮脚本 Ruff 检查通过；实际 6 次浏览器样本没有页面异常或被屏蔽的外部/mutation 请求。上游测试仍未执行，shadcn block 仍未整体集成。
