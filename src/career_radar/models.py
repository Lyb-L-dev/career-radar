"""项目使用的配置模型、抓取模型和职位模型。

集中维护 Pydantic 模型有两个好处：一是 YAML 配置能在启动阶段尽早报错；
二是同一份 ``PageAnalysis`` 模型可以直接交给支持结构化输出的 LLM SDK，
减少模型输出字段漂移导致的运行时错误。
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MatchLevel(str, Enum):
    """岗位与 2026 届应届生画像的匹配等级。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProfileFitLevel(str, Enum):
    """岗位要求与用户个人能力画像的匹配程度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class DifficultyLevel(str, Enum):
    """投递难度等级；它是基于公开 JD 的估算，不代表真实录取概率。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class CompanyType(str, Enum):
    """企业所有制/资本类型，用于配置、筛选和分组扫描。"""

    CENTRAL_SOE = "central_soe"
    LOCAL_SOE = "local_soe"
    PRIVATE = "private"
    FOREIGN = "foreign"
    JOINT_VENTURE = "joint_venture"
    OTHER = "other"


class IndustryCategory(str, Enum):
    """企业主营行业；与所有制类型分开，便于组合筛选。"""

    INTERNET = "internet"
    GAMING = "gaming"
    PET = "pet"
    ENTERPRISE_SOFTWARE = "enterprise_software"
    AI_DATA = "ai_data"
    IOT = "iot"
    FINTECH = "fintech"
    TELECOM = "telecom"
    ENERGY = "energy"
    MANUFACTURING = "manufacturing"
    CONSUMER = "consumer"
    OTHER = "other"


class MonitorMode(str, Enum):
    """监控侧重点：具体岗位、官方招聘通知或两者都监控。"""

    JOBS = "jobs"
    NOTICES = "notices"
    BOTH = "both"


class CompanyPriority(str, Enum):
    """公司池推荐优先级；福建本地且有官方荣誉依据的公司可设为高。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CandidateProfile(BaseModel):
    """用于能力匹配和难度评估的非敏感候选人画像。

    不包含姓名、电话等身份信息；这里的内容会随页面正文发送给所选 LLM，
    因此只应填写技能、项目和求职偏好等与评估直接相关的信息。
    """

    model_config = ConfigDict(extra="forbid")

    graduation_year: int = Field(default=2026, ge=2020, le=2100)
    education_level: str = "普通本科"
    school_background: str = "非 985/211 的普通本科（二本）"
    major: str = ""
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    internships: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    salary_range_k: list[int] = Field(default_factory=lambda: [3, 40], min_length=2, max_length=2)
    accept_internship: bool = True
    accept_relocation: bool = True
    max_difficulty: int = Field(default=8, ge=1, le=10)
    work_types: list[str] = Field(default_factory=lambda: ["校招", "实习"])
    skill_levels: dict[str, Literal["了解", "熟悉", "熟练"]] = Field(default_factory=dict)
    excluded_directions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    notes: str = "尚未补充专业和技能，能力匹配需保守判断"


class CompanyConfig(BaseModel):
    """单个企业的监控配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    url: str = Field(pattern=r"^https?://")
    company_type: CompanyType = CompanyType.PRIVATE
    industry_category: IndustryCategory = IndustryCategory.OTHER
    province: str | None = None
    city: str | None = None
    priority: CompanyPriority = CompanyPriority.MEDIUM
    monitor_mode: MonitorMode = MonitorMode.JOBS
    government_honors: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    enabled: bool = True
    discover_from_homepage: bool | Literal["auto"] = "auto"
    max_pages: int | None = Field(default=None, ge=1, le=5000)
    notes: str | None = None


