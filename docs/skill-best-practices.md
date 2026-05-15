# Skill 编写最佳实践

> 学习来源：Anthropic skills-creator、openclaw skill-creator 以及实际工程经验总结。

---

## 一、什么是 Skill？

Skill 是一个**自包含的能力包**，让 AI Agent 在特定任务上表现更好。可以理解为 AI Agent 的"专属 SOP 模块"：

- 把领域知识、工作流程、工具依赖编码成可重用的指令集
- 通过 `SKILL.md` 文件交付，内含 YAML frontmatter + Markdown 正文
- 当用户请求匹配时自动触发，动态加载到上下文

---

## 二、标准文件结构

```
skill-name/                     ← 技能根目录，名称即技能 ID
├── SKILL.md                    ← 必需：主文件，含 frontmatter + 说明
├── scripts/                    ← 可选：可执行脚本（Python / Bash）
├── references/                 ← 可选：参考文档（业务知识、API 文档）
└── assets/                     ← 可选：输出所需资产（模板、图片）
```

### 最小化原则

只包含**直接支持技能执行**的文件。不要添加 README.md、INSTALLATION_GUIDE.md、CHANGELOG.md 等辅助文档——这些只会增加噪音。

---

## 三、SKILL.md 格式规范

```markdown
---
name: skill-name
description: 清晰描述做什么，以及何时使用（触发场景）
---

# Skill Name

[核心说明]

## Workflow

1. 步骤一
2. 步骤二
3. 步骤三

## Rules

- 规则1
- 规则2

## Output Format

[输出格式说明]
```

### Frontmatter 关键字段

| 字段 | 说明 | 重要性 |
|------|------|--------|
| `name` | 技能唯一 ID，小写 + 连字符 | 必需 |
| `description` | **触发信号**：说明做什么 + 什么时候用 | 最关键 |

> ⚠️ **description 是触发机制**：Agent 只在 description 匹配用户请求时才加载这个 Skill。
> 它必须包含 "what" 和 "when to use"，不能只写功能而不写使用场景。

**好的 description 示例：**
```
客户服务工单处理。适用场景：(1) 接收并分类客户投诉工单，(2) 按优先级派单给对应团队，
(3) 跟踪 SLA 并触发升级，(4) 生成工单处理报告
```

**差的 description 示例：**
```
处理客服工单  ← 太简短，缺少触发场景
```

---

## 四、上下文窗口经济学（Progressive Disclosure）

上下文窗口是公共资源，Skills 共享它。设计时应分三层加载：

| 层级 | 内容 | 何时加载 | 大小建议 |
|------|------|----------|----------|
| 元数据 | name + description | 始终在上下文 | ~100 词 |
| SKILL.md 正文 | 核心指令 | 技能触发后 | < 500 行 |
| 附加资源 | scripts/references/assets | 按需加载 | 无限制 |

**核心原则**：AI 已经很聪明，只补充它**不知道的领域知识**。

---

## 五、自由度设计

根据任务的脆弱性和变化性，设计对应的自由度：

| 自由度 | 适用场景 | 实现方式 |
|--------|----------|----------|
| 高（文字说明） | 多种方法都可行，依赖上下文判断 | 高层原则 + 指引 |
| 中（伪代码/参数化脚本） | 有优选模式，但允许调整 | 模板 + 配置 |
| 低（具体脚本） | 操作易出错、强一致性要求 | 具体可执行脚本 |

---

## 六、Workflow 编写指南

### 必须做到

- **有序**：用编号列表，而非无序列表
- **端到端**：从触发条件到结束状态，完整覆盖
- **可执行**：每步骤有明确的输入、处理、输出
- **处理异常**：关键节点注明异常处理方式

### 示例

```markdown
## Workflow

1. **接收工单**：从工单系统获取待处理工单，提取分类标签和优先级
2. **分类验证**：检查分类是否匹配业务规则，无法判断时请求人工确认
3. **派单**：根据分类和优先级调用派单 API 分配给对应团队
4. **SLA 监控**：设置提醒，超时前15分钟自动发送催办通知
5. **完结记录**：工单关闭后生成处理报告并存档
```

---

## 七、Rules 编写指南

Rules 是**约束条件和业务规则**，不是操作步骤。

### 必须做到

- **具体可执行**：避免模糊表述
- **优先级明确**：冲突时有判断依据
- **合规性覆盖**：数据安全、权限控制

**好的规则：**
```
- 敏感词（附见 references/sensitive-words.md）命中时，立即停止处理并报告
- 单笔报销超过 10,000 元需部门负责人二次确认
- 所有用户个人信息在日志中必须脱敏
```

**差的规则：**
```
- 注意安全  ← 无法执行
- 做好检查  ← 无法执行
```

---

## 八、Output Format 规范

明确输出格式，让消费方（系统或人）无歧义地解析结果。

建议包含：
- 格式类型（JSON / Markdown / 表格）
- 关键字段及含义
- 成功/失败时的差异

**示例：**
```markdown
## Output Format

返回 JSON 对象：
{
  "status": "success|failed|pending",
  "ticket_id": "工单ID",
  "assigned_to": "派单人姓名",
  "sla_deadline": "ISO8601 时间",
  "summary": "处理摘要（Markdown）"
}
失败时额外包含 "error" 字段说明原因。
```

---

## 九、命名规范

| 要求 | 示例 |
|------|------|
| 全小写 + 连字符 | `customer-service` ✅ |
| 动词开头（描述动作） | `process-refund` ✅ |
| 工具命名空间前缀 | `gh-review-pr` ✅ |
| 长度 < 64 字符 | — |

❌ 避免：`CustomerService`、`cs_tool`、`my skill`

---

## 十、评估清单

在完成 Skill 前，对照以下清单自检：

- [ ] frontmatter 含 `name` 和 `description`
- [ ] `description` 涵盖**使用场景**（when to use），不只是功能描述
- [ ] Workflow 步骤有序、端到端、包含异常处理
- [ ] Rules 具体可执行，有优先级
- [ ] Output Format 明确字段和格式
- [ ] 没有添加不必要的辅助文档（README / CHANGELOG 等）
- [ ] SKILL.md 正文 < 500 行（超出则拆分到 references/）
- [ ] 名称符合规范（小写 + 连字符）

---

## 十一、参考资源

- [Anthropic Agent Skills 规范](https://github.com/anthropics/skills)
- [openclaw Skill Creator](https://github.com/openclaw/openclaw/tree/main/skills/skill-creator)
- [Skill Factory 评估报告](./skill-factory-assessment.md)
