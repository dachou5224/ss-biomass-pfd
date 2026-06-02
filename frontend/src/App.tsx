import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchInputTemplate, runFullSimulation } from './api'
import { chemistryFieldMeta, splitChemistryRows } from './chemistryFields'
import type {
  BootstrapResponse,
  ChemistryRow,
  FeedRow,
  FullComputeResponse,
  FullSimulationPayload,
} from './types'
import './App.css'

const CASE_OPTIONS = ['Case-1', 'Case-2', 'Case-3']
const COMPOSITION_ORDER = ['H2', 'CO', 'CO2', 'CH4', 'H2O', 'N2', 'Ar', 'H2S', 'NH3', 'COS', 'HCl']

const FEED_GROUPS = [
  {
    title: 'INCI 进料',
    subtitle: '核心边界流：生物质、载气、氧化剂与工艺水',
    streams: ['Biomass', 'CO2IN', 'CIN', 'H2OIN', 'O2IN', 'N2IN'],
  },
  {
    title: 'RGPOX 进料',
    subtitle: 'POX 段补氧',
    streams: ['O2POX'],
  },
  {
    title: 'SLAG 段返气 / 补充',
    subtitle: '后续返气与补加流',
    streams: ['POSTO2', 'POSTH2O', 'POSTCO2'],
  },
] as const

function formatNumber(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

function sortCompositionEntries(composition: Record<string, number> | undefined) {
  return Object.entries(composition ?? {})
    .filter(([, value]) => Math.abs(Number(value)) > 1e-6)
    .sort(([left], [right]) => {
      const leftIndex = COMPOSITION_ORDER.indexOf(left)
      const rightIndex = COMPOSITION_ORDER.indexOf(right)
      if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right)
      if (leftIndex === -1) return 1
      if (rightIndex === -1) return -1
      return leftIndex - rightIndex
    })
}

function compositionKeys(...compositions: Array<Record<string, number> | undefined>) {
  return Array.from(new Set(compositions.flatMap((composition) => sortCompositionEntries(composition).map(([key]) => key))))
}

function uniqueValues(rows: Array<Record<string, string>>, field: string) {
  return Array.from(new Set(rows.map((row) => row[field]).filter(Boolean)))
}

function effectiveGasContent(composition: Record<string, number> | undefined) {
  return (composition?.H2 ?? 0) + (composition?.CO ?? 0)
}

