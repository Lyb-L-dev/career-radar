/**
 * Career Radar 领域类型定义
 * 与后端（Python 监控服务）的数据结构保持语义一致，
 * 切换真实后端时只需在 services 层做字段适配。
 */

// ---------- 通用 ----------
export type MatchLevel = 'high' | 'medium' | 'low' | 'unknown'
export type ISODateTime = string
export type CompanyType = 'central_soe' | 'local_soe' | 'private' | 'foreign' | 'joint_venture' | 'other'
export type IndustryCategory = 'internet' | 'gaming' | 'pet' | 'enterprise_software' | 'ai_data' | 'iot' | 'fintech' | 'telecom' | 'energy' | 'manufacturing' | 'consumer' | 'other'
export type CompanyPriority = 'high' | 'medium' | 'low'
export type MonitorMode = 'jobs' | 'notices' | 'both'

export const COMPANY_TYPE_LABEL: Record<CompanyType, string> = {
  central_soe: '央企',
  local_soe: '地方国企',
  private: '民营企业',
  foreign: '外资企业',
  joint_venture: '合资企业',
  other: '其他',
}

export const INDUSTRY_CATEGORY_LABEL: Record<IndustryCategory, string> = {
  internet: '互联网',
  gaming: '游戏',
  pet: '宠物',
  enterprise_software: '企业软件',
  ai_data: 'AI 与数据',
  iot: '物联网',
  fintech: '金融科技',
  telecom: '通信',
  energy: '能源电力',
  manufacturing: '智能制造',
  consumer: '消费品',
  other: '其他',
}

export const MONITOR_MODE_LABEL: Record<MonitorMode, string> = {
  jobs: '具体岗位',
  notices: '招聘通知',
  both: '岗位与通知',
}

export const MATCH_LEVEL_LABEL: Record<MatchLevel, string> = {
  high: '高匹配',
  medium: '中匹配',
  low: '低匹配',
  unknown: '信息不足',
}

// ---------- 岗位 ----------
export type JobType = 'campus' | 'internship' | 'fulltime' | 'notice'
export type JobStatus = 'new' | 'updated' | 'closed' | 'ignored'

export const JOB_TYPE_LABEL: Record<JobType, string> = {
  campus: '校招',
  internship: '实习',
  fulltime: '全职',
  notice: '招聘通知',
}

export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  new: '新增',
  updated: '已更新',
  closed: '已关闭',
  ignored: '已忽略',
}

export interface JobChange {
  id: string
  time: ISODateTime
  type: 'discovered' | 'jd_updated' | 'entry_changed' | 'apply_changed' | 'closed'
  summary: string
  diff?: { removed: string[]; added: string[] }
}

export interface JobAnalysis {
  conclusion: string
  hasSkills: string[]
  missingSkills: string[]
  suggestions: string[]
  advice: string
}

export interface DifficultyFactor {
  label: string
  level: '低' | '中' | '高'
  note: string
}

export interface SourceCredibility {
  site: string
  page: string
  method: string
  urlVerified: boolean
  lastVerifiedAt: ISODateTime
}

export interface Job {
  id: string
  title: string
  companyId: string
  companyName: string
  companyType?: CompanyType
  companyIndustry?: IndustryCategory
  companyProvince?: string
  companyCity?: string
  companyPriority?: CompanyPriority
  recordType?: 'job' | 'notice'
  city: string
  type: JobType
  status: JobStatus
  gradYearMatch: MatchLevel
  abilityMatch: MatchLevel
  difficulty: number // 0-10
  isFavorite: boolean
  isApplied: boolean
  notInterested: boolean
  hasApplyUrl: boolean
  applyUrl?: string
  sourceUrl: string
  publishedAt?: string
  firstSeenAt: ISODateTime
  lastUpdatedAt: ISODateTime
  recommendReason?: string
  highlyRecommended?: boolean
  tags: string[]
  overview: string
  responsibilities: string[]
  requirements: string[]
  plusPoints: string[]
  locationDetail: string
  applyMethod: string
  jdText: string
  jdComplete?: boolean
  jdIncompleteReason?: string
  contactEmail?: string
  analysis: JobAnalysis
  difficultyFactors: DifficultyFactor[]
  source: SourceCredibility
  history: JobChange[]
}

