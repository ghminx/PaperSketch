"""원본 검토 agent를 유지한 응답 검증·그림에 연결된 검토 기록."""
import base64
import hashlib
import json

from agents.critic_agent import CriticAgent
from agents.refiner.pb_interact import PBInteract
from utils.base64_rw_helper import read_base64
from review_protocol import review_plan, ReviewDecision, context_hash

REWRITE_FIELDS = ['critic_suggestions', 'revised_description']


async def review_record(data: dict, field: str, status: str, details: dict) -> dict:
    """검토 대상 이미지 bytes와 요구 문맥을 판정에 연결."""
    image = await read_base64(data.get(field))
    return {'status': status if image else 'review_failed', 'image_field': field,
            'image_sha256': hashlib.sha256(base64.b64decode(image, validate=True)).hexdigest() if image else None,
            'context_sha256': context_hash(data), 'details': details}


def pb_steps(data: dict, *, final=False) -> list[dict]:
    """원본 PBInteract의 현재 턴에 맞춘 필수 응답 항목 구성."""
    count = sum(t['role'] == 'user' for t in data['chat_history'])
    steps = []
    if data['current_critic_round'][1] == 0:
        fields = [k for n in range(1, count+1) for k in (f'context_diagram{n}', f'context_user_turn{n}')]
        steps.append({'stage': 'context', 'fields': fields, 'final': final})
    fields = ['critique_latest_turn', *[f'critique_prior_turn{n}' for n in range(1, count)],
              'critique_source_content', 'critique_presentation']
    steps += [{'stage': 'critique', 'fields': fields, 'final': final},
              {'stage': 'gate', 'final': final, 'stop_after_gate': final}]
    if not final:
        steps.append({'stage': 'rewrite', 'fields': REWRITE_FIELDS})
    return steps


class ValidatedCriticAgent(CriticAgent):
    """원본 Critic 입력·처리 뒤에 유효 응답과 대상 그림 기록 연결."""
    async def process(self, data, source='stylist'):
        index = data.get('current_critic_round', 0)
        field = f'target_diagram_{source}_desc0_base64_jpg' if index == 0 else f'target_diagram_critic_desc{index-1}_base64_jpg'
        if index == 0 and source == 'planner':
            field = 'target_diagram_desc0_base64_jpg'
        step = {'stage': 'rewrite', 'fields': REWRITE_FIELDS}
        with review_plan([step]):
            result = await super().process(data, source=source)
        value = json.loads(step['response'])
        status = 'passed' if value['critic_suggestions'] == 'No changes needed.' else 'issues_remaining'
        record = await review_record(data, field, status, value)
        result['_latest_review'] = record
        result.setdefault('review_history', []).append(record)
        return result


class ValidatedPBInteract(PBInteract):
    """원본 이력 문맥화·비평·판단·수정의 단계별 응답 검사."""
    async def process(self, data):
        field = data['eval_image_field']
        steps = pb_steps(data)
        with review_plan(steps):
            result = await super().process(data)
        critique = next(s for s in steps if s['stage'] == 'critique')
        gate = next(s for s in steps if s['stage'] == 'gate')
        record = await review_record(data, field, 'passed' if gate['response'] == 'NO' else 'issues_remaining',
                                     {'critique': json.loads(critique['response']), 'decision': gate['response']})
        result['_latest_review'] = record
        result.setdefault('review_history', []).append(record)
        return result


async def final_review(processor, data: dict, action: str) -> dict:
    """선택 그림을 읽기 전용으로 검토하고 추가 이미지 생성 없이 세 상태 반환."""
    field = data['eval_image_field']
    target = await review_record(data, field, 'review_failed', {})
    previous = data.get('_latest_review')
    if previous and previous['status'] in ('passed', 'issues_remaining') and all(
            previous[k] == target[k] for k in ('image_field', 'image_sha256', 'context_sha256')):
        return {**previous, 'reused_existing_review': True}
    copied = dict(data)
    try:
        if action == 'generate':
            copied.update(current_critic_round=0, target_diagram_stylist_desc0=data[field.removesuffix('_base64_jpg')],
                          target_diagram_stylist_desc0_base64_jpg=data[field])
            step = {'stage': 'rewrite', 'fields': REWRITE_FIELDS, 'final': True}
            with review_plan([step]):
                await CriticAgent.process(processor.critic_agent, copied, source='stylist')
            value = json.loads(step['response'])
            status = 'passed' if value['critic_suggestions'] == 'No changes needed.' else 'issues_remaining'
            return {**target, 'status': status, 'details': value, 'reused_existing_review': False}
        # 완료 assistant 발언을 제외하여 원본 검토 시점의 pending 이력 복원
        copied['chat_history'] = data['chat_history'][:-1]
        i, j = data['current_critic_round']
        copied['current_critic_round'] = [i, max(1, j+1)]
        steps = pb_steps(copied, final=True)
        try:
            with review_plan(steps):
                await PBInteract.process(processor.refiner_agent, copied)
        except ReviewDecision as decision:
            critique = next(s for s in steps if s['stage'] == 'critique')
            return {**target, 'status': 'passed' if decision.decision == 'NO' else 'issues_remaining',
                    'details': {'critique': json.loads(critique['response']), 'decision': decision.decision},
                    'reused_existing_review': False}
        raise RuntimeError('Final PBInteract review did not reach a decision')
    except Exception as error:
        # 검토 실패 시에도 선택 그림을 유지하고 통과와 구분
        return {**target, 'status': 'review_failed', 'error_type': type(error).__name__, 'error': str(error),
                'reused_existing_review': False}