function renderChemistryField(
  row: ChemistryRow,
  onChange: (field: string, value: string) => void,
) {
  const meta = chemistryFieldMeta(row.Field)
  const value = String(row.Value ?? '')

  return (
    <label key={row.Field} className="chemistry-field">
      <span>{meta.label}</span>
      {meta.kind === 'select' ? (
        <select value={value} onChange={(event) => onChange(row.Field, event.target.value)}>
          {(meta.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : meta.kind === 'number' ? (
        <input
          type="number"
          step={meta.step ?? 1}
          min={meta.min}
          max={meta.max}
          value={value}
          onChange={(event) => onChange(row.Field, event.target.value)}
        />
      ) : (
        <input
          type="text"
          value={value}
          placeholder="留空=自动"
          onChange={(event) => onChange(row.Field, event.target.value)}
        />
      )}
      <small className="chemistry-field-hint">{meta.hint}</small>
    </label>
  )
}

function App() {
  const [selectedCase, setSelectedCase] = useState('Case-1')
  const [systemPBar, setSystemPBar] = useState(15)
  const [feedRows, setFeedRows] = useState<FeedRow[]>([])
  const [chemistryRows, setChemistryRows] = useState<ChemistryRow[]>([])
  const [o2inComposition, setO2inComposition] = useState({ O2: 0, N2: 0, Ar: 0 })
  const [templateInfo, setTemplateInfo] = useState<BootstrapResponse['checks'] | null>(null)
  const [result, setResult] = useState<FullComputeResponse | null>(null)
  const [isLoadingTemplate, setIsLoadingTemplate] = useState(true)
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState('')

  const o2Sum = useMemo(
    () => o2inComposition.O2 + o2inComposition.N2 + o2inComposition.Ar,
    [o2inComposition],
  )
  const negativeFeedCount = useMemo(
    () => feedRows.filter((row) => row.MassFlow_kg_h < 0).length,
    [feedRows],
  )
  const totalFeed = useMemo(
    () => feedRows.reduce((sum, row) => sum + row.MassFlow_kg_h, 0),
    [feedRows],
  )
  const { standard: standardChemistryRows, advancedInciSolid: advancedInciSolidRows } = useMemo(
    () => splitChemistryRows(chemistryRows),
    [chemistryRows],
  )

  const loadTemplate = useCallback(async (caseId: string) => {
    setIsLoadingTemplate(true)
    setError('')
    try {
      const data = await fetchInputTemplate(caseId)
      hydrateFromTemplate(data)
      setResult(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '模板加载失败')
    } finally {
      setIsLoadingTemplate(false)
    }
  }, [])

  function hydrateFromTemplate(data: BootstrapResponse) {
    setSelectedCase(data.inputs.case_id)
    setSystemPBar(Number(data.inputs.system_p_bar))
    setFeedRows(data.tables.feed)
    setChemistryRows(data.tables.chemistry.map((row) => ({ ...row, Value: row.Value ?? '' })))
    setO2inComposition({
      O2: Number(data.inputs.o2in_composition.O2 ?? 0),
      N2: Number(data.inputs.o2in_composition.N2 ?? 0),
      Ar: Number(data.inputs.o2in_composition.Ar ?? 0),
    })
    setTemplateInfo(data.checks)
  }

  useEffect(() => {
    void loadTemplate('Case-1')
  }, [loadTemplate])

  function updateFeedRow(stream: string, key: keyof FeedRow, value: number) {
    setFeedRows((rows) =>
      rows.map((row) => (row.Stream === stream ? { ...row, [key]: value } : row)),
    )
  }

  function updateChemistryRow(field: string, value: string) {
    setChemistryRows((rows) =>
      rows.map((row) => (row.Field === field ? { ...row, Value: value } : row)),
    )
  }

  const groupedFeeds = FEED_GROUPS.map((group) => ({
    ...group,
    rows: group.streams
      .map((stream) => feedRows.find((row) => row.Stream === stream))
      .filter((row): row is FeedRow => Boolean(row)),
  }))

  const payload: FullSimulationPayload = {
    case_id: selectedCase,
    system_p_bar: systemPBar,
    pfd_feeds: Object.fromEntries(
      feedRows.map((row) => [
        row.Stream,
        {
          mass_kg_h: Number(row.MassFlow_kg_h),
          temp_c: Number(row.Temp_C),
          pressure_bar: Number(row.Pressure_bar),
        },
      ]),
    ),
    o2in_composition: o2inComposition,
    chemistry: Object.fromEntries(chemistryRows.map((row) => [row.Field, row.Value])),
  }

  const equipmentSections = result
    ? [
        {
          key: 'inci',
          title: result.compositions.inci.title,
          equipmentId: result.compositions.inci.equipment_id,
          description: 'INCI 出口气组成，干/湿基共用同一主产物流。',
          dryStreamId: result.compositions.inci.dry_stream_id,
          wetStreamId: result.compositions.inci.wet_stream_id,
          dryVolPct: result.compositions.inci.dry_vol_pct,
          wetVolPct: result.compositions.inci.wet_vol_pct,
          streamRows: [
            { label: '状态基准', unit: '—', dry: '干基', wet: '湿基' },
            { label: '主产气流量', unit: 'kg/h', dry: '—', wet: formatNumber(result.result_summary.inci_top_kg_h, 0) },
            { label: 'Tar', unit: 'kg/h', dry: formatNumber(result.result_summary.inci_tar_kg_h, 1), wet: '—' },
            { label: 'INCI 渣', unit: 'kg/h', dry: formatNumber(result.result_summary.inci_slag_kg_h, 0), wet: '—' },
            ...compositionKeys(result.compositions.inci.dry_vol_pct, result.compositions.inci.wet_vol_pct).map((species) => ({
              label: species,
              unit: 'vol%',
              dry: formatNumber(result.compositions.inci.dry_vol_pct[species], 3),
              wet: formatNumber(result.compositions.inci.wet_vol_pct[species], 3),
            })),
          ],
          metrics: [
            {
              label: '13PGI-1 气体',
              value: `${formatNumber(result.result_summary.inci_top_kg_h, 0)} kg/h`,
            },
            {
              label: 'Tar',
              value: `${formatNumber(result.result_summary.inci_tar_kg_h, 1)} kg/h`,
            },
            {
              label: 'INCI 渣',
              value: `${formatNumber(result.result_summary.inci_slag_kg_h, 0)} kg/h`,
            },
          ],
        },
        {
          key: 'pox',
          title: result.compositions.pox.title,
          equipmentId: result.compositions.pox.equipment_id,
          description: 'POX 段显示反应器出口干基气体与急冷后湿基气体，便于对应 15PGR-1 / 15PGR-2。',
          dryStreamId: result.compositions.pox.dry_stream_id,
          wetStreamId: result.compositions.pox.wet_stream_id,
          dryVolPct: result.compositions.pox.dry_vol_pct,
          wetVolPct: result.compositions.pox.wet_vol_pct,
          streamRows: [
            { label: '状态基准', unit: '—', dry: '干基', wet: '湿基' },
            { label: '反应后主气', unit: 'kg/h', dry: '—', wet: formatNumber(result.result_summary.pox_gas_kg_h, 0) },
            { label: 'POX 灰渣', unit: 'kg/h', dry: formatNumber(result.result_summary.pox_ash_kg_h, 0), wet: '—' },
            { label: 'Quench 出口温度', unit: '°C', dry: '—', wet: formatNumber(result.result_summary.quench_t_out_c, 1) },
            ...compositionKeys(result.compositions.pox.dry_vol_pct, result.compositions.pox.wet_vol_pct).map((species) => ({
              label: species,
              unit: 'vol%',
              dry: formatNumber(result.compositions.pox.dry_vol_pct[species], 3),
              wet: formatNumber(result.compositions.pox.wet_vol_pct[species], 3),
            })),
          ],
          metrics: [
            {
              label: '15PGR-2 气体',
              value: `${formatNumber(result.result_summary.pox_gas_kg_h, 0)} kg/h`,
            },
            {
              label: 'POX 灰渣',
              value: `${formatNumber(result.result_summary.pox_ash_kg_h, 0)} kg/h`,
            },
            {
              label: 'Quench 出口温度',
              value: `${formatNumber(result.result_summary.quench_t_out_c, 1)} °C`,
            },
          ],
        },
      ]
    : []

  const feedStreamSections = result
    ? uniqueValues(
        result.tables.feed_summary.map((row) =>
          Object.fromEntries(Object.entries(row).map(([key, value]) => [key, String(value ?? '')])),
        ),
        '工段',
      ).map((sectionName) => {
        const rows = result.tables.feed_summary
          .map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, String(value ?? '')])))
          .filter((row) => row['工段'] === sectionName)
        return {
          key: sectionName,
          title: sectionName,
          streamIds: rows.map((row) => row.PFD),
          streamRows: [
            {
              label: '进料项',
              unit: '—',
              values: rows.map((row) => row['进料项']),
            },
            {
              label: '模型 Stream',
              unit: '—',
              values: rows.map((row) => row['模型 Stream']),
            },
            {
              label: '质量流量',
              unit: 'kg/h',
              values: rows.map((row) => row['kg/h']),
            },
            {
              label: '温度',
              unit: '°C',
              values: rows.map((row) => row['°C']),
            },
            {
              label: '压力',
              unit: 'bar',
              values: rows.map((row) => row['bar']),
            },
          ],
        }
      })
    : []

  const keyMetricSections = result
    ? [
        {
          key: 'inci',
          title: 'INCI 关键指标',
          subtitle: '对应 INCI 炉出口与 13PGI-1 物流。',
          metrics: [
            {
              label: '碳转化率',
              value: `${formatNumber(result.performance.carbon_conversion_inci_pct, 1)} %`,
            },
            {
              label: '冷煤气效率',
              value: `${formatNumber(result.performance.cold_gas_efficiency_inci_pct, 1)} %`,
            },
            {
              label: '有效气含量',
              value: `${formatNumber(effectiveGasContent(result.compositions.inci.dry_vol_pct), 2)} %`,
            },
          ],
        },
        {
          key: 'pox',
          title: 'POX 关键指标',
          subtitle: '对应 POX 段出口与 15PGR-1 / 15PGR-2 物流。',
          metrics: [
            {
              label: '碳转化率',
              value: `${formatNumber(result.performance.carbon_conversion_pox_pct, 1)} %`,
            },
            {
              label: '冷煤气效率',
              value: `${formatNumber(result.performance.cold_gas_efficiency_pox_pct, 1)} %`,
            },
            {
              label: '有效气含量',
              value: `${formatNumber(effectiveGasContent(result.compositions.pox.dry_vol_pct), 2)} %`,
            },
          ],
        },
      ]
    : []

  const solidRouting = result?.inci_solid_routing ?? null
  const entrainedSolidKgH =
    solidRouting !== null
      ? solidRouting.fly_ash_total_kg_h ??
        solidRouting.char_to_pox_kg_h + solidRouting.ash_to_pox_kg_h
      : null

  const solidRoutingMetrics = solidRouting
    ? [
        {
          label: '路由模式',
          value: solidRouting.mode ?? '—',
        },
        {
          label: '灰渣比（飞灰/底渣）',
          value: formatNumber(solidRouting.fly_ash_to_slag_ratio, 3),
        },
        {
          label: '飞灰总量（夹带）',
          value: `${formatNumber(entrainedSolidKgH, 1)} kg/h`,
        },
        {
          label: 'Char → POX',
          value: `${formatNumber(solidRouting.char_to_pox_kg_h, 1)} kg/h`,
        },
        {
          label: 'Ash → POX',
          value: `${formatNumber(solidRouting.ash_to_pox_kg_h, 1)} kg/h`,
        },
        {
          label: '13LBS-1 底渣',
          value: `${formatNumber(solidRouting.slag_to_u14_kg_h, 0)} kg/h`,
        },
        {
          label: '整体碳转化率',
          value: `${formatNumber(solidRouting.overall_biomass_carbon_conversion_pct, 2)} %`,
        },
      ]
    : []

  async function handleRun() {
    if (isLoadingTemplate || isRunning || feedRows.length === 0 || negativeFeedCount > 0 || Math.abs(o2Sum - 100) > 0.5) {
      return
    }
    setIsRunning(true)
    setError('')
    try {
      const data = await runFullSimulation(payload)
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '求解失败')
    } finally {
      setIsRunning(false)
    }
  }

  const noticeTone =
    error || negativeFeedCount > 0 ? 'danger' : Math.abs(o2Sum - 100) > 0.5 ? 'warn' : 'info'
  const runBlockedReason = isLoadingTemplate
    ? '正在载入模板…'
    : feedRows.length === 0
      ? error ? '模板载入失败，请重试' : '先载入模板默认值'
      : negativeFeedCount > 0
        ? '先修正负流量'
        : Math.abs(o2Sum - 100) > 0.5
          ? '先把 O2IN 调到约 100%'
          : ''
  const canRun = !isRunning && !runBlockedReason
  const noticeText = error
    ? error
    : negativeFeedCount > 0
      ? '存在负流量，请先修正输入。'
      : Math.abs(o2Sum - 100) > 0.5
        ? `O2IN 当前合计 ${formatNumber(o2Sum, 2)}%，建议先调到 100% 左右再求解。`
        : result
          ? result.result_summary.matched_case
            ? `已完成 ${result.result_summary.matched_case} 求解，结果表已刷新。`
            : '自定义工况已求解；结果有效。'
          : '模板已载入。调整左侧输入后，点击“运行求解并刷新结果”查看结果。'

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Biomass Gasifier Web UI · React + Vite MVP</p>
          <h1>生物质气化过程模拟器</h1>
          <p className="subtitle">
            同源代理到现有 Python 计算服务：左侧编辑输入，右侧查看结果总览与工况核查。
          </p>
        </div>
        <div className="topbar-badges">
          <span className="badge">Case {selectedCase}</span>
          <span className={`badge ${result ? 'badge-ok' : 'badge-info'}`}>
            {result ? '已求解' : isLoadingTemplate ? '模板载入中' : '待求解'}
          </span>
        </div>
      </header>

      <section className="overview-grid">
        <article className="overview-card">
          <span className="label">总进料</span>
          <strong>{formatNumber(totalFeed, 0)} kg/h</strong>
          <span className="meta">模板基线 {formatNumber(templateInfo?.total_feed_kg_h, 0)} kg/h</span>
        </article>
        <article className="overview-card">
          <span className="label">O2IN 合计</span>
          <strong>{formatNumber(o2Sum, 2)} %</strong>
          <span className="meta">负流量 {negativeFeedCount} 条</span>
        </article>
        <article className="overview-card">
          <span className="label">冷煤气效率 (总)</span>
          <strong>{formatNumber(result?.performance.cold_gas_efficiency_pct, 1)} %</strong>
          <span className="meta">
            INCI {formatNumber(result?.performance.cold_gas_efficiency_inci_pct, 1) ?? '—'} %
            &nbsp;|&nbsp;
            POX {formatNumber(result?.performance.cold_gas_efficiency_pox_pct, 1) ?? '—'} %
          </span>
        </article>
        <article className="overview-card">
          <span className="label">工况来源</span>
          <strong>{result?.result_summary.matched_case ?? '未求解 / 自定义'}</strong>
          <span className="meta">自定义工况不当作 warning</span>
        </article>
      </section>

      <div className={`notice notice-${noticeTone}`}>{noticeText}</div>

      <div className="page-grid">
        <aside className="panel controls-panel">
          <div className="panel-header">
            <div>
              <h2>用户输入</h2>
              <p>模板加载、边界流编辑与扩展化学参数。</p>
            </div>
            {isLoadingTemplate ? <span className="mini-status">载入中…</span> : null}
          </div>

          <section className="section-card">
            <div className="section-head">
              <h3>工况与系统边界</h3>
              <p>切换 Case 后，点击按钮重新载入模板。</p>
            </div>
            <div className="inline-grid">
              <label>
                <span>工况 CASE</span>
                <select value={selectedCase} onChange={(event) => setSelectedCase(event.target.value)}>
                  {CASE_OPTIONS.map((caseId) => (
                    <option key={caseId} value={caseId}>
                      {caseId}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>系统压力 [bar]</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  step={0.5}
                  value={systemPBar}
                  onChange={(event) => setSystemPBar(Number(event.target.value))}
                />
              </label>
            </div>
            <div className="button-row">
              <button type="button" className="button secondary" onClick={() => void loadTemplate(selectedCase)}>
                载入模板默认值
              </button>
              <button type="button" className="button primary" disabled={!canRun} onClick={() => void handleRun()}>
                {isRunning ? '求解中…' : runBlockedReason || '运行求解并刷新结果'}
              </button>
            </div>
          </section>

          {groupedFeeds.map((group) => (
            <section key={group.title} className="section-card">
              <div className="section-head">
                <h3>{group.title}</h3>
                <p>{group.subtitle}</p>
              </div>
              <div className="feed-stack">
                {group.rows.length === 0 ? (
                  <p className="empty-state">请先点击「载入模板默认值」</p>
                ) : group.rows.map((row) => (
                  <div key={row.Stream} className="feed-card">
                    <div className="feed-card-head">
                      <strong>{row.Stream}</strong>
                    </div>
                    <div className="triple-grid">
                      <label>
                        <span>流量 kg/h</span>
                        <input
                          type="number"
                          step={10}
                          value={row.MassFlow_kg_h}
                          onChange={(event) =>
                            updateFeedRow(row.Stream, 'MassFlow_kg_h', Number(event.target.value))
                          }
                        />
                      </label>
                      <label>
                        <span>温度 °C</span>
                        <input
                          type="number"
                          step={5}
                          value={row.Temp_C}
                          onChange={(event) => updateFeedRow(row.Stream, 'Temp_C', Number(event.target.value))}
                        />
                      </label>
                      <label>
                        <span>压力 bar</span>
                        <input
                          type="number"
                          min={0.1}
                          step={0.5}
                          value={row.Pressure_bar}
                          onChange={(event) =>
                            updateFeedRow(row.Stream, 'Pressure_bar', Number(event.target.value))
                          }
                        />
                      </label>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}

          <section className="section-card">
            <div className="section-head">
              <h3>氧化剂 O2IN 组成</h3>
              <p>三个 mol% 数字框，目标合计 100%。</p>
            </div>
            <div className="triple-grid">
              {(['O2', 'N2', 'Ar'] as const).map((key) => (
                <label key={key}>
                  <span>{key} mol%</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.05}
                    value={o2inComposition[key]}
                    onChange={(event) =>
                      setO2inComposition((current) => ({
                        ...current,
                        [key]: Number(event.target.value),
                      }))
                    }
                  />
                </label>
              ))}
            </div>
          </section>

          <details className="section-card details-card" open>
            <summary>化学调参（常规）</summary>
            <p className="details-copy">
              TA 趋近度、WGS/甲烷化 ΔT 等常规 chemistry 字段，直接映射后端计算表。
            </p>
            <div className="chemistry-grid">
              {standardChemistryRows.length === 0 ? (
                <p className="empty-state">请先载入模板默认值</p>
              ) : (
                standardChemistryRows.map((row) => renderChemistryField(row, updateChemistryRow))
              )}
            </div>
          </details>

          <details className="section-card details-card details-card-advanced">
            <summary>INCI 固相路由（高级）</summary>
            <p className="details-copy">
              流化床灰渣比与飞灰/底渣残炭，驱动 13LBS-1 底渣与 15PGI-1 夹带固相分流。默认 Fly Ash Ratio 模式对齐 DBI Case-1。
            </p>
            <div className="chemistry-grid">
              {advancedInciSolidRows.length === 0 ? (
                <p className="empty-state">模板中未找到固相路由字段</p>
              ) : (
                advancedInciSolidRows.map((row) => renderChemistryField(row, updateChemistryRow))
              )}
            </div>
          </details>
        </aside>

        <main className="panel results-panel">
          <div className="panel-header">
            <div>
              <h2>结果总览</h2>
              <p>纯计算结果、主组成和流程对应关系。</p>
            </div>
            <span className={`mini-status ${result ? 'mini-status-ok' : ''}`}>
              {result ? result.status : '尚未求解'}
            </span>
          </div>

          <section className="section-card">
            <div className="section-head">
              <h3>关键指标</h3>
              <p>按设备分别给出碳转化率、冷煤气效率和有效气含量（H2+CO 干基百分比）。</p>
            </div>
            <div className="unit-metrics-grid">
              {keyMetricSections.map((section) => (
                <article key={section.key} className="unit-metrics-card">
                  <div className="composition-head">
                    <h4>{section.title}</h4>
                    <p>{section.subtitle}</p>
                  </div>
                  <div className="results-grid unit-metric-items">
                    {section.metrics.map((metric) => (
                      <article key={`${section.key}-${metric.label}`} className="metric-card">
                        <span>{metric.label}</span>
                        <strong>{metric.value}</strong>
                      </article>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </section>

          {solidRouting ? (
            <section className="section-card solid-routing-card">
              <div className="section-head">
                <h3>INCI 固相路由摘要</h3>
                <p>
                  对应 DBI 13LBS-1 底渣与 15PGI-1 夹带固相（char + fly ash）。求解后随 inci_solid_routing 返回。
                </p>
              </div>
              <div className="results-grid solid-routing-metrics">
                {solidRoutingMetrics.map((metric) => (
                  <article key={metric.label} className="metric-card">
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          <section className="section-card">
            <div className="section-head">
              <h3>PFD 流程简图</h3>
              <p>先看物流编号，再对照下方 INCI / POX 组成表。</p>
            </div>
            <div className="process-diagram-frame">
              <img
                className="process-diagram"
                src="/core-topology.png"
                alt="SS Biomass PFD 简图，标出 INCI、RGPOX、Quench 及 13PGI-1、15PGR-1、15PGR-2 等物流编号"
              />
            </div>
          </section>

          {equipmentSections.map((section) => (
            <section key={section.key} className="section-card equipment-card">
              <div className="section-head">
                <h3>
                  {section.title} · {section.equipmentId}
                </h3>
                <p>{section.description}</p>
              </div>

              <div className="results-grid">
                {section.metrics.map((metric) => (
                  <article key={metric.label} className="metric-card">
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                  </article>
                ))}
              </div>

              <div className="stream-table-wrap">
                <div className="composition-head">
                  <h4>PFD 物流表格式</h4>
                  <p>按“项目行 + 物流编号列”阅读，更接近流程图中的物流表。</p>
                </div>
                <table className="stream-table">
                  <thead>
                    <tr>
                      <th>项目</th>
                      <th>单位</th>
                      <th>{section.dryStreamId} 干基</th>
                      <th>{section.wetStreamId} 湿基</th>
                    </tr>
                  </thead>
                  <tbody>
                    {section.streamRows.map((row) => (
                      <tr key={`${section.key}-${row.label}`}>
                        <td>{row.label}</td>
                        <td>{row.unit}</td>
                        <td>{row.dry}</td>
                        <td>{row.wet}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}

          <section className="section-card">
            <div className="section-head">
              <h3>进料物流表</h3>
              <p>进料也按 PFD stream table 格式呈现，与结果物流保持同一种读法。</p>
            </div>
            <div className="feed-stream-sections">
              {feedStreamSections.map((section) => (
                <div key={section.key} className="stream-table-wrap">
                  <div className="composition-head">
                    <h4>{section.title}</h4>
                    <p>按工段拆分的 PFD 进料物流表。</p>
                  </div>
                  <table className="stream-table">
                    <thead>
                      <tr>
                        <th>项目</th>
                        <th>单位</th>
                        {section.streamIds.map((streamId) => (
                          <th key={`${section.key}-${streamId}`}>{streamId}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {section.streamRows.map((row) => (
                        <tr key={`${section.key}-${row.label}`}>
                          <td>{row.label}</td>
                          <td>{row.unit}</td>
                          {row.values.map((value, index) => (
                            <td key={`${section.key}-${row.label}-${section.streamIds[index]}`}>{value}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}

export default App
