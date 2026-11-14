const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'

export type HealthResponse = {
  status: string
  version: string
}

export async function getHealth(): Promise<HealthResponse> {
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}/health/`)
  } catch (error) {
    throw new Error('The backend API could not be reached.', { cause: error })
  }

  if (!response.ok) {
    throw new Error(`The backend API returned HTTP ${response.status}.`)
  }
  return (await response.json()) as HealthResponse
}
