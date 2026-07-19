"""从 HTML 提取干净正文、候选链接，并对招聘相关链接进行启发式排序。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .models import LinkCandidate
from .url_utils import canonicalize_url, resolve_http_url

_CAREER_TERMS = (
    "career",
    "careers",
    "recruit",
    "recruitment",
    "join-us",
    "join us",
    "campus",
    "graduate",
    "graduates",
    "talent",
    "招聘",
    "校招",
    "校园招聘",
    "社会招聘",
    "实习",
    "加入我们",
    "人才招聘",
)
_JOB_TERMS = (
    "/job/",
    "/jobs/",
    "/position/",
    "/positions/",
    "jobid",
    "job_id",
    "jobdetail",
    "job-detail",
    "requisition",
    "vacancy",
    "职位详情",
    "岗位详情",
    "查看职位",
    "招聘岗位",
    "岗位招聘",
    "招聘职位",
    "立即申请",
    "view job",
    "job details",
    "job opening",
)
_PAGINATION_TERMS = ("下一页", "下页", "next", "more jobs", "更多职位", "加载更多")
_NOTICE_TERMS = (
    "招聘公告",
    "公开招聘",
    "校园招聘公告",
    "招聘简章",
    "招聘通知",
    "人才招聘公告",
    "招聘信息",
    "招聘启事",
    "招考公告",
)
_IRRELEVANT_TERMS = (
    "/news",
    "/tags/",
    "/tag/",
    "/blog",
    "/press",
    "/media",
    "/events",
    "/product",
    "/docs",
    "新闻",
    "资讯",
    "媒体",
    "活动",
)
_APPLICATION_TERMS = (
    "apply",
    "application",
    "立即申请",
    "申请职位",
    "投递",
    "应聘",
    "发送简历",
    "报名",
)
_EMAIL_PATTERN = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_IGNORED_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".zip",
    ".rar",
    ".mp4",
    ".mp3",
)


@dataclass(slots=True)
class PageDocument:
    """供 LLM 和链接遍历共同使用的页面表示。"""

    title: str
    text: str
    links: list[LinkCandidate]
    emails: list[str] = field(default_factory=list)


def _clean_visible_text(soup: BeautifulSoup) -> str:
    """删除不会直接呈现给求职者的节点，同时保留正文换行结构。"""

    for node in soup(["script", "style", "noscript", "svg", "canvas", "template"]):
        node.decompose()
    raw = soup.get_text("\n", strip=True)
    lines = [re.sub(r"[\t\r ]+", " ", line).strip() for line in raw.splitlines()]

    # 连续相同短行通常来自移动端/桌面端重复导航，去重能显著节省 LLM 输入。
    cleaned: list[str] = []
    previous = None
    for line in lines:
        if not line:
            continue
        if line == previous and len(line) < 200:
            continue
        cleaned.append(line)
        previous = line
    return "\n".join(cleaned)


def _score_link(text: str, url: str) -> tuple[int, int]:
    """用可解释的关键词评分补充 LLM，避免入口很明显时仍完全依赖模型。"""

    haystack = f"{text} {url}".casefold()
    is_notice = any(term in haystack for term in _NOTICE_TERMS)
    if any(term in haystack for term in _IRRELEVANT_TERMS) and not is_notice:
        return -100, -100
    career_score = sum(3 for term in _CAREER_TERMS if term in haystack)
    job_score = sum(4 for term in _JOB_TERMS if term in haystack)
    # 政府/国企官网通常把招聘公告放在“新闻、通知公告”栏目下。只有锚文本
    # 明确具有招聘公告语义时才放行，普通招聘活动新闻和企业新闻仍保持排除。
    if is_notice:
        career_score += 8
        job_score += 6
    if any(term in haystack for term in _PAGINATION_TERMS):
        job_score += 3
    # 中文官网常见职位详情路径变体：/job/、/jobs/、/jobInfo/、/jobDetail/ 等。
    if re.search(
        r"/(jobinfo|jobdetail|job|position|requisition)s?/[^/?#]+",
        url,
        re.IGNORECASE,
    ):
        job_score += 5
    # 一些中文官网把“招聘”简写为 zp，且入口只有图片没有锚文本，例如
    # /archives/2026zp。必须同时包含年份与独立 zp 路径段，避免把普通文章放开。
    if re.search(r"/(?:[^/?#]*/)*(?:20\d{2}[-_]?zp)(?:/|$)", url, re.IGNORECASE):
        job_score += 6
    return career_score, job_score


def parse_html(html: str, page_url: str) -> PageDocument:
    """解析 HTML，并保留页面上所有唯一的 HTTP(S) 锚点。"""

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = _clean_visible_text(soup)

    emails: list[str] = []
    for match in _EMAIL_PATTERN.findall(text):
        if match.casefold() not in {item.casefold() for item in emails}:
            emails.append(match)
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if href.casefold().startswith("mailto:"):
            address = href[7:].split("?", 1)[0].strip()
            if _EMAIL_PATTERN.fullmatch(address) and address.casefold() not in {
                item.casefold() for item in emails
            }:
                emails.append(address)

    unique: dict[str, LinkCandidate] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        resolved = resolve_http_url(page_url, href)
        if not resolved:
            continue
        if resolved.casefold().split("?", 1)[0].endswith(_IGNORED_EXTENSIONS):
            continue
        canonical = canonicalize_url(resolved)
        anchor_text = anchor.get_text(" ", strip=True)[:300]
        career_score, job_score = _score_link(anchor_text, canonical)
        candidate = LinkCandidate(
            text=anchor_text,
            url=canonical,
            career_score=career_score,
            job_score=job_score,
        )
        existing = unique.get(canonical)
        if existing is None or (career_score + job_score) > (
            existing.career_score + existing.job_score
        ):
            unique[canonical] = candidate
    return PageDocument(title=title, text=text, links=list(unique.values()), emails=emails)


def is_irrelevant_link(url: str, text: str = "") -> bool:
    """识别新闻、标签、产品与活动页，避免招聘入口分数误命中无关内容。"""

    haystack = f"{text} {urlsplit(url).path}".casefold()
    if any(term in haystack for term in _NOTICE_TERMS):
        return False
    return any(term in haystack for term in _IRRELEVANT_TERMS)


def application_links(document: PageDocument) -> list[str]:
    """返回页面中有明确申请语义的 HTTP(S) 锚点，按原页面顺序去重。"""

    result: list[str] = []
    for item in document.links:
        haystack = f"{item.text} {item.url}".casefold()
        if any(term in haystack for term in _APPLICATION_TERMS) and item.url not in result:
            result.append(item.url)
    return result


def extract_application_method(document: PageDocument) -> str | None:
    """从正文保留包含邮箱/投递指令的原始短行，供页面展示和人工核验。"""

    for line in document.text.splitlines():
        compact = line.strip()
        haystack = compact.casefold()
        if len(compact) <= 500 and (
            _EMAIL_PATTERN.search(compact)
            or any(term in haystack for term in _APPLICATION_TERMS[2:])
        ):
            return compact
    return None


def ranked_prompt_links(document: PageDocument, limit: int) -> list[LinkCandidate]:
    """把最可能与招聘有关的链接放在前面，同时保留部分普通导航供智能发现。"""

    ranked = sorted(
        document.links,
        key=lambda item: (item.career_score + item.job_score, item.job_score, item.text != ""),
        reverse=True,
    )
    return ranked[:limit]


def heuristic_follow_links(
    document: PageDocument,
    page_type: str,
    limit: int,
) -> list[str]:
    """根据页面类型挑选后续链接。

    LLM 可能因列表过长漏掉某些详情链接，因此 ``job_list`` 页面会额外跟踪所有
    得分足够高的岗位 URL；官网首页则只跟踪招聘入口，防止爬到新闻、产品页。
    """

    # 详情页只需要记录申请链接，不应继续进入申请表或推荐岗位，避免无边界遍历。
    if page_type == "job_detail":
        return []

    scored: list[tuple[int, str]] = []
    for item in document.links:
        if is_irrelevant_link(item.url, item.text):
            continue
        if page_type in {"job_list", "mixed"}:
            # 已进入招聘列表后只继续职位详情/分页，不再沿“招聘、实习”等宽泛
            # 导航词跳回新闻、培训、雇主品牌等内容页。
            score = item.job_score
            threshold = 3
        elif page_type == "career_home":
            score = max(item.job_score, item.career_score)
            threshold = 3
        else:
            score = item.career_score
            threshold = 3
        if score >= threshold:
            scored.append((score, item.url))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [url for _score, url in scored[:limit]]
