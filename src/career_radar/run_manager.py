"""在 FastAPI 进程内串行执行真实监控任务，并把摘要持久化到 SQLite。"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .llm import create_provider
from .pipeline import MonitoringCancelled, MonitorService
from .web_repository import WebRepository, company_id

LOGGER = logging.getLogger(__name__)


def _steps(status: str, message: str, duration_ms: int | None = None) -> list[dict[str, Any]]:
    """现有核心没有逐步骤回调，因此如实显示一个真实执行步骤，其余标记为汇总。"""

    definitions = (
        ("robots", "robots 检查"),
        ("homepage", "公开页面抓取"),
        ("entry", "招聘入口与详情发现"),
        ("llm", "LLM 结构化提取"),
        ("dedup", "SQLite 去重与变化检测"),
        ("report", "日报生成"),
        ("email", "邮件通知"),
    )
    return [
        {
            "key": key,
            "label": label,
            "status": status,
            "durationMs": duration_ms if key == "dedup" else None,
            "message": message,
        }
        for key, label in definitions
    ]


class RunConflictError(RuntimeError):
    """当前已有真实扫描在运行。"""


class RunManager:
    """单进程单任务执行器，防止浏览器重复点击导致并发抓取和 SQLite 竞争。"""

    def __init__(self, repository: WebRepository) -> None:
        self.repository = repository
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="career-radar-run")
        self._lock = threading.Lock()
        self._active_run_id: str | None = None
        self._active_payload: dict[str, Any] | None = None
        self._cancel_event: threading.Event | None = None
        self._recover_orphaned_runs()

    def _recover_orphaned_runs(self) -> None:
        """API 进程重启后，旧进程遗留的 running 记录不能继续显示为正在运行。"""

        for payload in self.repository.list_runs():
            if payload.get("status") in {"pending", "running", "stopping"}:
                payload["status"] = "interrupted"
                payload["canStop"] = False
                payload["finishedAt"] = datetime.now(
                    ZoneInfo(self.repository.settings.app.timezone)
                ).isoformat(timespec="seconds")
                payload["logs"].append(
                    {
                        "time": payload["finishedAt"],
                        "level": "WARN",
                        "message": "API 服务重启，无法恢复旧进程中的扫描任务。",
                    }
                )
                self.repository.save_run(payload)

    def create(
        self,
        scope: str = "all",
        send_email: bool = False,
        selected_company_id: str | None = None,
        selected_company_type: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self._active_run_id is not None:
                raise RunConflictError(f"扫描任务 {self._active_run_id} 正在运行，请勿重复创建")

            settings = self.repository.settings
            selected_names = [company.name for company in settings.companies if company.enabled]
            if scope == "failed":
                latest = next(iter(self.repository.list_runs()), None)
                failed = {
                    company["companyName"]
                    for company in (latest or {}).get("companies", [])
                    if company.get("status") == "failed"
                }
                selected_names = [name for name in selected_names if name in failed]
            elif scope == "company":
                if not selected_company_id:
                    raise ValueError("单企业扫描必须提供 companyId")
                found = self.repository.find_company(selected_company_id)
                if found is None:
                    raise ValueError("指定企业不存在")
                _index, selected = found
                if not selected.enabled:
                    raise ValueError("指定企业已暂停，请先启用监控")
                selected_names = [selected.name]
            elif scope == "company_type":
                if not selected_company_type:
                    raise ValueError("按公司类型扫描必须提供 companyType")
                selected_names = [
                    company.name
                    for company in settings.companies
                    if company.enabled and company.company_type.value == selected_company_type
                ]
            if not selected_names:
                raise ValueError("没有符合本次扫描范围的启用公司")

            # 在写入运行记录和启动后台线程前验证本进程是否真正读取到 API Key。
            # 这样缺少 Key/SDK 时前端会立即得到明确错误，而不是生成一个随后全盘失败的任务。
            create_provider(settings.llm)

            now = datetime.now(ZoneInfo(settings.app.timezone))
            run_id = f"run-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
            payload: dict[str, Any] = {
                "id": run_id,
                "code": f"RUN-{now.strftime('%Y%m%d-%H%M%S')}",
                "trigger": "retry" if scope == "failed" else "manual",
                "status": "pending",
                "startedAt": now.isoformat(timespec="seconds"),
                "durationMs": 0,
                "totalCompanies": len(selected_names),
                "finishedCompanies": 0,
                "successCount": 0,
                "skippedCount": 0,
                "failedCount": 0,
                "newJobs": 0,
                "updatedJobs": 0,
                "emailStatus": "not_sent" if send_email else "disabled",
                "sendEmail": send_email,
                "canStop": True,
                "companies": [
                    {
                        "companyId": company_id(name),
                        "companyName": name,
                        "status": "waiting",
                        "steps": _steps("waiting", "等待任务执行"),
                        "newJobs": 0,
                        "updatedJobs": 0,
                        "jobsSeen": 0,
                        "pagesVisited": 0,
                        "successfulPages": 0,
                        "failedPages": 0,
                        "currentPage": None,
                    }
                    for name in selected_names
                ],
                "logs": [
                    {
                        "time": now.isoformat(timespec="seconds"),
                        "level": "INFO",
                        "message": f"已创建真实扫描任务，共 {len(selected_names)} 家公司。",
                    }
                ],
            }
            self.repository.save_run(payload)
            cancel_event = threading.Event()
            self._active_run_id = run_id
            self._active_payload = payload
            self._cancel_event = cancel_event
            self._executor.submit(
                self._execute,
                payload,
                set(selected_names),
                send_email,
                cancel_event,
            )
            return payload

    def _execute(
        self,
        payload: dict[str, Any],
        company_names: set[str],
        send_email: bool,
        cancel_event: threading.Event,
    ) -> None:
        started = time.perf_counter()
        timezone = ZoneInfo(self.repository.settings.app.timezone)
        with self._lock:
            if cancel_event.is_set():
                payload["status"] = "stopping"
                payload["canStop"] = False
            else:
                payload["status"] = "running"
                payload["canStop"] = True
            self.repository.save_run(payload)

        def now() -> str:
            return datetime.now(timezone).isoformat(timespec="seconds")

        def company_payload(name: str) -> dict[str, Any]:
            return next(
                item for item in payload["companies"] if item["companyName"] == name
            )

        def company_started(config: Any) -> None:
            item = company_payload(config.name)
            item.update(
                {
                    "status": "running",
                    "startedAt": now(),
                    "currentPage": config.url,
                    "steps": _steps("running", "正在检查并抓取当前公开页面"),
                }
            )
            payload["logs"].append(
                {
                    "time": item["startedAt"],
                    "level": "INFO",
                    "company": config.name,
                    "message": f"开始扫描：{config.url}",
                }
            )
            self.repository.save_run(payload)

        def page_progress(name: str, event: dict[str, Any]) -> None:
            item = company_payload(name)
            item["currentPage"] = event.get("currentPage") or event.get("requestedUrl")
            item["pagesVisited"] = int(event.get("pagesVisited") or 0)
            phase = event.get("phase")
            if phase == "started":
                item["steps"] = _steps(
                    "running",
                    f"正在扫描第 {item['pagesVisited'] + 1} 页：{item['currentPage']}",
                )
            else:
                if phase == "completed":
                    item["successfulPages"] = int(item.get("successfulPages") or 0) + 1
                    level = "INFO"
                    message = (
                        f"页面完成（{event.get('pageType') or '未知类型'}，"
                        f"发现 {event.get('jobsFound') or 0} 个岗位）：{item['currentPage']}"
                    )
                else:
                    item["failedPages"] = int(item.get("failedPages") or 0) + 1
                    level = "ERROR"
                    message = event.get("error") or f"页面扫描失败：{item['currentPage']}"
                self.repository.save_page_visit(payload["id"], name, event)
                payload["logs"].append(
                    {
                        "time": event.get("fetchedAt") or now(),
                        "level": level,
                        "company": name,
                        "message": message,
                    }
                )
            # 每一次页面状态变化都落盘，前端轮询读到的是当前真实 URL 与页面数。
            self.repository.save_run(payload)

        def company_completed(result: Any, events: list[Any]) -> None:
            item = company_payload(result.company)
            company_new = sum(event.event_type == "new" for event in events)
            company_updated = sum(event.event_type == "updated" for event in events)
            failed = bool(result.errors)
            item.update(
                {
                    "status": "failed" if failed else "success",
                    "finishedAt": now(),
                    "pagesVisited": result.pages_visited,
                    "jobsSeen": len(result.jobs),
                    "newJobs": company_new,
                    "updatedJobs": company_updated,
                    "steps": _steps(
                        "failed" if failed else "success",
                        result.errors[0]
                        if failed
                        else "页面抓取、LLM 提取和 SQLite 入库均已完成",
                    ),
                }
            )
            if failed:
                item["error"] = "\n".join(result.errors)
                payload["failedCount"] += 1
            else:
                payload["successCount"] += 1
            payload["finishedCompanies"] += 1
            payload["newJobs"] += company_new
            payload["updatedJobs"] += company_updated
            payload["logs"].append(
                {
                    "time": item["finishedAt"],
                    "level": "WARN" if failed else "INFO",
                    "company": result.company,
                    "message": (
                        f"公司扫描完成并已入库：成功页面 {item['successfulPages']}，"
                        f"失败页面 {item['failedPages']}，岗位 {len(result.jobs)}，"
                        f"新增 {company_new}，更新 {company_updated}。"
                    ),
                }
            )
            self.repository.save_run(payload)

        try:
            result = MonitorService(self.repository.settings).run(
                company_names=company_names,
                disable_email=not send_email,
                on_company_start=company_started,
                on_page_progress=page_progress,
                on_company_complete=company_completed,
                should_cancel=cancel_event.is_set,
            )
            finished = datetime.now(timezone)
            failed_count = sum(
                company["status"] == "failed" for company in payload["companies"]
            )
            with self._lock:
                if cancel_event.is_set():
                    raise MonitoringCancelled("用户请求停止扫描")
                payload.update(
                    {
                        "status": "partial" if failed_count else "completed",
                        "finishedAt": finished.isoformat(timespec="seconds"),
                        "durationMs": int((time.perf_counter() - started) * 1000),
                        "finishedCompanies": result.companies_processed,
                        "successCount": max(0, result.companies_processed - failed_count),
                        "failedCount": failed_count,
                        "newJobs": result.new_jobs,
                        "updatedJobs": result.updated_jobs,
                        "emailStatus": "sent" if result.email_sent else ("not_sent" if send_email else "disabled"),
                        "canStop": False,
                    }
                )
                payload["logs"].append(
                    {
                        "time": payload["finishedAt"],
                        "level": "WARN" if failed_count else "INFO",
                        "message": (
                            f"扫描完成：新增 {result.new_jobs}，更新 {result.updated_jobs}，"
                            f"错误 {len(result.errors)}。"
                        ),
                    }
                )
        except MonitoringCancelled:
            finished = datetime.now(timezone).isoformat(timespec="seconds")
            incomplete = [
                company
                for company in payload["companies"]
                if company["status"] in {"waiting", "running"}
            ]
            for company in incomplete:
                company.update(
                    {
                        "status": "skipped",
                        "skipReason": "user_stop",
                        "finishedAt": finished,
                        "currentPage": None,
                        "steps": _steps("skipped", "用户停止，本轮不再继续"),
                    }
                )
            payload.update(
                {
                    "status": "interrupted",
                    "finishedAt": finished,
                    "durationMs": int((time.perf_counter() - started) * 1000),
                    "finishedCompanies": payload["totalCompanies"],
                    "skippedCount": len(incomplete),
                    "emailStatus": "not_sent" if send_email else "disabled",
                    "canStop": False,
                }
            )
            payload["logs"].append(
                {
                    "time": finished,
                    "level": "WARN",
                    "message": "扫描已在安全点停止；已完成企业的入库结果已保留。",
                }
            )
        except Exception as exc:
            finished = datetime.now(timezone).isoformat(timespec="seconds")
            payload.update(
                {
                    "status": "failed",
                    "finishedAt": finished,
                    "durationMs": int((time.perf_counter() - started) * 1000),
                    "failedCount": len(company_names),
                    "canStop": False,
                }
            )
            payload["logs"].append(
                {
                    "time": finished,
                    "level": "ERROR",
                    "message": f"扫描任务失败：{type(exc).__name__}: {exc}",
                }
            )
            LOGGER.exception("Web 扫描任务失败：%s", payload["id"])
        finally:
            with self._lock:
                payload["canStop"] = False
                self.repository.save_run(payload)
                if self._active_run_id == payload["id"]:
                    self._active_run_id = None
                    self._active_payload = None
                    self._cancel_event = None

    def stop(self, run_id: str) -> None:
        """请求任务在当前 HTTP/LLM 调用返回后的最近安全点停止。"""

        with self._lock:
            if (
                run_id != self._active_run_id
                or self._active_payload is None
                or self._cancel_event is None
            ):
                raise ValueError("该任务当前没有运行")
            if self._cancel_event.is_set():
                return
            self._cancel_event.set()
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
            self._active_payload["status"] = "stopping"
            self._active_payload["canStop"] = False
            self._active_payload["logs"].append(
                {
                    "time": timestamp,
                    "level": "WARN",
                    "message": "已收到停止请求；当前 HTTP/LLM 调用返回后将在最近安全点停止。",
                }
            )
            self.repository.save_run(self._active_payload)
