"""원본 검토 호출의 단계별 응답 계약과 제한된 재요청 문맥."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import hashlib

REVIEW_PLAN = ContextVar('paper_sketch_review_plan', default=None)


def context_hash(data: dict) -> str:
    """방법론·캡션·사용자 요구가 같은 검토인지 식별하는 hash 반환."""
    value = {'content': data['content'], 'caption': data['visual_intent'],
             'requests': [t['content'] for t in data.get('chat_history', []) if t['role'] == 'user']}
    if data.get('task_name') != 'plot':
        value['canvas_ratio'] = data.get('additional_info', {}).get('rounded_ratio', '1:1')
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class ReviewResponseError(ValueError):
    """두 번의 응답이 모두 검토 계약을 충족하지 못한 상태."""


class ReviewDecision(Exception):
    """최종 검토의 판단 뒤 rewrite 진행을 막는 내부 종료 신호."""
    def __init__(self, decision: str):
        self.decision = decision
        super().__init__(decision)


@contextmanager
def review_plan(steps: list[dict]):
    """명시된 에이전트 단계에만 응답 검사 적용."""
    token = REVIEW_PLAN.set(iter(steps))
    try:
        yield
    finally:
        REVIEW_PLAN.reset(token)


def validate_review(text: str, contract: dict) -> str:
    """필수 문자열·판단·무변경 일관성을 검사한 원본 호환 응답 반환."""
    if contract['stage'] == 'gate':
        result = text.strip().upper()
        if result not in ('YES', 'NO'):
            raise ValueError('Expected exactly YES or NO')
        return result
    cleaned = text.strip()
    if cleaned.startswith('```json') and cleaned.endswith('```'):
        cleaned = cleaned[7:-3].strip()
    elif cleaned.startswith('```') and cleaned.endswith('```'):
        cleaned = cleaned[3:-3].strip()
    result = json.loads(cleaned)
    fields = contract['fields']
    if not isinstance(result, dict) or set(result) != set(fields):
        raise ValueError('Expected exactly these fields: ' + ', '.join(fields))
    if any(not isinstance(result[k], str) or not result[k].strip() for k in fields):
        raise ValueError('All required values must be non-empty strings')
    if contract['stage'] == 'rewrite':
        no_change = [result[k].strip().rstrip('.').casefold() == 'no changes needed' for k in fields]
        if any(no_change) and not all(no_change):
            raise ValueError('No-change suggestions and description must agree')
        if all(no_change):
            result = {k: 'No changes needed.' for k in fields}
    return json.dumps(result, ensure_ascii=False)
