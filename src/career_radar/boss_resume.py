"""Read non-contact job-fit evidence from the user's private BOSS resume DOCX."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_SKILL_NAMES = (
    "Python", "SQL", "FastAPI", "Flask", "React", "Next.js", "MySQL",
    "PostgreSQL", "SQLite", "Redis", "Kafka", "Spark Streaming", "TensorFlow",
    "Scikit-learn", "RAG", "Embedding", "pgvector", "LangGraph", "Playwright",
    "Pytest", "Docker", "n8n", "Git", "Ollama", "Qwen",
)
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"(?:https?://|github\.com/)[^\s，。；;]+", re.I)


class BossResumeError(ValueError):
    """The local resume cannot be read safely for job-fit facts."""


@dataclass(frozen=True, slots=True)
class ResumeFacts:
    skills: tuple[str, ...]
    projects: tuple[str, ...]


def _clean(text: str) -> str:
    text = _PHONE.sub("", text)
    text = _EMAIL.sub("", text)
    return _URL.sub("", text).strip()


def extract_resume_facts(path: Path) -> ResumeFacts:
    """Read text including Word text boxes; never return names or contact fields."""
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise BossResumeError("BOSS 私有简历缺失或超过 5 MB")
    try:
        with ZipFile(path) as archive:
            entry = archive.getinfo("word/document.xml")
            if entry.file_size > 4_000_000:
                raise BossResumeError("BOSS 简历正文过大，无法安全读取")
            root = ElementTree.fromstring(archive.read(entry))
    except (OSError, BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise BossResumeError("BOSS 私有简历不是可读取的 DOCX") from exc
    paragraphs = [
        "".join(node.text or "" for node in paragraph.iter(_W + "t")).strip()
        for paragraph in root.iter(_W + "p")
    ]
    paragraphs = [text for text in paragraphs if text and len(text) < 1_000]
    corpus = "\n".join(paragraphs)
    skills = tuple(
        name for name in _SKILL_NAMES
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", corpus, re.I)
    )
    projects: list[str] = []
    for index, paragraph in enumerate(paragraphs):
        # Identify project headings from structure and technical evidence instead
        # of embedding a particular user's project names in the public source.
        if len(paragraph) > 160 or any(
            marker in paragraph for marker in ("个人信息", "教育", "学校", "姓名", "电话", "邮箱", "求职", "技能")
        ) or _PHONE.search(paragraph) or _EMAIL.search(paragraph):
            continue
        nearby = paragraphs[index + 1 : index + 4]
        following = next((text for text in nearby if len(text) >= 110), nearby[0] if nearby else "")
        heading_context = f"{paragraph} {nearby[0] if nearby else ''}".casefold()
        has_technology = any(name.casefold() in heading_context for name in skills)
        if not has_technology or not (
            ("项目" in paragraph and paragraph not in {"项目经历", "项目经验", "项目"})
            or len(following) >= 110
        ):
            continue
        technologies = nearby[0] if nearby and nearby[0] != following and "/" in nearby[0] else ""
        evidence = _clean(f"{paragraph[:140]}；技术：{technologies[:130]}；项目：{following[:300]}")
        if evidence and evidence not in projects:
            projects.append(evidence[:500])
    if not skills or not projects:
        raise BossResumeError("BOSS 简历缺少可识别的技能或项目证据，请核对文件内容")
    return ResumeFacts(skills=skills, projects=tuple(projects[:6]))
