"""Bounded background model work with persisted requests and explicit retry."""

import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from ..application.llm import CompatibleApplicationGateway
from ..public_errors import public_error_message
from .service import identifier


class GrowthManager:
    def __init__(self, service, coordinator, gateway_factory=CompatibleApplicationGateway):
        self.service = service
        self.coordinator = coordinator
        self.gateway_factory = gateway_factory
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="growth")
        self.lock = threading.Lock()
        self.closed = False
        for operation in service.repo.all("operations"):
            if operation["status"] in {"queued", "running"}:
                operation.update(status="failed", error="本地服务已重启，已保存输入，请重试继续。", updatedAt=service.timestamp())
                service.repo.save("operations", operation["id"], operation)

    def start(self, kind, payload, request_id):
        fingerprint = identifier(kind, payload)
        request_key = identifier(kind, request_id)
        with self.lock:
            if self.closed:
                raise ValueError("服务正在关闭，请稍后重试")
            previous = next((o for o in self.service.repo.all("operations") if o["requestKey"] == request_key), None)
            if previous:
                if previous["inputHash"] != fingerprint:
                    raise ValueError("同一请求编号不能提交不同内容")
                return self.service.public_operation(previous)
            if kind == "answer":
                self.service.prepare_answer(payload)
            if kind == "session":
                payload = {**payload, "sessionId": uuid4().hex}
            if kind == "project":
                payload = {**payload, "sessionId": uuid4().hex, "evidenceId": uuid4().hex}
            operation = {"id": uuid4().hex, "kind": kind, "requestKey": request_key, "inputHash": fingerprint, "payload": payload, "status": "queued", "error": None, "result": None, "createdAt": self.service.timestamp(), "updatedAt": self.service.timestamp()}
            self.service.repo.save("operations", operation["id"], operation)
            self.executor.submit(self._run, operation["id"])
        return self.service.public_operation(operation)

    def retry(self, operation_id):
        with self.lock:
            if self.closed:
                raise ValueError("服务正在关闭")
            operation = self.service.require("operations", operation_id)
            if operation["status"] != "failed":
                return self.service.public_operation(operation)
            operation.update(status="queued", error=None, updatedAt=self.service.timestamp())
            self.service.repo.save("operations", operation_id, operation)
            self.executor.submit(self._run, operation_id)
        return self.service.public_operation(operation)

    def _run(self, operation_id):
        operation = self.service.require("operations", operation_id)
        try:
            with self.coordinator.acquire("growth", operation_id, {"llm"}):
                operation.update(status="running", updatedAt=self.service.timestamp())
                self.service.repo.save("operations", operation_id, operation)
                # Capture a single configuration for all calls in this operation.
                config = self.service.web.settings.llm.model_copy(deep=True)
                gateway = self.gateway_factory(config)
                handlers = {"analyze": self.service.analyze, "session": self.service.create_session, "hint": self.service.hint, "answer": self.service.answer, "project": self.service.project}
                # A restart after result commit must not repeat the scoring.
                payload = operation["payload"]
                committed = self.service.repo.get("sessions", payload.get("sessionId", ""))
                result = None
                if operation["kind"] in {"session", "project"} and committed and committed["status"] != "generating":
                    result = {"sessionId": committed["id"]}
                if operation["kind"] == "answer":
                    evidence_id = identifier(payload["sessionId"], payload["questionId"])
                    if self.service.repo.get("evidence", evidence_id):
                        result = {"sessionId": payload["sessionId"], "evidenceId": evidence_id}
                result = result or handlers[operation["kind"]]({**payload, "modelIdentity": {"provider": config.provider, "model": config.model}}, gateway)
                operation.update(status="completed", result=result, error=None)
        except Exception as exc:
            operation.update(status="failed", error=public_error_message(exc, context="成长任务"))
        finally:
            operation["updatedAt"] = self.service.timestamp()
            self.service.repo.save("operations", operation_id, operation)

    def shutdown(self):
        with self.lock:
            self.closed = True
        self.executor.shutdown(wait=True)