// ---------- AI 申请材料 ----------
export type ApplicationStatus =
  | 'created'
  | 'evaluating'
  | 'waiting_for_approval'
  | 'drafting'
  | 'factual_review'
  | 'recruiter_review'
  | 'revising'
  | 'rendering'
  | 'verifying'
  | 'ready'
  | 'rejected'
  | 'failed'

export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  created: '已创建',
  evaluating: '正在评估岗位',
  waiting_for_approval: '等待人工批准',
  drafting: '正在生成材料',
  factual_review: '事实审查',
  recruiter_review: '招聘视角审查',
  revising: '正在修订',
  rendering: '正在生成文档',
  verifying: '正在校验文档',
  ready: '材料已就绪',
  rejected: '已放弃',
  failed: '执行失败',
}

export type ApplicationDimensionName =
  | 'skills'
  | 'projects_experience'
  | 'education_graduation'
  | 'career'
  | 'logistics'

export const APPLICATION_DIMENSION_LABEL: Record<ApplicationDimensionName, string> = {
  skills: '技能匹配',
  projects_experience: '项目与经历',
  education_graduation: '学历与届别',
  career: '发展方向',
  logistics: '城市与到岗条件',
}

export interface ApplicationEligibility {
  name: string
  verdict: 'pass' | 'fail' | 'unknown'
  reason: string
  evidence?: string
}

export interface ApplicationDimension {
  name: ApplicationDimensionName
  score: number
  weight: number
  strengths: string[]
  gaps: string[]
  evidence: string[]
}

export interface ApplicationRequirementCoverage {
  requirement: string
  priority: 'required' | 'preferred' | 'unknown'
  status: 'matched' | 'partial' | 'gap' | 'unknown'
  candidate_evidence: string[]
  honest_bridge?: string
}

export interface ApplicationEvaluation {
  eligibility: ApplicationEligibility[]
  dimensions: ApplicationDimension[]
  overall_score: number
  difficulty_score: number
  verdict: 'strong' | 'good' | 'moderate' | 'weak' | 'ineligible'
  recommendation: string
  requirement_coverage: ApplicationRequirementCoverage[]
}

export interface ApplicationArtifact {
  kind: 'resume_docx' | 'resume_pdf' | 'cover_letter_docx' | 'cover_letter_pdf'
  fileName: string
  sha256: string
  downloadUrl: string
}

export interface ApplicationTask {
  id: string
  jobId: string
  status: ApplicationStatus
  failedStep?: ApplicationStatus
  progress: number
  error?: string
  nextAction: string
  coverLetterMode: 'auto' | 'always' | 'never'
  resumePageTarget: number
  createdAt: ISODateTime
  updatedAt: ISODateTime
  approvedAt?: ISODateTime
  completedAt?: ISODateTime
  isRunning: boolean
  canApprove: boolean
  canResume: boolean
  canReject: boolean
  canRender: boolean
  job?: {
    title: string
    company: string
    location?: string
    recruitmentType?: string
  }
  evaluation?: ApplicationEvaluation
  artifacts: ApplicationArtifact[]
}

export interface ApplicationProfileStatus {
  ready: boolean
  verificationStatus: string
  message?: string
  [key: string]: unknown
}

export type ReputationScanStatus = 'pending' | 'running' | 'completed' | 'partial' | 'failed' | 'interrupted'
export type ReputationPlatformStatus = 'waiting' | 'running' | 'success' | 'failed'

export interface ReputationPlatform {
  key: 'xiaohongshu' | 'zhihu' | 'weibo' | 'nowcoder'
  label: string
  status: ReputationPlatformStatus
  evidenceCount: number
  error?: string
}

