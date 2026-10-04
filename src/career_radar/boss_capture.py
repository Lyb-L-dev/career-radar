"""Small, resume-aware BOSS capture using the existing local CDP scraper."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .application.llm import CompatibleApplicationGateway
from .application.models import ProfileVerificationStatus
from .application.profile import ApplicationProfileError, load_application_profile
from .boss_ai import PROMPT_VERSION, BossAIScreener, screening_context_hash
from .boss_resume import BossResumeError, extract_resume_facts
from .models import CandidateProfile, Settings
from .platform_leads import (
    BossExportError,
    BossLead,
    BossLeadRepository,
    BossPreferences,
    parse_boss_export,
    triage_boss_lead,
)

_ROLE = re.compile(
    r"fde|forward deployed|ai|agent|llm|人工智能|智能体|大模型|python|后端|数据开发|大数据开发|数据工程|应用开发|应用工程|数据分析|商业智能|bi开发|测试开发|自动化测试|全栈|机器学习|算法应用|软件开发|数字化研发|数据平台",
    re.I,
)
_OFF_TARGET = re.compile(r"销售|商务拓展|市场营销|运营专员|产品经理|视觉设计|平面设计|讲师|算法研究员|sales|marketing|product manager", re.I)
_ONE_TO_THREE_YEARS = re.compile(r"1\s*[-~—至]\s*3\s*年")
_TWO_PLUS_YEARS = re.compile(r"2\s*[-~—至]\s*3\s*年|[2-9]\s*年(?:以上|及以上)")
_JUNIOR_EXCEPTION = re.compile(r"接受应届|应届(?:生|毕业生)?可(?:投|申请)|经验不限|不限经验|无经验要求|可放宽工作经验")
_REQUIRES_WORK_YEARS = re.compile(r"(?:至少|要求|需|必须).{0,12}[2-9]\s*年.{0,8}工作经验|[2-9]\s*年以上工作经验")
_SMALL_COMPANY = re.compile(r"0-20|20-99|100-499")


class BossCaptureError(ValueError):
    """A capture prerequisite or safe stage failed."""


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    keyword: str = ""
    city: str = "全国"
    pages: int = 1
    max_details: int = 8


@dataclass(frozen=True, slots=True)
class SearchTarget:
    family: str
    keyword: str
    experience: str


def model_identity(settings: Settings) -> str:
    llm = settings.llm
    return f"{llm.provider}|{llm.base_url or ''}|{llm.model}|thinking={not llm.disable_thinking}"


def candidate_from_verified_resume(settings: Settings) -> CandidateProfile:
    """Use confirmed resume facts, never contact fields or unverified claims."""
    try:
        private = load_application_profile(settings.application.profile_path)
    except ApplicationProfileError as exc:
        raise BossCaptureError("请先在用户画像中确认私有简历，再按简历抓取 BOSS") from exc
    if private.verification_status is not ProfileVerificationStatus.CONFIRMED:
        raise BossCaptureError("私有简历尚未确认，无法按简历筛选 BOSS")
    projects = [
        f"{item.name}：{item.description[:260]}；技术：{', '.join(item.technologies[:8])}"
        for item in private.projects[:8]
    ]
    internships = [
        f"{item.role}：{item.organization}；{'; '.join(item.achievements[:2])}"
        for item in private.experiences[:5]
        if "实习" in item.role
    ]
    skills = [item.name for item in private.skills[:30]]
    resume_docx = settings.application.profile_path.parent / "boss_resume.docx"
    if resume_docx.is_file():
        try:
            facts = extract_resume_facts(resume_docx)
        except BossResumeError as exc:
            raise BossCaptureError("最新 BOSS 简历无法读取，请检查 private/boss_resume.docx") from exc
        skills = list(facts.skills)
        projects = list(facts.projects)
    candidate = settings.candidate.model_copy(
        update={
            "skills": skills,
            "projects": projects,
            "internships": internships,
            "has_work_experience": bool(private.experiences),
        }
    )
    return candidate.model_copy(
        update={"target_roles": [target.family for target in plan_resume_searches(candidate)]}
    )


def plan_resume_searches(candidate: CandidateProfile, extra_keyword: str = "") -> list[SearchTarget]:
    """Cover resume-supported junior technical tracks with one bounded search each."""
    skills = {skill.casefold() for skill in candidate.skills}
    targets: list[SearchTarget] = []
    if extra_keyword.strip():
        targets.append(SearchTarget("补充方向", extra_keyword.strip(), "101"))
    if skills & {"rag", "langgraph", "embedding", "pgvector"}:
        targets.append(SearchTarget("AI 应用开发", "AI应用开发", "102"))
    if "python" in skills and skills & {"fastapi", "flask"}:
        targets.append(SearchTarget("Python 后端", "Python开发", "101"))
    if skills & {"kafka", "spark streaming"} and "sql" in skills:
        targets.append(SearchTarget("数据开发", "数据开发", "102"))
    if "sql" in skills and skills & {"scikit-learn", "tensorflow"}:
        targets.append(SearchTarget("数据分析", "数据分析", "102"))
    if skills & {"pytest", "playwright"} and "python" in skills:
        targets.append(SearchTarget("测试开发", "测试开发", "101"))
    if skills & {"react", "next.js"} and skills & {"fastapi", "flask"}:
        targets.append(SearchTarget("全栈开发", "全栈开发", "103"))
    if skills & {"scikit-learn", "tensorflow"} and "python" in skills:
        targets.append(SearchTarget("机器学习应用", "机器学习工程师", "102"))
    if skills & {"rag", "langgraph"} and "python" in skills:
        targets.append(SearchTarget("FDE 与场景交付", "FDE", "101"))
    if not targets:
        raise BossCaptureError("简历中缺少可识别的目标技术方向，无法安全生成搜索计划")
    return targets


def _lead_from_raw(raw: dict[str, Any]) -> BossLead | None:
    enriched = dict(raw)
    enriched["tags_list"] = " | ".join(
        part for part in (str(raw.get("tags_list") or raw.get("tags") or ""), str(raw.get("job_labels") or "")) if part
    )
    try:
        return parse_boss_export(json.dumps([enriched], ensure_ascii=False))[0]
    except BossExportError:
        return None


def select_detail_candidates(
    listings: list[dict[str, Any]],
    candidate: CandidateProfile,
    preferences: BossPreferences,
    max_details: int,
    recently_reviewed: dict[str, dict[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Discard explicit mismatches before visiting any detail page."""
    now = datetime.now(UTC).isoformat()
    seen: set[str] = set()
    ranked: list[tuple[int, bool, str, dict[str, Any]]] = []
    counts = {"listed": 0, "duplicate": 0, "recently_reviewed": 0, "hard_rejected": 0, "off_target": 0, "unclear_company": 0}
    for raw in listings:
        counts["listed"] += 1
        link = str(raw.get("job_link") or "")
        if not link or link in seen:
            counts["duplicate"] += 1
            continue
        seen.add(link)
        lead = _lead_from_raw(raw)
        if lead is None:
            counts["hard_rejected"] += 1
            continue
        previous = (recently_reviewed or {}).get(_link_hash(lead.source_url))
        if previous and previous.get("listing_hash") == _listing_hash(lead):
            counts["recently_reviewed"] += 1
            continue
        triage = triage_boss_lead(lead, candidate, now, preferences)
        if triage["blockers"]:
            counts["hard_rejected"] += 1
            continue
        if candidate.has_work_experience is False and _TWO_PLUS_YEARS.search(lead.tags):
            counts["hard_rejected"] += 1
            continue
        if not lead.company_identified:
            counts["unclear_company"] += 1
            continue
        if _OFF_TARGET.search(lead.title) or (
            raw.get("_search_family") != "补充方向"
            and not _ROLE.search(f"{lead.title} {lead.skills}")
        ):
            counts["off_target"] += 1
            continue
        stretch = bool(_ONE_TO_THREE_YEARS.search(lead.tags))
        match_count = sum(
            1 for skill in candidate.skills if len(skill) >= 3 and skill.casefold() in f"{lead.title} {lead.skills}".casefold()
        )
        score = int(triage["score"]) + min(match_count * 4, 16)
        if _SMALL_COMPANY.search(str(raw.get("company_scale") or "")):
            score += 5
        if stretch:
            score -= 18
        ranked.append((score, stretch, str(raw.get("_search_family") or "手动搜索"), raw))
    ranked.sort(key=lambda item: item[0], reverse=True)
    families: dict[str, list[tuple[int, bool, str, dict[str, Any]]]] = {}
    for item in ranked:
        families.setdefault(item[2], []).append(item)
    selected: list[dict[str, Any]] = []
    stretch_limit = max(1, max_details // 4)
    stretch_count = 0
    while len(selected) < max_details and any(families.values()):
        for group in families.values():
            if len(selected) >= max_details:
                break
            while group:
                _, stretch, _, raw = group.pop(0)
                if stretch and stretch_count >= stretch_limit:
                    continue
                selected.append(raw)
                stretch_count += int(stretch)
                break
    counts["shortlisted"] = len(selected)
    return selected, counts


def _link_hash(link: str) -> str:
    return hashlib.sha256(link.encode("utf-8")).hexdigest()


def _listing_hash(lead: BossLead) -> str:
    fields = {name: getattr(lead, name) for name in ("title", "company", "location", "salary", "tags", "skills")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _history_context(candidate: CandidateProfile, model: str, preferences: BossPreferences) -> str:
    payload = {
        "candidate": candidate.model_dump(mode="json"),
        "model": model,
        "preferences": {"current_student": preferences.current_student, "accept_internship": preferences.accept_internship},
        "prompt_version": PROMPT_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _recent_history(path: Path, context: str) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("context") != context:
        return {}
    cutoff = datetime.now(UTC) - timedelta(days=7)
    result = {}
    stored = payload.get("reviewed")
    if not isinstance(stored, dict):
        return {}
    for digest, record in stored.items():
        if not isinstance(record, dict):
            continue
        try:
            timestamp = record.get("reviewed_at")
            fingerprint = record.get("listing_hash")
            if (
                re.fullmatch(r"[0-9a-f]{64}", digest)
                and re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                and cutoff <= datetime.fromisoformat(timestamp) <= datetime.now(UTC)
            ):
                result[digest] = {"reviewed_at": timestamp, "listing_hash": fingerprint}
        except (TypeError, ValueError):
            continue
    return result


def _save_history(path: Path, context: str, reviewed: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"context": context, "reviewed": reviewed}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _scraper_paths(config_dir: Path) -> tuple[Path, Path, Path]:
    root = Path(
        os.environ.get("CAREER_RADAR_BOSS_SCRAPER_DIR", str(config_dir.parent / "boss-zhipin-scraper"))
    ).expanduser().resolve()
    python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    script = root / "scripts" / "boss_cdp_raw.py"
    if not python.is_file() or not script.is_file():
        raise BossCaptureError("找不到已安装的 BOSS 抓取工具，请检查 boss-zhipin-scraper 目录")
    return root, python, script


def _run_scraper(command: list[str], root: Path, timeout: int) -> None:
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BossCaptureError("BOSS 抓取工具未完成；请检查专用 Edge 是否已登录并保持打开") from exc
    if result.returncode != 0 and not _cdp_ready():
        raise BossCaptureError("BOSS 专用 Edge 已关闭；请重新运行 --setup-edge --no-wait-login 后再抓取")
    if result.returncode != 0:
        raise BossCaptureError("BOSS 抓取失败；请先在专用 Edge 登录并完成可能出现的人工验证")


def _cdp_ready() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 9222), timeout=1):
            return True
    except OSError:
        return False


def run_profiled_capture(
    request: CaptureRequest,
    settings: Settings,
    leads: BossLeadRepository,
    config_dir: Path,
    progress: Callable[[str, dict[str, int]], None] | None = None,
    command_runner: Callable[[list[str], Path, int], None] = _run_scraper,
    gateway_factory: Callable[[], CompatibleApplicationGateway] | None = None,
) -> dict[str, int]:
    """Search -> list gate -> limited details -> MiMo -> persist accepted only."""
    if settings.llm.provider != "mimo":
        raise BossCaptureError("按简历抓取只使用小米 MiMo，请先在设置中选择 MiMo")
    candidate = candidate_from_verified_resume(settings)
    searches = plan_resume_searches(candidate, request.keyword)
    preferences = leads.get_preferences(candidate.accept_internship)
    if preferences.current_student is not False or preferences.accept_internship:
        raise BossCaptureError("请先将 BOSS 求职身份设为已毕业且不接受实习")
    root, python, script = _scraper_paths(config_dir)
    model = model_identity(settings)
    history_path = config_dir / "private" / "boss_capture_history.json"
    context = _history_context(candidate, model, preferences)
    reviewed = _recent_history(history_path, context)
    cutoff = datetime.now(UTC) - timedelta(days=7)
    for item in leads.list_leads(candidate, model):
        if not item["aiResult"] or not item["source_url"]:
            continue
        try:
            if datetime.fromisoformat(item["lastSeenAt"]) >= cutoff:
                stored = leads.get_ai_source(item["id"])
                if stored:
                    reviewed.setdefault(_link_hash(item["source_url"]), {
                        "reviewed_at": item["lastSeenAt"],
                        "listing_hash": _listing_hash(stored[0]),
                    })
        except (TypeError, ValueError):
            continue
    newly_reviewed: dict[str, str] = {}
    screen_config = settings.llm.model_copy(update={
        "max_output_tokens": min(settings.llm.max_output_tokens, 1800),
        "max_retries": min(settings.llm.max_retries, 2),
        "request_timeout_seconds": min(settings.llm.request_timeout_seconds, 45),
    })
    make_gateway = gateway_factory or (lambda: CompatibleApplicationGateway(screen_config))
    update = progress or (lambda _stage, _counts: None)
    counts = {"searches": len(searches), "listed": 0, "shortlisted": 0, "details": 0, "recently_reviewed": 0, "hard_rejected": 0, "off_target": 0, "unclear_company": 0, "ai_rejected": 0, "ai_failed": 0, "accepted": 0}
    temp_root = config_dir / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="boss-capture-", dir=temp_root) as directory:
        work = Path(directory)
        listings: list[dict[str, Any]] = []
        for index, target in enumerate(searches, 1):
            update(f"搜索 {index}/{len(searches)}：{target.family}", counts)
            output = work / f"list-{index}.json"
            command_runner([
                str(python), str(script), "--keyword", target.keyword, "--city", request.city,
                "--pages", str(request.pages), "--experience", target.experience,
                "--no-detail", "--output", str(output),
            ], root, 360)
            if output.is_file():
                payload = json.loads(output.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
                    listings.extend(
                        {**row, "_search_family": target.family}
                        for row in payload["jobs"] if isinstance(row, dict)
                    )
        shortlist, gate_counts = select_detail_candidates(
            listings, candidate, preferences, request.max_details, reviewed
        )
        counts.update(gate_counts)
        update("列表筛选完成", counts)
        if not shortlist:
            return counts
        filtered_file = work / "shortlist.json"
        filtered_file.write_text(json.dumps({"jobs": shortlist}, ensure_ascii=False), encoding="utf-8")
        details_file = work / "details.json"
        update("抓取候选岗位完整 JD", counts)
        command_runner([
            str(python), str(script), "--input", str(filtered_file), "--detail",
            "--max-details", str(request.max_details), "--detail-output", str(details_file),
        ], root, 1200)
        if not details_file.is_file():
            return counts
        details = json.loads(details_file.read_text(encoding="utf-8"))
        if not isinstance(details, list):
            raise BossCaptureError("BOSS 详情文件格式无效，未导入任何岗位")
        by_link = {str(row.get("job_link") or ""): row for row in shortlist}
        temp_leads = BossLeadRepository(work / "screening.db")
        temp_leads.initialize()
        temp_leads.set_preferences(preferences)
        screener = BossAIScreener(temp_leads, make_gateway)
        accepted: list[tuple[BossLead, dict[str, Any]]] = []
        for raw_detail in details:
            if not isinstance(raw_detail, dict):
                continue
            link = str(raw_detail.get("job_link") or "")
            original = by_link.get(link)
            if original is None:
                continue
            combined = {**original, **raw_detail}
            combined["job_labels"] = original.get("job_labels", "")
            lead = _lead_from_raw(combined)
            if lead is None or not lead.jd_complete:
                continue
            counts["details"] += 1
            triage = triage_boss_lead(lead, candidate, datetime.now(UTC).isoformat(), preferences)
            if triage["blockers"] or not lead.company_identified or len(lead.description) > 8_000:
                counts["hard_rejected"] += 1
                newly_reviewed[_link_hash(lead.source_url)] = _listing_hash(lead)
                continue
            if (
                (_ONE_TO_THREE_YEARS.search(lead.tags) or _REQUIRES_WORK_YEARS.search(lead.description))
                and not _JUNIOR_EXCEPTION.search(lead.description)
                and candidate.has_work_experience is False
            ):
                counts["hard_rejected"] += 1
                newly_reviewed[_link_hash(lead.source_url)] = _listing_hash(lead)
                continue
            update("小米 MiMo 核对报名条件", counts)
            temp_leads.import_leads([lead])
            try:
                result = screener.screen(lead.id, candidate, model)["result"]
            except (ValueError, RuntimeError):
                counts["ai_failed"] += 1
                continue
            newly_reviewed[_link_hash(lead.source_url)] = _listing_hash(lead)
            if (result["eligibility"] != "ineligible" and result["fit"] in {"strong", "reasonable"}
                    and result["action"] in {"prioritize", "consider"}):
                accepted.append((lead, result))
            else:
                counts["ai_rejected"] += 1
        if counts["ai_failed"] and not accepted:
            update("小米 MiMo 分析失败", counts)
            raise BossCaptureError("小米 MiMo 未能完成岗位判断；本批未导入，请检查模型密钥或额度")
        if leads.get_preferences(candidate.accept_internship) != preferences:
            raise BossCaptureError("抓取期间求职身份已变化，本批未导入；请重新运行")
        if accepted:
            leads.import_leads([lead for lead, _ in accepted])
            for lead, result in accepted:
                leads.save_ai_result(
                    lead.id, screening_context_hash(lead, candidate, model, preferences),
                    result, candidate, model, preferences,
                )
        counts["accepted"] = len(accepted)
        if newly_reviewed:
            now = datetime.now(UTC).isoformat()
            reviewed.update({
                digest: {"reviewed_at": now, "listing_hash": fingerprint}
                for digest, fingerprint in newly_reviewed.items()
            })
            try:
                _save_history(history_path, context, reviewed)
            except OSError:
                counts["history_saved"] = 0
        update("完成", counts)
        return counts


class BossCaptureManager:
    """One bounded manual capture at a time; status is local process state."""

    def __init__(self, leads: BossLeadRepository, settings_loader: Callable[[], Settings], config_dir: Path):
        self.leads = leads
        self.settings_loader = settings_loader
        self.config_dir = config_dir
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {"state": "idle", "stage": "", "counts": {}}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def plan(self, extra_keyword: str = "") -> dict[str, Any]:
        candidate = candidate_from_verified_resume(self.settings_loader())
        searches = plan_resume_searches(candidate, extra_keyword)
        return {
            "searches": [
                {"family": target.family, "keyword": target.keyword}
                for target in searches
            ],
            "resumeProjectCount": len(candidate.projects),
        }

    def open_browser(self) -> dict[str, bool]:
        if _cdp_ready():
            return {"ready": True}
        root, python, script = _scraper_paths(self.config_dir)
        _run_scraper([str(python), str(script), "--setup-edge", "--no-wait-login"], root, 60)
        if not _cdp_ready():
            raise BossCaptureError("专用 Edge 未能启动；请检查本机浏览器安装")
        return {"ready": True}

    def start(self, request: CaptureRequest) -> dict[str, Any]:
        settings = self.settings_loader()
        if settings.llm.provider != "mimo":
            raise BossCaptureError("按简历抓取只使用小米 MiMo，请先在设置中选择 MiMo")
        candidate_from_verified_resume(settings)
        _scraper_paths(self.config_dir)
        if not _cdp_ready():
            raise BossCaptureError("请先打开 BOSS 专用 Edge：在抓取工具目录运行 --setup-edge --no-wait-login")
        with self._lock:
            if self._status["state"] == "running":
                raise BossCaptureError("已有一批 BOSS 岗位正在抓取，请等待完成")
            self._status = {"state": "running", "stage": "准备搜索", "counts": {}}
        thread = threading.Thread(target=self._run, args=(request, settings), daemon=True, name="boss-profiled-capture")
        thread.start()
        return self.status()

    def _progress(self, stage: str, counts: dict[str, int]) -> None:
        with self._lock:
            self._status = {"state": "running", "stage": stage, "counts": dict(counts)}

    def _run(self, request: CaptureRequest, settings: Settings) -> None:
        try:
            counts = run_profiled_capture(request, settings, self.leads, self.config_dir, self._progress)
        except BossCaptureError as exc:
            with self._lock:
                self._status = {"state": "failed", "stage": str(exc), "counts": self._status["counts"]}
        except Exception:
            with self._lock:
                self._status = {"state": "failed", "stage": "抓取中断，未导入未经确认的岗位；请检查本地日志", "counts": self._status["counts"]}
        else:
            with self._lock:
                self._status = {"state": "complete", "stage": "完成", "counts": counts}
