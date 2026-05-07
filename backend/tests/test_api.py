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
    assert '# ' in r2.json()['skill_md']


def test_test_endpoint_score():
    payload = {
        'skill_spec': {
            'name': 'x', 'description': 'd', 'role': 'r',
            'workflow': ['a'], 'rules': ['b'], 'tools': ['c'],
            'constraints': ['d'], 'exceptions': [], 'output_format': 'json'
        },
        'query': 'demo'
    }
    r = client.post('/test', json=payload)
    assert r.status_code == 200
    assert r.json()['score'] == 100