export interface ReputationEvidence {
  id: string
  platform: ReputationPlatform['key']
  platformLabel: string
  title: string
  excerpt: string
  url?: string
  publishedAt?: string
  interactionCount: number
  searchQuery: string
  relevanceScope?: 'job' | 'company'
  matchedCompanyTerms?: string[]
  matchedJobTerms?: string[]
}

export interface ReputationTopic {
  name: '工作强度' | '薪资福利' | '管理氛围' | '成长空间' | '稳定性' | '面试体验' | '岗位边界' | '其他'
  sentiment: 'positive' | 'mixed' | 'negative' | 'unknown'
  summary: string
  evidence_ids: string[]
}

export interface ReputationAnalysis {
  overall_summary: string
  risk_level: 'low' | 'medium' | 'high' | 'unknown'
  confidence: 'low' | 'medium' | 'high'
  positive_signals: string[]
  risk_signals: string[]
  interview_tips: string[]
  topics: ReputationTopic[]
  disclaimer: string
}

export interface ReputationScan {
  id: string
  jobId: string
  companyName: string
  jobTitle: string
  status: ReputationScanStatus
  startedAt: ISODateTime
  updatedAt: ISODateTime
  finishedAt?: ISODateTime
  durationMs?: number
  queries: string[]
  platforms: ReputationPlatform[]
  evidence: ReputationEvidence[]
  analysis?: ReputationAnalysis
  errors: string[]
  disclaimer: string
}

export interface ReputationHealth {
  enabled: boolean
  available: boolean
  message: string
  platforms: Array<{ key: ReputationPlatform['key']; label: string }>
}

export type JobTab = 'recommended' | 'notice' | 'new' | 'updated' | 'all' | 'favorite'

export interface JobFilter {
  tab: JobTab
  keyword?: string
  companyId?: string
  companyType?: CompanyType
  industryCategory?: IndustryCategory
  province?: string
  city?: string
  type?: JobType
  gradYearMatch?: MatchLevel
  abilityMatch?: MatchLevel
  difficultyMax?: number
  changedWithinDays?: number
  hasApplyUrl?: boolean
}

// ---------- 企业 ----------
export type CompanyStatus =
  | 'active'               // 正常
  | 'scanning'             // 扫描中
  | 'pending_verification' // 等待首次验证
  | 'robots_blocked'       // robots 禁止
  | 'structure_error'      // 页面结构异常
  | 'request_failed'       // 请求失败
  | 'paused'               // 已暂停

export const COMPANY_STATUS_LABEL: Record<CompanyStatus, string> = {
  active: '正常',
  scanning: '扫描中',
  pending_verification: '等待首次验证',
  robots_blocked: 'robots 禁止',
  structure_error: '页面结构异常',
  request_failed: '请求失败',
  paused: '已暂停',
}

export type RenderMode = 'auto' | 'static' | 'dynamic'
export type RobotsStatus = 'allowed' | 'blocked' | 'unknown'

export const RENDER_MODE_LABEL: Record<RenderMode, string> = {
  auto: '自动',
  static: '静态抓取',
  dynamic: '浏览器渲染',
}

export interface Company {
  id: string
  name: string
  shortName: string
  website: string
  careersUrl?: string
  industry: string
  industryCategory?: IndustryCategory
  companyType: CompanyType
  province?: string
  city?: string
  priority?: CompanyPriority
  monitorMode?: MonitorMode
  governmentHonors?: string[]
  evidenceUrls?: string[]
  status: CompanyStatus
  renderMode: RenderMode
  robotsStatus: RobotsStatus
  lastScanAt?: ISODateTime
  recentJobCount: number
  consecutiveFailures: number
  maxPages: number
  recruitmentChannel?: RecruitmentChannel
  parentCompany?: string
  attributionKeywords?: string[]
  enabled: boolean
  note?: string
  discoveredEntry?: string
  lastError?: string
  addedAt: ISODateTime
}

export type CompanyCandidateDecision = 'pending' | 'shortlisted' | 'rejected' | 'monitored'

