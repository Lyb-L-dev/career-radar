# 官网岗位填表复用核查（2026-09-28）

需求：Career Radar 评估官网岗位并由用户批准后，复用已确认的私有画像填写招聘系统表单；未知字段再由用户填写并记住。官网表单形态多样，用户必须核对并亲自提交。

## 采用判断

优先使用 [FormPilot](https://github.com/rockbenben/form-pilot/tree/69b6e6707f04684d3ebf2593f7eb9082725b210c) 作为**独立浏览器扩展**，Career Radar 只输出其兼容 JSON。核查的固定提交为 `69b6e6707f04684d3ebf2593f7eb9082725b210c`，仓库未归档，`package.json` 版本为 1.2.1，仓库 `LICENSE` 为 MIT。未复制上游源码。

| 证据 | 对当前项目的意义 |
|---|---|
| [导入实现](https://github.com/rockbenben/form-pilot/blob/69b6e6707f04684d3ebf2593f7eb9082725b210c/lib/storage/resume-store.ts)：`importResume` 合并缺失字段，并将字符串电话/邮箱转换为候选数组 | Career Radar 可以导出最小但语义完整的资料，不让用户重新录入联系方式 |
| [资料模型](https://github.com/rockbenben/form-pilot/blob/69b6e6707f04684d3ebf2593f7eb9082725b210c/lib/storage/types.ts)：基本信息、教育、工作、项目、技能和求职意向 | 与现有 `ApplicationProfile` 大部分事实可映射；缺失的生日、性别、期望薪资等留空 |
| [填表编排](https://github.com/rockbenben/form-pilot/blob/69b6e6707f04684d3ebf2593f7eb9082725b210c/lib/engine/orchestrator.ts)、[字段扫描](https://github.com/rockbenben/form-pilot/blob/69b6e6707f04684d3ebf2593f7eb9082725b210c/lib/engine/scanner.ts)、[Moka 适配](https://github.com/rockbenben/form-pilot/blob/69b6e6707f04684d3ebf2593f7eb9082725b210c/lib/engine/adapters/moka.ts) | 扩展有通用匹配、平台适配、低置信度提示；不能据此保证任意官网 100% 填对 |
| [敏感字段规则](https://github.com/rockbenben/form-pilot/blob/69b6e6707f04684d3ebf2593f7eb9082725b210c/lib/capture/sensitive.ts)、[中文使用说明](https://github.com/rockbenben/form-pilot/blob/69b6e6707f04684d3ebf2593f7eb9082725b210c/README.zh.md) | 默认跳过身份证、银行卡、验证码、密码；扩展本地保存，用户需主动点“记住本页”才能跨站复用手填答案 |
| [导入测试](https://github.com/rockbenben/form-pilot/blob/69b6e6707f04684d3ebf2593f7eb9082725b210c/tests/lib/storage/resume-store.test.ts) | 上游有电话/邮箱旧格式兼容测试；本次没有运行上游完整测试或在真实招聘站点验证 |

未采用整体嵌入。FormPilot 的 `chrome.storage.local` 与 Career Radar 的私有 YAML 是不同存储，直接把整个扩展并入 React 管理端会复制一套浏览器权限、DOM 适配和版本维护。当前桥接只需要一个明确的导入文件；重导入需在扩展清理旧版本，尚无双向同步。

本地验证：`tests/test_formpilot_export.py` 检查字段、日期及未知值不猜测；`tests/test_api.py` 检查只有 `ready` 任务能主动导出、跨站来源写请求被拒绝，列表和详情不泄露联系方式。测试均使用合成画像。它们证明桥接和授权边界，不证明 FormPilot 对任何具体官网表单的填充覆盖率。下一步应针对实际准备投递的官网系统，逐页人工验收选项、附件、重复字段和最终提交前状态。