class AppConfig(BaseModel):
    """本地存储、输出和通知筛选设置。"""

    model_config = ConfigDict(extra="forbid")

    timezone: str = "Asia/Shanghai"
    database_path: Path = Path("data/career_radar.db")
    company_catalog_path: Path = Path("data/company_candidates.json")
    output_dir: Path = Path("output")
    log_dir: Path = Path("logs")
    daily_run_time: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    report_retention_days: int = Field(default=90, ge=7, le=3650)
    output_match_levels: list[MatchLevel] = Field(
        default_factory=lambda: list(MatchLevel)
    )
    notify_match_levels: list[MatchLevel] = Field(
        default_factory=lambda: [MatchLevel.HIGH]
    )
    notify_profile_fit_levels: list[ProfileFitLevel] = Field(
        default_factory=lambda: [
            ProfileFitLevel.HIGH,
            ProfileFitLevel.MEDIUM,
            ProfileFitLevel.UNKNOWN,
        ]
    )
    notify_max_difficulty_score: int = Field(default=10, ge=1, le=10)
    include_updates_in_output: bool = True
    write_empty_report: bool = False
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:7100",
            "http://localhost:7100",
        ],
        min_length=1,
        max_length=20,
    )

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        """定时输出依赖 IANA 时区，启动时提前捕获拼写或系统数据缺失。"""

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"无效时区：{value}") from exc
        return value

    @field_validator("cors_origins")
    @classmethod
    def cors_origins_must_be_http(cls, values: list[str]) -> list[str]:
        """本地管理端只接受明确的 HTTP(S) 来源，不允许通配符放宽访问。"""

        normalized = []
        for value in values:
            origin = value.strip().rstrip("/")
            if not re.fullmatch(r"https?://[^/\s]+", origin):
                raise ValueError(f"无效 CORS 来源：{value}")
            normalized.append(origin)
        return list(dict.fromkeys(normalized))


class CrawlerConfig(BaseModel):
    """网络抓取的合规、安全和容量限制。"""

    model_config = ConfigDict(extra="forbid")

    render_mode: Literal["never", "auto", "always"] = "auto"
    request_delay_min_seconds: float = Field(default=5, ge=0)
    request_delay_max_seconds: float = Field(default=10, ge=0)
    request_timeout_seconds: float = Field(default=30, gt=0)
    playwright_timeout_seconds: float = Field(default=45, gt=0)
    playwright_wait_after_load_ms: int = Field(default=1500, ge=0)
    max_pages_per_company: int = Field(default=120, ge=1, le=5000)
    max_follow_links_per_page: int = Field(default=100, ge=1, le=2000)
    # 同一路径只允许少量不同查询参数组合进入队列，避免筛选器组合指数扩散。
    max_query_variants_per_path: int = Field(default=3, ge=1, le=20)
    max_links_in_prompt: int = Field(default=500, ge=10, le=5000)
    max_download_bytes: int = Field(default=10_000_000, ge=100_000)
    min_static_text_chars: int = Field(default=800, ge=0)
    user_agent: str = Field(min_length=10)

    @model_validator(mode="after")
    def validate_delay_range(self) -> CrawlerConfig:
        """最小间隔不能大于最大间隔，否则随机等待没有明确含义。"""

        if self.request_delay_min_seconds > self.request_delay_max_seconds:
            raise ValueError("request_delay_min_seconds 不能大于最大值")
        return self


class LLMConfig(BaseModel):
    """大模型供应商与上下文切片设置。"""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai", "anthropic", "deepseek"] = "openai"
    model: str = Field(min_length=1)
    base_url: str | None = None
    request_timeout_seconds: float = Field(default=120, gt=0)
    max_output_tokens: int = Field(default=30_000, ge=1024)
    max_input_chars: int = Field(default=140_000, ge=10_000)
    chunk_overlap_chars: int = Field(default=4_000, ge=0)
    max_retries: int = Field(default=3, ge=1, le=10)
    # DeepSeek 官方接口支持关闭思考模式；兼容代理不支持该扩展参数时可设为 false。
    disable_thinking: bool = True

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> LLMConfig:
        """重叠区必须显著小于切片，避免切片循环无法前进。"""

        if self.chunk_overlap_chars >= self.max_input_chars // 2:
            raise ValueError("chunk_overlap_chars 必须小于 max_input_chars 的一半")
        return self