export type RecruitmentChannel =
  | 'official_careers'
  | 'official_homepage'
  | 'group_recruitment'
  | 'official_notice_source'

export type RecruitmentChannelStatus =
  | 'official_site_pending'
  | 'no_official_site'
  | 'no_careers_channel'
  | 'official_careers'
  | 'group_recruitment'
  | 'official_notice_source'
  | 'manual_only'
  | 'third_party_lead'
  | 'not_hiring'

export const RECRUITMENT_CHANNEL_STATUS_LABEL: Record<RecruitmentChannelStatus, string> = {
  official_site_pending: '官网待核验',
  no_official_site: '未找到官网',
  no_careers_channel: '官网无招聘渠道',
  official_careers: '官方招聘入口',
  group_recruitment: '集团统一招聘',
  official_notice_source: '官方公告来源',
  manual_only: '仅人工维护',
  third_party_lead: '第三方待核验',
  not_hiring: '当前未招聘',
}

export type RecruitmentSourceKind =
  | 'official_homepage'
  | 'official_careers'
  | 'group_recruitment'
  | 'government_notice'
  | 'official_account'
  | 'official_document'
  | 'official_email'
  | 'third_party_lead'

export type RecruitmentSourceVerification = 'verified_official' | 'pending' | 'rejected'
export type RecruitmentMaterialType = 'webpage' | 'pdf' | 'image' | 'text' | 'email'

export interface RecruitmentSource {
  id: string
  candidateId: string
  sourceKind: RecruitmentSourceKind
  verificationStatus: RecruitmentSourceVerification
  materialType: RecruitmentMaterialType
  title: string
  sourceUrl?: string
  content?: string
  publishedAt?: string
  parentCompany?: string
  importedJobId?: string
  createdAt: ISODateTime
  updatedAt: ISODateTime
}

export type WechatAccountScope = 'company' | 'group'
export type WechatAccountVerification = 'verified' | 'pending' | 'rejected'

export interface WechatRecruitmentAccount {
  id: string
  candidateId: string
  accountName: string
  accountIdentifier?: string
  bizId?: string
  scope: WechatAccountScope
  parentCompany?: string
  attributionKeywords: string[]
  verificationStatus: WechatAccountVerification
  enabled: boolean
  createdAt: ISODateTime
  updatedAt: ISODateTime
}

export interface WechatRecruitmentHealth {
  enabled: boolean
  available: boolean
  message: string
}

export type WechatArticleClassification =
  | 'official_recruitment'
  | 'third_party_lead'
  | 'non_recruitment'

export interface WechatRecruitmentArticle {
  id: string
  candidateId: string
  accountId?: string
  title: string
  accountName?: string
  url: string
  summary?: string
  publishedAt?: string
  classification: WechatArticleClassification
  verificationStatus: RecruitmentSourceVerification
  reason: string
  sourceId?: string
  importedJobId?: string
  firstSeenAt: ISODateTime
  updatedAt: ISODateTime
}

export type WechatRecruitmentScanStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'interrupted'

export interface WechatRecruitmentScan {
  id: string
  candidateId: string
  companyName: string
  status: WechatRecruitmentScanStatus
  startedAt: ISODateTime
  updatedAt: ISODateTime
  finishedAt?: ISODateTime
  accounts: Array<{
    id: string
    name: string
    verificationStatus: WechatAccountVerification
  }>
  queries: string[]
  articles: Array<{
    id: string
    title: string
    accountName?: string
    url: string
    publishedAt?: string
    classification: WechatArticleClassification
    reason: string
    event: 'new' | 'updated' | 'unchanged'
    imported: boolean
  }>
  stats: {
    searched: number
    read: number
    official: number
    leads: number
    ignored: number
    imported: number
    new: number
    updated: number
    unchanged: number
  }
  errors: string[]
}

export interface CompanyCandidateSource {
  key: string
  title: string
  url: string
  count: number
}

