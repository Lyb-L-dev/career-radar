"""验证 Career Radar 画像到 FormPilot 1.2.1 JSON 导入格式的语义映射。"""

from career_radar.application.formpilot_export import to_formpilot_resume
from career_radar.application.models import ApplicationProfile


def test_formpilot_export_maps_verified_facts_without_guessing_missing_answers() -> None:
    profile = ApplicationProfile.model_validate(
        {
            "verification_status": "confirmed",
            "contact": {
                "name": "测试候选人",
                "phone": "13811112222",
                "email": "candidate@example.com",
                "location": "福州",
                "github": "https://github.com/example",
            },
            "education": [
                {
                    "institution": "测试大学",
                    "degree": "本科",
                    "major": "计算机科学",
                    "start_date": "2022.09",
                    "end_date": "2026.06",
                    "source_ids": ["confirmed"],
                }
            ],
            "experiences": [
                {
                    "organization": "测试公司",
                    "role": "开发实习生",
                    "start_date": "2025-07",
                    "end_date": "至今",
                    "responsibilities": ["开发内部工具"],
                    "source_ids": ["confirmed"],
                }
            ],
            "projects": [
                {
                    "name": "检索项目",
                    "description": "构建向量检索服务",
                    "responsibilities": ["负责 API"],
                    "technologies": ["Python", "FastAPI"],
                    "source_ids": ["confirmed"],
                }
            ],
            "skills": [
                {"name": "Python", "level": "熟悉", "source_ids": ["confirmed"]},
                {"name": "FastAPI", "level": "熟悉", "source_ids": ["confirmed"]},
            ],
            "preferences": {
                "target_roles": ["AI 应用开发"],
                "accepted_work_types": ["校招", "实习"],
            },
            "sources": [
                {
                    "id": "confirmed",
                    "kind": "user_confirmed",
                    "path": "C:/private/source.docx",
                    "imported_at": "2026-09-28T00:00:00+08:00",
                }
            ],
            "review_notes": ["不对外展示的备注"],
        }
    )

    exported = to_formpilot_resume(profile)

    assert exported["basic"]["phone"] == "13811112222"
    assert exported["basic"]["socialLinks"] == {"github": "https://github.com/example"}
    assert exported["education"][0]["startDate"] == "2022-09"
    assert exported["education"][0]["endDate"] == "2026-06"
    assert exported["work"][0]["endDate"] == ""
    assert exported["projects"][0]["role"] == ""
    assert exported["skills"] == {
        "languages": ["Python"],
        "tools": ["FastAPI"],
        "certificates": [],
    }
    assert exported["jobPreference"]["positions"] == ["AI 应用开发"]
    assert exported["jobPreference"]["jobType"] == ""
    assert exported["jobPreference"]["salaryRange"] == ""
    assert "C:/private/source.docx" not in str(exported)
    assert "不对外展示的备注" not in str(exported)
