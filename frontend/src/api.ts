const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function chat(
  conversation_id: string | null,
  message: string,
  provider?: string,
  model?: string,
  api_key?: string,
) {
  const res = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id, message, provider, model, api_key }),
  })
  return res.json()
}

export function chatStream(
  conversation_id: string | null,
  message: string,
  provider?: string,
  model?: string,
  onToken?: (token: string) => void,
  onDone?: (data: { spec: any; missing_slots: string[]; need_confirmation: boolean }) => void,
  onInit?: (conversation_id: string) => void,
  api_key?: string,
): AbortController {
  const controller = new AbortController()
  fetch(`${API}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id, message, provider, model, api_key }),
    signal: controller.signal,
  }).then(async (res) => {
    const reader = res.body?.getReader()
    if (!reader) return
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(line.slice(6))
            if (parsed.type === 'init' && onInit) onInit(parsed.conversation_id)
            if (parsed.type === 'token' && onToken) onToken(parsed.content)
            if (parsed.type === 'done' && onDone) onDone(parsed)
          } catch {}
        }
      }
    }
  }).catch(() => {})
  return controller
}

export async function upload(conversationId: string, file: File) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API}/upload/${conversationId}`, { method: 'POST', body: fd })
  return res.json()
}

export async function testSpec(skill_spec: any, query: string) {
  const res = await fetch(`${API}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill_spec, query }),
  })
  return res.json()
}

export async function exportSkill(conversationId: string) {
  const res = await fetch(`${API}/export/${conversationId}`, { method: 'POST' })
  return res.json()
}

export async function renderSkill(spec: any) {
  const res = await fetch(`${API}/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(spec),
  })
  return res.json()
}

export async function getDraft(conversationId: string) {
  const res = await fetch(`${API}/draft/${conversationId}`)
  return res.json()
}

export async function getModels() {
  const res = await fetch(`${API}/models`)
  return res.json()
}

export async function getHealth() {
  const res = await fetch(`${API}/health`)
  return res.json()
}

export async function getLLMSettings() {
  const res = await fetch(`${API}/settings`)
  return res.json()
}

export async function saveLLMSettings(payload: {
  provider: string
  model: string
  api_key: string
  base_url: string
}) {
  const res = await fetch(`${API}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return res.json()
}
