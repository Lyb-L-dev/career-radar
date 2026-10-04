# BOSS 直聘抓取项目核查（2026-09-24）

问题：GitHub 上是否有能抓取 BOSS 直聘职位及完整 JD 的项目？结论是**有**，但所查较新的方案都依赖用户已登录的真实浏览器或其会话，不能视为 Career Radar 当前“无需登录的企业官方公开页面”抓取器的直接替代。

## 候选与判断

| 项目 | 核查快照 | 实际能力和证据 | 判断 |
| --- | --- | --- | --- |
| [eatmoreduck/boss-zhipin-scraper](https://github.com/eatmoreduck/boss-zhipin-scraper) | [16cc992](https://github.com/eatmoreduck/boss-zhipin-scraper/commit/16cc992bbf1d4e9efc7cfba4d39e819176a6bb28)，2026-09-17 | [主脚本](https://github.com/eatmoreduck/boss-zhipin-scraper/blob/16cc992bbf1d4e9efc7cfba4d39e819176a6bb28/scripts/boss_cdp_raw.py) 通过 Chrome/Edge CDP 复用登录态，收集列表 JSON、打开详情页提取 JD、输出 JSON/CSV；[测试](https://github.com/eatmoreduck/boss-zhipin-scraper/blob/16cc992bbf1d4e9efc7cfba4d39e819176a6bb28/tests/test_chrome_setup.py) 覆盖职位映射、JD 截断拒绝、无效详情跳过等；[MIT](https://github.com/eatmoreduck/boss-zhipin-scraper/blob/16cc992bbf1d4e9efc7cfba4d39e819176a6bb28/LICENSE)。 | 最值得研究；源码实有抓取逻辑，但未在本机登录 BOSS 做端到端验证。 |
| [HeyClioo/boss-zhipin-jd-scraper](https://github.com/HeyClioo/boss-zhipin-jd-scraper) | [c050316](https://github.com/HeyClioo/boss-zhipin-jd-scraper/commit/c0503160e2f9e86744555971d885d97606a85f12)，2026-07-14 | [SKILL.md](https://github.com/HeyClioo/boss-zhipin-jd-scraper/blob/c0503160e2f9e86744555971d885d97606a85f12/SKILL.md) 描述使用已登录浏览器滚动列表、逐页读取 JD、按职位 ID 去重并导出 Markdown；仓库树只有文档、技能文件、许可，没有独立可运行的爬虫包或测试；[MIT](https://github.com/HeyClioo/boss-zhipin-jd-scraper/blob/c0503160e2f9e86744555971d885d97606a85f12/LICENSE)。 | 适合借鉴操作思路；不能当作已经验证可安装的 Python 抓取库。 |
| [randolph555/boss-zhipin-scraper-tui](https://github.com/randolph555/boss-zhipin-scraper-tui) | [2afe8b1](https://github.com/randolph555/boss-zhipin-scraper-tui/commit/2afe8b10b08106c8b4988563d79b02348d314b0e)，2026-07-09 | 包含 CDP 抓取脚本和实时终端界面；[README.crawler.md](https://github.com/randolph555/boss-zhipin-scraper-tui/blob/2afe8b10b08106c8b4988563d79b02348d314b0e/README.crawler.md) 仍指向 eatmoreduck 原项目，且明确 Windows 未实测；[LICENSE](https://github.com/randolph555/boss-zhipin-scraper-tui/blob/2afe8b10b08106c8b4988563d79b02348d314b0e/LICENSE) 版权行为 eatmoreduck。 | 是在抓取脚本上增加 TUI 的派生路线；当前 Windows 环境优先评估原项目。 |
| [jhcoco/bosszp](https://github.com/jhcoco/bosszp) | [522250f](https://github.com/jhcoco/bosszp/commit/522250ff097909439bd72a58d2433bfc1a5bdab3)，2024-06-17 | [Scrapy spider](https://github.com/jhcoco/bosszp/blob/522250ff097909439bd72a58d2433bfc1a5bdab3/bosszp/spiders/boss.py) 使用旧列表页 XPath，只抽列表字段；源码中还有硬编码的旧会话 token，仓库树未见 LICENSE。 | 适合了解历史实现；不能直接复制或作为当前可用的完整 JD 方案。 |

## 对 Career Radar 的适配

本项目 [README.md](../README.md) 明确当前主链只访问**无需登录的公开 HTTP(S) 页面**，正式岗位以企业官方招聘页、官方公告等为依据；第三方招聘平台链接作为待核验线索。BOSS 直聘数据适合另设“第三方线索导入”入口，保留平台来源、原始链接、采集时间和核验状态，再与企业官网/官方公告交叉核验；不能直接写入“官方已确认岗位”。

若未来实施，优先研究 eatmoreduck 的列表字段映射、详情 JD 失败判定和断点保存。它的 [pyproject.toml](https://github.com/eatmoreduck/boss-zhipin-scraper/blob/16cc992bbf1d4e9efc7cfba4d39e819176a6bb28/pyproject.toml) 要求 Python >=3.10，主要运行依赖 requests 和 websocket-client；这与本项目 Python 版本相容，但接入还需要浏览器登录态、会话隔离、数据来源映射和独立回归。README 的 Windows 单元测试/基础 CLI 声明不等于在当前机器上成功抓取 BOSS。

本次通过 GitHub 仓库接口阅读了固定提交的源码、许可和相关测试；**没有安装或运行这些项目，也没有访问 BOSS 账户、发起真实抓取、验证当前平台页面/接口是否仍可用**。因此结论是“确有可研究项目”，不是“已验证今天能稳定抓取”。
