import type { BootstrapResponse, FullComputeResponse, FullSimulationPayload } from './types'

const RAW_API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim() ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

function isAbsoluteUrl(value: string) {
  return /^https?:\/\//i.test(value)
}

function isLocalDevHost(hostname: string) {
  return hostname === 'localhost' || hostname === '127.0.0.1'
}

function resolveApiBaseUrl() {
  if (!RAW_API_BASE_URL) return '/api'
  if (typeof window === 'undefined') return RAW_API_BASE_URL
  if (isAbsoluteUrl(RAW_API_BASE_URL) && isLocalDevHost(window.location.hostname)) {
    return '/api'
  }
  return RAW_API_BASE_URL
}

const API_BASE_URL = resolveApiBaseUrl()

function toRequestError(error: unknown) {
  if (error instanceof Error && error.message === 'Failed to fetch') {
    return new Error('无法连接计算服务。请检查前端代理配置或后端 API 可用性。')
  }
  return error instanceof Error ? error : new Error('请求失败')
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
      },
      body: JSON.stringify(payload),
    })
  } catch (error) {
    throw toRequestError(error)
  }

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
