# Skill Factory 任务实现拆解

## 1. 产品能力拆解
- Chat-first Skill 构建：对话驱动需求采集与追问。
- 多模态输入：文档上传入口（先本地存储）。
- SkillSpec 中间结构：统一生成与导出。
- Skill 渲染/测试/导出：形成闭环。

## 2. 后端实现
- FastAPI API 网关：`/chat`、`/upload`、`/draft`、`/render`、`/test`、`/export`。
- 本地存储层：`data/skill_drafts` 与 `data/attachments`。
- 轻量推理引擎：规则抽取、追问生成、确认信号识别。

## 3. 前端实现
- 现代化三栏布局 + 玻璃拟态视觉。
- 主流 LLM 聊天体验：消息气泡、输入区、状态反馈。
- 交互确认：检测“完成/确认”后提醒用户最终确认。

## 4. 质量保障
- 后端 pytest：核心 API 及渲染流程。
- 前端 vitest：基础渲染能力测试。

## 5. 部署方式
- 前后端分离部署（Vite + FastAPI）。
- 本地路径通过 `SKILL_FACTORY_STORAGE` 配置。
