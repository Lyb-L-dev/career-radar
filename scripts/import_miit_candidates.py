"""从多份政府公开名单生成优质企业候选库。

这个脚本只用于维护 ``data/company_candidates.json``，不会修改 ``config.yaml``，
也不会把数千家企业直接加入每日扫描。来源覆盖重点“小巨人”、国家企业技术中心、
央企以及福建数字经济创新企业；名单只能证明规模/创新资质，不能替代劳动制度背调。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
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

NDRC_TECH_CENTER_SOURCE = SourceSpec(
    key="ndrc-national-enterprise-technology-centers-2023",
    filename="ndrc_all_technology_centers_2023.pdf",
    title="国家企业技术中心名单（全部）",
    url="https://zfxxgk.ndrc.gov.cn/web/iteminfo.jsp?id=20182",
    expected_count=1714,
)

SASAC_CENTRAL_SOURCE = SourceSpec(
    key="sasac-central-enterprises-2026",
    filename="central_enterprises_data.js",
    title="国家政务服务平台央企名录",
    url="https://gjzwfw.www.gov.cn/col/col1560/index.html",
    expected_count=99,
)

FUJIAN_DIGITAL_SOURCE = SourceSpec(
    key="fujian-digital-innovation-enterprises-2025",
    filename="fujian_digital_innovation_2025.html",
    title="2025年度福建省数字经济核心产业创新企业名单",
    url="https://fgw.fujian.gov.cn/zwgk/gsgg/202508/t20250801_6985427.htm",
    expected_count=350,
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

    if any(word in name for word in ("游戏", "互动娱乐", "数字娱乐")):
        return "gaming"
    if any(word in name for word in ("宠物", "动物保健", "兽药")):
        return "pet"
    if any(word in name for word in ("互联网", "网络科技", "电子商务", "电商")):
        return "internet"
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
    if any(word in name for word in ("消费", "食品", "饮料", "日化", "服饰")):
        return "consumer"
    return "manufacturing"


def _tech_signals(name: str) -> list[str]:
    return [label for label, words in TECH_SIGNAL_RULES.items() if any(word in name for word in words)]


def _candidate_id(source_key: str, name: str) -> str:
    digest = hashlib.sha256(f"{source_key}|{name}".encode()).hexdigest()[:16]
    return f"candidate-{digest}"


def _name_key(name: str) -> str:
    """统一全半角括号和空白，但不删除可能区分法人的名称字符。"""

    normalized = unicodedata.normalize("NFKC", name).rstrip("*＊")
    return re.sub(r"\s+", "", normalized).casefold()


def _source_metadata(source: SourceSpec) -> dict[str, Any]:
    return {
        "key": source.key,
        "title": source.title,
        "url": source.url,
        "count": source.expected_count,
    }


def _new_record(
    *,
    source: SourceSpec,
    sequence: int,
    name: str,
    source_region: str,
    province: str,
    city: str | None,
    score: int,
    quality_signal: str,
    scale_level: str,
    scale_evidence: str,
    company_type: str = "other",
    official_website: str | None = None,
) -> dict[str, Any]:
    """生成统一候选结构，所有推断字段都保留证据说明。"""

    return {
        "id": _candidate_id(source.key, name),
        "name": name,
        "sourceRegion": source_region,
        "province": province,
        "city": city,
        "sourceKey": source.key,
        "sourceTitle": source.title,
        "evidenceUrl": source.url,
        "sourceSequence": sequence,
        "sourceKeys": [source.key],
        "sourceTitles": [source.title],
        "evidenceUrls": [source.url],
        "qualityEvidenceScore": score,
        "qualitySignals": [quality_signal],
        "scaleLevel": scale_level,
        "scaleEvidence": [scale_evidence],
        "techSignals": _tech_signals(name),
        "suggestedIndustryCategory": _infer_industry(name),
        "suggestedCompanyType": company_type,
        "officialWebsite": official_website,
        "dueDiligenceStatus": "unverified",
    }


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
                    _new_record(
                        source=source,
                        sequence=sequence,
                        name=name,
                        source_region=source_region,
                        province=province,
                        city=city,
                        score=85,
                        quality_signal="工信部建议继续支持的重点专精特新“小巨人”企业",
                        scale_level="medium",
                        scale_evidence="国家级重点专精特新中小企业，具备细分领域竞争力",
                    )
                )

    sequences = [record["sourceSequence"] for record in records]
    expected_sequences = list(range(1, source.expected_count + 1))
    if sequences != expected_sequences:
        raise RuntimeError(
            f"{path.name} 序号不连续：抽取 {len(records)} 行，预期 {source.expected_count} 行"
        )
    return records


def _extract_ndrc_technology_centers(source_dir: Path) -> list[dict[str, Any]]:
    """抽取发改委 1714 家国家企业技术中心所在企业。"""

    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - 只在维护脚本缺依赖时触发
        raise RuntimeError("缺少 pdfplumber，请先执行 pip install -e .") from exc

    source = NDRC_TECH_CENTER_SOURCE
    path = source_dir / source.filename
    if not path.is_file():
        raise FileNotFoundError(f"找不到国家企业技术中心 PDF：{path}")
    records: list[dict[str, Any]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                raise RuntimeError(f"{path.name} 第 {page.page_number} 页没有识别到表格")
            for table in tables:
                for row in table:
                    if len(row) < 4 or not _compact(row[0]).isdigit():
                        continue
                    sequence = int(_compact(row[0]))
                    name = _compact(row[1]).rstrip("*＊")
                    source_region = _compact(row[3])
                    province, city = _normalize_region(source_region)
                    records.append(
                        _new_record(
                            source=source,
                            sequence=sequence,
                            name=name,
                            source_region=source_region,
                            province=province,
                            city=city,
                            score=90,
                            quality_signal="国家发展改革委等部门认定的国家企业技术中心所在企业",
                            scale_level="medium_or_above",
                            scale_evidence="拥有国家级企业技术中心，具备较强研发投入与创新组织能力",
                        )
                    )
    sequences = [record["sourceSequence"] for record in records]
    if sequences != list(range(1, source.expected_count + 1)):
        raise RuntimeError(
            f"{path.name} 序号不连续：抽取 {len(records)} 行，预期 {source.expected_count} 行"
        )
    return records


def _extract_central_enterprises(source_dir: Path) -> list[dict[str, Any]]:
    """读取国家政务服务平台公开的央企名称与官网地址。"""

    source = SASAC_CENTRAL_SOURCE
    path = source_dir / source.filename
    if not path.is_file():
        raise FileNotFoundError(f"找不到央企名录数据文件：{path}")
    text = path.read_text(encoding="utf-8")
    try:
        rows = json.loads(text[text.index("[") : text.rindex("]") + 1])
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"央企名录数据结构异常：{path}") from exc
    records = [
        _new_record(
            source=source,
            sequence=int(row["num"]),
            name=str(row["name"]).strip(),
            source_region="全国",
            province="全国",
            city=None,
            score=95,
            quality_signal="国务院国资委监管中央企业",
            scale_level="large",
            scale_evidence="国家政务服务平台央企名录，集团层面规模企业",
            company_type="central_soe",
            official_website=str(row.get("link") or "").strip() or None,
        )
        for row in rows
    ]
    sequences = [record["sourceSequence"] for record in records]
    if sequences != list(range(1, source.expected_count + 1)):
        raise RuntimeError(
            f"{path.name} 序号不连续：抽取 {len(records)} 行，预期 {source.expected_count} 行"
        )
    return records


class _FirstHtmlTableParser(HTMLParser):
    """只读取首个 HTML 表格，避免维护脚本额外依赖浏览器或 pandas。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.finished = False
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag == "table" and not self.finished:
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in {"th", "td"}:
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self.in_table and tag in {"th", "td"} and self.current_cell is not None:
            if self.current_row is not None:
                self.current_row.append("".join(self.current_cell).strip())
            self.current_cell = None
        elif self.in_table and tag == "tr" and self.current_row is not None:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = None
        elif self.in_table and tag == "table":
            self.in_table = False
            self.finished = True


