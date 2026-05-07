import { useState } from 'react'
import { chat, upload, testSpec } from './api'

type Msg = { role: 'user'|'assistant'; content: string }

export function App(){
  const [messages, setMessages] = useState<Msg[]>([{role:'assistant', content:'你好，我是 Skill Factory。请描述你的业务目标，我会持续追问并生成 SkillSpec。'}])
  const [text, setText] = useState('')
  const [cid, setCid] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [spec, setSpec] = useState<any>({})
  const [missing, setMissing] = useState<string[]>([])
  const [testResult, setTestResult] = useState<any>(null)

  const send = async () => {
    if(!text.trim()) return
    const user = {role:'user' as const, content:text}
    setMessages(prev=>[...prev,user]); setLoading(true)
    const data = await chat(cid, text)
    setCid(data.conversation_id)
    setSpec(data.spec)
    setMissing(data.missing_slots || [])
    setMessages(prev=>[...prev,{role:'assistant', content:data.reply + (data.need_confirmation ? '\n\n✅ 是否确认完成当前 Skill 草稿？' : '')}])
    setText(''); setLoading(false)
  }

  const onUpload = async (f?: File) => {
    if(!f || !cid) return
    const data = await upload(cid, f)
    setSpec(data.spec)
    setMessages(prev=>[...prev,{role:'assistant', content:`已上传并解析：${f.name}`}])
  }

  const runTest = async () => {
    const data = await testSpec(spec, '请模拟处理一个客户投诉流程')
    setTestResult(data)
  }

  return <div className='app'>
    <aside className='panel glass'>
      <h2>Skill Factory</h2><p>Chat-first Skill Builder</p>
      <div className='hint'>会话ID：{cid || '未创建'}</div>
      <input type='file' onChange={e=>onUpload(e.target.files?.[0])} />
    </aside>
    <main className='chat'>
      <div className='messages'>{messages.map((m,i)=><div key={i} className={`msg ${m.role}`}>{m.content}</div>)}</div>
      <div className='composer glass'>
        <textarea value={text} onChange={e=>setText(e.target.value)} placeholder='输入需求、规则、工具、约束...' />
        <button onClick={send} disabled={loading}>{loading?'生成中...':'发送'}</button>
      </div>
    </main>
    <aside className='panel glass'>
      <h3>SkillSpec 工作台</h3>
      <p>缺失槽位：{missing.length?missing.join(', '):'无'}</p>
      <button onClick={runTest}>运行测试</button>
      {testResult && <div className='result'>Score: {testResult.score}<br/>{(testResult.checks||[]).join(' | ')}</div>}
      <pre>{JSON.stringify(spec, null, 2)}</pre>
    </aside>
  </div>
}
