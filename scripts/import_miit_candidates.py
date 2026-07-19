"""从工信部公开 PDF 生成企业候选库。

这个脚本只用于维护 ``data/company_candidates.json``，不会修改 ``config.yaml``，
也不会把上千家企业直接加入每日扫描。PDF 表格解析依赖 ``pdfplumber``，运行前可执行
``pip install pdfplumber``。生成的数据仍需人工补充企业官网、招聘入口和劳动风险背调。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceSpec:
    """一份官方名单的文件、标题和可核验来源。"""

    key: str
    filename: str
    title: str
    url: str
    expected_count: int


SOURCES = (
    SourceSpec(
        key="miit-key-little-giant-batch-1-year-3",
        filename="miit_first_batch_year3.pdf",
        title="建议继续支持的专精特新“小巨人”企业名单（第一批第三年）",
        url=(
            "https://www.miit.gov.cn/cms_files/filemanager/1226211233/attach/"
            "20244/bc918b07c4064658955a97246d069c8b.pdf"
        ),
        expected_count=409,
    ),
    SourceSpec(
        key="miit-key-little-giant-batch-2-year-3",
        filename="miit_second_batch_year3.pdf",
        title="建议继续支持的专精特新“小巨人”企业名单（第二批第三年）",
        url=(
            "https://www.miit.gov.cn/cms_files/filemanager/1226211233/attach/"
            "20243/e06b50962e81471cb6163f72d4694295.pdf"
        ),
        expected_count=381,
    ),
    SourceSpec(
        key="miit-key-little-giant-batch-3-year-2",
        filename="miit_third_batch_year2.pdf",
        title="建议继续支持的专精特新“小巨人”企业名单（第三批第二年）",
        url=(
            "https://www.miit.gov.cn/cms_files/filemanager/1226211233/attach/"
            "20243/5e6cfbab42ec4087a9a135426b0ec60b.pdf"
        ),
        expected_count=398,
    ),
)


PLANNED_CITIES = {
    "北京市": ("北京", "北京"),
    "天津市": ("天津", "天津"),
    "上海市": ("上海", "上海"),
    "重庆市": ("重庆", "重庆"),
    "大连市": ("辽宁", "大连"),
    "宁波市": ("浙江", "宁波"),
    "厦门市": ("福建", "厦门"),
    "青岛市": ("山东", "青岛"),
    "深圳市": ("广东", "深圳"),
}

TECH_SIGNAL_RULES = {
    "数据/软件": ("数据", "软件", "信息技术", "云计算", "数字科技", "数据库"),
    "人工智能": ("人工智能", "算法", "智能科技", "智慧科技", "机器视觉"),
    "半导体/电子": ("半导体", "集成电路", "芯片", "微电子", "光电", "电子"),
    "通信/物联网": ("通信", "通讯", "物联", "网络安全", "信息安全"),
    "机器人/自动化": ("机器人", "自动化", "智能装备", "智能制造"),
    "新能源": ("新能源", "储能", "光伏", "电力科技", "能源科技"),
}


def _compact(value: str | None) -> str:
    """清除 PDF 单元格换行和多余空白，但保留企业名称中的正常字符。"""

    return re.sub(r"\s+", "", value or "").strip()


def _normalize_region(raw: str) -> tuple[str, str | None]:
    """把省份/计划单列市转换成前端可筛选的省、市字段。"""

    if raw in PLANNED_CITIES:
        return PLANNED_CITIES[raw]
    if raw == "新疆生产建设兵团":
        return "新疆", None
    province = raw
    for suffix in ("壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "省", "市"):
        if province.endswith(suffix):
            province = province[: -len(suffix)]
            break
    return province, None


def _infer_industry(name: str) -> str:
    """仅根据企业名称做保守行业初筛；前端会明确标注需要人工复核。"""

    if any(word in name for word in ("软件", "信息技术", "数据库", "云计算")):
        return "enterprise_software"
    if any(word in name for word in ("数据", "人工智能", "算法", "数字科技")):
        return "ai_data"
    if any(word in name for word in ("通信", "通讯", "网络安全", "信息安全")):
        return "telecom"
    if any(word in name for word in ("物联", "传感", "智能家居")):
        return "iot"
    if any(word in name for word in ("金融科技", "支付", "证券软件")):
        return "fintech"
    if any(word in name for word in ("新能源", "储能", "光伏", "电力", "能源")):
        return "energy"
    if any(word in name for word in ("消费", "食品", "宠物", "日化")):
        return "consumer"
    return "manufacturing"


def _tech_signals(name: str) -> list[str]:
    return [label for label, words in TECH_SIGNAL_RULES.items() if any(word in name for word in words)]


def _candidate_id(source_key: str, name: str) -> str:
    digest = hashlib.sha256(f"{source_key}|{name}".encode()).hexdigest()[:16]
    return f"candidate-{digest}"


def _extract_source(pdf_dir: Path, source: SourceSpec) -> list[dict[str, Any]]:
    """抽取一份 PDF，并用连续序号与预期数量双重校验。"""

    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - 只在维护脚本缺依赖时触发
        raise RuntimeError("缺少 pdfplumber，请先执行 pip install pdfplumber") from exc

    path = pdf_dir / source.filename
    if not path.is_file():
        raise FileNotFoundError(f"找不到官方名单 PDF：{path}")

    records: list[dict[str, Any]] = []
    last_source_region = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                raise RuntimeError(f"{path.name} 第 {page.page_number} 页没有识别到表格")
            for row in tables[0]:
                if len(row) < 3:
                    continue
                sequence_text = _compact(row[0])
                if not sequence_text.isdigit():
                    continue
                sequence = int(sequence_text)
                # 官方表格偶尔用跨行合并单元格表示同一省份，pdfplumber 会把后续
                # 行解析成 None；此时沿用上一条非空地区，而不是丢弃企业。
                source_region = _compact(row[1]) or last_source_region
                name = _compact(row[2])
                if not source_region or not name:
                    raise RuntimeError(f"{path.name} 第 {sequence} 行存在空地区或空企业名")
                last_source_region = source_region
                province, city = _normalize_region(source_region)
                records.append(
                    {
                        "id": _candidate_id(source.key, name),
                        "name": name,
                        "sourceRegion": source_region,
                        "province": province,
                        "city": city,
                        "sourceKey": source.key,
                        "sourceTitle": source.title,
                        "evidenceUrl": source.url,
                        "sourceSequence": sequence,
                        "qualityEvidenceScore": 85,
                        "qualitySignals": ["工信部建议继续支持的重点专精特新“小巨人”企业"],
                        "techSignals": _tech_signals(name),
                        "suggestedIndustryCategory": _infer_industry(name),
                        "dueDiligenceStatus": "unverified",
                    }
                )

    sequences = [record["sourceSequence"] for record in records]
    expected_sequences = list(range(1, source.expected_count + 1))
    if sequences != expected_sequences:
        raise RuntimeError(
            f"{path.name} 序号不连续：抽取 {len(records)} 行，预期 {source.expected_count} 行"
        )
    return records


def build_catalog(pdf_dir: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for source in SOURCES:
        records.extend(_extract_source(pdf_dir, source))

    names: dict[str, str] = {}
    for record in records:
        normalized = re.sub(r"\s+", "", record["name"]).casefold()
        if normalized in names:
            raise RuntimeError(f"企业名称重复：{record['name']} 与 {names[normalized]}")
        names[normalized] = record["name"]

    records.sort(
        key=lambda item: (
            0 if item["province"] == "福建" else 1,
            0 if item["techSignals"] else 1,
            item["province"],
            item["sourceKey"],
            item["sourceSequence"],
        )
    )
    return {
        "schemaVersion": 1,
        "generatedAt": date.today().isoformat(),
        "total": len(records),
        "disclaimer": (
            "该名单仅证明企业进入工信部建议继续支持的重点专精特新“小巨人”名单，"
            "不等同于员工体验、双休、现金流、无劳动争议或当前正在招聘。启用监控前必须"
            "核验官方官网和招聘入口，投递前仍应检查劳动风险、岗位边界与实际工作制度。"
        ),
        "sources": [
            {
                "key": source.key,
                "title": source.title,
                "url": source.url,
                "count": source.expected_count,
            }
            for source in SOURCES
        ],
        "items": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="从工信部 PDF 生成 Career Radar 企业候选库")
    parser.add_argument("--pdf-dir", type=Path, default=Path("tmp/pdfs"))
    parser.add_argument("--output", type=Path, default=Path("data/company_candidates.json"))
    args = parser.parse_args()

    catalog = build_catalog(args.pdf_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已生成 {args.output}：{catalog['total']} 家候选企业")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
