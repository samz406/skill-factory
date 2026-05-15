# Skill Factory 工程评估报告

> 基于对 Anthropic skills-creator、openclaw skill-creator 的研究，评估当前 Skill Factory 工程的现状、差距与改进路径。

---

## 一、当前系统架构

```
Frontend (React + Vite)
    ↕ REST API (FastAPI)
Backend
  ├── engine.py      - 规则推理 + SKILL.md 渲染
  ├── llm.py         - LLM 对话 / 信息提取 / 评估
  ├── models.py      - Pydantic 数据模型
  ├── database.py    - SQLite 持久化
  ├── store.py       - Draft 存储层
  └── main.py        - API 路由
```

**核心流程：** 用户对话 → LLM 提取 SkillSpec（6个槽位）→ 渲染 SKILL.md → 测试 → 导出

---

## 二、与最佳实践对比评估

### 2.1 SKILL.md 格式

| 方面 | 最佳实践 | 改进前状态 | 改进后状态 |
|------|----------|-----------|-----------|
| YAML frontmatter | 必须包含，是触发机制 | ❌ 无 frontmatter | ✅ 已添加 |
| description 作为触发信号 | 必须涵盖 what + when | ❌ 仅有短文本 | ✅ 合并 description + role + 步骤数 |
| Workflow 步骤格式 | 有序编号列表 | ❌ 无序列表 | ✅ 已改为编号列表 |
| 空内容省略 | 不填写的槽位不生成空节 | ❌ 写"待补充" | ✅ 已跳过空内容 |
| 辅助文档 | 不添加 README 等 | ✅ 无多余文件 | ✅ 保持 |

### 2.2 评分与评估

| 方面 | 最佳实践 | 改进前状态 | 改进后状态 |
|------|----------|-----------|-----------|
| 评分维度 | 多维质量评估 | ❌ 仅计数非空槽位(5个=100分) | ✅ 6维度加权评分 |
| description 质量 | 关键评分维度 | ❌ 不评估 | ✅ 长度 + 内容双维 |
| LLM 质量评估 | 深度分析 | ❌ 无 | ✅ 新增 llm_evaluate_skill() |
| 评估缓存 | 收集反馈优化 | ❌ 无持久化 | ✅ evaluations 表 + API |
| 改进建议 | 可操作 | ❌ 无 | ✅ 有具体 suggestions |

### 2.3 对话引导

| 方面 | 最佳实践 | 当前状态 | 建议 |
|------|----------|----------|------|
| 渐进式追问 | 一次聚焦1-2个问题 | ✅ 已实现 | — |
| 上下文压缩 | 长对话摘要 | ✅ 已实现 | — |
| 流式回复 | SSE 流式输出 | ✅ 已实现 | — |
| 描述触发意识 | 引导用户说清楚使用场景 | ❌ 未专门引导 | 在 SYSTEM_PROMPT 中加强 |
| 模板/示例库 | 行业模板加速 | ❌ 无 | P1 功能 |

### 2.4 技能文件管理

| 方面 | 最佳实践 | 当前状态 | 建议 |
|------|----------|----------|------|
| 附加资源支持 | scripts/references/assets | ❌ 仅单文件 | P1：支持附件打包 |
| 版本管理 | git 式版本控制 | ❌ 无 | 长期规划 |
| 导出格式 | .skill（zip）包 | ❌ 仅 .md | P1：支持 .skill 格式 |
| Agent 同步 | 多平台适配 | ✅ 已支持6个平台 | — |

---

## 三、评分详情（改进后系统）

### 新评分算法（满分100分）

| 维度 | 权重 | 计分规则 |
|------|------|----------|
| description 质量 | 20分 | 非空+10，>50字+10 |
| workflow 完整性 | 最高25分 | 有步骤+10，每步+5（封顶25） |
| rules 具体性 | 最高20分 | 有规则+5，每条+5（封顶20） |
| output_format | 15分 | 有定义+15 |
| tools 覆盖 | 最高10分 | 每工具+5（封顶10） |
| constraints 严格性 | 最高10分 | 每约束+5（封顶10） |