class SMTPConfig(BaseModel):
    """可选 SMTP 邮件通知设置；密码只从环境变量读取。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    host: str = ""
    port: int = Field(default=465, ge=1, le=65535)
    use_ssl: bool = True
    use_starttls: bool = False
    username: str = ""
    password_env: str = "SMTP_PASSWORD"
    from_address: str = ""
    to_addresses: list[str] = Field(default_factory=list)
    subject_prefix: str = "[Career Radar]"
    jd_summary_chars: int = Field(default=500, ge=100, le=5000)

    @model_validator(mode="after")
    def validate_transport(self) -> SMTPConfig:
        """SSL 和 STARTTLS 是两种连接方式，不能同时打开。"""

        if self.use_ssl and self.use_starttls:
            raise ValueError("SMTP 的 use_ssl 与 use_starttls 不能同时为 true")
        if self.enabled and not (
            self.host and self.username and self.from_address and self.to_addresses
        ):
            raise ValueError("启用 SMTP 后必须填写 host/username/from_address/to_addresses")
        return self


class ReputationConfig(BaseModel):
    """本机社交口碑调查配置；只允许调用 OpenCLI 的只读搜索/详情命令。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    opencli_command: str = "opencli"
    platforms: list[Literal["xiaohongshu", "zhihu", "weibo", "nowcoder"]] = Field(
        default_factory=lambda: ["xiaohongshu", "zhihu", "weibo", "nowcoder"],
        min_length=1,
        max_length=4,
    )
    results_per_query: int = Field(default=5, ge=1, le=20)
    detail_results_per_platform: int = Field(default=2, ge=0, le=5)
    command_timeout_seconds: int = Field(default=90, ge=15, le=300)
    max_evidence_items: int = Field(default=40, ge=4, le=100)
    max_evidence_chars: int = Field(default=4_000, ge=500, le=20_000)

    @field_validator("platforms")
    @classmethod
    def platforms_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("reputation.platforms 不能重复")
        return values


class Settings(BaseModel):
    """完整配置文件的根模型。"""

    model_config = ConfigDict(extra="forbid")

    app: AppConfig = Field(default_factory=AppConfig)
    crawler: CrawlerConfig
    llm: LLMConfig
    smtp: SMTPConfig = Field(default_factory=SMTPConfig)
    reputation: ReputationConfig = Field(default_factory=ReputationConfig)
    candidate: CandidateProfile = Field(default_factory=CandidateProfile)
    companies: list[CompanyConfig] = Field(min_length=1)

    @field_validator("companies")
    @classmethod
    def company_names_must_be_unique(
        cls, companies: list[CompanyConfig]
    ) -> list[CompanyConfig]:
        """公司名用于日志、筛选和数据库展示，因此要求唯一。"""

        names = [item.name.casefold().strip() for item in companies]
        if len(names) != len(set(names)):
            raise ValueError("companies 中的公司名称不能重复")
        return companies


class LinkCandidate(BaseModel):
    """从 HTML 锚点抽取出的候选链接及启发式分数。"""

    text: str
    url: str
    career_score: int = 0
    job_score: int = 0


class FollowLink(BaseModel):
    """LLM 判断值得继续访问的招聘导航、列表或详情链接。"""

    url: str
    kind: Literal["career_section", "job_list", "job_detail", "pagination"]
    reason: str = ""