def _extract_fujian_digital_enterprises(source_dir: Path) -> list[dict[str, Any]]:
    """抽取福建数字经济独角兽、未来独角兽和瞪羚企业。"""

    source = FUJIAN_DIGITAL_SOURCE
    path = source_dir / source.filename
    if not path.is_file():
        raise FileNotFoundError(f"找不到福建数字经济企业名单 HTML：{path}")
    parser = _FirstHtmlTableParser()
    parser.feed(path.read_text(encoding="utf-8"))
    if not parser.rows:
        raise RuntimeError(f"{path.name} 未找到企业名单表格")
    score_by_type = {"独角兽企业": 92, "未来独角兽企业": 84, "瞪羚企业": 80}
    scale_by_type = {
        "独角兽企业": "medium_or_above",
        "未来独角兽企业": "growth_stage",
        "瞪羚企业": "growth_stage",
    }
    records: list[dict[str, Any]] = []
    for cells in parser.rows:
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        sequence = int(cells[0])
        name = _compact(cells[1])
        city = cells[2].removesuffix("市")
        enterprise_type = cells[3]
        if enterprise_type not in score_by_type:
            raise RuntimeError(f"未知福建数字企业类型：{enterprise_type}")
        records.append(
            _new_record(
                source=source,
                sequence=sequence,
                name=name,
                source_region=cells[2],
                province="福建",
                city=city,
                score=score_by_type[enterprise_type],
                quality_signal=f"福建省数字经济核心产业{enterprise_type}",
                scale_level=scale_by_type[enterprise_type],
                scale_evidence=f"经福建省核验审查认定为{enterprise_type}，具备成长或估值门槛",
            )
        )
    sequences = [record["sourceSequence"] for record in records]
    if sequences != list(range(1, source.expected_count + 1)):
        raise RuntimeError(
            f"{path.name} 序号不连续：抽取 {len(records)} 行，预期 {source.expected_count} 行"
        )
    return records


