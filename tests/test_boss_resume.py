from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

from career_radar.boss_resume import extract_resume_facts


def test_reads_text_box_projects_and_returns_no_contact_details(tmp_path: Path) -> None:
    path = tmp_path / "resume.docx"
    description = (
        "独立开发 Python FastAPI 与 RAG 应用，完成数据库检索、接口测试和部署。"
        * 4
        + " 手机 13800138000；邮箱 sample@example.com；github.com/example/project"
    )
    paragraphs = [
        "个人信息 手机 13800138000 邮箱 sample@example.com",
        "JarvisOS 个人项目 FastAPI React LangGraph",
        description,
    ]
    body = "".join(f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>" for text in paragraphs)
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:txbxContent>{body}</w:txbxContent></w:body></w:document>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    facts = extract_resume_facts(path)
    assert {"Python", "FastAPI", "RAG", "React", "LangGraph"} <= set(facts.skills)
    assert len(facts.projects) == 1
    assert "13800138000" not in facts.projects[0]
    assert "sample@example.com" not in facts.projects[0]
    assert "github.com" not in facts.projects[0]
