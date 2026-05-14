"""LLM client supporting OpenAI, DeepSeek, Qwen, and Kimi via OpenAI-compatible APIs."""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, List

from .config import PROVIDER_CONFIGS, get_effective_provider_config, settings
from .models import ChatMessage, SkillSpec

logger = logging.getLogger(__name__)

COMPRESS_THRESHOLD = 20   # compress history when messages exceed this count
COMPRESS_KEEP_RECENT = 8  # keep the most recent N messages uncompressed

HISTORY_COMPRESS_PROMPT = """请将以下对话历史压缩为简洁的摘要（不超过300字），保留关键业务信息、用户提供的规则、流程步骤和决策。

对话历史：
{conversation}

只输出摘要内容，不要任何前缀或解释。"""

SYSTEM_PROMPT = """你是 Skill Factory，一个帮助企业构建 AI Agent Skill 的智能助手。

你的任务是：
1. 理解用户的业务背景、流程、规则和约束
2. 通过对话逐步完善 SkillSpec 的各个槽位：
   - workflow（端到端流程步骤）
   - rules（业务规则和合规要求）
   - tools（需要调用的 API 或系统）
   - constraints（权限、时效、风控、审计等约束）
   - output_format（输出格式规范）
3. 针对缺失的槽位主动追问
4. 引导用户完成完整的 Skill 描述

生成的 SKILL.md 将遵循行业标准格式，包含：
- YAML frontmatter（name + description，description 是触发信号，需涵盖使用场景）
- 清晰的 Workflow 步骤（有序列表）
- 精确的 Rules 和 Constraints
- 明确的 Output Format

回复要求：
- 用中文回复，亲切专业
- 每次只聚焦追问一到两个最重要的缺失信息
- 确认用户提供的新信息并给出积极反馈
- 当所有槽位填写完整时，提示用户进行测试和导出
"""

SPEC_EXTRACT_PROMPT = """根据以下对话历史，提取并更新 SkillSpec 的结构化信息。

对话历史：
{conversation}

当前 SkillSpec：
{current_spec}

请根据对话中用户提供的信息，返回更新后的 SkillSpec JSON（只返回 JSON，不要其他文字）：
{{
  "name": "Skill 名称（如能从对话中提取）",
  "description": "业务描述（简洁概括，不超过150字）",
  "role": "执行角色描述",
  "workflow": ["流程步骤1", "流程步骤2"],
  "rules": ["规则1", "规则2"],
  "tools": ["工具/API1", "工具/API2"],
  "constraints": ["约束1", "约束2"],
  "exceptions": ["异常处理1"],
  "output_format": "输出格式描述"
}}

注意：
- 保留原有信息，仅追加或更新新信息
- 如果某槽位对话中未提及，保持原值
- workflow 和 rules 等列表字段只追加新内容，不删除现有内容
"""

TEST_PROMPT = """你是一个 AI Skill 执行模拟器。

基于以下 SkillSpec，模拟执行一次用户的测试查询：

SkillSpec：
{spec}

用户测试问题：{query}

请按照 SkillSpec 中定义的流程、规则和约束来模拟回答，展示 Skill 的执行效果。
回复格式：
1. 模拟执行过程（简述关键步骤）
2. 最终输出结果
"""


def is_llm_configured() -> bool:
    """Check if LLM is properly configured with an API key."""
    cfg = get_effective_provider_config()
    return bool(cfg.get("api_key"))


