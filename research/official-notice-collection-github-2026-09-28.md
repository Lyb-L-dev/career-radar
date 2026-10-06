# 官网招聘公告信息收集项目复用核查（2026-09-28）

目标是补足 Career Radar **已监控官方域名**中未从首页链接暴露的招聘公告。当前 HTML/ATS/去重/robots/限速链路已存在；首轮官网覆盖报告显示，旧公司首页能打开却难以定位招聘入口，新增结构化来源虽有岗位但公司范围仍有限。本轮没有把第三方聚合站的记录直接当成官网事实。

## GitHub 候选与决定

| 项目与固定提交 | 源码核查结果 | 许可/运行条件 | 决定 |
|---|---|---|---|
| [trafilatura `1e31e3e`](https://github.com/adbar/trafilatura/blob/1e31e3e9eb2e4f6fbfd4bc04355bc74005a780e6/trafilatura/sitemaps.py) | `extract_robots_sitemaps` 能从 robots 文本提取站点地图；`sitemap_search` 会自行联网，绕开 Career Radar 的公网校验、robots 和限速 | Apache-2.0；本机已装 2.2.0 | **已接入前者**，复用现有 robots 响应；XML 抓取仍走项目自己的受控抓取器，不调用 `sitemap_search` |
| [RSSHub `f2e7337`](https://github.com/DIYgod/RSSHub/blob/f2e7337be4f1c54bd36680b425c4a5484b36b4cf/lib/routes/gov/zj/ningbogzw-notice.ts) | 宁波国资委公告路由确实指向官方国企招聘公告栏目，但本次访问该官网超时，未证实当前仍可用；[湖南大学校招路由](https://github.com/DIYgod/RSSHub/blob/f2e7337be4f1c54bd36680b425c4a5484b36b4cf/lib/routes/hnu/careers.ts)指向校方页面，但元数据中的站点名出现 `undefined` | AGPL-3.0；整体是独立服务 | 可作为**线索来源**评估，暂不复制路由或把聚合结果直接入正式岗位库 |
| [Campus-Jobs-Scraper `ab1c42f`](https://github.com/hunhunzhang/Campus-Jobs-Scraper/blob/ab1c42ffa320a8bee5596f5d41d8b8ee59a6ea64/tencent_crawler.py) | README 与腾讯脚本显示其硬编码腾讯、字节等大厂接口，高并发导出 Excel；不解决中小企业官网公告入口定位 | 所查提交的仓库树没有 LICENSE | 不复制源码；“先核实公开接口再做站点适配”的思路与现有 JSON Feed 一致 |
| [ultimate-sitemap-parser `6ab7704`](https://github.com/GateNLP/ultimate-sitemap-parser/blob/6ab7704f53ad06fc9bd9742ef9c91848b8f9d7f5/pyproject.toml) | 成熟的 sitemap/index/RSS 解析与测试，但其联网树遍历需要另做安全适配 | GPL-3.0-or-later，Python ≥3.10 | 不复制或直接引入 GPL 代码；当前只需有限 XML URL 发现 |
| [sitemap-parser `7c7e696`](https://github.com/TheLovinator1/sitemap-parser/blob/7c7e6963fbf141021a2e39e36ca680659a6de3b6/pyproject.toml) | 支持传入 XML 字符串，源码用 `niquests`/`xmltodict` | MIT，但最低 Python 3.14；Career Radar 支持 3.10 起 | 版本不匹配，不接入 |
| [xixicc2027 `093e086`](https://github.com/xixicc186/xixicc2027/blob/093e0867e17da27fbc7779b9814f21cae159f163/README.md) | 2026-09-28 更新的 442 条 2027 届聚合数据，部分有官网网申链接，许多条 `apply_url=null`、仅提示搜索公众号；[抓取 Skill](https://github.com/xixicc186/xixicc2027/blob/093e0867e17da27fbc7779b9814f21cae159f163/skill/qiuzhao-feed/scripts/fetch_render.py)直接从 GitHub 下载 JSON 并本地渲染 | 所查提交没有 LICENSE；主要面向 2027 届，与当前已确认画像的 2026 届不完全匹配 | 可作为人工发现线索，不批量复制数据或直接入库 |
| [job-pulse `4ca8b74`](https://github.com/Leeeezhao/job-pulse/blob/4ca8b741a958a54876e472373496b015a5266fba/README.md) | 记录多家官网/API 的实测方法，也明确承认早期 URL 大量写错；医疗 AI 公司清单里部分 Moka slug 明示“需验证” | 所查提交没有 LICENSE；偏大厂与算法/研究岗 | 借鉴“逐站核验请求参数”方法，链接一律重新核对，不复制静态数据 |
| [wechat-recruit-bot `a50ae32`](https://github.com/chuichuizhao/wechat-recruit-bot/blob/a50ae32bb878bbd24e4929bbf8c354a8bd20718a/README.md) | 微信机器人接收招聘文字/公众号链接，提取后同步飞书 | MIT；依赖第三方微信 SDK、Qwen 和飞书配置；Career Radar 已有公众号发现链路 | 暂不接入额外账号/平台系统 |

没有明确许可证时，不把“公开可看”当成“可以复制”。RSSHub 和 USP 的许可证也不适合在本项目中直接粘贴代码。本地新增的 XML 层使用已安装的 `lxml` 安全解析接口，是针对 Career Radar 网络边界编写的适配代码，不含上游复制片段。

## 本轮已接入的范围

`RobotsPolicy` 缓存官方 `Sitemap:` 声明；`PageFetcher.fetch_sitemap` 用现有公网目标校验、robots、限速、重定向和下载大小限制读取同域 XML，不经 Playwright。发现器只接受 `urlset`/`sitemapindex` 的直接 `<loc>`，拒绝 DTD/实体、跨域位置和站外重定向；最多读取 3 份地图、挑出 20 个招聘语义 URL，并继续服从每公司页面上限及查询参数变体上限。候选 URL 只是抓取入口，正文仍要走现有提取和匹配链路，地图中出现一个地址不等于存在当前岗位。

配置项 `discover_from_sitemap: auto|true|false` 默认 `auto`，只对首页发现或公告监控自动启用。合成端到端测试验证了“首页无链接、地图有官方公告”时可走到真实公告页；错误 XML、跨域链接和站外重定向均不会产生候选。2026-09-28 用本项目 `PageFetcher` 对 ZStack 官方 `https://www.zstack.io/sitemap.xml` 做只读探针：HTTP 200，解析 310 个同域页面，但无招聘语义路径；同日对当前三家首页入口飞通、共享数据、云天半导体做受控站点地图探针，招聘候选 URL 均为 0。因此**当前公司池尚无经真实站点验证的新增岗位**。此结果不能外推为其它官网的召回提升。

下一步应在确有公告栏目却首页不可见的官方域名上验证增益；对 URL 无语义的公告栏目，站点地图单独无法判断标题，需补该站公开列表/API 的适配器或使用已核验的 RSSHub 路由作发现线索。正式启用任何线索源前仍需检查公告日期、公司归属和可投递入口。
