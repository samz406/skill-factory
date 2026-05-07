from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from .models import ChatRequest, ChatMessage, TestRequest, TestResponse, SkillSpec
from .store import store
from .engine import build_reply, infer_spec_delta, render_skill_md, parse_attachment, score_spec, missing_slots

app = FastAPI(title="Skill Factory API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    draft = store.get(req.conversation_id) if req.conversation_id else store.create()
    draft.messages.append(ChatMessage(role="user", content=req.message))
    draft.spec = infer_spec_delta(req.message, draft.spec)
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
    }


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
    draft.messages.append(ChatMessage(role="assistant", content=f"已解析附件：{file.filename}\n提取预览：{parsed.get('raw_preview','')[:200]}"))
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
def test(req: TestRequest):
    checks = [
        "workflow ok" if req.skill_spec.workflow else "workflow missing",
        "rules ok" if req.skill_spec.rules else "rules missing",
        "tools ok" if req.skill_spec.tools else "tools missing",
        "output_format ok" if req.skill_spec.output_format else "output_format missing",
    ]
    return TestResponse(
        answer=f"模拟执行完成：针对“{req.query}”输出建议结果。",
        checks=checks,
        score=score_spec(req.skill_spec),
        tool_calls=[{"name": req.skill_spec.tools[0], "status": "simulated"}] if req.skill_spec.tools else []
    )


@app.post("/export/{conversation_id}")
def export(conversation_id: str):
    draft = store.get(conversation_id)
    content = render_skill_md(draft.spec)
    export_dir = Path(store.root) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / f"{conversation_id}.md"
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "file": str(target), "score": score_spec(draft.spec)}
