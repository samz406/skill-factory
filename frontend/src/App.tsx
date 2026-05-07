import { useState } from 'react'
import { chat } from './lib/api'

type Msg = { role: 'user'|'assistant'; content: string }

export function App(){
  const [messages, setMessages] = useState<Msg[]>([{role:'assistant', content:'你好，我是 Skill Factory。请描述你的业务目标，我会持续追问并生成 SkillSpec。'}])
  const [text, setText] = useState('')
  const [cid, setCid] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const send = async () => {
    if(!text.trim()) return
    const user = {role:'user' as const, content:text}
    setMessages(prev=>[...prev,user]); setLoading(true)
    const data = await chat(cid, text)
    setCid(data.conversation_id)
    setMessages(prev=>[...prev,{role:'assistant', content:data.reply + (data.need_confirmation ? '\n\n✅ 是否确认完成当前 Skill 草稿？' : '')}])
    setText(''); setLoading(false)
  }

  return <div className='app'>
    <aside className='panel glass'>
      <h2>Skill Factory</h2>
      <p>Chat-first Skill Builder</p>
    </aside>
    <main className='chat'>
      <div className='messages'>
        {messages.map((m,i)=><div key={i} className={`msg ${m.role}`}>{m.content}</div>)}
      </div>
      <div className='composer glass'>
        <textarea value={text} onChange={e=>setText(e.target.value)} placeholder='输入需求、规则、工具、约束...' />
        <button onClick={send} disabled={loading}>{loading?'生成中...':'发送'}</button>
      </div>
    </main>
    <aside className='panel glass'>
      <h3>实时协同</h3>
      <ul><li>边聊天边解析</li><li>边生成边确认</li><li>最终可导出 SKILL.md</li></ul>
    </aside>
  </div>
}
