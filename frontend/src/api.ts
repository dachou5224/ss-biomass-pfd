import type { BootstrapResponse, FullComputeResponse, FullSimulationPayload } from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `请求失败: ${response.status}`)
  }

  return (await response.json()) as T
}

export function fetchInputTemplate(caseId: string) {
  return postJson<BootstrapResponse>('/v1/demo/input-read', { case_id: caseId })
}

export function runFullSimulation(payload: FullSimulationPayload) {
  return postJson<FullComputeResponse>('/v1/compute/simulate-full', payload)
}
