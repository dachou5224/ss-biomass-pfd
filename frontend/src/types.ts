export type FeedRow = {
  Stream: string
  MassFlow_kg_h: number
  Temp_C: number
  Pressure_bar: number
}

export type ChemistryRow = {
  Field: string
  Value: string | number
}

export type LiteChecks = {
  total_feed_kg_h: number
  total_inci_feed_kg_h: number
  total_rgpox_feed_kg_h: number
  total_slag_feed_kg_h: number
  o2in_sum_mol_pct: number
  o2in_is_100_pct: boolean
  negative_feed_count: number
}

export type BootstrapResponse = {
  mode: 'input-read'
  inputs: {
    case_id: string
    system_p_bar: number
    o2in_composition: Record<'O2' | 'N2' | 'Ar', number>
    o2pox: {
      purity_vol_pct: number
    }
  }
  tables: {
    feed: FeedRow[]
    specs: Array<Record<string, string | number>>
    chemistry: ChemistryRow[]
  }
  checks: LiteChecks
}

export type FullSimulationPayload = {
  case_id: string
  system_p_bar: number
  pfd_feeds: Record<
    string,
    {
      mass_kg_h: number
      temp_c: number
      pressure_bar: number
    }
  >
  o2in_composition: Record<'O2' | 'N2' | 'Ar', number>
  chemistry: Record<string, string | number>
}

export type FullComputeResponse = {
  status: 'ok' | 'check'
  checks: LiteChecks
  input: {
    case_id: string
    system_p_bar: number
  }
  result_summary: {
    matched_case: string | null
    inci_top_kg_h: number
    inci_tar_kg_h: number
    inci_pgi_total_kg_h: number
    inci_slag_kg_h: number
    pox_gas_kg_h: number
    pox_ash_kg_h: number
    quench_t_out_c: number | null
    quench_h2o_added_kg_h: number | null
  }
  inci_solid_routing: InciSolidRouting | null
  performance: {
    cold_gas_efficiency_pct: number | null
    cold_gas_efficiency_inci_pct: number | null
    cold_gas_efficiency_pox_pct: number | null
    carbon_conversion_pct: number | null
    carbon_conversion_inci_pct: number | null
    carbon_conversion_pox_pct: number | null
    h2_co_ratio_dry: number | null
  }
  compositions: {
    inci_wet_vol_pct: Record<string, number>
    rgpox_wet_vol_pct: Record<string, number>
    inci: {
      title: string
      equipment_id: string
      dry_stream_id: string
      wet_stream_id: string
      dry_vol_pct: Record<string, number>
      wet_vol_pct: Record<string, number>
    }
    pox: {
      title: string
      equipment_id: string
      dry_stream_id: string
      wet_stream_id: string
      dry_vol_pct: Record<string, number>
      wet_vol_pct: Record<string, number>
    }
  }
  tables: {
    feed_summary: Array<Record<string, string | number | null>>
  }
}

export type InciSolidRouting = {
  mode: string | null
  fly_ash_total_kg_h: number | null
  fly_ash_to_slag_ratio: number | null
  char_to_pox_kg_h: number
  ash_to_pox_kg_h: number
  char_to_slag_kg_h: number
  ash_to_slag_kg_h: number
  slag_to_u14_kg_h: number
  overall_biomass_carbon_conversion_pct: number | null
}