**达到100分需要：**
- description > 50字
- workflow >= 3个步骤
- rules >= 3条规则
- output_format 已定义
- tools >= 2个
- constraints >= 2个

### LLM 评估维度（0-100，需配置 LLM）

1. **description_quality** - 描述是否清晰说明场景和触发条件
2. **workflow_completeness** - 步骤是否覆盖全流程
3. **rules_specificity** - 规则是否可执行、无歧义
4. **output_clarity** - 输出格式是否明确
5. **tool_coverage** - 工具依赖是否清晰定义
6. **constraint_rigor** - 约束是否涵盖风险点

---

## 四、仍待改进的领域

### 优先级 P1（近期）

1. **description 引导强化**
   - 在聊天界面提示用户说明"什么时候会用到这个 Skill"
   - 引导用户补充触发场景，而非仅描述功能

2. **行业模板库**
   - 提供客服、财务、HR、法务等常用 Skill 模板
   - 加速初始槽位填充

3. **Skill 版本历史**
   - 对同一 conversation_id 的 SkillSpec 变更做版本快照
   - 支持回滚到之前版本

4. **批量测试用例**
   - 在测试面板支持添加多个测试 query
   - 批量运行并统计通过率

### 优先级 P2（中期）

5. **渐进披露结构**
   - 支持生成 `references/` 子文件（大规则文档、API文档）
   - 主 SKILL.md 精简，细节放 references

6. **.skill 打包格式**
   - 支持将 SKILL.md + 附件打包为 .skill（zip）文件
   - 与 Anthropic skills 生态兼容

7. **评估反馈闭环**
   - 评估结果收集后，用于微调 Skill 生成提示词
   - 展示历史评分趋势

### 优先级 P3（长期）

8. **Git 式版本管理**
   - 类似 git diff 对比两个版本的 SkillSpec 差异

9. **Skill Marketplace**
   - 团队间共享优质 Skill

10. **A/B 测试框架**
    - 对同一业务场景生成多个 Skill 变体，比较效果

---

## 五、改进前后对比示例

### 改进前的 SKILL.md 输出

```markdown
# 客服工单处理

## Description
处理客服工单

## Role
企业知识编译助手

## Workflow
- 接收工单
- 处理工单
- 关闭工单

## Rules
- 待补充

## Tools
- 待补充

## Constraints
- 敏感信息必须脱敏
- 高风险操作必须二次确认

## Exceptions
- 待补充

## Output Format
待补充
```

### 改进后的 SKILL.md 输出

```markdown
---
name: 客服工单处理
description: 处理客服工单。角色：客服处理助手。包含 3 个执行步骤。
---

# 客服工单处理

处理客服工单

## Role

客服处理助手

## Workflow

1. 接收工单并分类
2. 按优先级派单给对应团队
3. 跟踪 SLA 并发送提醒

## Rules

- 敏感词过滤
- 高优先级工单优先处理

## Tools

- 工单系统API

## Constraints

- 敏感信息必须脱敏
- 高风险操作必须二次确认

## Output Format

JSON 结构化结果 + Markdown 摘要
```

**关键改进：**
- ✅ 增加了标准 YAML frontmatter
- ✅ Workflow 改为有序编号列表
- ✅ 空内容槽位不再写"待补充"
- ✅ 格式与 Anthropic/openclaw 规范对齐

---

## 六、技术债清单

| 问题 | 严重程度 | 建议 |
|------|----------|------|
| SQLite 无并发写保护 | 中 | 多用户场景下改用 WAL 模式或 PostgreSQL |
| 评估结果不与 Skill 版本绑定 | 中 | 增加 spec_hash 字段，对应特定版本 |
| SKILL.md 名称使用中文 | 低 | 建议 name 字段强制英文/拼音 |
| 前端 score 计算与后端不同步 | 低 | 前端 calcScore 已废弃，统一用后端 score |

---

*最后更新：2026-05-14*
