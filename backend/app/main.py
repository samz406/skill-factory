from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from .models import ChatRequest, ChatMessage, TestRequest, TestResponse, SkillSpec
from .store import store
from .engine import build_reply, infer_spec_delta, render_skill_md

app = FastAPI(title="Skill Factory API", version="0.1.0")

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
    return {
        "conversation_id": draft.conversation_id,
        "reply": reply,
        "spec": draft.spec.model_dump(),
        "need_confirmation": "确认" in req.message or "完成" in req.message,
    }


@app.post("/upload/{conversation_id}")
async def upload(conversation_id: str, file: UploadFile = File(...)):
    draft = store.get(conversation_id)
    target = store.attachments / f"{conversation_id}_{file.filename}"
    data = await file.read()
    target.write_bytes(data)
    draft.attachments.append(str(target))
    draft.messages.append(ChatMessage(role="assistant", content=f"已解析附件：{file.filename}（本地存储）"))
    store.save(draft)
    return {"ok": True, "path": str(target)}


@app.get("/draft/{conversation_id}")
def get_draft(conversation_id: str):
    draft = store.get(conversation_id)
    return draft.model_dump()


@app.post("/render")
def render(spec: SkillSpec):
    return {"skill_md": render_skill_md(spec)}


@app.post("/test", response_model=TestResponse)
def test(req: TestRequest):
    checks = [
        "规则约束已载入" if req.skill_spec.rules else "规则为空",
        "输出格式已定义" if req.skill_spec.output_format else "输出格式待补充",
    ]
    score = 80 + (10 if req.skill_spec.rules else 0) + (10 if req.skill_spec.output_format else 0)
    return TestResponse(
        answer=f"模拟执行：已根据问题《{req.query}》返回建议结果。",
        checks=checks,
        score=min(score, 100),
        tool_calls=[]
    )


@app.post("/export/{conversation_id}")
def export(conversation_id: str):
    draft = store.get(conversation_id)
    content = render_skill_md(draft.spec)
    export_dir = Path(store.root) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / f"{conversation_id}.md"
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "file": str(target)}
