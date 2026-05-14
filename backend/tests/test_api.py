from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get('/health')
    assert r.status_code == 200


def test_chat_and_render():
    r = client.post('/chat', json={'message': '我们有客服SOP流程和输出规则'})
    assert r.status_code == 200
    data = r.json()
    assert data['conversation_id']
    assert 'missing_slots' in data
    spec = data['spec']
    r2 = client.post('/render', json=spec)
    assert r2.status_code == 200
    skill_md = r2.json()['skill_md']
    assert '# ' in skill_md
    # Verify YAML frontmatter is present
    assert skill_md.startswith('---\n')
    assert 'name:' in skill_md
    assert 'description:' in skill_md


def test_test_endpoint_score():
    # A complete spec that meets the weighted scoring thresholds for 100 points:
    # description >50 chars (+20), workflow >=3 steps (+25), rules >=3 (+20),
    # output_format (+15), tools >=2 (+10), constraints >=2 (+10)
    payload = {
        'skill_spec': {
            'name': 'customer-service',
            'description': '客服工单处理 Skill，适用于客诉受理、分类派单、SLA跟进等全流程场景，支持优先级管理和自动上报机制',
            'role': '客服处理助手',
            'workflow': ['接收工单并分类', '按优先级派单给对应团队', '跟踪 SLA 并发送提醒'],
            'rules': ['敏感词过滤', '高优先级工单优先处理', '超期工单自动上报'],
            'tools': ['工单系统API', '消息推送服务'],
            'constraints': ['敏感信息必须脱敏', '高风险操作必须二次确认'],
            'exceptions': [],
            'output_format': 'JSON 结构化结果 + Markdown 摘要'
        },
        'query': 'demo'
    }
    r = client.post('/test', json=payload)
    assert r.status_code == 200
    assert r.json()['score'] == 100


def test_evaluate_endpoint():
    # Create a conversation first
    r = client.post('/chat', json={'message': '我需要构建一个财务报销审批流程'})
    cid = r.json()['conversation_id']

    # Evaluate it (rule-based fallback, no LLM configured)
    r2 = client.post(f'/evaluate/{cid}')
    assert r2.status_code == 200
    data = r2.json()
    assert 'score' in data
    assert 'dimensions' in data
    assert 'feedback' in data
    assert 'suggestions' in data
    assert 'evaluation_id' in data
    assert data['conversation_id'] == cid

    # Retrieve cached evaluation
    r3 = client.get(f'/evaluate/{cid}')
    assert r3.status_code == 200
    assert r3.json()['evaluation_id'] == data['evaluation_id']

    # List all evaluations
    r4 = client.get('/evaluations')
    assert r4.status_code == 200
    assert any(e['conversation_id'] == cid for e in r4.json()['evaluations'])

