"""고정 후보 4개 그룹의 6개씩 선발 후 최종 10개 검색 연결."""
import hashlib
import json
from pathlib import Path

from google.genai import types

from agents.retriever_agent import RetrieverAgent
from utils import generation_utils
from bridge import write_json


REQUEST_CHAR_BUDGET = 1_000_000
GROUP_CHAR_BUDGET = 800_000
PER_GROUP = 6


def candidate_text(index: int, row: dict) -> str:
    """원본 Retriever 형식의 전체 후보 블록 구성."""
    return (f"Candidate Diagram {index}:\n- Diagram ID: {row['id']}\n"
            f"- Caption: {row['visual_intent']}\n"
            f"- Methodology section: {str(row['content'])}\n\n")


class GroupedRetrieverAgent(RetrieverAgent):
    """auto만 단계 검색으로 교체하고 원본의 나머지 모드 계약 유지."""

    def __init__(self, *, groups_dir: Path | None, audit_path: Path | None = None, **kwargs):
        super().__init__(**kwargs)
        self.groups_dir = groups_dir
        self.audit_path = audit_path

    def _load_groups(self):
        """원본 앞 200개와 고정 그룹의 전문·순서·hash 일치 검증."""
        if self.groups_dir is None:
            raise ValueError('Grouped auto retrieval requires --reference-groups')
        raw = (self.exp_config.dataset_dir / 'ref.json').read_bytes()
        active = json.loads(raw)[:200]
        manifest_path = self.groups_dir / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if hashlib.sha256(raw).hexdigest() != manifest['source_ref_sha256']:
            raise ValueError('Reference groups do not match the prepared dataset hash')
        groups, restored = [], []
        for entry in manifest['groups']:
            rows = json.loads((self.groups_dir / entry['json_file']).read_text(encoding='utf-8'))
            text = (self.groups_dir / entry['text_file']).read_text(encoding='utf-8')
            expected = ''.join(candidate_text(len(restored) + index, row)
                               for index, row in enumerate(rows, 1))
            if (text != expected or hashlib.sha256(text.encode('utf-8')).hexdigest() != entry['text_sha256']
                    or len(text) > GROUP_CHAR_BUDGET or len(rows) < PER_GROUP):
                raise ValueError('Reference group content or size does not match its contract')
            groups.append((rows, text))
            restored.extend(rows)
        if len(groups) != 4 or len(active) != 200 or restored != active or len({r['id'] for r in active}) != 200:
            raise ValueError('Expected four ordered groups covering exactly the first 200 references')
        return active, groups, manifest

    def _request(self, data: dict, rows: list, text: str, count: int):
        """원본 관련성 기준을 유지하고 현재 선발 수·출력 schema만 변경."""
        system = self.system_prompt.split('# Output Format', 1)[0]
        system = system.replace('Top 10', f'Top {count}').replace('~200', str(len(rows)))
        system += (f'\n# Output Format\nReturn only a strictly valid JSON object whose single key '
                   f'is "selected_diagrams" and whose value is an array of exactly {count} '
                   'distinct diagram IDs from this candidate pool. Do not include explanations.\n')
        user = (f"**Target Input**\n- Caption: {data['visual_intent']}\n"
                f"- Methodology section: {str(data['content'])}\n\n**Candidate Pool**\n{text}"
                f'Now select the Top {count} most relevant diagrams using the instructions provided.')
        if len(system) + len(user) > REQUEST_CHAR_BUDGET:
            raise ValueError('Completed retrieval request exceeds the 1,000,000-character budget')
        return system, user

    def _save_audit(self, audit: dict):
        """완료 결과 이전에도 단계별 검색 진행 기록 보존."""
        if self.audit_path is not None:
            write_json(self.audit_path, audit)

    async def _select(self, data, rows, text, count, name, audit):
        """요청별 모델 선택 수행 후 허용 pool·선발 수·중복 여부 검증."""
        system, user = self._request(data, rows, text, count)
        stage = {'stage': name, 'status': 'pending', 'candidate_ids': [r['id'] for r in rows],
                 'select_count': count, 'request_chars': len(system) + len(user)}
        audit['stages'].append(stage)
        self._save_audit(audit)
        replies = await generation_utils.call_model_with_retry_async(
            model_name=self.model_name, contents=[{'type': 'text', 'text': user}],
            config=types.GenerateContentConfig(system_instruction=system,
                temperature=self.exp_config.temperature, candidate_count=1, max_output_tokens=50000),
            max_attempts=5, retry_delay=30)
        try:
            response = json.loads(replies[0])
            if not isinstance(response, dict) or set(response) != {'selected_diagrams'}:
                raise ValueError('Expected only the selected_diagrams field')
            ids = response['selected_diagrams']
            allowed = set(stage['candidate_ids'])
            if (not isinstance(ids, list) or len(ids) != count or any(not isinstance(i, str) for i in ids)
                    or len(set(ids)) != count or any(i not in allowed for i in ids)):
                raise ValueError(f'Expected {count} distinct reference IDs from this stage candidate pool')
        except ValueError:
            stage['status'] = 'invalid_response'
            self._save_audit(audit)
            raise
        stage.update(status='complete', selected_ids=ids)
        self._save_audit(audit)
        return ids

    async def process(self, data: dict, retrieval_setting: str = 'auto') -> dict:
        """auto에서는 4회 예선과 최종 1회 선택 후 원본 Planner 계약 반환."""
        if retrieval_setting != 'auto':
            return await super().process(data, retrieval_setting=retrieval_setting)
        active, groups, manifest = self._load_groups()
        # 긴 사용자 입력은 일부 그룹 호출 뒤가 아니라 첫 호출 전에 차단
        for rows, text in groups:
            self._request(data, rows, text, PER_GROUP)
        longest = sum(sum(sorted((len(candidate_text(999, row)) for row in rows), reverse=True)[:PER_GROUP])
                      for rows, _ in groups)
        self._request(data, active[:24], ' ' * longest, 10)
        audit = {'strategy': 'grouped-4x6-to10', 'source_ref_sha256': manifest['source_ref_sha256'],
                 'groups_manifest_sha256': hashlib.sha256((self.groups_dir / 'manifest.json').read_bytes()).hexdigest(),
                 'status': 'running', 'candidate_count': 200, 'per_group': PER_GROUP,
                 'finalist_count': 24, 'stages': []}
        data['retrieval_audit'] = audit
        self._save_audit(audit)
        shortlisted = []
        for number, (rows, text) in enumerate(groups, 1):
            shortlisted.extend(await self._select(data, rows, text, PER_GROUP, f'group-{number:02d}', audit))
        # 그룹별 반환 순위의 영향을 줄이도록 최종 후보를 원본 순서로 배치
        selected = set(shortlisted)
        finalists = [row for row in active if row['id'] in selected]
        text = ''.join(candidate_text(index, row) for index, row in enumerate(finalists, 1))
        if len(finalists) != 24 or len(text) > GROUP_CHAR_BUDGET:
            raise ValueError('Expected 24 finalists within the candidate character budget')
        ids = await self._select(data, finalists, text, 10, 'final', audit)
        data['top10_references'] = ids
        data['retrieved_examples'] = []
        audit.update(status='complete', final_ids=ids)
        self._save_audit(audit)
        return data
