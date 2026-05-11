import json
import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from pathlib import Path
from .models import ChatRequest, ChatMessage, TestRequest, TestResponse, SkillSpec
from .store import store
from .engine import build_reply, infer_spec_delta, render_skill_md, parse_attachment, score_spec, missing_slots
from .llm import (
    is_llm_configured,
    list_providers,
    llm_chat_reply,
    llm_chat_stream,
    llm_extract_spec,
    llm_test_skill,
    maybe_compress,
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
    skill_name = (draft.spec.name or conversation_id).replace(" ", "_") or "skill"
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
        "description": "Claude Code CLI 自定义命令 (~/.claude/commands/)",
        "path_template": "~/.claude/commands/{skill_name}.md",
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

    skill_name = (draft.spec.name or "skill").replace(" ", "_")
    content = render_skill_md(draft.spec)

    if req.custom_path:
        dest_dir = Path(req.custom_path).expanduser()
    else:
        path_tpl: str = target["path_template"]  # type: ignore[index]
        dest = Path(path_tpl.replace("{skill_name}", skill_name)).expanduser()
        dest_dir = dest.parent

    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{skill_name}.md"
    dest_file = dest_dir / filename
    dest_file.write_text(content, encoding="utf-8")

    return {
        "ok": True,
        "target": req.target_id or "custom",
        "file": str(dest_file),
    }