export interface CompanyCandidate {
  id: string
  name: string
  sourceRegion: string
  province: string
  city?: string
  sourceKey: string
  sourceTitle: string
  evidenceUrl: string
  sourceKeys?: string[]
  sourceTitles?: string[]
  evidenceUrls?: string[]
  sourceSequence: number
  qualityEvidenceScore: number
  qualitySignals: string[]
  scaleLevel?: 'large' | 'medium_or_above' | 'medium' | 'growth_stage' | 'unknown'
  scaleEvidence?: string[]
  techSignals: string[]
  suggestedIndustryCategory: IndustryCategory
  dueDiligenceStatus: 'unverified' | 'in_progress' | 'verified'
  fitScore: number
  fitLevel: 'high' | 'medium' | 'low'
  fitReasons: string[]
  decision: CompanyCandidateDecision
  monitored: boolean
  officialWebsite?: string
  careersUrl?: string
  companyType: CompanyType
  industryCategory: IndustryCategory
  recruitmentChannelStatus: RecruitmentChannelStatus
  parentCompany?: string
  groupRecruitmentUrl?: string
  attributionKeywords: string[]
  reviewNote?: string
  reviewedAt?: ISODateTime
}

export interface CompanyWebsiteSuggestion {
  website: string
  title: string
  snippet: string
  score: number
}

export interface CompanyWebsiteDiscovery {
  status: 'found' | 'ambiguous' | 'not_found'
  confidence: 'high' | 'medium' | 'low'
  website?: string
  message: string
  candidates: CompanyWebsiteSuggestion[]
  cached: boolean
}

export interface CompanyCandidateStats {
  total: number
  fujian: number
  highFit: number
  techRelated: number
  pending: number
  shortlisted: number
  rejected: number
  monitored: number
}

export interface CompanyCandidatePage {
  items: CompanyCandidate[]
  total: number
  page: number
  pageSize: number
  pages: number
  catalogTotal: number
  generatedAt?: string
  disclaimer: string
  sources: CompanyCandidateSource[]
  stats: CompanyCandidateStats
  provinceCounts: Record<string, number>
}

export interface CompanyPageRecord {
  runId?: string
  url: string
  requestedUrl?: string
  pageType: string
  method: 'requests' | 'playwright'
  httpStatus: number | null
  contentLength: number
  llmExtracted: boolean
  jobsFound?: number
  status?: 'success' | 'failed'
  error?: string
  fetchedAt: ISODateTime
}

export interface CompanyError {
  time: ISODateTime
  message: string
  technicalDetail: string
}

export interface CompanyTestResult {
  robotsAllowed: boolean
  homepageReachable: boolean
  entryFound: boolean
  entryUrl?: string
  needsBrowserRender: boolean
  estimatedPages: number
}

// ---------- 运行任务 ----------
export type RunStatus = 'pending' | 'running' | 'stopping' | 'completed' | 'partial' | 'interrupted' | 'failed'
export type RunTrigger = 'manual' | 'scheduled' | 'retry'

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  pending: '等待中',
  running: '运行中',
  stopping: '正在停止',
  completed: '已完成',
  partial: '部分完成',
  interrupted: '已中断',
  failed: '失败',
}

export type StepStatus = 'success' | 'skipped' | 'failed' | 'running' | 'waiting'

export interface RunStep {
  key: string
  label: string
  status: StepStatus
  durationMs?: number
  message: string
}

export interface CompanyRun {
  companyId: string
  companyName: string
  status: 'success' | 'skipped' | 'failed' | 'running' | 'waiting'
  steps: RunStep[]
  newJobs: number
  updatedJobs: number
  jobsSeen?: number
  pagesVisited?: number
  successfulPages?: number
  failedPages?: number
  currentPage?: string
  error?: string
}

export type EmailStatus = 'sent' | 'not_sent' | 'failed' | 'disabled'

export interface RunLog {
  time: ISODateTime
  level: 'INFO' | 'WARN' | 'ERROR'
  company?: string
  message: string
}

