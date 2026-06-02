export const INCI_SOLID_ROUTING_FIELDS = [
  'INCI Solid Routing Mode',
  'INCI Fly Ash / Slag Mass Ratio',
  'INCI Fly Ash Residual C wt% dry',
  'INCI Slag Residual C wt% dry',
  'INCI Overall Biomass C Conversion',
] as const

export type ChemistryFieldKind = 'text' | 'number' | 'select'

export type ChemistryFieldMeta = {
  label: string
  hint: string
  kind: ChemistryFieldKind
  options?: readonly string[]
  step?: number
  min?: number
  max?: number
}

export const CHEMISTRY_FIELD_META: Record<string, ChemistryFieldMeta> = {
  'INCI Solid Routing Mode': {
    label: '固相路由模式',
    hint: 'Fly Ash Ratio：流化床灰渣比；DBI Boundary：冻结边界表；Legacy Fraction：旧分流系数。',
    kind: 'select',
    options: ['Fly Ash Ratio', 'DBI Boundary', 'Legacy Fraction'],
  },
  'INCI Fly Ash / Slag Mass Ratio': {
    label: '灰渣比（飞灰/底渣）',
    hint: '飞灰含 15PGI-1 夹带 char+fly ash；底渣为 13LBS-1。Case-1 DBI ≈ 2.503。',
    kind: 'number',
    step: 0.01,
    min: 0.1,
    max: 20,
  },
  'INCI Fly Ash Residual C wt% dry': {
    label: '飞灰残炭 wt% (dry)',
    hint: '夹带固相干基残炭百分比。',
    kind: 'number',
    step: 0.1,
    min: 0,
    max: 100,
  },
  'INCI Slag Residual C wt% dry': {
    label: '底渣残炭 wt% (dry)',
    hint: '13LBS-1 渣线干基残炭；Case-1 DBI = 0%。',
    kind: 'number',
    step: 0.1,
    min: 0,
    max: 100,
  },
  'INCI Overall Biomass C Conversion': {
    label: '整体生物质碳转化率',
    hint: '留空=自动（DBI 边界或 model_fixed）；也可填 0–1 小数。',
    kind: 'text',
  },
  'TA DeltaT WGS (C)': {
    label: 'INCI · WGS ΔT (°C)',
    hint: '受限平衡 WGS 参考温度偏移。',
    kind: 'number',
    step: 5,
  },
  'TA DeltaT Meth (C)': {
    label: 'INCI · 甲烷化 ΔT (°C)',
    hint: '甲烷化 TA 参考温度偏移。',
    kind: 'number',
    step: 10,
  },
  'WGS Equilibrium Approach Eta': {
    label: 'INCI · WGS η',
    hint: 'WGS 趋近度 0–1。',
    kind: 'number',
    step: 0.05,
    min: 0,
    max: 1,
  },
  'Meth Equilibrium Approach Eta': {
    label: 'INCI · 甲烷化 η',
    hint: '甲烷化趋近度 0–1。',
    kind: 'number',
    step: 0.05,
    min: 0,
    max: 1,
  },
  'RGPOX TA DeltaT WGS (C)': {
    label: 'RGPOX · WGS ΔT (°C)',
    hint: '15PGR-1 湿基对标用 WGS TA。',
    kind: 'number',
    step: 5,
  },
  'RGPOX TA DeltaT Meth (C)': {
    label: 'RGPOX · 甲烷化 ΔT (°C)',
    hint: 'RGPOX 段甲烷化 TA。',
    kind: 'number',
    step: 10,
  },
  'RGPOX WGS Equilibrium Approach Eta': {
    label: 'RGPOX · WGS η',
    hint: 'RGPOX WGS 趋近度。',
    kind: 'number',
    step: 0.05,
    min: 0,
    max: 1,
  },
  'RGPOX Meth Equilibrium Approach Eta': {
    label: 'RGPOX · 甲烷化 η',
    hint: 'RGPOX 甲烷化趋近度。',
    kind: 'number',
    step: 0.05,
    min: 0,
    max: 1,
  },
}

const INCI_SOLID_ROUTING_SET = new Set<string>(INCI_SOLID_ROUTING_FIELDS)

const INTERNAL_CHEMISTRY_FIELDS = new Set([
  'Sample',
  'Tar Formula',
  'Constraint Mode',
  'RGPOX CH4 Target @1300C (%)',
  'RGPOX CH4 Target @1400C (%)',
  'RGPOX CH4 Target @1500C (%)',
])

export function isInciSolidRoutingField(field: string) {
  return INCI_SOLID_ROUTING_SET.has(field)
}

export function isInternalChemistryField(field: string) {
  return INTERNAL_CHEMISTRY_FIELDS.has(field)
}

export function chemistryFieldMeta(field: string): ChemistryFieldMeta {
  return (
    CHEMISTRY_FIELD_META[field] ?? {
      label: field,
      hint: '映射后端 chemistry 字段。',
      kind: 'text',
    }
  )
}

export function splitChemistryRows<T extends { Field: string }>(rows: T[]) {
  const standard: T[] = []
  const advancedInciSolid: T[] = []

  for (const row of rows) {
    if (isInternalChemistryField(row.Field)) continue
    if (isInciSolidRoutingField(row.Field)) {
      advancedInciSolid.push(row)
      continue
    }
    standard.push(row)
  }

  const order = new Map(INCI_SOLID_ROUTING_FIELDS.map((field, index) => [field, index]))
  advancedInciSolid.sort(
    (left, right) => (order.get(left.Field as (typeof INCI_SOLID_ROUTING_FIELDS)[number]) ?? 0)
      - (order.get(right.Field as (typeof INCI_SOLID_ROUTING_FIELDS)[number]) ?? 0),
  )

  return { standard, advancedInciSolid }
}