def _get_client():
    """Create an OpenAI-compatible client for the configured provider."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return None

    cfg = get_effective_provider_config()
    if not cfg["api_key"]:
        return None

    return AsyncOpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
    )


def _get_model() -> str:
    cfg = get_effective_provider_config()
    return cfg["model"]


async def llm_compress_history(messages: List[ChatMessage]) -> str:
    """Summarize a list of messages into a short text. Returns empty string if LLM unavailable."""
    client = _get_client()
    if not client:
        return ""

    conversation = "\n".join(f"[{m.role}]: {m.content}" for m in messages)
    prompt = HISTORY_COMPRESS_PROMPT.format(conversation=conversation)

    try:
        resp = await client.chat.completions.create(
            model=_get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning("LLM compress history error: %s", e)
        return ""


def _build_openai_messages(
    messages: List[ChatMessage],
    current_spec: SkillSpec,
    history_summary: str | None = None,
) -> list[dict]:
    """Build the messages list to send to the LLM, with optional compressed history prefix."""
    miss = _missing_slots_list(current_spec)
    system_content = SYSTEM_PROMPT
    if miss:
        system_content += f"\n\n当前缺失槽位：{', '.join(miss)}。请针对第一个缺失槽位进行追问。"
    else:
        system_content += "\n\n所有槽位已填写完整，引导用户进行测试和导出。"

    openai_messages: list[dict] = [{"role": "system", "content": system_content}]

    if history_summary:
        openai_messages.append({
            "role": "system",
            "content": f"【历史对话摘要】\n{history_summary}",
        })

    for m in messages:
        openai_messages.append({"role": m.role, "content": m.content})

    return openai_messages


async def maybe_compress(draft) -> None:
    """If draft messages exceed threshold, compress older messages and update draft in-place."""
    if len(draft.messages) <= COMPRESS_THRESHOLD:
        return
    old_msgs = draft.messages[:-COMPRESS_KEEP_RECENT]
    recent_msgs = draft.messages[-COMPRESS_KEEP_RECENT:]
    summary = await llm_compress_history(old_msgs)
    if summary:
        draft.history_summary = f"{draft.history_summary}\n\n{summary}" if draft.history_summary else summary
        draft.messages = recent_msgs


async def llm_chat_reply(
    messages: List[ChatMessage],
    current_spec: SkillSpec,
    history_summary: str | None = None,
) -> str:
    """Generate a chat reply using the LLM. Returns empty string if LLM unavailable."""
    client = _get_client()
    if not client:
        return ""

    openai_messages = _build_openai_messages(messages, current_spec, history_summary)

    try:
        resp = await client.chat.completions.create(
            model=_get_model(),
            messages=openai_messages,
            max_tokens=800,
            temperature=0.7,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning("LLM chat error: %s", e)
        return ""


async def llm_chat_stream(
    messages: List[ChatMessage],
    current_spec: SkillSpec,
    history_summary: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream a chat reply using the LLM."""
    client = _get_client()
    if not client:
        yield ""
        return

    openai_messages = _build_openai_messages(messages, current_spec, history_summary)

    try:
        stream = await client.chat.completions.create(
            model=_get_model(),
            messages=openai_messages,
            max_tokens=800,
            temperature=0.7,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    except Exception as e:
        logger.warning("LLM stream error: %s", e)
        yield ""


async def llm_extract_spec(
    messages: List[ChatMessage],
    current_spec: SkillSpec,
) -> SkillSpec | None:
    """Extract/update SkillSpec from conversation using LLM."""
    client = _get_client()
    if not client:
        return None

    conversation = "\n".join(f"[{m.role}]: {m.content}" for m in messages)
    prompt = SPEC_EXTRACT_PROMPT.format(
        conversation=conversation,
        current_spec=json.dumps(current_spec.model_dump(), ensure_ascii=False, indent=2),
    )

    try:
        resp = await client.chat.completions.create(
            model=_get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        # Merge with current spec, preserving existing non-empty values
        merged = current_spec.model_dump()
        for key, val in data.items():
            if key in merged:
                if isinstance(val, list) and isinstance(merged[key], list):
                    # Merge lists without duplicates
                    combined = merged[key] + [v for v in val if v and v not in merged[key]]
                    merged[key] = combined
                elif val and not merged[key]:
                    merged[key] = val
                elif val and isinstance(val, str):
                    merged[key] = val
        return SkillSpec(**merged)
    except Exception as e:
        logger.warning("LLM spec extract error: %s", e)
        return None


async def llm_test_skill(spec: SkillSpec, query: str) -> str:
    """Simulate skill execution using LLM."""
    client = _get_client()
    if not client:
        return ""

    prompt = TEST_PROMPT.format(
        spec=json.dumps(spec.model_dump(), ensure_ascii=False, indent=2),
        query=query,
    )

    try:
        resp = await client.chat.completions.create(
            model=_get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.5,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning("LLM test error: %s", e)
        return ""


def list_providers() -> list[dict]:
    """List all supported LLM providers with their config."""
    result = []
    for provider, cfg in PROVIDER_CONFIGS.items():
        import os
        api_key = os.getenv(cfg["env_key"], settings.llm_api_key if settings.llm_provider == provider else "")
        result.append({
            "provider": provider,
            "default_model": cfg["default_model"],
            "base_url": cfg["base_url"],
            "configured": bool(api_key),
        })
    return result


def _missing_slots_list(spec: SkillSpec) -> list[str]:
    miss = []
    if not spec.workflow:
        miss.append("workflow")
    if not spec.rules:
        miss.append("rules")
    if not spec.tools:
        miss.append("tools")
    if not spec.constraints:
        miss.append("constraints")
    if not spec.output_format:
        miss.append("output_format")
    return miss


EVALUATE_PROMPT = """请对以下 AI Agent Skill 的质量进行全面评估。

SkillSpec:
{spec}

渲染后的 SKILL.md:
{skill_md}

请从以下维度评分（每项0-100），并给出整体反馈和可操作的改进建议。
返回严格的 JSON 格式（不要任何其他文字）：
{{
  "score": <整体综合评分 0-100>,
  "dimensions": {{
    "description_quality": <描述质量：是否清晰说明场景和触发条件 0-100>,
    "workflow_completeness": <流程完整性：步骤是否覆盖全流程 0-100>,
    "rules_specificity": <规则具体性：规则是否可执行、无歧义 0-100>,
    "output_clarity": <输出清晰度：输出格式是否明确 0-100>,
    "tool_coverage": <工具覆盖：工具依赖是否清晰定义 0-100>,
    "constraint_rigor": <约束严格性：约束是否涵盖风险点 0-100>
  }},
  "feedback": "<2-3句总体评价，指出最大优点和最主要不足>",
  "suggestions": [
    "<具体改进建议1>",
    "<具体改进建议2>",
    "<具体改进建议3>"
  ]
}}"""


async def llm_evaluate_skill(spec: SkillSpec, skill_md: str) -> dict:
    """Use LLM to evaluate skill quality and return structured evaluation data."""
    client = _get_client()
    if not client:
        return {}

    prompt = EVALUATE_PROMPT.format(
        spec=json.dumps(spec.model_dump(), ensure_ascii=False, indent=2),
        skill_md=skill_md,
    )

    try:
        resp = await client.chat.completions.create(
            model=_get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        return json.loads(raw)
    except Exception as e:
        logger.warning("LLM evaluate skill error: %s", e)
        return {}
