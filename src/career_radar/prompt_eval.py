"""提示词回归评测：用固定样例验证 LLM 提取与页面分类。

参考 promptfoo 的思路，但直接复用当前配置的 LLM 供应商，无需额外依赖：
改提示词或换模型后运行 ``career-radar eval-prompts``，即可在合入前发现
“JD 提取变差、页面类型误判”等回归。样例不依赖候选人画像，结果稳定。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .discovery import PageDocument
from .llm import LLMProvider, PageAnalyzer, create_provider
from .models import Settings

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalCase:
    """一个离线评测样例：输入页面文本，断言应提取到的内容。"""

    name: str
    page_text: str
    expected_page_type: str | None = None
    expected_title: str | None = None
    expected_location: str | None = None
    expected_keywords: tuple[str, ...] = ()
    expect_no_jobs: bool = False


BUILTIN_CASES: tuple[EvalCase, ...] = (
    EvalCase(
        name="标准校招 JD 提取",
        expected_page_type="job_detail",
        expected_title="后端开发工程师",
        expected_location="福州",
        expected_keywords=("Python", "微服务", "2026 届"),
        page_text=(
            "职位名称：后端开发工程师\n"
            "工作地点：福州\n"
            "岗位职责：负责公司核心业务系统的设计与开发，参与微服务架构建设。\n"
            "任职资格：2026 届本科及以上学历，熟悉 Python 与 MySQL，有项目经验者优先。\n"
            "投递方式：请通过官网申请链接投递简历。"
        ),
    ),
    EvalCase(
        name="列表页多条岗位",
        expected_page_type="job_list",
        expected_title="前端开发工程师",
        expected_keywords=("React",),
        page_text=(
            "招聘岗位：\n"
            "1. 前端开发工程师 ｜ 厦门 ｜ 熟悉 React、TypeScript\n"
            "2. 测试开发工程师 ｜ 福州 ｜ 熟悉自动化测试\n"
            "3. 产品经理 ｜ 深圳 ｜ 负责需求分析"
        ),
    ),
    EvalCase(
        name="官网首页无招聘信息",
        expected_page_type="no_jobs",
        expect_no_jobs=True,
        page_text=(
            "欢迎访问示例科技有限公司官网。公司专注于人工智能与大数据产品，"
            "最新新闻请查看新闻中心，联系方式见页脚。"
        ),
    ),
)


@dataclass
class EvalResult:
    """单个样例的评测结论。"""

    case: EvalCase
    passed: bool
    failures: list[str]


@dataclass
class EvalReport:
    """整轮评测汇总。"""

    results: list[EvalResult]

    def all_passed(self) -> bool:
        return all(result.passed for result in self.results)

    def markdown(self) -> str:
        lines = [
            "# Career Radar 提示词评测报告",
            "",
            f"- 样例总数：{len(self.results)}",
            f"- 通过：{sum(result.passed for result in self.results)}",
            f"- 失败：{sum(not result.passed for result in self.results)}",
            "",
        ]
        for result in self.results:
            lines.append(f"## {result.case.name}")
            lines.append("")
            lines.append("✅ 通过" if result.passed else "❌ 失败")
            if result.failures:
                lines.append("")
                for failure in result.failures:
                    lines.append(f"- {failure}")
            lines.append("")
        return "\n".join(lines)


def _check_case(case: EvalCase, analysis) -> list[str]:
    """按样例断言检查分析结果，返回失败原因列表。"""

    failures: list[str] = []
    if case.expected_page_type and analysis.page_type != case.expected_page_type:
        failures.append(
            f"页面类型期望 {case.expected_page_type}，实际 {analysis.page_type}"
        )
    if case.expect_no_jobs and analysis.jobs:
        failures.append("应判定为无岗位，但提取到了岗位")
    if case.expected_title:
        titles = [job.title for job in analysis.jobs]
        if not any(
            case.expected_title.casefold() in title.casefold() for title in titles
        ):
            failures.append(
                f"未提取到标题包含 {case.expected_title!r} 的岗位，"
                f"实际标题：{titles[:5]}"
            )
    if case.expected_location:
        locations = [job.location or "" for job in analysis.jobs]
        if not any(
            case.expected_location.casefold() in location.casefold()
            for location in locations
        ):
            failures.append(
                f"未提取到地点包含 {case.expected_location!r} 的岗位，"
                f"实际地点：{locations[:5]}"
            )
    if case.expected_keywords:
        haystack = " ".join(
            f"{job.description or ''} {job.requirements or ''}"
            for job in analysis.jobs
        ).casefold()
        missing = [
            keyword
            for keyword in case.expected_keywords
            if keyword.casefold() not in haystack
        ]
        if missing:
            failures.append(f"JD 中缺少关键词：{missing}")
    return failures


def run_prompt_eval(
    settings: Settings,
    *,
    provider: LLMProvider | None = None,
    cases: list[EvalCase] | None = None,
    limit: int | None = None,
) -> EvalReport:
    """运行评测；未注入 provider 时使用配置中的真实 LLM 供应商。"""

    provider = provider or create_provider(settings.llm)
    analyzer = PageAnalyzer(settings.llm, provider, settings.candidate)
    selected = list(cases or BUILTIN_CASES)
    if limit is not None:
        selected = selected[:limit]
    results: list[EvalResult] = []
    for case in selected:
        document = PageDocument(title=case.name, text=case.page_text, links=[])
        try:
            analysis = analyzer.analyze_page(
                "评测样例",
                "https://eval.example/job",
                document,
                link_limit=0,
                monitor_mode="jobs",
            )
        except Exception as exc:
            LOGGER.exception("评测样例调用失败：%s", case.name)
            results.append(
                EvalResult(case=case, passed=False, failures=[f"LLM 调用失败：{exc}"])
            )
            continue
        failures = _check_case(case, analysis)
        results.append(EvalResult(case=case, passed=not failures, failures=failures))
    return EvalReport(results=results)
