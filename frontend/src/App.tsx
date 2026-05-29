import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchInputTemplate, runFullSimulation } from './api'
import type {
  BootstrapResponse,
  ChemistryRow,
  FeedRow,
  FullComputeResponse,
  FullSimulationPayload,
} from './types'
import './App.css'

const CASE_OPTIONS = ['Case-1', 'Case-2', 'Case-3']

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
      ? '先载入模板默认值'
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
            ? `已完成 ${result.result_summary.matched_case} 求解，对标与组成表已刷新。`
            : '自定义工况已求解；结果有效，但不参与 Case-1/2/3 对标。'
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
          <span className="badge">API /v1/compute/simulate-full</span>
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
          <span className="label">冷煤气效率</span>
          <strong>{formatNumber(result?.performance.cold_gas_efficiency_pct, 1)} %</strong>
          <span className="meta">来自纯计算接口</span>
        </article>
        <article className="overview-card">
          <span className="label">对标工况</span>
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
                {group.rows.map((row) => (
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

          <details className="section-card details-card">
            <summary>扩展物性 / 样品 / 调参</summary>
            <p className="details-copy">
              当前直接映射后端 chemistry 表。这样前端不依赖 Excel 布局，也不必复制后端计算逻辑。
            </p>
            <div className="chemistry-grid">
              {chemistryRows.map((row) => (
                <label key={row.Field}>
                  <span>{row.Field}</span>
                  <input
                    type="text"
                    value={String(row.Value ?? '')}
                    onChange={(event) => updateChemistryRow(row.Field, event.target.value)}
                  />
                </label>
              ))}
            </div>
          </details>
        </aside>

        <main className="panel results-panel">
          <div className="panel-header">
            <div>
              <h2>结果总览</h2>
              <p>纯计算结果、主组成、对标差异和求解追踪。</p>
            </div>
            <span className={`mini-status ${result ? 'mini-status-ok' : ''}`}>
              {result ? result.status : '尚未求解'}
            </span>
          </div>

          <section className="section-card">
            <div className="section-head">
              <h3>关键指标</h3>
              <p>首屏先看产气、Tar、渣和急冷段结果。</p>
            </div>
            <div className="results-grid">
              <article className="metric-card">
                <span>13PGI-1 气体</span>
                <strong>{formatNumber(result?.result_summary.inci_top_kg_h, 0)} kg/h</strong>
              </article>
              <article className="metric-card">
                <span>Tar</span>
                <strong>{formatNumber(result?.result_summary.inci_tar_kg_h, 1)} kg/h</strong>
              </article>
              <article className="metric-card">
                <span>INCI 渣</span>
                <strong>{formatNumber(result?.result_summary.inci_slag_kg_h, 0)} kg/h</strong>
              </article>
              <article className="metric-card">
                <span>RGPOX 气体</span>
                <strong>{formatNumber(result?.result_summary.pox_gas_kg_h, 0)} kg/h</strong>
              </article>
              <article className="metric-card">
                <span>碳转化率</span>
                <strong>{formatNumber(result?.performance.carbon_conversion_pct, 1)} %</strong>
              </article>
              <article className="metric-card">
                <span>H2/CO</span>
                <strong>{formatNumber(result?.performance.h2_co_ratio_dry, 2)}</strong>
              </article>
            </div>
          </section>

          <section className="table-grid">
            <div className="section-card">
              <div className="section-head">
                <h3>INCI 湿基 vol%</h3>
                <p>主产气组成</p>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>组分</th>
                    <th>vol%</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result?.compositions.inci_wet_vol_pct ?? {}).map(([key, value]) => (
                    <tr key={key}>
                      <td>{key}</td>
                      <td>{formatNumber(Number(value), 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="section-card">
              <div className="section-head">
                <h3>RGPOX 湿基 vol%</h3>
                <p>急冷出口主组成</p>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>组分</th>
                    <th>vol%</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result?.compositions.rgpox_wet_vol_pct ?? {}).map(([key, value]) => (
                    <tr key={key}>
                      <td>{key}</td>
                      <td>{formatNumber(Number(value), 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="table-grid">
            <div className="section-card">
              <div className="section-head">
                <h3>INCI 对标偏差</h3>
                <p>仅在匹配标准工况时显示。</p>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>组分</th>
                    <th>DBI</th>
                    <th>模型</th>
                    <th>Δ pp</th>
                  </tr>
                </thead>
                <tbody>
                  {(result?.comparison.inci_wet ?? []).map((row) => (
                    <tr key={String(row['组分'])}>
                      <td>{String(row['组分'])}</td>
                      <td>{row['DBI'] === null || row['DBI'] === undefined ? '—' : String(row['DBI'])}</td>
                      <td>{String(row['模型'])}</td>
                      <td>{row['Δ pp'] === null || row['Δ pp'] === undefined ? '—' : String(row['Δ pp'])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="section-card">
              <div className="section-head">
                <h3>RGPOX 对标偏差</h3>
                <p>和 Streamlit 结果页保持同一阅读顺序。</p>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>组分</th>
                    <th>DBI</th>
                    <th>模型</th>
                    <th>Δ pp</th>
                  </tr>
                </thead>
                <tbody>
                  {(result?.comparison.rgpox_wet ?? []).map((row) => (
                    <tr key={String(row['组分'])}>
                      <td>{String(row['组分'])}</td>
                      <td>{row['DBI'] === null || row['DBI'] === undefined ? '—' : String(row['DBI'])}</td>
                      <td>{String(row['模型'])}</td>
                      <td>{row['Δ pp'] === null || row['Δ pp'] === undefined ? '—' : String(row['Δ pp'])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="section-card">
            <div className="section-head">
              <h3>进料台账</h3>
              <p>前端直接显示纯计算输入汇总，不再依赖 Streamlit 本地状态。</p>
            </div>
            <table>
              <thead>
                <tr>
                  <th>工段</th>
                  <th>PFD</th>
                  <th>进料项</th>
                  <th>模型 Stream</th>
                  <th>kg/h</th>
                  <th>°C</th>
                  <th>bar</th>
                </tr>
              </thead>
              <tbody>
                {(result?.tables.feed_summary ?? []).map((row) => (
                  <tr key={`${row.PFD}-${row['模型 Stream']}`}>
                    <td>{String(row['工段'])}</td>
                    <td>{String(row['PFD'])}</td>
                    <td>{String(row['进料项'])}</td>
                    <td>{String(row['模型 Stream'])}</td>
                    <td>{String(row['kg/h'])}</td>
                    <td>{String(row['°C'])}</td>
                    <td>{String(row['bar'])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <details className="section-card details-card" open>
            <summary>单元追踪 / AUDIT</summary>
            <table>
              <thead>
                <tr>
                  <th>单元</th>
                  <th>状态</th>
                  <th>说明</th>
                  <th>入口 kg/h</th>
                  <th>出口 kg/h</th>
                </tr>
              </thead>
              <tbody>
                {(result?.tables.unit_trace ?? []).map((row) => (
                  <tr key={`${row.unit_name}-${row.status}`}>
                    <td>{row.unit_name}</td>
                    <td>{row.status}</td>
                    <td>{row.notes}</td>
                    <td>{formatNumber(row.inlet_total_kg_h, 1)}</td>
                    <td>{formatNumber(row.outlet_total_kg_h, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </main>
      </div>
    </div>
  )
}

export default App
