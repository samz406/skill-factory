import json
import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from pathlib import Path
from .models import ChatRequest, ChatMessage, TestRequest, TestResponse, SkillSpec, SkillEvaluation
from .store import store
from .engine import build_reply, infer_spec_delta, render_skill_md, parse_attachment, score_spec, missing_slots
from .llm import (
    is_llm_configured,
    list_providers,
    llm_chat_reply,
    llm_chat_stream,
    llm_extract_spec,
    llm_test_skill,
    llm_evaluate_skill,
    llm_improve_skill,
    maybe_compress,
)
from .database import (
    db_save_evaluation,
    db_get_evaluation,
    db_list_evaluations,
)
from .config import settings, PROVIDER_CONFIGS, get_effective_provider_config, save_llm_config

app = FastAPI(title="Skill Factory API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "llm_configured": is_llm_configured()}


@app.get("/models")
def get_models():
    """List all supported LLM providers and their configuration status."""
    return {
        "providers": list_providers(),
        "current_provider": settings.llm_provider,
        "current_model": get_effective_provider_config()["model"],
    }


class LLMSettingsRequest(BaseModel):
    provider: str
    model: str
    api_key: str
    base_url: str = ""


@app.get("/settings")
def get_settings():
    """Return current LLM configuration."""
    cfg = get_effective_provider_config()
    return {
        "provider": settings.llm_provider,
        "model": cfg["model"],
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
    }


@app.post("/settings")
def update_settings(req: LLMSettingsRequest):
    """Save LLM configuration to file and apply immediately."""
    save_llm_config(
        provider=req.provider,
        api_key=req.api_key,
        model=req.model,
        base_url=req.base_url,
    )
    return {"ok": True, "llm_configured": bool(req.api_key)}


@app.post("/chat")
async def chat(req: ChatRequest):
    _apply_request_overrides(req)

    draft = store.get(req.conversation_id) if req.conversation_id else store.create()
    draft.messages.append(ChatMessage(role="user", content=req.message))

    reply = ""
    if is_llm_configured():
        await maybe_compress(draft)
        reply = await llm_chat_reply(draft.messages, draft.spec, draft.history_summary)
        updated_spec = await llm_extract_spec(draft.messages, draft.spec)
        if updated_spec:
            draft.spec = updated_spec
        else:
            draft.spec = infer_spec_delta(req.message, draft.spec)
    else:
        draft.spec = infer_spec_delta(req.message, draft.spec)

    if not reply:
        reply = build_reply(req.message, draft.spec)

    draft.messages.append(ChatMessage(role="assistant", content=reply))
    store.save(draft)
    miss = missing_slots(draft.spec)
    return {
        "conversation_id": draft.conversation_id,
        "reply": reply,
        "spec": draft.spec.model_dump(),
        "missing_slots": miss,
        "need_confirmation": ("确认" in req.message or "完成" in req.message) and not miss,
        "llm_used": is_llm_configured(),
    }


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat endpoint using Server-Sent Events."""
    _apply_request_overrides(req)

    draft = store.get(req.conversation_id) if req.conversation_id else store.create()
    draft.messages.append(ChatMessage(role="user", content=req.message))
    conversation_id = draft.conversation_id

    async def event_generator():
        yield f"data: {json.dumps({'type': 'init', 'conversation_id': conversation_id})}\n\n"

        full_reply = ""
        if is_llm_configured():
            await maybe_compress(draft)
            async for token in llm_chat_stream(draft.messages, draft.spec, draft.history_summary):
                full_reply += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        else:
            fallback_reply = build_reply(req.message, draft.spec)
            full_reply = fallback_reply
            yield f"data: {json.dumps({'type': 'token', 'content': fallback_reply})}\n\n"

        if is_llm_configured() and full_reply:
            draft.messages.append(ChatMessage(role="assistant", content=full_reply))
            updated_spec = await llm_extract_spec(draft.messages, draft.spec)
            if updated_spec:
                draft.spec = updated_spec
            else:
                draft.spec = infer_spec_delta(req.message, draft.spec)
        else:
            draft.messages.append(ChatMessage(role="assistant", content=full_reply))
            draft.spec = infer_spec_delta(req.message, draft.spec)

        store.save(draft)
        miss = missing_slots(draft.spec)
        yield f"data: {json.dumps({'type': 'done', 'spec': draft.spec.model_dump(), 'missing_slots': miss, 'need_confirmation': ('确认' in req.message or '完成' in req.message) and not miss})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/upload/{conversation_id}")
async def upload(conversation_id: str, file: UploadFile = File(...)):
    draft = store.get(conversation_id)
    if not draft.conversation_id:
        raise HTTPException(status_code=404, detail="conversation not found")

    target = store.attachments / f"{conversation_id}_{file.filename}"
    data = await file.read()
    target.write_bytes(data)
    parsed = parse_attachment(str(target))
    draft.attachments.append(str(target))
    draft.spec = infer_spec_delta("附件已上传", draft.spec, parsed)

    preview = parsed.get("raw_preview", "")[:200]
    msg = f"已解析附件：{file.filename}\n\n提取预览：\n{preview}"
    draft.messages.append(ChatMessage(role="assistant", content=msg))
    store.save(draft)
    return {"ok": True, "path": str(target), "parsed": parsed, "spec": draft.spec.model_dump()}


@app.get("/draft/{conversation_id}")
def get_draft(conversation_id: str):
    draft = store.get(conversation_id)
    return {**draft.model_dump(), "missing_slots": missing_slots(draft.spec), "score": score_spec(draft.spec)}


@app.post("/render")
def render(spec: SkillSpec):
    return {"skill_md": render_skill_md(spec)}


@app.post("/test", response_model=TestResponse)
async def test(req: TestRequest):
    answer = ""
    if is_llm_configured():
        answer = await llm_test_skill(req.skill_spec, req.query)

    if not answer:
        answer = f'模拟执行完成：针对"{req.query}"输出建议结果。'

    checks = [
        "workflow ok" if req.skill_spec.workflow else "workflow missing",
        "rules ok" if req.skill_spec.rules else "rules missing",
        "tools ok" if req.skill_spec.tools else "tools missing",
        "output_format ok" if req.skill_spec.output_format else "output_format missing",
    ]
    return TestResponse(
        answer=answer,
        checks=checks,
        score=score_spec(req.skill_spec),
        tool_calls=[{"name": req.skill_spec.tools[0], "status": "simulated"}] if req.skill_spec.tools else [],
    )


@app.post("/export/{conversation_id}")
def export(conversation_id: str):
    draft = store.get(conversation_id)
    content = render_skill_md(draft.spec)
    export_dir = Path(store.root) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / f"{conversation_id}.md"
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "file": str(target), "score": score_spec(draft.spec), "content": content}


def _apply_request_overrides(req: ChatRequest) -> None:
    """Override global LLM settings for this request if provider/model/api_key specified."""
    if req.api_key:
        settings.llm_api_key = req.api_key
    if req.provider:
        settings.llm_provider = req.provider
        if not req.api_key:
            cfg = PROVIDER_CONFIGS.get(req.provider, {})
            api_key = os.getenv(cfg.get("env_key", ""), "")
            if api_key:
                settings.llm_api_key = api_key
    if req.model:
        settings.llm_model = req.model


# ──────────────────────────────────────────────
# Skill evaluation (quality scoring + caching)
# ──────────────────────────────────────────────

@app.post("/evaluate/{conversation_id}")
async def evaluate_skill(conversation_id: str):
    """Run LLM-based quality evaluation for a skill and cache the result."""
    draft = store.get(conversation_id)
    if not draft.conversation_id:
        raise HTTPException(status_code=404, detail="conversation not found")

    skill_md = render_skill_md(draft.spec)
    basic_score = score_spec(draft.spec)

    llm_data: dict = {}
    if is_llm_configured():
        llm_data = await llm_evaluate_skill(draft.spec, skill_md)

    # Build evaluation from LLM data (or fall back to rule-based scoring)
    dimensions: dict = llm_data.get("dimensions", {})
    if not dimensions:
        # Rule-based fallback dimensions
        dimensions = {
            "description_quality": min(100, len(draft.spec.description) * 2) if draft.spec.description else 0,
            "workflow_completeness": min(100, len(draft.spec.workflow) * 20) if draft.spec.workflow else 0,
            "rules_specificity": min(100, len(draft.spec.rules) * 25) if draft.spec.rules else 0,
            "output_clarity": 100 if draft.spec.output_format else 0,
            "tool_coverage": min(100, len(draft.spec.tools) * 33) if draft.spec.tools else 0,
            "constraint_rigor": min(100, len(draft.spec.constraints) * 33) if draft.spec.constraints else 0,
        }

    overall_score = llm_data.get("score", basic_score)
    feedback = llm_data.get("feedback", "基于规则评估完成，建议配置 LLM 获取更详细的质量分析。")
    suggestions = llm_data.get("suggestions", [])
    if not suggestions:
        from .engine import missing_slots as _missing
        miss = _missing(draft.spec)
        if miss:
            suggestions = [f"补充缺失槽位：{', '.join(miss)}"]
        if not draft.spec.description or len(draft.spec.description) < 50:
            suggestions.append("扩展 description 字段，详细描述技能适用场景和触发条件（建议50字以上）")
        if draft.spec.workflow and len(draft.spec.workflow) < 3:
            suggestions.append("细化 workflow 步骤，建议至少3个有序步骤以确保完整覆盖流程")

    evaluation = SkillEvaluation(
        conversation_id=conversation_id,
        score=overall_score,
        dimensions=dimensions,
        feedback=feedback,
        suggestions=suggestions,
    )
    saved = db_save_evaluation(evaluation)
    return saved.model_dump()


@app.get("/evaluate/{conversation_id}")
def get_evaluation(conversation_id: str):
    """Return the most recent evaluation for a conversation."""
    evaluation = db_get_evaluation(conversation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="no evaluation found for this conversation")
    return evaluation.model_dump()


@app.get("/evaluations")
def list_evaluations():
    """Return all cached skill evaluations ordered by most recent first."""
    return {"evaluations": db_list_evaluations()}


# ──────────────────────────────────────────────
# Skill improvement (judge-driven auto-improvement)
# ──────────────────────────────────────────────

@app.post("/improve/{conversation_id}")
async def improve_skill(conversation_id: str):
    """Auto-improve the skill spec using the latest evaluation feedback.

    If no evaluation is cached, runs one first.  The updated spec is saved
    back to the draft and both old/new scores are returned so the caller can
    show the improvement delta.
    """
    draft = store.get(conversation_id)
    if not draft.conversation_id:
        raise HTTPException(status_code=404, detail="conversation not found")

    # Ensure we have evaluation data to guide the improvement
    evaluation = db_get_evaluation(conversation_id)
    if not evaluation:
        # Run a fresh evaluation first
        skill_md = render_skill_md(draft.spec)
        basic_score = score_spec(draft.spec)
        llm_data: dict = {}
        if is_llm_configured():
            llm_data = await llm_evaluate_skill(draft.spec, skill_md)

        dimensions: dict = llm_data.get("dimensions", {})
        if not dimensions:
            dimensions = {
                "description_quality": min(100, len(draft.spec.description) * 2) if draft.spec.description else 0,
                "workflow_completeness": min(100, len(draft.spec.workflow) * 20) if draft.spec.workflow else 0,
                "rules_specificity": min(100, len(draft.spec.rules) * 25) if draft.spec.rules else 0,
                "output_clarity": 100 if draft.spec.output_format else 0,
                "tool_coverage": min(100, len(draft.spec.tools) * 33) if draft.spec.tools else 0,
                "constraint_rigor": min(100, len(draft.spec.constraints) * 33) if draft.spec.constraints else 0,
            }
        evaluation_obj = SkillEvaluation(
            conversation_id=conversation_id,
            score=llm_data.get("score", basic_score),
            dimensions=dimensions,
            feedback=llm_data.get("feedback", ""),
            suggestions=llm_data.get("suggestions", []),
        )
        evaluation = db_save_evaluation(evaluation_obj)

    score_before = evaluation.score
    eval_dict = evaluation.model_dump()

    improved_spec: SkillSpec | None = None
    if is_llm_configured():
        improved_spec = await llm_improve_skill(draft.spec, eval_dict)

    if not improved_spec:
        # Rule-based fallback: fill obvious gaps
        improved_spec = draft.spec.model_copy(deep=True)
        if not improved_spec.description or len(improved_spec.description) < 50:
            improved_spec.description = (improved_spec.description or "") + "。适用场景：请补充具体使用场景和触发条件。"
        if len(improved_spec.workflow) < 3:
            improved_spec.workflow = improved_spec.workflow + [
                s for s in ["梳理输入条件并初始化执行上下文", "执行核心业务处理逻辑", "验证输出并记录执行结果"]
                if s not in improved_spec.workflow
            ][: max(0, 3 - len(improved_spec.workflow))]
        if not improved_spec.constraints:
            improved_spec.constraints = ["敏感信息必须脱敏处理", "高风险操作需二次确认"]
        if not improved_spec.output_format:
            improved_spec.output_format = "返回 JSON 对象：{\"status\": \"success|failed\", \"result\": \"处理结果摘要\"}"

    draft.spec = improved_spec
    store.save(draft)

    score_after = score_spec(improved_spec)

    # Append a summary message to the conversation so the user sees what changed
    summary_lines = [f"🔧 **Skill 自动优化完成**（评分：{score_before} → {score_after} 分）"]
    if eval_dict.get("suggestions"):
        summary_lines.append("\n已根据以下建议进行优化：")
        for s in eval_dict["suggestions"][:3]:
            summary_lines.append(f"- {s}")
    summary_lines.append("\n请检查右侧 SkillSpec 并继续完善，或点击「渲染 SKILL.md」查看最新结果。")
    draft.messages.append(ChatMessage(role="assistant", content="\n".join(summary_lines)))
    store.save(draft)

    return {
        "ok": True,
        "score_before": score_before,
        "score_after": score_after,
        "delta": score_after - score_before,
        "spec": improved_spec.model_dump(),
        "message": "\n".join(summary_lines),
    }


# ──────────────────────────────────────────────
# Conversation history management
# ──────────────────────────────────────────────

@app.get("/conversations")
def list_conversations():
    """List all conversations ordered by last update."""
    return {"conversations": store.list()}


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages."""
    deleted = store.delete(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True}


import re as _re

_SAFE_NAME_RE = _re.compile(r"[^\w\-]")  # keep word chars and hyphens only


def _sanitize_skill_name(spec_name: str, fallback: str = "skill") -> str:
    """Return a safe file-system name containing only word characters and hyphens."""
    raw = (spec_name or fallback).replace(" ", "_")
    safe = _SAFE_NAME_RE.sub("", raw)
    return safe or fallback


def _validate_sync_path(raw: str) -> Path:
    """Expand and resolve a user-supplied sync path, rejecting traversal attempts.

    Only paths inside the user's home directory are accepted for custom_path.
    """
    resolved = Path(raw).expanduser().resolve()
    home = Path.home().resolve()
    if not str(resolved).startswith(str(home)):
        raise HTTPException(
            status_code=400,
            detail="custom_path must be inside the user's home directory",
        )
    return resolved


# ──────────────────────────────────────────────
# Task 2: Direct skill file download
# ──────────────────────────────────────────────

@app.get("/download/{conversation_id}")
def download_skill(conversation_id: str):
    """Return the rendered SKILL.md as a downloadable file attachment."""
    draft = store.get(conversation_id)
    if not draft.conversation_id:
        raise HTTPException(status_code=404, detail="conversation not found")
    content = render_skill_md(draft.spec)
    skill_name = _sanitize_skill_name(draft.spec.name, conversation_id)
    filename = f"{skill_name}.md"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ──────────────────────────────────────────────
# Task 3: Sync skill to agent tools
# ──────────────────────────────────────────────

AGENT_TARGETS = {
    "claude_code": {
        "id": "claude_code",
        "label": "Claude Code",
        "icon": "🤖",
        "description": "Claude Code Skills 目录 (~/.claude/skills/)",
        "path_template": "~/.claude/skills/{skill_name}/SKILL.md",
    },
    "cursor": {
        "id": "cursor",
        "label": "Cursor",
        "icon": "🖱️",
        "description": "Cursor IDE 规则文件 (~/.cursor/rules/)",
        "path_template": "~/.cursor/rules/{skill_name}.md",
    },
    "cline": {
        "id": "cline",
        "label": "Cline (VS Code)",
        "icon": "💻",
        "description": "Cline VS Code 扩展 (~/.cline/rules/)",
        "path_template": "~/.cline/rules/{skill_name}.md",
    },
    "continue": {
        "id": "continue",
        "label": "Continue.dev",
        "icon": "▶️",
        "description": "Continue.dev 编码助手 (~/.continue/skills/)",
        "path_template": "~/.continue/skills/{skill_name}.md",
    },
    "open_claw": {
        "id": "open_claw",
        "label": "Open Claw",
        "icon": "🦅",
        "description": "Open Claw Agent (~/.openclaw/skills/)",
        "path_template": "~/.openclaw/skills/{skill_name}.md",
    },
    "hermes": {
        "id": "hermes",
        "label": "Hermes",
        "icon": "🌐",
        "description": "Hermes Agent (~/.hermes/skills/)",
        "path_template": "~/.hermes/skills/{skill_name}.md",
    },
}


@app.get("/agent_targets")
def get_agent_targets():
    """Return the list of supported agent sync targets."""
    return {"targets": list(AGENT_TARGETS.values())}


class SyncRequest(BaseModel):
    target_id: str
    custom_path: str = ""  # optional override for the destination directory


@app.post("/sync/{conversation_id}")
def sync_skill(conversation_id: str, req: SyncRequest):
    """Write the rendered SKILL.md into the target agent's config directory."""
    draft = store.get(conversation_id)
    if not draft.conversation_id:
        raise HTTPException(status_code=404, detail="conversation not found")

    target = AGENT_TARGETS.get(req.target_id)
    if not target and not req.custom_path:
        raise HTTPException(status_code=400, detail=f"unknown target_id: {req.target_id}")

    skill_name = _sanitize_skill_name(draft.spec.name)
    content = render_skill_md(draft.spec)

    if req.custom_path:
        dest_dir = _validate_sync_path(req.custom_path)
        dest_file = dest_dir / f"{skill_name}.md"
    else:
        path_tpl: str = target["path_template"]  # type: ignore[index]
        dest_file = Path(path_tpl.replace("{skill_name}", skill_name)).expanduser()
        dest_dir = dest_file.parent

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file.write_text(content, encoding="utf-8")

    return {
        "ok": True,
        "target": req.target_id or "custom",
        "file": str(dest_file),
    }
