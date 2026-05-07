const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
export async function chat(conversation_id: string | null, message: string){
  const res = await fetch(`${API}/chat`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({conversation_id,message})})
  return res.json()
}
export async function upload(conversationId: string, file: File){
  const fd = new FormData(); fd.append('file', file)
  const res = await fetch(`${API}/upload/${conversationId}`, {method:'POST', body: fd})
  return res.json()
}
export async function testSpec(skill_spec: any, query: string){
  const res = await fetch(`${API}/test`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({skill_spec, query})})
  return res.json()
}
