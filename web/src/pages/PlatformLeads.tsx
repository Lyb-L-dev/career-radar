import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import { ArrowUpRight, Bookmark, FileJson, MoreHorizontal, Plus, RefreshCw, Sparkles } from 'lucide-react';
import { apiRequest } from '@/services/config';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { EmptyState, ErrorState, ListSkeleton } from '@/components/common/StateViews';
import { SourceNote } from '@/components/jobs/SourceNote';
import { GrowthTargetButton } from '@/components/GrowthSummary';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router';
import { safeJobsReturn } from '@/lib/browserState';
import { usePlatformLeads } from '@/hooks/usePlatformLeads';
import { useUrlSearch, useListScroll } from '@/hooks/useBrowserState';
import { getPlatformLeads, PLATFORM_LEADS_KEY } from '@/services/platformLeads';
import type { PlatformLead, Category } from '@/services/platformLeads';
type StateField = 'favorite' | 'applied' | 'hidden';
interface ImportPreview {
    total: number;
    completeJd: number;
    needsReview: number;
}
interface ImportResult {
    total: number;
    new: number;
    updated: number;
    unchanged: number;
}
interface BossPreferences {
    currentStudent: boolean | null;
    acceptInternship: boolean;
}
interface CrawlStatus {
    state: 'idle' | 'running' | 'complete' | 'failed';
    stage: string;
    counts: Record<string, number>;
}
interface CrawlPlan {
    searches: {
        family: string;
        keyword: string;
    }[];
    resumeProjectCount: number;
}
const CATEGORIES: {
    value: Category | 'all';
    label: string;
}[] = [
    { value: 'all', label: '待看（不含排除）' },
    { value: 'priority', label: '优先阅读' },
    { value: 'review', label: '需确认' },
    { value: 'lower', label: '低优先级' },
    { value: 'excluded', label: '已排除' },
];
const CATEGORY_LABEL: Record<Category, string> = {
    priority: '优先阅读',
    review: '需确认',
    lower: '低优先级',
    excluded: '已排除',
};
const ELIGIBILITY_LABEL = {
    eligible: 'AI 判断：报名条件基本符合',
    ineligible: 'AI 提示资格不符，请核对原文',
    unknown: '报名资格仍需确认',
};
const FIT_LABEL = {
    strong: '方向高度相关',
    reasonable: '方向可考虑',
    weak: '方向匹配较弱',
    unknown: '方向信息不足',
};
const ACTION_LABEL = {
    prioritize: '建议优先核对并投递',
    consider: '建议阅读后决定',
    defer: '建议暂缓',
};
function localDate(value: string): string {
    return new Date(value).toLocaleDateString('zh-CN');
}
export default function PlatformLeadsPage({ embedded = false, focusLeadId = null }: {
    embedded?: boolean;
    focusLeadId?: string | null;
}) {
    const client = useQueryClient();
    const leadQuery = usePlatformLeads();
    const leads = useMemo(() => leadQuery.data ?? [], [leadQuery.data]);
    const [params, setParams] = useSearchParams();
    const navigate = useNavigate();
    const search = useUrlSearch();
    const keyword = params.get('q') ?? '';
    const categoryParam = params.get('category');
    const category = ['priority', 'review', 'lower', 'excluded'].includes(categoryParam ?? '') ? categoryParam as Category : 'all';
    const includeHandled = params.get('handled') === '1';
    const setCategory = useCallback((value: Category | 'all') => { setParams(old => { const next = new URLSearchParams(old); next.set('category', value); return next; }); }, [setParams]);
    useListScroll(!leadQuery.isPending);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [content, setContent] = useState('');
    const [filename, setFilename] = useState('');
    const [preview, setPreview] = useState<ImportPreview | null>(null);
    const [busy, setBusy] = useState(false);
    const [preferences, setPreferences] = useState<BossPreferences | null>(null);
    const [preferencesBusy, setPreferencesBusy] = useState(false);
    const [workingId, setWorkingId] = useState<string | null>(null);
    const [batchProgress, setBatchProgress] = useState<{
        done: number;
        total: number;
    } | null>(null);
    const [crawlStatus, setCrawlStatus] = useState<CrawlStatus | null>(null);
    const [crawlKeyword, setCrawlKeyword] = useState('');
    const [crawlCity, setCrawlCity] = useState('全国');
    const [crawlPages, setCrawlPages] = useState(1);
    const [crawlMaxDetails, setCrawlMaxDetails] = useState(8);
    const [crawlPlan, setCrawlPlan] = useState<CrawlPlan | null>(null);
    const [crawlPlanError, setCrawlPlanError] = useState('');
    const [crawlStarting, setCrawlStarting] = useState(false);
    const [browserOpening, setBrowserOpening] = useState(false);
    const [manageOpen, setManageOpen] = useState(false);
    const stopAfterCurrent = useRef(false);
    const focusedOnce = useRef<string | null>(null);
    const load = useCallback(async (silent = false) => {
        if (!silent)
            setLoading(true);
        try {
            const [, currentPreferences] = await Promise.all([
                client.fetchQuery({ queryKey: PLATFORM_LEADS_KEY, queryFn: getPlatformLeads, staleTime: 0 }),
                apiRequest<BossPreferences>('/platform-leads/preferences'),
            ]);
            setPreferences(currentPreferences);
            setError('');
        }
        catch (cause) {
            setError(cause instanceof Error ? cause.message : '加载失败');
        }
        finally {
            if (!silent)
                setLoading(false);
        }
    }, [client]);
    useEffect(() => { void load(); }, [load]);
    useEffect(() => () => { stopAfterCurrent.current = true; }, []);
    useEffect(() => {
        void apiRequest<CrawlStatus>('/platform-leads/crawl').then(setCrawlStatus).catch(() => undefined);
    }, []);
    useEffect(() => {
        if (!manageOpen)
            return;
        const timer = window.setTimeout(() => {
            void apiRequest<CrawlPlan>(`/platform-leads/crawl/plan?keyword=${encodeURIComponent(crawlKeyword.trim())}`)
                .then((plan) => { setCrawlPlan(plan); setCrawlPlanError(''); })
                .catch((cause) => { setCrawlPlan(null); setCrawlPlanError(cause instanceof Error ? cause.message : '无法读取简历搜索方向'); });
        }, 250);
        return () => window.clearTimeout(timer);
    }, [manageOpen, crawlKeyword]);
    useEffect(() => {
        if (crawlStatus?.state !== 'running')
            return;
        const timer = window.setInterval(() => {
            void apiRequest<CrawlStatus>('/platform-leads/crawl').then((next) => {
                setCrawlStatus(next);
                if (next.state === 'complete') {
                    setCategory('all');
                    void load(true);
                    if (next.counts.ai_failed) {
                        toast.warning(`保留 ${next.counts.accepted ?? 0} 条；${next.counts.ai_failed} 条 MiMo 判断未完成`);
                    }
                    else {
                        toast.success(`按简历抓取完成，保留 ${next.counts.accepted ?? 0} 条岗位`);
                    }
                }
            }).catch(() => undefined);
        }, 3000);
        return () => window.clearInterval(timer);
    }, [crawlStatus?.state, load, setCategory]);
    useEffect(() => {
        if (!focusLeadId || focusedOnce.current === focusLeadId || !leads.some(lead => lead.id === focusLeadId))
            return;
        focusedOnce.current = focusLeadId;
        requestAnimationFrame(() => document.getElementById(`lead-${focusLeadId}`)?.scrollIntoView({ block: 'start' }));
    }, [focusLeadId, leads]);
    const visible = useMemo(() => leads.filter((lead) => {
        if (lead.id === focusLeadId)
            return true;
        if (category === 'all' && lead.category === 'excluded')
            return false;
        if (category !== 'all' && lead.category !== category)
            return false;
        if (!includeHandled && (lead.isHidden || lead.isApplied))
            return false;
        const query = keyword.trim().toLocaleLowerCase();
        if (query && !`${lead.title} ${lead.company} ${lead.description}`.toLocaleLowerCase().includes(query))
            return false;
        return true;
    }), [leads, category, keyword, includeHandled, focusLeadId]);
    const counts = useMemo(() => Object.fromEntries(CATEGORIES.map((item) => [item.value, leads.filter((lead) => item.value === 'all' ? lead.category !== 'excluded' : lead.category === item.value).length])), [leads]);
    const aiQueue = useMemo(() => leads.filter((lead) => lead.aiScreenable && !lead.isApplied && !lead.isHidden &&
        lead.category !== 'excluded' && !lead.aiResult).slice(0, 20), [leads]);
    async function requestScreen(leadId: string): Promise<void> {
        await apiRequest(`/platform-leads/${encodeURIComponent(leadId)}/ai-screen`, {
            method: 'POST', body: JSON.stringify({ confirmed: true }),
        });
        await load(true);
    }
    async function screenOne(leadId: string) {
        if (workingId || batchProgress)
            return;
        setWorkingId(leadId);
        try {
            await requestScreen(leadId);
            toast.success('AI 筛选已完成，请核对原始 JD 与报名条件');
        }
        catch (cause) {
            toast.error(cause instanceof Error ? cause.message : 'AI 筛选失败');
        }
        finally {
            setWorkingId(null);
        }
    }
    async function screenBatch() {
        if (workingId || batchProgress || aiQueue.length === 0)
            return;
        const queue = [...aiQueue];
        stopAfterCurrent.current = false;
        setBatchProgress({ done: 0, total: queue.length });
        let done = 0;
        for (const lead of queue) {
            if (stopAfterCurrent.current)
                break;
            setWorkingId(lead.id);
            try {
                await requestScreen(lead.id);
                done += 1;
                setBatchProgress({ done, total: queue.length });
            }
            catch (cause) {
                toast.error(cause instanceof Error ? cause.message : 'AI 筛选失败，已停止本批');
                break;
            }
        }
        setWorkingId(null);
        setBatchProgress(null);
        if (done > 0)
            toast.success(`本次完成 ${done} 条 AI 筛选`);
    }
    async function chooseFile(file: File | undefined) {
        setContent('');
        setPreview(null);
        setFilename('');
        if (!file)
            return;
        if (file.size > 5000000) {
            toast.error('单个 JSON 文件最多 5 MB，请分批导入');
            return;
        }
        setBusy(true);
        try {
            const text = await file.text();
            const result = await apiRequest<ImportPreview>('/platform-leads/preview', {
                method: 'POST', body: JSON.stringify({ content: text }),
            });
            setContent(text);
            setPreview(result);
            setFilename(file.name);
        }
        catch (cause) {
            toast.error(cause instanceof Error ? cause.message : '无法预览文件');
        }
        finally {
            setBusy(false);
        }
    }
    async function savePreferences(next: BossPreferences) {
        setPreferencesBusy(true);
        try {
            const saved = await apiRequest<BossPreferences>('/platform-leads/preferences', {
                method: 'PUT', body: JSON.stringify(next),
            });
            setPreferences(saved);
            await load(true);
            toast.success('求职身份已更新，岗位与 AI 判断已按新条件重算');
        }
        catch (cause) {
            toast.error(cause instanceof Error ? cause.message : '求职身份保存失败');
        }
        finally {
            setPreferencesBusy(false);
        }
    }
    async function importFile() {
        if (!content)
            return;
        setBusy(true);
        try {
            const result = await apiRequest<ImportResult>('/platform-leads/import', {
                method: 'POST', body: JSON.stringify({ content }),
            });
            toast.success(`导入完成：新增 ${result.new}，更新 ${result.updated}，未变化 ${result.unchanged}`);
            setContent('');
            setPreview(null);
            setFilename('');
            await load();
        }
        catch (cause) {
            toast.error(cause instanceof Error ? cause.message : '导入失败');
        }
        finally {
            setBusy(false);
        }
    }
    async function startProfiledCrawl() {
        setCrawlStarting(true);
        try {
            const next = await apiRequest<CrawlStatus>('/platform-leads/crawl', {
                method: 'POST',
                body: JSON.stringify({
                    keyword: crawlKeyword.trim(), city: crawlCity.trim(),
                    pages: crawlPages, maxDetails: crawlMaxDetails,
                }),
            });
            setCrawlStatus(next);
            toast.success(`已开始按简历抓取 ${crawlPlan?.searches.length ?? '多个'} 个方向`);
        }
        catch (cause) {
            toast.error(cause instanceof Error ? cause.message : '无法开始抓取');
        }
        finally {
            setCrawlStarting(false);
        }
    }
    async function openBossBrowser() {
        setBrowserOpening(true);
        try {
            await apiRequest<{
                ready: boolean;
            }>('/platform-leads/crawl/browser', { method: 'POST' });
            toast.success('BOSS 专用 Edge 已打开；请在窗口中确认登录状态');
        }
        catch (cause) {
            toast.error(cause instanceof Error ? cause.message : '无法打开 BOSS 专用 Edge');
        }
        finally {
            setBrowserOpening(false);
        }
    }
    async function toggleState(lead: PlatformLead, field: StateField) {
        const current = field === 'favorite' ? lead.isFavorite : field === 'applied' ? lead.isApplied : lead.isHidden;
        try {
            await apiRequest(`/platform-leads/${encodeURIComponent(lead.id)}/state`, {
                method: 'POST', body: JSON.stringify({ field, value: !current }),
            });
            await load();
        }
        catch (cause) {
            toast.error(cause instanceof Error ? cause.message : '状态保存失败');
        }
    }
    return (<div className="min-w-0 max-w-full space-y-6 overflow-x-hidden">
      {!embedded && <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">平台机会池</h1>
        <p className="max-w-2xl text-sm leading-6 text-ink-secondary">
          集中查看 AI/FDE 岗位，校招和应届优先。这里的职位来自 BOSS 平台，投递前可打开原始页面核对。
        </p>
      </header>}

      <Dialog open={manageOpen} onOpenChange={setManageOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader><DialogTitle>获取 BOSS 岗位</DialogTitle></DialogHeader>
          <div className="space-y-5">
            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-ink">按简历筛选抓取</h3>
          <p className="text-xs leading-5 text-ink-secondary">自动搜索简历支持的初级技术方向，先筛列表，再用小米 MiMo 核对少量完整 JD。</p>
          {crawlPlan && <p className="text-xs leading-5 text-ink-secondary">本次覆盖 {crawlPlan.searches.length} 个方向：{crawlPlan.searches.map((item) => item.family).join('、')}。简历证据含 {crawlPlan.resumeProjectCount} 个项目。</p>}
          {crawlPlanError && <p role="alert" className="text-xs text-danger">{crawlPlanError}</p>}
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs text-ink-secondary">补充关键词（可选）
              <Input value={crawlKeyword} onChange={(event) => setCrawlKeyword(event.target.value)} className="w-48" placeholder="如 数字化研发" maxLength={40}/>
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-secondary">城市
              <Input value={crawlCity} onChange={(event) => setCrawlCity(event.target.value)} className="w-28" placeholder="全国" maxLength={30}/>
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-secondary">每方向页数
              <select value={crawlPages} onChange={(event) => setCrawlPages(Number(event.target.value))} className="block h-9 rounded-md border bg-surface px-3 text-sm text-ink"><option value={1}>1 页</option><option value={2}>2 页</option></select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-secondary">最多读 JD
              <select value={crawlMaxDetails} onChange={(event) => setCrawlMaxDetails(Number(event.target.value))} className="block h-9 rounded-md border bg-surface px-3 text-sm text-ink"><option value={4}>4 条</option><option value={8}>8 条</option><option value={12}>12 条</option></select>
            </label>
            <Button size="sm" disabled={crawlStarting || crawlStatus?.state === 'running' || crawlKeyword.trim().length === 1 || !crawlCity.trim() || Boolean(crawlPlanError)} onClick={() => { void startProfiledCrawl(); }}>
              {crawlStatus?.state === 'running' ? '抓取中…' : '开始筛选抓取'}
            </Button>
            <Button size="sm" variant="outline" disabled={browserOpening} onClick={() => { void openBossBrowser(); }}>
              {browserOpening ? '正在打开…' : '打开 BOSS 登录窗口'}
            </Button>
          </div>
          {crawlStatus && crawlStatus.state !== 'idle' && <p role="status" className={`text-xs ${crawlStatus.state === 'failed' ? 'text-danger' : 'text-ink-secondary'}`}>
            {crawlStatus.stage}{crawlStatus.counts.listed ? ` · 列表 ${crawlStatus.counts.listed} 条` : ''}{crawlStatus.counts.shortlisted !== undefined ? ` · 读 JD ${crawlStatus.counts.shortlisted} 条` : ''}{crawlStatus.state === 'complete' ? ` · 保留 ${crawlStatus.counts.accepted ?? 0} 条` : ''}{crawlStatus.counts.ai_failed ? ` · MiMo 未完成 ${crawlStatus.counts.ai_failed} 条` : ''}
          </p>}
          {crawlStatus?.state === 'complete' && <p className="text-xs text-ink-tertiary">
            本批跳过：近期已审 {crawlStatus.counts.recently_reviewed ?? 0} 条、明确硬条件 {crawlStatus.counts.hard_rejected ?? 0} 条、非目标方向 {crawlStatus.counts.off_target ?? 0} 条、招聘方不明 {crawlStatus.counts.unclear_company ?? 0} 条、MiMo 判断不合适 {crawlStatus.counts.ai_rejected ?? 0} 条。
          </p>}
            </section>

      <details className="border-t border-black/[0.08] pt-4">
        <summary className="cursor-pointer text-sm font-medium text-ink">手动导入 JSON（跳过抓取前筛选）</summary>
      <div className="mt-3 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <FileJson className="mt-0.5 size-5 shrink-0 text-brand-foreground"/>
            <div className="min-w-0">
              <h2 className="font-semibold text-ink">导入 BOSS 抓取结果</h2>
              <p className="text-xs leading-5 text-ink-secondary">
                支持 boss-zhipin-scraper 导出的职位列表或详情 JSON；文件只上传到本机 Career Radar。{' '}
                <a href="https://github.com/eatmoreduck/boss-zhipin-scraper" target="_blank" rel="noreferrer" className="text-brand-foreground underline-offset-2 hover:underline">查看抓取工具</a>
              </p>
            </div>
          </div>
          <Input id="boss-json-file" type="file" accept=".json,application/json" aria-label="选择 BOSS 职位 JSON 文件" className="sr-only" onChange={(event) => { void chooseFile(event.target.files?.[0]); }}/>
          <Button asChild variant="outline" className="w-full sm:w-auto"><label htmlFor="boss-json-file" className="cursor-pointer">选择 JSON 文件</label></Button>
        </div>
        {preview && (<div className="flex flex-wrap items-center gap-3 rounded-lg bg-brand-soft p-3 text-sm">
            <span className="font-medium">{filename}</span>
            <span>共 {preview.total} 条</span>
            <span>完整 JD {preview.completeJd} 条</span>
            <span>需确认 {preview.needsReview} 条</span>
            <Button size="sm" onClick={() => { void importFile(); }} disabled={busy}>确认导入</Button>
          </div>)}
      </div>
      </details>

      {preferences && (<details className="border-t border-black/[0.08] pt-4">
          <summary className="cursor-pointer text-sm font-medium text-ink">求职身份 · {preferences.currentStudent === false ? '已毕业' : preferences.currentStudent ? '在校' : '待确认'} · {preferences.acceptInternship ? '接受实习' : '不接受实习'}</summary>
        <div className="mt-4 flex flex-col items-stretch gap-4 sm:flex-row sm:items-center">
          <div className="w-full min-w-0 sm:flex-1">
            <p className="text-sm font-semibold text-ink">你的当前求职身份</p>
            <p className="text-xs text-ink-secondary">已毕业时排除明确要求在校生的岗位；关闭实习后保留应届正式岗和初级社招。</p>
          </div>
          <label className="flex w-full items-center justify-between gap-2 text-sm text-ink-secondary sm:w-auto sm:justify-start">
            在校状态
            <select value={preferences.currentStudent === null ? 'unknown' : preferences.currentStudent ? 'student' : 'graduated'} disabled={preferencesBusy} onChange={(event) => {
                void savePreferences({
                    ...preferences,
                    currentStudent: event.target.value === 'unknown' ? null : event.target.value === 'student',
                });
            }} className="h-9 rounded-lg border bg-surface px-3 text-ink">
              <option value="unknown">待确认</option>
              <option value="graduated">已毕业</option>
              <option value="student">仍在校</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-secondary">
            <input type="checkbox" checked={preferences.acceptInternship} disabled={preferencesBusy} onChange={(event) => { void savePreferences({ ...preferences, acceptInternship: event.target.checked }); }}/>
            接受实习岗位
          </label>
        </div>
        </details>)}
          </div>
        </DialogContent>
      </Dialog>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="boss-category" className="text-sm font-medium text-ink-secondary">查看</label>
          <select id="boss-category" value={category} onChange={(event) => setCategory(event.target.value as Category | 'all')} className="h-9 rounded-lg border bg-surface px-3 text-sm text-ink">
            {CATEGORIES.map((item) => <option key={item.value} value={item.value}>{item.label} · {counts[item.value] ?? 0}</option>)}
          </select>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {batchProgress ? (<>
                <span className="text-xs text-ink-secondary">MiMo {batchProgress.done}/{batchProgress.total}</span>
                <Button size="sm" variant="outline" onClick={() => { stopAfterCurrent.current = true; }}>当前条完成后停止</Button>
              </>) : aiQueue.length > 0 ? (<Button size="sm" variant="outline" disabled={workingId !== null} title="使用小米 MiMo 顺序核对最多 20 条完整 JD；已排除岗位自动跳过" onClick={() => { void screenBatch(); }}>
                <Sparkles className="size-4"/>MiMo 筛选 {aiQueue.length} 条
              </Button>) : null}
            <Button size="sm" variant="outline" onClick={() => setManageOpen(true)}>
              <Plus className="size-4"/>{crawlStatus?.state === 'running' ? '抓取中' : '获取岗位'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { void load(); }} aria-label="刷新机会">
              <RefreshCw className="size-4"/>
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Input {...search.bind} aria-label="搜索 BOSS 岗位" placeholder="搜索岗位、公司或 JD" className="max-w-md"/>
          <label className="flex items-center gap-2 text-sm text-ink-secondary">
            <input type="checkbox" checked={includeHandled} onChange={(event) => setParams(old => { const next = new URLSearchParams(old); next.set('handled', event.target.checked ? '1' : '0'); return next; })}/>
            显示已投递和已隐藏
          </label>
        </div>
      </section>

      {error && leads.length > 0 && <p role="status" className="text-sm text-danger">刷新失败，保留上次结果。<Button variant="ghost" onClick={() => { void load(true); }}>重试</Button></p>}
      {loading && !leadQuery.data ? <ListSkeleton card/> : error && !leadQuery.data ? <ErrorState description={error} onRetry={() => { void load(); }}/> : visible.length === 0 ? (<EmptyState title={leads.length ? '当前筛选下没有机会' : '还没有导入 BOSS 职位'} description={leads.length ? '切换分组、显示已处理岗位或换个关键词。' : '点击“获取岗位”按简历抓取，或导入已有 JSON。'}/>) : (<div className="space-y-3">
          {visible.map((lead) => (<Card key={lead.id} className="gap-3 p-5"><div id={`lead-${lead.id}`} className="scroll-mt-24"/>{focusLeadId === lead.id && <Button variant="ghost" className="mb-3" onClick={() => { if (params.has('from'))
                navigate(safeJobsReturn(params.get('from')));
            else
                setParams(old => { const next = new URLSearchParams(old); next.delete('lead'); return next; }); }}>关闭选中详情，返回列表</Button>}
              <div className="flex flex-wrap items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-semibold text-ink">{lead.title}</h2>
                    <GrowthTargetButton source="boss" id={lead.id} disabled={!lead.jdComplete}/>
                    <Badge variant={lead.category === 'excluded' ? 'destructive' : 'secondary'}>{CATEGORY_LABEL[lead.category]}</Badge>
                    {!lead.jdComplete && <Badge variant="outline">JD 待确认</Badge>}
                    {!lead.companyIdentified && <Badge variant="outline">招聘方待核对</Badge>}
                    {lead.jdComplete && !lead.aiScreenable && <Badge variant="outline">JD 较长，请人工核对</Badge>}
                    {lead.isApplied && <Badge variant="outline">已投递</Badge>}
                  </div>
                  <p className="mt-1 text-sm text-ink-secondary">
                    {lead.company || '公司待确认'} · {lead.location || '地点未提供'} · {lead.salary || '薪资未提供'}
                  </p>
                </div>
                <span className="text-xs font-medium text-ink-secondary" title="阅读优先级，并非录取概率">
                  阅读排序 {lead.score}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                <SourceNote kind="boss"/>
                {lead.tags && <Badge variant="outline">{lead.tags}</Badge>}
                <span className="self-center text-xs text-ink-tertiary" title="本机最近导入或抓取到该职位的日期，不是 BOSS 发布日期">最近见到 {localDate(lead.lastSeenAt)}</span>
              </div>
              {(lead.blockers.length > 0 || lead.reasons.length > 0) && <details className="text-sm text-ink-secondary">
                <summary className="cursor-pointer font-medium text-brand-foreground">查看筛选理由</summary>
                <div className="mt-2 space-y-1">
                  {lead.blockers.map((reason) => <p key={reason} className="text-danger">{reason}</p>)}
                  {lead.reasons.map((reason) => <p key={reason}>· {reason}</p>)}
                  <p className="text-xs text-ink-tertiary">本机首次导入 {localDate(lead.firstSeenAt)}</p>
                </div>
              </details>}
              {lead.description && (<details className="rounded-lg bg-surface-subtle p-3 text-sm">
                  <summary className="cursor-pointer font-medium">查看完整 JD</summary>
                  <pre className="mt-3 whitespace-pre-wrap break-words font-sans reading-copy">{lead.description}</pre>
                </details>)}
              {lead.aiResult ? (<div className="min-w-0 space-y-2 break-words rounded-lg bg-brand-soft p-4 text-sm">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline">{ELIGIBILITY_LABEL[lead.aiResult.eligibility]}</Badge>
                    <Badge variant="outline">{FIT_LABEL[lead.aiResult.fit]}</Badge>
                    <Badge variant="outline">{ACTION_LABEL[lead.aiResult.action]}</Badge>
                    <span className="self-center text-xs text-ink-tertiary">
                      AI 分析于 {lead.aiCheckedAt ? localDate(lead.aiCheckedAt) : '最近'} · 非录用保证
                    </span>
                  </div>
                  <details><summary className="cursor-pointer text-ink">画像匹配判断 · 查看分析</summary><p className="mt-2 reading-copy text-ink">{lead.aiResult.summary}</p></details>
                  {lead.aiResult.eligibility_checks.length > 0 && (<details>
                      <summary className="cursor-pointer text-xs font-medium text-brand-foreground">查看资格判断依据</summary>
                      <ul className="mt-2 space-y-1 text-xs text-ink-secondary">
                        {lead.aiResult.eligibility_checks.map((check, index) => (<li key={index}>
                            {check.requirement}：{check.verdict === 'met' ? '符合' : check.verdict === 'unmet' ? '不符合' : '待确认'}
                            {check.job_quote && ` · JD「${check.job_quote}」`}
                            {check.candidate_quote && ` · 画像「${check.candidate_quote}」`}
                          </li>))}
                      </ul>
                    </details>)}
                  {lead.aiResult.matched_evidence.length > 0 && <p className="text-xs text-ink-secondary">已有证据：{lead.aiResult.matched_evidence.join('、')}</p>}
                  {lead.aiResult.gaps.length > 0 && <p className="text-xs text-ink-secondary">仍需确认：{lead.aiResult.gaps.join('；')}</p>}
                  <p className="text-xs text-ink-secondary">下一步：{lead.aiResult.next_step}</p>
                  {lead.aiResult.fit === 'weak' && (<p className="text-xs text-ink-secondary">
                      判断只依据当前画像。如果你有尚未记录的真实 AI/Agent 项目，
                      <Link to="/profile" className="text-brand-foreground underline-offset-2 hover:underline">先补充画像证据</Link>，岗位会自动显示为需要重新评估。
                    </p>)}
                </div>) : lead.aiNeedsRefresh ? (<p className="text-xs text-ink-secondary">岗位、画像或模型已变化，原 AI 结果已失效。</p>) : null}
              <div className="flex flex-wrap gap-2">
                {lead.aiScreenable && lead.category !== 'excluded' && !lead.aiResult && (<Button size="sm" variant="outline" disabled={workingId !== null || batchProgress !== null} onClick={() => { void screenOne(lead.id); }}>
                    <Sparkles className="size-4"/>
                    {workingId === lead.id ? '分析中…' : lead.aiNeedsRefresh ? '更新 AI 判断' : 'AI 判断能否投'}
                  </Button>)}
                <Button size="sm" variant="outline" onClick={() => { void toggleState(lead, 'favorite'); }}>
                  <Bookmark className="size-4"/>{lead.isFavorite ? '已收藏' : '收藏'}
                </Button>
                <Button size="sm" asChild>
                  <a href={lead.source_url} target="_blank" rel="noreferrer">
                    去 BOSS 查看 <ArrowUpRight className="size-4"/>
                  </a>
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild><Button size="sm" variant="ghost" aria-label={`更多操作：${lead.title}`}><MoreHorizontal className="size-4"/>更多</Button></DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => { void toggleState(lead, 'applied'); }}>{lead.isApplied ? '取消已投递' : '标记已投递'}</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => { void toggleState(lead, 'hidden'); }}>{lead.isHidden ? '恢复显示' : '不感兴趣'}</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </Card>))}
        </div>)}
    </div>);
}