export interface Run {
  id: string
  code: string
  trigger: RunTrigger
  status: RunStatus
  startedAt: ISODateTime
  finishedAt?: ISODateTime
  durationMs: number
  totalCompanies: number
  finishedCompanies: number
  successCount: number
  skippedCount: number
  failedCount: number
  newJobs: number
  updatedJobs: number
  emailStatus: EmailStatus
  sendEmail: boolean
  canStop?: boolean
  companies: CompanyRun[]
  logs: RunLog[]
}

// ---------- 日报 ----------
export type FileStatus = 'generated' | 'none'

export interface Report {
  date: string // YYYY-MM-DD
  newJobs: number
  updatedJobs: number
  highMatchJobs: number
  markdownStatus: FileStatus
  csvStatus: FileStatus
  emailStatus: EmailStatus
  summary: string
  topJobIds: string[]
  newJobIds: string[]
  updatedJobIds: string[]
  anomalies: string[]
  tomorrowFocus: string[]
}

// ---------- 通知 ----------
export type NotificationType =
  | 'high_match_job'
  | 'company_failed'
  | 'run_completed'
  | 'report_ready'
  | 'email_failed'
  | 'config_error'
  | 'system'

export interface NotificationItem {
  id: string
  type: NotificationType
  title: string
  body: string
  time: ISODateTime
  read: boolean
  link?: string
}

// ---------- 用户画像 ----------
export type SkillLevel = '了解' | '熟悉' | '熟练'

export interface SkillTag {
  name: string
  level: SkillLevel
}

export interface ProjectExperience {
  id: string
  name: string
  description: string
  skills: string[]
}

export interface CandidateProfile {
  gradYear: string
  degree: string
  schoolBackground: string
  major: string
  targetRoles: string[]
  cities: string[]
  salaryRange: [number, number]
  acceptInternship: boolean
  acceptRelocation: boolean
  maxDifficulty: number
  workTypes: string[]
  skills: SkillTag[]
  projects: ProjectExperience[]
  internships: string[]
  excludedDirections: string[]
  notes: string
  completeness: number
}

// ---------- 系统设置 ----------
export interface AppSettings {
  basic: {
    timezone: string
    outputDir: string
    dbPath: string
    dailyRunTime: string
    reportRetentionDays: number
  }
  crawler: {
    minDelay: number
    maxDelay: number
    defaultRenderMode: RenderMode
    minContentLength: number
    maxPagesPerCompany: number
    requestTimeout: number
    respectRobots: boolean
  }
  llm: {
    provider: 'DeepSeek' | 'OpenAI' | 'Anthropic'
    model: string
    apiBaseUrl: string
    apiKeyMasked: string
    apiKeyConfigured: boolean
    jsonOutput: boolean
    maxChunkLength: number
    chunkOverlap: number
    timeout: number
    retries: number
  }
  email: {
    enabled: boolean
    smtpHost: string
    smtpPort: number
    encryption: 'SSL' | 'STARTTLS' | 'none'
    fromAddress: string
    toAddresses: string[]
    sendOnNew: boolean
    sendOnUpdate: boolean
    minMatchLevel: MatchLevel
    maxDifficulty: number
  }
}

// ---------- 总览 ----------
export interface AttentionItem {
  id: string
  kind: 'verify' | 'smtp' | 'offline_test' | 'company_failed'
  text: string
  actionLabel: string
  link: string
}

export interface DashboardStats {
  todayNew: number
  todayNewDelta: number
  todayUpdated: number
  todayUpdatedDelta: number
  highMatch: number
  highMatchDelta: number
  monitoredCompanies: number
  lastScanAt: ISODateTime
  environment: {
    python: string
    chromium: string
    dbJobCount: number
    jobHistoryCount: number
    emailEnabled: boolean
    successCompanies: number
    pendingCompanies: number
  }
  attentionItems: AttentionItem[]
}

// ---------- 全局搜索 ----------
export interface SearchResults {
  jobs: Job[]
  companies: Company[]
  reports: Report[]
  runs: Run[]
}
