# Third-Party Notices

Career Radar 的申请材料工作流参考了以下开源项目的工作流思想：

## AI Job Search

- 项目：`MadsLorentzen/ai-job-search`
- 地址：https://github.com/MadsLorentzen/ai-job-search
- 许可证：MIT License
- 使用范围：岗位评估、起草与独立审稿分离、事实核验、PDF/ATS 检查和不可信岗位正文边界的工作流设计。

Career Radar 使用 Python 和自身的数据模型重新实现这些能力，并针对中文校招与
DeepSeek 进行适配。原项目的 MIT 版权与许可声明如下：

```text
MIT License

Copyright (c) 2026 Mads Lorentzen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 运行时依赖

Career Radar 提供可选的 FormPilot JSON 导出桥接，供用户自行安装浏览器扩展。
没有打包或复制 FormPilot 的代码，也没有把它作为运行时依赖：

- [FormPilot](https://github.com/rockbenben/form-pilot)（MIT，Copyright (c) 2026 rockbenben）：参考其公开的 1.2.1 导入数据模型与工作流，Career Radar 使用自身 Python 模型完成字段转换。扩展在浏览器本地负责填表和答案记忆。

Career Radar 直接使用了以下开源库，其许可证声明由各项目保留：

- [trafilatura](https://github.com/adbar/trafilatura)（Apache-2.0）：用于优先
  提取正文并去除导航/页脚样板，失败时自动回退到内置 BeautifulSoup 清洗；
  同时复用 `extract_robots_sitemaps` 识别官方站点地图声明。
- [lxml](https://github.com/lxml/lxml)（BSD-3-Clause）：对已通过本机抓取安全边界的
  官方 XML 站点地图做有界解析，不复制第三方站点地图爬虫源码。
- [apprise](https://github.com/caronc/apprise)（BSD-3-Clause）：用于把岗位
  摘要推送到 Telegram、企业微信、钉钉、ntfy 等渠道。
- [litellm](https://github.com/BerriAI/litellm)（MIT，可选安装）：
  `pip install -e ".[llm-gateway]"` 后，通过 `provider: litellm` 统一接入
  各模型供应商。
# Frontend accessibility verification

`axe-core` 4.13.0 (Deque Systems and contributors) is used only as a development/test dependency, injected by the local browser verification scripts. It is licensed under Mozilla Public License 2.0. The original license is retained in `web/node_modules/axe-core/LICENSE`; upstream: https://github.com/dequelabs/axe-core/tree/v4.13.0. It is not imported into the production application bundle.
