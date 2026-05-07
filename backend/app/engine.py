import json
import re
from pathlib import Path
from typing import Dict, List
from .models import SkillSpec

SLOT_GUIDE = {
    "workflow": "请补充端到端流程步骤（触发条件→处理动作→结束条件）。",
    "rules": "请补充必须遵循的业务规则或合规要求。",
    "tools": "请补充需要调用的系统/API与鉴权方式。",
    "constraints": "请补充权限、时效、风控、审计等约束。",
    "output_format": "请补充输出格式（JSON Schema / 表格字段 / Markdown 模板）。",
}


def parse_attachment(path: str) -> Dict[str, List[str] | str]:
    p = Path(path)
    suffix = p.suffix.lower()
    content = ""

    if suffix in {".txt", ".md", ".csv", ".json", ".py", ".log"}:
        content = p.read_text(encoding="utf-8", errors="ignore")[:15000]
    elif suffix == ".pdf":
        content = _parse_pdf(p)
    elif suffix in {".docx", ".doc"}:
        content = _parse_docx(p)
    else:
        content = f"[binary:{suffix}]"

    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    rules = [ln for ln in lines if any(k in ln for k in ["必须", "禁止", "不得", "规则", "合规"])]
    workflow = [ln for ln in lines if re.search(r"(步骤|流程|->|→|第一|第二)", ln)]
    tools = [ln for ln in lines if re.search(r"(API|接口|系统|Webhook|数据库)", ln, re.IGNORECASE)]

    return {
        "summary": lines[0][:120] if lines else "",
        "rules": rules[:8],
        "workflow": workflow[:8],
        "tools": tools[:8],
        "raw_preview": "\n".join(lines[:20]),
    }


def _parse_pdf(path: Path) -> str:
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages[:20]:  # limit to 20 pages
                text = page.extract_text() or ""
                text_parts.append(text)
        return "\n".join(text_parts)[:15000]
    except ImportError:
        return "[PDF parsing requires pdfplumber]"
    except Exception as e:
        return f"[PDF parse error: {e}]"


def _parse_docx(path: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)[:15000]
    except ImportError:
        return "[DOCX parsing requires python-docx]"
    except Exception as e:
        return f"[DOCX parse error: {e}]"


def infer_spec_delta(message: str, spec: SkillSpec, parsed: dict | None = None) -> SkillSpec:
    """Rule-based spec inference (used as fallback when LLM is not configured)."""
    new = spec.model_copy(deep=True)
    text = message.strip()
    if text and not new.description:
        new.description = text[:150]

    if re.search(r"(SOP|流程|步骤|审批)", text, re.IGNORECASE):
        new.workflow.append("梳理输入条件并执行标准化流程")
    if re.search(r"(规则|合规|风控|必须|禁止)", text):
        new.rules.append("执行过程中严格遵循业务规则，冲突时中止并请求确认")
    if re.search(r"(工具|API|接口|系统)", text, re.IGNORECASE):
        new.tools.append("内部业务系统/API")
    if re.search(r"(输出|格式|JSON|表格)", text, re.IGNORECASE):
        new.output_format = "Markdown说明 + JSON结构化结果"

    if parsed:
        if parsed.get("summary") and not new.description:
            new.description = str(parsed["summary"])
        new.workflow.extend(parsed.get("workflow", []))
        new.rules.extend(parsed.get("rules", []))
        new.tools.extend(parsed.get("tools", []))

    new.constraints = list(dict.fromkeys(new.constraints + ["敏感信息必须脱敏", "高风险操作必须二次确认"]))
    new.workflow = list(dict.fromkeys(new.workflow))
    new.rules = list(dict.fromkeys(new.rules))
    new.tools = list(dict.fromkeys(new.tools))
    return new


def missing_slots(spec: SkillSpec) -> list[str]:
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


def build_reply(message: str, spec: SkillSpec) -> str:
    """Rule-based reply builder (used as fallback when LLM is not configured)."""
    miss = missing_slots(spec)
    if "确认" in message or "完成" in message:
        if not miss:
            return "所有关键槽位已完整，已进入最终确认。你可以执行测试并导出 SKILL.md。"
        return "当前尚未完成，缺少：" + "、".join(miss) + "。\n" + SLOT_GUIDE[miss[0]]
    if miss:
        return "我已更新草稿。\n下一步：" + SLOT_GUIDE[miss[0]]
    return "草稿已较完整。建议现在进行 Skill 测试，确认后导出部署。"


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


def score_spec(spec: SkillSpec) -> int:
    slots = [bool(spec.workflow), bool(spec.rules), bool(spec.tools), bool(spec.constraints), bool(spec.output_format)]
    return int(sum(slots) / len(slots) * 100)


def to_json_spec(spec: SkillSpec) -> str:
    return json.dumps(spec.model_dump(), ensure_ascii=False, indent=2)
