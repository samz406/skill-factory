# Skill Factory

企业知识到 AI Skill 的编译系统（MVP）。

## 架构
- `frontend/`: React + Vite 聊天式 Skill Builder UI
- `backend/`: FastAPI 服务，负责解析、追问、SkillSpec、导出
- `data/`: 本地文件存储（附件、草稿、导出）
- `docs/TASK_BREAKDOWN.md`: 任务拆解与实现说明

## 功能清单（MVP）
- 聊天驱动 Skill 构建（自动追问 + 确认）
- 文档上传（本地落盘）
- SkillSpec 草稿维护
- SKILL.md 渲染
- 模拟测试（规则检查 + 评分）
- 导出部署文件（Markdown）

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
- `SKILL_FACTORY_STORAGE`：本地存储目录（默认 `./data`）

## 测试
### 后端
```bash
cd backend
pytest
```

### 前端
```bash
cd frontend
npm run test
```

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
