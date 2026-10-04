type SourceKind = 'official' | 'boss'

/** 来源始终用文字呈现，避免把平台线索误认为已核验的官网岗位。 */
export function SourceNote({ kind, site }: { kind: SourceKind; site?: string }) {
  const official = kind === 'official'
  return (
    <span
      className="inline-flex max-w-[170px] flex-col rounded-md bg-surface-subtle px-2 py-0.5 text-xs font-medium leading-5 text-ink-secondary"
      title={official ? `来源：企业招聘页${site ? `（${site}）` : ''}` : '来源：BOSS直聘；投递前核对原始职位'}
    >
      <span>{official ? '企业招聘页' : 'BOSS直聘 · 待核对'}</span>
      {official && site && <span className="block max-w-full truncate text-[11px] font-normal text-ink-tertiary">{site}</span>}
    </span>
  )
}