class JobPosting(BaseModel):
    """最终写入 SQLite 和日报的标准职位结构。"""

    model_config = ConfigDict(extra="forbid")

    # 央国企常把招聘信息发布为正式公告且不提供独立职位入口。notice 与普通
    # job 共用可靠的去重、变化检测和通知链路，但在 API/前端独立展示。
    record_type: Literal["job", "notice"] = "job"
    company: str = ""
    title: str = Field(min_length=1)
    location: str | None = None
    # ``description`` 保存页面上的完整 JD 原文，不是模型摘要。
    description: str = ""
    requirements: str | None = None
    recruitment_type: str | None = None
    is_2026_target: bool | None = None
    target_graduates: str | None = None
    published_at: str | None = None
    valid_until: str | None = None
    apply_url: str | None = None
    contact_email: str | None = None
    application_method: str | None = None
    jd_complete: bool = True
    jd_incomplete_reason: str | None = None
    source_url: str = ""
    match_level: MatchLevel = MatchLevel.LOW
    match_reason: str = ""
    profile_fit_level: ProfileFitLevel = ProfileFitLevel.UNKNOWN
    profile_fit_reason: str = "候选人画像信息不足"
    difficulty_level: DifficultyLevel = DifficultyLevel.MEDIUM
    difficulty_score: int = Field(default=5, ge=1, le=10)
    difficulty_reason: str = "仅依据公开 JD 的初步估算"

    @field_validator(
        "location",
        "requirements",
        "recruitment_type",
        "target_graduates",
        "published_at",
        "valid_until",
        "apply_url",
        "contact_email",
        "application_method",
        "jd_incomplete_reason",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        """模型常用空字符串表达未知值，入库前统一转换为 NULL。"""

        if isinstance(value, str) and not value.strip():
            return None
        return value


class PageAnalysis(BaseModel):
    """LLM 对一个页面（或一个长页面切片）的结构化分析结果。"""

    model_config = ConfigDict(extra="forbid")

    page_type: Literal["no_jobs", "career_home", "job_list", "job_detail", "mixed"]
    contains_recruitment_info: bool
    jobs: list[JobPosting] = Field(default_factory=list)
    follow_links: list[FollowLink] = Field(default_factory=list)
    notes: str = ""


class ReputationTopic(BaseModel):
    """口碑报告的一个主题结论，证据编号必须来自本次扫描。"""

    model_config = ConfigDict(extra="forbid")

    name: Literal["工作强度", "薪资福利", "管理氛围", "成长空间", "稳定性", "面试体验", "岗位边界", "其他"]
    sentiment: Literal["positive", "mixed", "negative", "unknown"] = "unknown"
    summary: str
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class SocialReputationAnalysis(BaseModel):
    """DeepSeek 对多平台公开评价的谨慎归纳，不代表事实认定。"""

    model_config = ConfigDict(extra="forbid")

    overall_summary: str
    risk_level: Literal["low", "medium", "high", "unknown"] = "unknown"
    confidence: Literal["low", "medium", "high"] = "low"
    positive_signals: list[str] = Field(default_factory=list, max_length=20)
    risk_signals: list[str] = Field(default_factory=list, max_length=20)
    interview_tips: list[str] = Field(default_factory=list, max_length=20)
    topics: list[ReputationTopic] = Field(default_factory=list, max_length=20)
    disclaimer: str = (
        "社交平台内容可能主观、过时或无法核实，仅作求职背调线索；重要信息请在面试和书面 Offer 中确认。"
    )


class StoredJobEvent(BaseModel):
    """职位入库后的事件，用于只输出新增或发生变化的记录。"""

    event_type: Literal["new", "updated", "unchanged", "preview"]
    job: JobPosting
    entity_key: str
    fingerprint: str
    detected_at: str


class CompanyRunResult(BaseModel):
    """单个公司的抓取结果；错误被隔离后也会记录在此。"""

    company: str
    pages_visited: int = 0
    jobs: list[JobPosting] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class RunResult(BaseModel):
    """一次完整运行的统计和输出文件路径。"""

    started_at: str
    finished_at: str
    companies_processed: int
    pages_visited: int
    jobs_seen: int
    new_jobs: int
    updated_jobs: int
    unchanged_jobs: int
    report_path: str | None = None
    csv_path: str | None = None
    email_sent: bool = False
    errors: list[str] = Field(default_factory=list)