_SCALE_RANK = {"unknown": 0, "growth_stage": 1, "medium": 2, "medium_or_above": 3, "large": 4}


def _merge_duplicate(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    """同一法人命中多份名单时合并证据，同时保留原候选 ID 和审批状态关联。"""

    for target, source in (
        ("sourceKeys", "sourceKey"),
        ("sourceTitles", "sourceTitle"),
        ("evidenceUrls", "evidenceUrl"),
    ):
        if incoming[source] not in existing[target]:
            existing[target].append(incoming[source])
    for field in ("qualitySignals", "scaleEvidence", "techSignals"):
        existing[field] = list(dict.fromkeys([*existing[field], *incoming[field]]))
    evidence_bonus = min(6, (len(existing["sourceKeys"]) - 1) * 3)
    existing["qualityEvidenceScore"] = min(
        100,
        max(existing["qualityEvidenceScore"], incoming["qualityEvidenceScore"]) + evidence_bonus,
    )
    if _SCALE_RANK[incoming["scaleLevel"]] > _SCALE_RANK[existing["scaleLevel"]]:
        existing["scaleLevel"] = incoming["scaleLevel"]
    if incoming.get("suggestedCompanyType") == "central_soe":
        existing["suggestedCompanyType"] = "central_soe"
    if not existing.get("officialWebsite") and incoming.get("officialWebsite"):
        existing["officialWebsite"] = incoming["officialWebsite"]
    if existing["province"] != "福建" and incoming["province"] == "福建":
        existing["province"] = "福建"
        existing["city"] = incoming.get("city")
        existing["sourceRegion"] = incoming["sourceRegion"]


def build_catalog(pdf_dir: Path, source_dir: Path | None = None) -> dict[str, Any]:
    source_dir = source_dir or pdf_dir.parent / "catalog_sources"
    records: list[dict[str, Any]] = []
    for source in SOURCES:
        records.extend(_extract_source(pdf_dir, source))
    records.extend(_extract_ndrc_technology_centers(source_dir))
    records.extend(_extract_central_enterprises(source_dir))
    records.extend(_extract_fujian_digital_enterprises(source_dir))

    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        key = _name_key(record["name"])
        if key in merged:
            _merge_duplicate(merged[key], record)
        else:
            merged[key] = record
    records = list(merged.values())

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
            "候选企业来自政府公开的重点“小巨人”、国家企业技术中心、央企和福建数字经济"
            "创新企业名单，只能作为规模、创新或成长性证据，不等同于员工体验、双休、现金流"
            "健康、无劳动争议或当前正在招聘。启用监控前仍应核验官网，投递前必须检查劳动风险、"
            "岗位边界与实际工作制度。"
        ),
        "sources": [
            *[_source_metadata(source) for source in SOURCES],
            _source_metadata(NDRC_TECH_CENTER_SOURCE),
            _source_metadata(SASAC_CENTRAL_SOURCE),
            _source_metadata(FUJIAN_DIGITAL_SOURCE),
        ],
        "items": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="从多份政府公开名单生成 Career Radar 企业候选库")
    parser.add_argument("--pdf-dir", type=Path, default=Path("tmp/pdfs"))
    parser.add_argument("--source-dir", type=Path, default=Path("tmp/catalog_sources"))
    parser.add_argument("--output", type=Path, default=Path("data/company_candidates.json"))
    args = parser.parse_args()

    catalog = build_catalog(args.pdf_dir, args.source_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已生成 {args.output}：{catalog['total']} 家候选企业")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
