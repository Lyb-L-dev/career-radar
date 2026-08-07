"""企业 CSV 导入的解析、校验和去重，不执行任何网络请求。"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .api_validations import safe_public_url
from .models import CompanyConfig

MAX_IMPORT_ROWS = 2000

_HEADER_ALIASES = {
    "name": {"name", "企业名称", "公司名称"},
    "website": {"website", "官网", "官网地址"},
    "careers_url": {
        "careers_url",
        "careersurl",
        "招聘入口",
        "招聘地址",
        "招聘网址",
    },
    "company_type": {"company_type", "companytype", "公司类型", "企业类型"},
    "industry_category": {
        "industry_category",
        "industrycategory",
        "行业",
        "行业分类",
    },
    "province": {"province", "省份", "省"},
    "city": {"city", "城市", "市"},
    "priority": {"priority", "优先级"},
    "monitor_mode": {"monitor_mode", "monitormode", "监控模式"},
    "enabled": {"enabled", "是否启用", "启用"},
}
_COMPANY_TYPES = {
    "央企": "central_soe",
    "地方国企": "local_soe",
    "民营": "private",
    "民企": "private",
    "外企": "foreign",
    "合资": "joint_venture",
    "其他": "other",
}
_INDUSTRIES = {
    "互联网": "internet",
    "游戏": "gaming",
    "宠物": "pet",
    "企业软件": "enterprise_software",
    "人工智能与数据": "ai_data",
    "物联网": "iot",
    "金融科技": "fintech",
    "通信": "telecom",
    "能源": "energy",
    "制造业": "manufacturing",
    "消费": "consumer",
    "其他": "other",
}
_PRIORITIES = {"高": "high", "中": "medium", "低": "low"}
_MONITOR_MODES = {
    "岗位": "jobs",
    "招聘通知": "notices",
    "通知": "notices",
    "两者": "both",
}
_TRUE_VALUES = {"1", "true", "yes", "y", "是", "启用"}
_FALSE_VALUES = {"0", "false", "no", "n", "否", "停用"}


@dataclass(frozen=True)
class CompanyImportResult:
    rows: list[dict[str, Any]]
    companies: list[dict[str, Any]]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total": len(self.rows),
            "valid": sum(row["status"] == "valid" for row in self.rows),
            "duplicate": sum(row["status"] == "duplicate" for row in self.rows),
            "invalid": sum(row["status"] == "invalid" for row in self.rows),
        }


def _header_map(fieldnames: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_name in fieldnames:
        normalized = raw_name.strip().lstrip("\ufeff").casefold()
        for target, aliases in _HEADER_ALIASES.items():
            if normalized in {alias.casefold() for alias in aliases}:
                result[target] = raw_name
                break
    return result


def _value(row: dict[str, str | None], headers: dict[str, str], field: str) -> str:
    raw = row.get(headers[field]) if field in headers else None
    return str(raw or "").strip()


def _enabled(value: str) -> bool:
    if not value:
        return True
    normalized = value.casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError("是否启用只能填写 true/false、1/0、是/否或启用/停用")


def parse_company_csv(
    csv_text: str,
    existing_names: set[str],
) -> CompanyImportResult:
    """解析企业 CSV；重复项可跳过，任何无效行会阻止整批提交。"""

    if not csv_text.strip():
        raise ValueError("CSV 文件为空")
    try:
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
        fieldnames = list(reader.fieldnames or [])
        headers = _header_map(fieldnames)
        if "name" not in headers:
            raise ValueError("CSV 缺少“企业名称”或 name 列")
        if "website" not in headers and "careers_url" not in headers:
            raise ValueError("CSV 至少需要“官网地址”或“招聘入口”列")
        source_rows = list(reader)
    except csv.Error as exc:
        raise ValueError(f"CSV 格式错误：{exc}") from exc
    if not source_rows:
        raise ValueError("CSV 没有数据行")
    if len(source_rows) > MAX_IMPORT_ROWS:
        raise ValueError(f"单次最多导入 {MAX_IMPORT_ROWS} 家企业")

    seen = {name.strip().casefold() for name in existing_names}
    preview_rows: list[dict[str, Any]] = []
    companies: list[dict[str, Any]] = []
    for row_number, source in enumerate(source_rows, start=2):
        errors: list[str] = []
        name = _value(source, headers, "name")
        website = _value(source, headers, "website")
        careers_url = _value(source, headers, "careers_url")
        normalized_name = name.casefold()
        target_url = careers_url or website
        if not name:
            errors.append("企业名称不能为空")
        elif len(name) > 200:
            errors.append("企业名称不能超过 200 个字符")
        if not errors and normalized_name in seen:
            preview_rows.append(
                {
                    "rowNumber": row_number,
                    "name": name,
                    "url": target_url,
                    "status": "duplicate",
                    "errors": [],
                }
            )
            continue
        if not target_url:
            errors.append("官网地址和招聘入口不能同时为空")

        company_type_raw = _value(source, headers, "company_type")
        industry_raw = _value(source, headers, "industry_category")
        priority_raw = _value(source, headers, "priority")
        monitor_raw = _value(source, headers, "monitor_mode")
        company_type = _COMPANY_TYPES.get(company_type_raw, company_type_raw or "private")
        industry = _INDUSTRIES.get(industry_raw, industry_raw or "other")
        priority = _PRIORITIES.get(priority_raw, priority_raw or "medium")
        monitor_mode = _MONITOR_MODES.get(monitor_raw, monitor_raw or "jobs")
        try:
            enabled = _enabled(_value(source, headers, "enabled"))
        except ValueError as exc:
            enabled = True
            errors.append(str(exc))

        company: dict[str, Any] | None = None
        if not errors:
            try:
                normalized_url = safe_public_url(target_url)
                if website:
                    safe_public_url(website)
                model = CompanyConfig(
                    name=name,
                    url=normalized_url,
                    company_type=company_type,
                    industry_category=industry,
                    province=_value(source, headers, "province") or None,
                    city=_value(source, headers, "city") or None,
                    priority=priority,
                    monitor_mode=monitor_mode,
                    enabled=enabled,
                    discover_from_homepage=False if careers_url else "auto",
                )
                company = model.model_dump(mode="json")
            except ValidationError as exc:
                errors.extend(
                    str(error["msg"])
                    for error in exc.errors(include_url=False)[:3]
                )
            except ValueError as exc:
                errors.append(str(exc).splitlines()[0])

        if errors:
            status = "invalid"
        else:
            status = "valid"
            seen.add(normalized_name)
            assert company is not None
            companies.append(company)
        preview_rows.append(
            {
                "rowNumber": row_number,
                "name": name or "未填写",
                "url": target_url,
                "status": status,
                "errors": errors,
            }
        )
    return CompanyImportResult(rows=preview_rows, companies=companies)
