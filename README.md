# Skill Factory

Skill Factory 是一套面向企业 AI Agent 场景的 Skill 构建平台，定位为“AI Agent 时代的知识编译器”。

它通过聊天交互、文档解析、图片理解与 AI 自动追问，将企业中的 SOP、FAQ、流程说明和专家经验等非结构化知识，逐步转化为可执行、可测试、可导出的标准化 AI Skill。

## 架构
- `frontend/`: React + Vite 聊天式 Skill Builder UI
- `backend/`: FastAPI 服务，负责解析、追问、SkillSpec、导出
- `data/`: 本地文件存储（附件、草稿、导出）
- `docs/`: 需求文档与任务拆解说明

## 功能清单
- 🤖 **多模型聊天**：支持 OpenAI、DeepSeek、Qwen（通义）、Kimi（月之暗面）
- 💬 **流式对话**：SSE 实时流式输出，对话体验流畅
- 📝 **智能 Skill 构建**：LLM 自动追问缺失槽位，补全 SkillSpec
- 📎 **文档解析**：支持 PDF / Word / Markdown / TXT，自动提取规则和流程
- 🏗️ **SkillSpec 管理**：实时预览结构化 Skill 描述
- 📋 **SKILL.md 渲染**：一键生成标准化 Skill 文档
- 🧪 **Skill 测试**：LLM 模拟执行 + 规则检查 + 评分
- ⬇️ **导出部署**：下载 SKILL.md 文件

## 本地开发

### 后端
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm install
npm run dev
```

默认前端请求 `http://localhost:8000`，可通过 `VITE_API_URL` 覆盖。

## 配置

### 存储
- `SKILL_FACTORY_STORAGE`：本地存储目录（默认 `./data`）

### LLM 配置（选择其一）

| 环境变量 | 说明 | 示例 |
|----------|------|------|
| `LLM_PROVIDER` | 模型厂商 | `openai` / `deepseek` / `qwen` / `kimi` |
| `LLM_API_KEY` | 通用 API Key | `sk-...` |
| `LLM_MODEL` | 覆盖默认模型 | `gpt-4o` |
| `LLM_BASE_URL` | 覆盖 API 地址 | `https://api.openai.com/v1` |
| `OPENAI_API_KEY` | OpenAI 专用 Key | `sk-...` |
| `DEEPSEEK_API_KEY` | DeepSeek 专用 Key | `sk-...` |
| `QWEN_API_KEY` | Qwen 专用 Key | `sk-...` |
| `KIMI_API_KEY` | Kimi 专用 Key | `sk-...` |

**示例（DeepSeek）：**
```bash
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-your-key
uvicorn app.main:app --reload --port 8000
```

**示例（Qwen）：**
```bash
export LLM_PROVIDER=qwen
export QWEN_API_KEY=sk-your-key
uvicorn app.main:app --reload --port 8000
```

未配置 LLM 时，系统自动切换为规则模式（可正常运行，追问和测试效果较弱）。

## 测试
### 后端
```bash
cd backend
PYTHONPATH=. pytest tests/test_api.py -v
```

### 前端
```bash
cd frontend
npm run test
```

## API 文档
启动后端后访问：`http://localhost:8000/docs`

主要接口：
- `POST /chat` - 对话（含 LLM 追问与 SkillSpec 更新）
- `POST /chat/stream` - 流式对话（SSE）
- `POST /upload/{conversation_id}` - 文档上传与解析
- `GET /draft/{conversation_id}` - 获取当前草稿
- `POST /render` - 渲染 SKILL.md
- `POST /test` - 模拟测试与评分
- `POST /export/{conversation_id}` - 导出 Skill 文档
- `GET /models` - 查看支持的模型列表

## 编译与部署
### 构建
```bash
cd frontend && npm run build
cd ../backend && pip install -r requirements.txt
```

### 生产运行
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

前端 `dist/` 可部署到 Nginx/Vercel/Netlify，后端可部署到容器或 VM。

