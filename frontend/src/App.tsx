import { useState, useRef, useEffect, useCallback } from 'react'
import { chat, chatStream, upload, testSpec, exportSkill, renderSkill, getHealth, getLLMSettings, saveLLMSettings, listConversations, deleteConversation, downloadSkill, getAgentTargets, syncSkill, getDraft, evaluateSkill, type ConversationMeta, type AgentTarget, type SkillEvaluation } from './api'

type Msg = { role: 'user' | 'assistant'; content: string; streaming?: boolean }
type Tab = 'spec' | 'skill_md' | 'test'

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', models: ['gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo'] },
  { value: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-reasoner'] },
  { value: 'qwen', label: 'Qwen (通义)', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-plus', 'qwen-turbo', 'qwen-max'] },
  { value: 'kimi', label: 'Kimi (月之暗面)', baseUrl: 'https://api.moonshot.cn/v1', models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'] },
]

const DEFAULT_GREETING: Msg = {
  role: 'assistant',
  content: '你好，我是 Skill Factory 🏭\n\n请描述你的业务目标和场景，我会通过对话帮你逐步构建 AI Skill。\n\n你可以告诉我：\n- 这个 Skill 要解决什么业务问题？\n- 有哪些操作流程或规则？\n- 需要调用哪些系统或 API？',
}

export function App() {
  const [messages, setMessages] = useState<Msg[]>([DEFAULT_GREETING])
  const [text, setText] = useState('')
  const [cid, setCid] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [spec, setSpec] = useState<any>({})
  const [missing, setMissing] = useState<string[]>([])
  const [tab, setTab] = useState<Tab>('spec')
  const [skillMd, setSkillMd] = useState('')
  const [testQuery, setTestQuery] = useState('请模拟处理一个典型业务场景')
  const [testResult, setTestResult] = useState<any>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [provider, setProvider] = useState(PROVIDERS[0].value)
  const [model, setModel] = useState(PROVIDERS[0].models[0])
  const [apiKey, setApiKey] = useState('')
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null)
  const [exportMsg, setExportMsg] = useState('')
  const [score, setScore] = useState(0)
  const [showSettings, setShowSettings] = useState(false)
  const [settingsSaved, setSettingsSaved] = useState(false)
  const [baseUrl, setBaseUrl] = useState('')
  // Conversation history
  const [conversations, setConversations] = useState<ConversationMeta[]>([])
  const [showHistory, setShowHistory] = useState(false)
  // Agent sync
  const [showSync, setShowSync] = useState(false)
  const [agentTargets, setAgentTargets] = useState<AgentTarget[]>([])
  const [syncResults, setSyncResults] = useState<Record<string, string>>({})
  const [syncLoading, setSyncLoading] = useState(false)
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set())
  // Evaluation
  const [evaluation, setEvaluation] = useState<SkillEvaluation | null>(null)
  const [evalLoading, setEvalLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const streamController = useRef<AbortController | null>(null)

  const refreshHistory = useCallback(async () => {
    try {
      const data = await listConversations()
      setConversations(data.conversations || [])
    } catch {}
  }, [])

  useEffect(() => {
    getHealth().then(d => setLlmConfigured(d.llm_configured)).catch(() => setLlmConfigured(false))
    getLLMSettings().then(d => {
      if (d.provider) onProviderChange(d.provider)
      if (d.model) setModel(d.model)
      if (d.api_key) setApiKey(d.api_key)
      if (d.base_url) setBaseUrl(d.base_url)
    }).catch(() => {})
    refreshHistory()
    getAgentTargets().then(d => setAgentTargets(d.targets || [])).catch(() => {})
  }, [])

  useEffect(() => {
    if (messagesEndRef.current?.scrollIntoView) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  const calcScore = useCallback((s: any) => {
    const slots = ['workflow', 'rules', 'tools', 'constraints', 'output_format']
    const filled = slots.filter(k => s[k] && (Array.isArray(s[k]) ? s[k].length > 0 : s[k]))
    return Math.round((filled.length / slots.length) * 100)
  }, [])

  const startNewConversation = () => {
    setCid(null)
    setMessages([DEFAULT_GREETING])
    setSpec({})
    setMissing([])
    setScore(0)
    setSkillMd('')
    setExportMsg('')
    setTestResult(null)
    setEvaluation(null)
    setShowHistory(false)
  }

  const loadConversation = async (id: string) => {
    try {
      const data = await getDraft(id)
      setCid(id)
      setSpec(data.spec || {})
      setScore(calcScore(data.spec || {}))
      setMissing(data.missing_slots || [])
      const msgs: Msg[] = (data.messages || []).map((m: any) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }))
      if (msgs.length === 0) {
        msgs.unshift({ role: 'assistant', content: '（已加载历史对话）' })
      }
      setMessages(msgs)
      setShowHistory(false)
    } catch {}
  }

  const handleDeleteConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await deleteConversation(id)
    await refreshHistory()
    if (cid === id) startNewConversation()
  }

  const send = async () => {
    if (!text.trim() || loading) return
    const userMsg = text.trim()
    setText('')
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setLoading(true)

    // Add streaming placeholder
    setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true }])

    let initDone = false
    streamController.current = chatStream(
      cid,
      userMsg,
      provider,
      model,
      (token) => {
        setMessages(prev => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last?.streaming) next[next.length - 1] = { ...last, content: last.content + token }
          return next
        })
      },
      (data) => {
        setMessages(prev => {
          const next = [...prev]
          const last = next[next.length - 1]
          if (last?.streaming) {
            let content = last.content
            if (data.need_confirmation) content += '\n\n✅ 所有槽位已完整，可以进行测试并导出 SKILL.md。'
            next[next.length - 1] = { role: 'assistant', content }
          }
          return next
        })
        setSpec(data.spec)
        setMissing(data.missing_slots || [])
        setScore(calcScore(data.spec))
        setLoading(false)
        refreshHistory()
      },
      (convId) => {
        if (!initDone) { setCid(convId); initDone = true }
      },
      apiKey || undefined,
    )
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const onUpload = async (f?: File) => {
    if (!f) return
    let convId = cid
    if (!convId) {
      // Create a conversation first by sending a placeholder message
      const data = await chat(null, '开始上传文档', provider, model, apiKey || undefined)
      convId = data.conversation_id
      setCid(convId)
      setSpec(data.spec)
    }
    if (!convId) return
    setMessages(prev => [...prev, { role: 'assistant', content: `正在解析附件：${f.name}...` }])
    const data = await upload(convId, f)
    setSpec(data.spec)
    setScore(calcScore(data.spec))
    setMessages(prev => {
      const next = [...prev]
      next[next.length - 1] = {
        role: 'assistant',
        content: `✅ 已解析附件：**${f.name}**\n\n` +
          (data.parsed?.rules?.length ? `提取规则：${data.parsed.rules.slice(0, 2).join('；')}\n` : '') +
          (data.parsed?.workflow?.length ? `提取流程：${data.parsed.workflow.slice(0, 2).join('；')}` : ''),
      }
      return next
    })
    refreshHistory()
  }

  const runRender = async () => {
    if (!spec || Object.keys(spec).length === 0) return
    const data = await renderSkill(spec)
    setSkillMd(data.skill_md || '')
    setTab('skill_md')
  }

  const runTest = async () => {
    if (!testQuery.trim()) return
    setTestLoading(true)
    const data = await testSpec(spec, testQuery)
    setTestResult(data)
    setTestLoading(false)
    setTab('test')
  }

  const runEvaluate = async () => {
    if (!cid) return
    setEvalLoading(true)
    try {
      const data = await evaluateSkill(cid)
      setEvaluation(data)
    } catch {
      setEvaluation(null)
    }
    setEvalLoading(false)
  }

  const runExport = async () => {
    if (!cid) return
    const data = await exportSkill(cid)
    if (data.ok) {
      setSkillMd(data.content || '')
      setExportMsg(`✅ 已导出到：${data.file}（评分：${data.score}分）`)
      setTab('skill_md')
    }
  }

  const runDownload = async () => {
    if (!cid) return
    try {
      await downloadSkill(cid, spec?.name)
    } catch {
      setExportMsg('❌ 下载失败，请先生成 Skill')
    }
  }

  const openSync = () => {
    setSyncResults({})
    setSelectedAgents(new Set(agentTargets.map(t => t.id)))
    setShowSync(true)
  }

  const runSync = async () => {
    if (!cid) return
    setSyncLoading(true)
    const results: Record<string, string> = {}
    for (const targetId of selectedAgents) {
      try {
        const data = await syncSkill(cid, targetId)
        results[targetId] = data.ok ? `✅ ${data.file}` : `❌ 失败`
      } catch {
        results[targetId] = '❌ 请求失败'
      }
    }
    setSyncResults(results)
    setSyncLoading(false)
  }

  const onProviderChange = (p: string) => {
    setProvider(p)
    const cfg = PROVIDERS.find(x => x.value === p)
    if (cfg) setModel(cfg.models[0])
  }

  const specSlots = [
    { key: 'workflow', label: '流程', icon: '🔄' },
    { key: 'rules', label: '规则', icon: '📋' },
    { key: 'tools', label: '工具', icon: '🔧' },
    { key: 'constraints', label: '约束', icon: '🔒' },
    { key: 'output_format', label: '输出格式', icon: '📄' },
  ]

  const isLlmReady = Boolean(llmConfigured || apiKey)

  return (
    <div className="app">
      {/* Left sidebar */}
      <aside className="panel glass left-panel">
        <div className="logo">🏭 Skill Factory</div>
        <p className="tagline">AI Agent 知识编译器</p>

        {/* LLM Status */}
        <div className={`status-badge ${isLlmReady ? 'status-ok' : 'status-warn'}`}>
          {llmConfigured === null ? '⏳ 检测中...' : isLlmReady ? '🟢 LLM 已就绪' : '🟡 LLM 未配置（规则模式）'}
        </div>

        {/* Conversation */}
        <div className="section">
          <div className="section-title">当前会话</div>
          <div className="conv-id">{cid ? `${cid.slice(0, 8)}...` : '未创建'}</div>
          <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
            <button className="btn btn-secondary" style={{ flex: 1, fontSize: 11, padding: '5px 0' }} onClick={startNewConversation}>
              ✨ 新对话
            </button>
            <button
              className="btn btn-secondary"
              style={{ flex: 1, fontSize: 11, padding: '5px 0' }}
              onClick={() => { refreshHistory(); setShowHistory(true) }}
            >
              📋 历史
            </button>
          </div>
        </div>

        {/* File Upload */}
        <div className="section">
          <div className="section-title">文档上传</div>
          <div className="upload-area" onClick={() => fileInputRef.current?.click()}>
            📎 点击上传文件
            <br />
            <small>PDF / Word / TXT / MD</small>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.md,.csv"
            style={{ display: 'none' }}
            onChange={e => onUpload(e.target.files?.[0])}
          />
        </div>

        {/* Progress */}
        <div className="section">
          <div className="section-title">完成度 {score}%</div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${score}%` }} />
          </div>
          <div className="slot-list">
            {specSlots.map(s => {
              const val = spec[s.key]
              const filled = Array.isArray(val) ? val.length > 0 : Boolean(val)
              return (
                <div key={s.key} className={`slot-item ${filled ? 'slot-ok' : 'slot-miss'}`}>
                  {s.icon} {s.label} {filled ? '✓' : '✗'}
                </div>
              )
            })}
          </div>
        </div>

        {/* Actions */}
        <div className="section">
          <button className="btn btn-primary" onClick={runRender} disabled={!spec?.name && !spec?.description}>
            📝 渲染 SKILL.md
          </button>
          <button className="btn btn-secondary" onClick={runExport} disabled={!cid} style={{ marginTop: 6 }}>
            💾 导出文件
          </button>
          <button className="btn btn-secondary" onClick={runDownload} disabled={!cid} style={{ marginTop: 6 }}>
            📥 下载 SKILL.md
          </button>
          <button className="btn btn-secondary" onClick={openSync} disabled={!cid} style={{ marginTop: 6 }}>
            🔄 同步到 Agent
          </button>
          {exportMsg && <div className="export-msg">{exportMsg}</div>}
        </div>
      </aside>

      {/* Center: Chat */}
      <main className="chat">
        <div className="chat-header">
          <span>Chat Builder</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {missing.length > 0 && (
              <span className="missing-hint">待填写：{missing.join(' · ')}</span>
            )}
            <button className="settings-btn" onClick={() => setShowSettings(true)} title="设置">
              ⚙️
            </button>
          </div>
        </div>
        <div className="messages">
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className="msg-content">
                {m.content || (m.streaming ? <span className="typing-dot">●</span> : '')}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
        <div className="composer glass">
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="描述业务需求、规则、流程、约束...（Enter 发送，Shift+Enter 换行）"
            disabled={loading}
          />
          <button onClick={send} disabled={loading || !text.trim()} className="btn btn-send">
            {loading ? '⏳' : '发送'}
          </button>
        </div>
      </main>

      {/* Right sidebar: workspace */}
      <aside className="panel glass right-panel">
        <div className="tab-bar">
          <button className={`tab ${tab === 'spec' ? 'tab-active' : ''}`} onClick={() => setTab('spec')}>
            SkillSpec
          </button>
          <button className={`tab ${tab === 'skill_md' ? 'tab-active' : ''}`} onClick={() => setTab('skill_md')}>
            SKILL.md
          </button>
          <button className={`tab ${tab === 'test' ? 'tab-active' : ''}`} onClick={() => setTab('test')}>
            测试
          </button>
        </div>

        {tab === 'spec' && (
          <div className="tab-content">
            <pre className="spec-preview">{JSON.stringify(spec, null, 2)}</pre>
          </div>
        )}

        {tab === 'skill_md' && (
          <div className="tab-content">
            {skillMd ? (
              <pre className="md-preview">{skillMd}</pre>
            ) : (
              <div className="empty-hint">点击左侧"渲染 SKILL.md"生成预览</div>
            )}
          </div>
        )}

        {tab === 'test' && (
          <div className="tab-content">
            <div className="section-title">测试查询</div>
            <textarea
              value={testQuery}
              onChange={e => setTestQuery(e.target.value)}
              className="test-input"
              rows={3}
            />
            <button className="btn btn-primary" onClick={runTest} disabled={testLoading}>
              {testLoading ? '执行中...' : '▶ 运行测试'}
            </button>
            {testResult && (
              <div className="test-result">
                <div className="test-score">评分：{testResult.score} 分</div>
                <div className="test-checks">
                  {(testResult.checks || []).map((c: string, i: number) => (
                    <div key={i} className={`check-item ${c.includes('ok') ? 'check-ok' : 'check-fail'}`}>
                      {c.includes('ok') ? '✅' : '❌'} {c}
                    </div>
                  ))}
                </div>
                <div className="section-title" style={{ marginTop: 12 }}>模拟输出</div>
                <div className="test-answer">{testResult.answer}</div>
                {testResult.tool_calls?.length > 0 && (
                  <>
                    <div className="section-title" style={{ marginTop: 8 }}>Tool Calls</div>
                    <pre className="spec-preview">{JSON.stringify(testResult.tool_calls, null, 2)}</pre>
                  </>
                )}
              </div>
            )}

            <div className="section-title" style={{ marginTop: 16 }}>质量评估</div>
            <button className="btn btn-secondary" onClick={runEvaluate} disabled={evalLoading || !cid} style={{ width: '100%' }}>
              {evalLoading ? '评估中...' : '🔍 运行质量评估'}
            </button>
            {evaluation && (
              <div className="test-result" style={{ marginTop: 8 }}>
                <div className="test-score">综合评分：{evaluation.score} 分</div>
                <div className="test-checks" style={{ marginTop: 6 }}>
                  {Object.entries(evaluation.dimensions).map(([dim, val]) => {
                    const labels: Record<string, string> = {
                      description_quality: '描述质量',
                      workflow_completeness: '流程完整性',
                      rules_specificity: '规则具体性',
                      output_clarity: '输出清晰度',
                      tool_coverage: '工具覆盖',
                      constraint_rigor: '约束严格性',
                    }
                    const pct = val as number
                    return (
                      <div key={dim} className={`check-item ${pct >= 60 ? 'check-ok' : 'check-fail'}`}>
                        {pct >= 60 ? '✅' : '⚠️'} {labels[dim] || dim}: {pct}分
                      </div>
                    )
                  })}
                </div>
                {evaluation.feedback && (
                  <>
                    <div className="section-title" style={{ marginTop: 10 }}>总体评价</div>
                    <div className="test-answer">{evaluation.feedback}</div>
                  </>
                )}
                {evaluation.suggestions?.length > 0 && (
                  <>
                    <div className="section-title" style={{ marginTop: 10 }}>改进建议</div>
                    <ul style={{ paddingLeft: 16, margin: 0, fontSize: 13 }}>
                      {evaluation.suggestions.map((s, i) => (
                        <li key={i} style={{ marginBottom: 4 }}>{s}</li>
                      ))}
                    </ul>
                  </>
                )}
                <div style={{ fontSize: 11, color: '#999', marginTop: 8 }}>
                  评估时间：{new Date(evaluation.created_at).toLocaleString()}（已缓存）
                </div>
              </div>
            )}
          </div>
        )}
      </aside>

      {/* Settings Modal */}
      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal-panel glass" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span>⚙️ 大模型配置</span>
              <button className="modal-close" onClick={() => setShowSettings(false)}>✕</button>
            </div>

            <div className="modal-body">
              <div className="settings-section">
                <div className="settings-section-title">🤖 大模型配置</div>
                <div className="settings-row">
                  <label className="settings-label">提供商</label>
                  <select value={provider} onChange={e => onProviderChange(e.target.value)} className="select settings-select">
                    {PROVIDERS.map(p => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>
                <div className="settings-row">
                  <label className="settings-label">模型</label>
                  <select value={model} onChange={e => setModel(e.target.value)} className="select settings-select">
                    {(PROVIDERS.find(p => p.value === provider)?.models || []).map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
                <div className="settings-row">
                  <label className="settings-label">API URL</label>
                  <input
                    type="text"
                    value={baseUrl}
                    onChange={e => setBaseUrl(e.target.value)}
                    placeholder={PROVIDERS.find(p => p.value === provider)?.baseUrl || 'https://api.openai.com/v1'}
                    className="settings-input"
                  />
                </div>
                <div className="settings-row">
                  <label className="settings-label">API Key</label>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                    placeholder="sk-..."
                    className="settings-input"
                  />
                </div>
                <div className="settings-row">
                  <label className="settings-label">状态</label>
                  <span className={`status-badge settings-status ${isLlmReady ? 'status-ok' : 'status-warn'}`}>
                    {llmConfigured === null ? '⏳ 检测中...' : isLlmReady ? '🟢 已就绪' : '🟡 未配置'}
                  </span>
                </div>
                <div className="settings-row" style={{ justifyContent: 'flex-end', marginTop: 8 }}>
                  {settingsSaved && <span style={{ color: '#4caf50', marginRight: 12, fontSize: 13 }}>✅ 已保存</span>}
                  <button
                    className="btn btn-primary"
                    onClick={async () => {
                      await saveLLMSettings({ provider, model, api_key: apiKey, base_url: baseUrl })
                      setLlmConfigured(Boolean(apiKey))
                      setSettingsSaved(true)
                      setTimeout(() => setSettingsSaved(false), 3000)
                    }}
                  >
                    💾 保存
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* History Modal */}
      {showHistory && (
        <div className="modal-overlay" onClick={() => setShowHistory(false)}>
          <div className="modal-panel glass" style={{ width: 480 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span>📋 历史对话</span>
              <button className="modal-close" onClick={() => setShowHistory(false)}>✕</button>
            </div>
            <div className="modal-body">
              {conversations.length === 0 ? (
                <div className="empty-hint">暂无历史对话</div>
              ) : (
                <div className="history-list">
                  {conversations.map(c => (
                    <div key={c.id} className="history-item" onClick={() => loadConversation(c.id)}>
                      <div className="history-item-main">
                        <div className="history-title">{c.title || '（未命名对话）'}</div>
                        <div className="history-time">{new Date(c.updated_at).toLocaleString('zh-CN')}</div>
                      </div>
                      <button
                        className="history-del-btn"
                        onClick={e => handleDeleteConversation(c.id, e)}
                        title="删除"
                      >
                        🗑️
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Sync to Agent Modal */}
      {showSync && (
        <div className="modal-overlay" onClick={() => setShowSync(false)}>
          <div className="modal-panel glass" style={{ width: 500 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span>🔄 同步到 Agent 工具</span>
              <button className="modal-close" onClick={() => setShowSync(false)}>✕</button>
            </div>
            <div className="modal-body">
              <div style={{ fontSize: 12, color: '#8899cc', marginBottom: 12 }}>
                选择要将 Skill 同步到的 Agent 工具，点击"同步"后将把 SKILL.md 写入对应工具的默认配置目录。
              </div>
              <div className="sync-target-list">
                {agentTargets.map(t => (
                  <label key={t.id} className="sync-target-item">
                    <input
                      type="checkbox"
                      checked={selectedAgents.has(t.id)}
                      onChange={e => {
                        const next = new Set(selectedAgents)
                        e.target.checked ? next.add(t.id) : next.delete(t.id)
                        setSelectedAgents(next)
                      }}
                      className="sync-checkbox"
                    />
                    <span className="sync-target-icon">{t.icon}</span>
                    <span className="sync-target-info">
                      <span className="sync-target-label">{t.label}</span>
                      <span className="sync-target-path">{t.description}</span>
                    </span>
                    {syncResults[t.id] && (
                      <span className="sync-result">{syncResults[t.id]}</span>
                    )}
                  </label>
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
                <button
                  className="btn btn-primary"
                  style={{ width: 'auto', padding: '8px 24px' }}
                  disabled={syncLoading || selectedAgents.size === 0 || !cid}
                  onClick={runSync}
                >
                  {syncLoading ? '同步中...' : `🔄 同步到 ${selectedAgents.size} 个工具`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
