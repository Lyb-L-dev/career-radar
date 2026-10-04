# Scrapling 能否很好地爬取 BOSS 直聘？（2026-09-24）

**结论：目前不能证明。** [D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) 是通用抓取框架，能够作为构建 BOSS 直聘抓取器的浏览器层，但截至本次核查的固定提交，没有 BOSS 直聘适配器、示例、测试或成功抓取证据。安装后直接调用通用 `StealthyFetcher.fetch(boss_url)`，不能据此预期稳定获取列表和完整 JD。

核查快照：[0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f](https://github.com/D4Vinci/Scrapling/commit/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f)，提交日期 2026-09-23。完整 Git tree 有 309 项且未截断；路径中未发现 boss/zhipin 命名文件。[GitHub issue 搜索](https://github.com/D4Vinci/Scrapling/issues?q=zhipin) 的 zhipin/boss 结果也未找到对应 issue；这只是“未找到公开证据”，并不证明无人私下使用。

## 代码里确实能用的能力

- [DynamicFetcher 与会话实现](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/scrapling/engines/_browsers/_controllers.py)：基于 Playwright，可用 `cdp_url` 连接现有浏览器，用 `user_data_dir` 保存会话，支持等待 CSS 节点、浏览器页面操作和捕获 XHR。源码中 `connect_over_cdp` 负责连接，`capture_xhr` 把匹配的响应装入结果。
- [XHR 文档示例](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/docs/fetching/dynamic.md)：支持读取匹配响应的 URL、状态和原始 body。技术上可作为 BOSS 页面搜索接口响应的采集层，但还需自行实现筛选参数、列表映射、分页、登录状态与字段完整性判断。
- [StealthyFetcher](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/scrapling/fetchers/stealth_chrome.py)：提供 real_chrome、cdp_url、user_data_dir、浏览器上下文和 Cloudflare challenge 选项。[Stealth 文档](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/docs/fetching/stealthy.md) 的示例是 Cloudflare 等通用场景，没有 BOSS 的验证测试。Cloudflare 处理能力不能推导为 BOSS 登录、验证码和风控均可通过。
- [tests/fetchers/sync/test_dynamic.py](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/tests/fetchers/sync/test_dynamic.py) 测试普通页面响应和无效 CDP URL；这证明测试覆盖部分通用接口，不是已登录 BOSS 的端到端验证。

## 与已有 BOSS 专用项目比较

[之前核查的 eatmoreduck/boss-zhipin-scraper](boss-zhipin-sources-2026-09-24.md) 在[固定提交的主脚本](https://github.com/eatmoreduck/boss-zhipin-scraper/blob/16cc992bbf1d4e9efc7cfba4d39e819176a6bb28/scripts/boss_cdp_raw.py) 中已有 BOSS 列表 JSON 字段映射、职位 URL、详情页 JD 提取、登录截断和短正文拒绝、去重及输出流程。Scrapling 提供更通用的浏览器 API，不提供这些 BOSS 业务规则。两者结合属于**开发一个新适配器**，而不是直接复用一个完成品。

BOSS 专用项目也未在本机执行真实抓取，不能把它与 Scrapling 的静态源码对比说成现场成功率对比。

### 针对 BOSS 的方式比较

| 方式 | 已登录会话 | BOSS 列表与完整 JD | 当前证据支持的判断 |
| --- | --- | --- | --- |
| Scrapling 默认 Headless/StealthyFetcher | 默认启动新浏览器；需另外提供登录会话 | 仅通用页面/选择器能力；无 BOSS 字段映射和截断识别 | 无证据表明开箱即用。Cloudflare solver 处理的是 Cloudflare challenge，不能推出能处理 BOSS 验证。 |
| Scrapling 连接已登录 Chrome + 自写 BOSS 适配器 | 可通过 cdp_url；[实现](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/scrapling/engines/_browsers/_controllers.py#L78) 调用 connect_over_cdp | [capture_xhr](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/scrapling/engines/_browsers/_base.py#L157) 可采集搜索接口响应；BOSS 业务规则仍须自写 | 技术路线可行，但与原生 CDP 项目使用同一登录浏览器，并无已证实的抓取成功率优势。 |
| eatmoreduck BOSS 专用 CDP 脚本 | 必须使用已登录的本机 Chrome/Edge 会话 | [map_api_job](https://github.com/eatmoreduck/boss-zhipin-scraper/blob/16cc992bbf1d4e9efc7cfba4d39e819176a6bb28/scripts/boss_cdp_raw.py#L607) 映射字段；[extract_detail_fields](https://github.com/eatmoreduck/boss-zhipin-scraper/blob/16cc992bbf1d4e9efc7cfba4d39e819176a6bb28/scripts/boss_cdp_raw.py#L854) 拒绝登录截断、导航页和过短 JD；[测试](https://github.com/eatmoreduck/boss-zhipin-scraper/blob/16cc992bbf1d4e9efc7cfba4d39e819176a6bb28/tests/test_chrome_setup.py#L628) 覆盖这些边界 | 若目标仅是 BOSS，当前代码准备度最高；真实网站成功率仍需当天、同会话、同查询实测。 |
| HeyClioo 的浏览器技能 | 要求用户已登录浏览器 | [技能](https://github.com/HeyClioo/boss-zhipin-jd-scraper/blob/c0503160e2f9e86744555971d885d97606a85f12/SKILL.md) 逐页导航、提取显示文本、导出 Markdown | 适合少量人工监督采集；仓库没有独立爬虫包和测试，不能据此证明批量稳定性。 |

Scrapling 的[自适应选择器](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/docs/parsing/adaptive.md#L103)能在页面结构改变后尝试重新定位已记录的元素；它需要先记录元素特征，并且文档说明重复元素选择器只保存第一个匹配元素的特征。对多条职位列表，不能把“找到了相似节点”直接当成正确岗位；须以职位 ID、公司和详情链接核对归属。这项优势主要减少选择器维护，不解决登录状态、接口字段、分页、JD 是否完整。

若要客观比较“谁更能抓到 BOSS”，应在用户自己已登录的同一浏览器、同一城市/关键词、同一短时间窗口运行小样本，对比列表返回数量、详情成功率、JD 关键字段完整性、误混岗位、验证码/限流次数及每条耗时。没有这组数据，不能根据 star 数或通用功能宣传给出成功率排名。

## 对 Career Radar 的建议

当前 [crawler.py](../src/career_radar/crawler.py) 已有 requests、Playwright、robots 检查、限速和公网目标校验，[discovery.py](../src/career_radar/discovery.py) 已做正文/链接提取。引入 Scrapling 不会自动解决 BOSS 特有的会话与岗位字段问题，也会增加重叠浏览器层。[pyproject.toml](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/pyproject.toml) 的抓取功能附加依赖包含 Playwright >=1.62、Patchright、curl_cffi、Browserforge、Protego 等；本机现有 Playwright 为 1.61.0，接入需重新解依赖并回归。项目本身要求 Python >=3.10，[BSD-3-Clause 许可](https://github.com/D4Vinci/Scrapling/blob/0b85f7ec20b32a91cf4c5b7fa9bede36d03e157f/LICENSE) 可按条件复用。

若只是需要 BOSS 岗位数据，先围绕一个**已登录的浏览器会话**和 BOSS 专用项目验证小样本：列表字段、完整 JD、失败状态、去重与更新；验证需要在用户会话中进行。只在发现现有 Playwright 无法满足特定需求时，才试验 Scrapling 的 CDP/XHR 能力。第三方平台数据应沿用 Career Radar 的“待核验线索”来源边界，不能写成官方已确认岗位。

本次仅阅读固定提交的源码、文档、测试、许可，并检查本机依赖；**未安装 Scrapling、未登录 BOSS、未执行真实抓取**，因此“能否很好地爬取”尚无实测结论。
