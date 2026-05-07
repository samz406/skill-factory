# Skill Factory 需求规格说明（PR补充文档）

## 1. 目标与定位
Skill Factory 是企业 AI Agent 场景下的“知识编译器”，将企业沉淀的 SOP、FAQ、流程制度、专家经验等知识，转译为可执行的 Skill 能力描述。

核心目标：
- 降低企业 AI 落地门槛。
- 让非 Prompt 工程师也能构建可用 Skill。
- 形成“知识资产 -> SkillSpec -> SKILL.md -> 测试 -> 导出部署”的闭环。

## 2. 核心用户与场景
- 运营、客服、审核、销售支持、知识管理人员。
- AI 产品经理与业务分析师。
- 企业内部 Agent 平台实施团队。

典型场景：
- 客服 SOP 自动化答复与处置流程。
- 审核流程规则化处理与风险校验。
- 企业知识库问答与标准化输出。

## 3. 功能需求（MVP）

### 3.1 Chat-first Skill Builder
1. 用户通过聊天描述业务背景、流程、规则、约束。
2. 系统自动提取并填充 SkillSpec 槽位：
   - workflow
   - rules
   - tools
   - constraints
   - output_format
3. 系统根据缺失槽位自动追问。
4. 用户确认“完成”后，系统给出完成状态和后续建议。

### 3.2 文档与附件处理
1. 支持上传本地附件（MVP：先存本地）。
2. 可解析文本类附件并抽取：流程、规则、工具线索。
3. 解析结果可回填到 SkillSpec。

### 3.3 SkillSpec 构建
SkillSpec 采用统一中间结构：
```json
{
  "name": "",
  "description": "",
  "role": "",
  "workflow": [],
  "rules": [],
  "tools": [],
  "constraints": [],
  "exceptions": [],
  "output_format": ""
}
```

### 3.4 Skill 渲染与导出
1. 支持 SkillSpec -> SKILL.md 渲染。
2. 支持导出到本地文件（Markdown）。
3. 输出导出结果路径与完整度评分。

### 3.5 Skill 测试
1. 提供模拟测试接口。
2. 返回：
   - 模拟回答
   - 检查项结果（workflow/rules/tools/output）
   - 评分
   - 模拟 tool calls

## 4. 非功能需求
- 本地开发可运行（前后端分离）。
- API 可扩展为生产部署（容器化友好）。
- 代码具备基础测试覆盖。
- 存储路径可配置（`SKILL_FACTORY_STORAGE`）。

## 5. API 需求映射
- `POST /chat`: 对话驱动提取与追问。
- `POST /upload/{conversation_id}`: 附件上传与解析回填。
- `GET /draft/{conversation_id}`: 获取当前草稿、缺失槽位、评分。
- `POST /render`: 渲染 SKILL.md。
- `POST /test`: 模拟测试与评分。
- `POST /export/{conversation_id}`: 导出 Skill 文档。

## 6. 前端需求映射
- 聊天主界面：消息流、发送状态、完成确认提示。
- 工作台侧栏：
  - 缺失槽位展示
  - SkillSpec 实时预览
  - 测试执行入口
- 附件上传入口并与会话绑定。

## 7. 验收标准
1. 能通过聊天持续构建 SkillSpec。
2. 能上传附件并将解析结果回填草稿。
3. 能展示缺失槽位并引导补全。
4. 能执行模拟测试并返回评分。
5. 能导出 SKILL.md 文件。
6. README 包含开发、测试、部署说明。

## 8. 后续扩展（非MVP）
- 图片 OCR / 流程图理解。
- 企业知识库与 Confluence/飞书集成。
- 版本管理、审计日志、评估体系（SkillOps）。
- 多平台 Skill Renderer 与 Marketplace。
