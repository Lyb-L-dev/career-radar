"""生成匿名申请文档并执行结构校验；不会读取真实 config、数据库或私有画像。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from career_radar.application.document_renderer import ApplicationDocumentRenderer
from career_radar.application.document_verifier import ApplicationDocumentVerifier
from career_radar.application.models import (
    ApplicationConfig,
    ApplicationDraftBundle,
    ApplicationProfile,
    ApplicationRun,
    ApplicationStatus,
)
from career_radar.models import JobPosting


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile = ApplicationProfile.model_validate(
        {
            "verification_status": "confirmed",
            "contact": {
                "name": "张同学",
                "phone": "13800000000",
                "email": "candidate@example.com",
                "location": "福建福州",
                "github": "https://github.com/example",
            },
            "education": [],
            "experiences": [],
            "projects": [],
            "skills": [],
            "awards": [],
            "leadership": [],
            "sources": [
                {
                    "id": "resume",
                    "kind": "user_confirmed",
                    "imported_at": "2026-07-22T08:00:00+08:00",
                    "visually_verified": True,
                }
            ],
        }
    )
    drafts = ApplicationDraftBundle.model_validate(
        {
            "resume": {
                "headline": "2026届数据开发与数据分析候选人",
                "professional_summary": "具备数据采集、清洗、分析和可视化项目经验，能够使用 Python 与 SQL 完成端到端数据处理。",
                "skills": [
                    {"text": "Python：数据清洗、接口调用与自动化脚本", "source_ids": ["resume"]},
                    {"text": "MySQL：查询、聚合与基础数据库设计", "source_ids": ["resume"]},
                    {"text": "FastAPI：后端接口与数据服务开发", "source_ids": ["resume"]},
                ],
                "education": [
                    {
                        "institution": "示例学院",
                        "degree": "本科",
                        "major": "数据科学与大数据技术",
                        "period": "2022.09-2026.06",
                        "highlights": ["主修数据库、数据结构、机器学习与大数据处理课程"],
                        "source_ids": ["resume"],
                    }
                ],
                "experiences": [],
                "projects": [
                    {
                        "name": "企业招聘信息监控系统",
                        "period": "2026.03-2026.07",
                        "summary": "面向校招岗位的官网信息抓取、结构化提取和变化检测工具。",
                        "bullets": [
                            "使用 Python、BeautifulSoup 与 Playwright 采集公开招聘页面，并遵守 robots.txt 和请求间隔。",
                            "通过 FastAPI、SQLite 和结构化大模型输出完成岗位入库、匹配评分与运行进度展示。",
                            "设计公司、岗位和 JD 哈希去重规则，支持异常隔离和断点恢复。",
                        ],
                        "technologies": ["Python", "FastAPI", "SQLite", "Playwright"],
                        "source_ids": ["resume"],
                    },
                    {
                        "name": "电商数据分析平台",
                        "period": "2025.09-2025.12",
                        "summary": "完成公开销售数据的清洗、指标计算和可视化分析。",
                        "bullets": [
                            "使用 Pandas 处理缺失值和重复记录，构建销售、品类与地区指标。",
                            "编写 SQL 完成多维聚合，并使用可视化图表展示趋势与异常。",
                        ],
                        "technologies": ["Python", "Pandas", "MySQL"],
                        "source_ids": ["resume"],
                    },
                ],
                "awards": [
                    {"text": "校级数据分析竞赛二等奖", "source_ids": ["resume"]},
                    {"text": "学习优秀奖学金", "source_ids": ["resume"]},
                ],
                "leadership": [
                    {"text": "班级学习委员：协助课程通知与学习资料整理", "source_ids": ["resume"]}
                ],
            },
            "cover_letter": {
                "subject": "应聘数据开发工程师",
                "salutation": "招聘团队您好：",
                "paragraphs": [
                    "我希望申请贵公司的数据开发工程师岗位，并将数据处理与工程实践能力用于真实业务场景。",
                    "在企业招聘信息监控系统项目中，我完成了公开页面采集、结构化数据入库和接口开发，这些经历与岗位的数据处理职责直接相关。",
                    "我目前仍处于职业起步阶段，会诚实面对经验差距，并通过明确的学习计划和可验证项目成果持续提升。",
                ],
                "closing": "感谢您审阅我的申请，期待进一步交流。",
                "requirement_bridges": ["用真实项目回应 Python、SQL 和接口开发要求"],
                "source_ids": ["resume"],
            },
        }
    )
    job = JobPosting(
        company="示例科技有限公司",
        title="数据开发工程师",
        description="负责数据处理与服务开发。",
    )
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    run = ApplicationRun(
        id="app-20260722000000-smoke123",
        job_id="smoke-job",
        job_content_hash="1" * 64,
        profile_hash="2" * 64,
        status=ApplicationStatus.RENDERING,
        created_at=now,
        updated_at=now,
    )
    config = ApplicationConfig(output_dir=args.output.resolve(), pdf_mode="never")
    renderer = ApplicationDocumentRenderer(config)
    rendered = renderer.render(run, job, profile, drafts, "2026年07月22日")
    report = ApplicationDocumentVerifier(config).verify(
        run, job, profile, drafts, rendered, now
    )
    print(
        json.dumps(
            {
                "resume": str(rendered.resume_docx),
                "coverLetter": str(rendered.cover_letter_docx),
                "verification": report.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
