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

/** Trigger a browser download of the rendered SKILL.md file. */
export async function downloadSkill(conversationId: string, skillName?: string) {
  const res = await fetch(`${API}/download/${conversationId}`)
  if (!res.ok) throw new Error('download failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = skillName ? `${skillName}.md` : 'skill.md'
  a.click()
  URL.revokeObjectURL(url)
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

// ── Conversation history ──────────────────────

export async function listConversations(): Promise<{ conversations: ConversationMeta[] }> {
  const res = await fetch(`${API}/conversations`)
  return res.json()
}

export interface ConversationMeta {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export async function deleteConversation(conversationId: string) {
  const res = await fetch(`${API}/conversations/${conversationId}`, { method: 'DELETE' })
  return res.json()
}

// ── Agent sync ───────────────────────────────

export interface AgentTarget {
  id: string
  label: string
  icon: string
  description: string
  path_template: string
}

export async function getAgentTargets(): Promise<{ targets: AgentTarget[] }> {
  const res = await fetch(`${API}/agent_targets`)
  return res.json()
}

export async function syncSkill(conversationId: string, target_id: string, custom_path = '') {
  const res = await fetch(`${API}/sync/${conversationId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_id, custom_path }),
  })
  return res.json()
}

// ── Skill evaluation ─────────────────────────

export interface SkillEvaluation {
  evaluation_id: string
  conversation_id: string
  score: number
  dimensions: Record<string, number>
  feedback: string
  suggestions: string[]
  created_at: string
}

export async function evaluateSkill(conversationId: string): Promise<SkillEvaluation> {
  const res = await fetch(`${API}/evaluate/${conversationId}`, { method: 'POST' })
  if (!res.ok) throw new Error('evaluate failed')
  return res.json()
}

export async function getEvaluation(conversationId: string): Promise<SkillEvaluation> {
  const res = await fetch(`${API}/evaluate/${conversationId}`)
  if (!res.ok) throw new Error('no evaluation found')
  return res.json()
}

export async function listEvaluations(): Promise<{ evaluations: SkillEvaluation[] }> {
  const res = await fetch(`${API}/evaluations`)
  return res.json()
}
