from .models import SkillSpec


FOLLOW_UPS = [
    "请补充该流程的输入来源与触发条件。",
    "是否有必须调用的内部工具/API？",
    "输出格式需要 JSON、表格还是自然语言？",
    "有没有强约束（合规、权限、时效）？",
]


def build_reply(message: str, spec: SkillSpec) -> str:
    hints = []
    low = message.lower()
    if "规则" in message or "rule" in low:
        hints.append("我已记录业务规则，建议再补充异常分支。")
    if "工具" in message or "api" in low:
        hints.append("我已记录工具依赖，请补充鉴权方式和失败重试策略。")
    if "完成" in message or "确认" in message:
        hints.append("已收到确认信号，我将进入最终校验阶段。")
    if not hints:
        hints.append("我已解析你的输入，正在合并到 SkillSpec 草稿。")
    return "\n".join(hints + ["\n下一步：" + FOLLOW_UPS[hash(message) % len(FOLLOW_UPS)]])


def infer_spec_delta(message: str, spec: SkillSpec) -> SkillSpec:
    new = spec.model_copy(deep=True)
    if not new.description:
        new.description = message[:120]
    if "SOP" in message or "流程" in message:
        new.workflow.append("从输入材料抽取流程节点并标准化")
    if "规则" in message:
        new.rules.append("遵循用户提供的业务规则，冲突时请求确认")
    if "输出" in message:
        new.output_format = "结构化 Markdown + JSON摘要"
    if "工具" in message or "API" in message:
        new.tools.append("企业内部API")
    new.constraints = list(dict.fromkeys(new.constraints + ["敏感信息脱敏", "关键决策需二次确认"]))
    return new


def render_skill_md(spec: SkillSpec) -> str:
    return f"""# {spec.name or 'Skill Factory Draft'}

## Description
{spec.description}

## Role
{spec.role or '企业知识编译助手'}

## Workflow
{chr(10).join(f'- {w}' for w in spec.workflow) or '- 待补充'}

## Rules
{chr(10).join(f'- {r}' for r in spec.rules) or '- 待补充'}

## Tools
{chr(10).join(f'- {t}' for t in spec.tools) or '- 待补充'}

## Constraints
{chr(10).join(f'- {c}' for c in spec.constraints) or '- 待补充'}

## Exceptions
{chr(10).join(f'- {e}' for e in spec.exceptions) or '- 待补充'}

## Output Format
{spec.output_format or '待补充'}
"""
