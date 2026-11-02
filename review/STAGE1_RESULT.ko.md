# 1단계 구현 및 검증 결과

- 수행일: 2026-11-02임.
- 범위: 로컬 스킬 폴더, 원본 코드 복사, 모델 요청·응답 연결 최소 검증까지임.

## 구현 내용

- `skills/paper-sketch/assets/interact/`에 Interact `ed08ef7e427ce147194af91d8ae6326a6cbc9cbd`의 관련 파일 30개를 byte 변경 없이 복사함. 원본 라이선스와 SHA-256 manifest를 보존함.
- 원본 agent·prompt·processor의 내용을 수정하지 않음. 실행기에서 provider 모듈 import 이전에 `utils.generation_utils` 호출 경계만 로컬 bridge로 대체함.
- `scripts/bridge.py`: 원본 요청·모델 설정·user/model 순서·입력 이미지를 요청 폴더에 기록하고, host 응답을 기다린 뒤 원본 list 반환 계약으로 변환함.
- `scripts/respond.py`: 텍스트 파일·이미지 파일·명시적 오류를 응답 JSON으로 제출함. 부분 JSON을 읽지 않도록 임시 파일 저장 후 rename함.
- `scripts/probe.py`: 원본 Planner 또는 Visualizer 단일 검증 실행기임. 전체 pipeline 실행기로 소개하지 않음.
- 영어 실행 지침은 `skills/paper-sketch/SKILL.md`, 한국어 검토본은 `review/SKILL.ko.md`임. 영어 스킬·실행 코드는 한국어 검토본을 참조하지 않음.
- 실행 중 자료는 Git 제외된 `runs/` 아래에 저장함. 전역 스킬 설치·원본 reference 변경·모델 API 호출은 수행하지 않음.

## 연결 방식

```text
원본 Python agent가 프롬프트·입력을 구성
  → bridge가 request.json과 입력 이미지를 기록
  → 활성 채팅의 Codex가 요청을 읽고 추론 또는 imagegen 도구 처리
  → respond.py로 response.json 제출
  → 기다리던 원본 Python이 응답을 읽고 기존 후처리를 계속 실행
```

- 자동 provider API처럼 Python에서 Codex 도구를 직접 호출하는 구조가 아님. 현재는 Codex가 파일 요청을 능동적으로 처리하는 방식임.
- 각 요청을 새로운 독립 모델 context에서 실행하는 보장은 없음. 다중 턴 역할·입력 분리는 파일에 보존되나 host가 이미 본 정보를 제거할 수는 없음.
- SDK는 원본 message/config 타입 사용에 필요하며, 실제 provider client는 import하지 않음. 원본 모델명·temperature·token 설정을 기록하나 host가 동일하게 실행한다고 보장하지 않음.

## 검증 결과

| 검증 | 결과 |
|---|---|
| 원본 Planner의 prompt 구성·응답 후처리 | fixture 텍스트로 통과함 |
| 원본 Visualizer의 이미지 응답·JPEG 변환 | 16×16 fixture 이미지로 통과함. 실제 생성 이미지가 아님 |
| 원본 PBInteract의 문맥화·Critic·gating·rewrite | fixture 응답 4회로 통과함. model 역할·상세 설명 공개 시점·이미지 연결을 검사함 |
| host 오류·미응답 timeout | 정상 성공으로 숨기지 않고 예외로 전달됨 |
| 복사 원본 30개 hash·로컬 원본 byte 비교 | 모두 동일함 |
| skill-creator quick_validate | 통과함 |
| 실제 활성 채팅 Codex → 원본 Planner 왕복 | 요청 파일 판독·영어 설명 작성·응답 제출 후 Python 정상 종료 확인됨 |

- 자동 검증 명령: 격리 환경에서 `python -m unittest discover -s tests -v` 수행함. 5개 테스트 통과함.
- 실제 host 왕복 자료: `runs/stage1-host-planner/`의 `request.json`, `host-response.txt`, `response.json`, `result.json`임. 참고 그림을 사용하지 않는 합성 입력으로 수행함.
- Python 3.11 실행 환경에서 검증함. 원본 권장 Python 3.12 전체 실행 환경 검증과 구분함.
- 필요한 패키지는 `data/.uv-cache/` 기반 uv 격리 환경에서 사용함. 기존 전역 Python 환경에는 설치하지 않음.

## 미검증 및 다음 단계

- 실제 imagegen 도구 실행, dataset retrieval, 전체 processor 연결, 후보 병렬 실행, 전체 사용자 피드백·저장·재개는 미검증 상태임.
- imagegen 결과 파일을 bridge 응답으로 사용할 수 있는 인터페이스는 구현됨. 실제 도구 반환물과의 왕복 검증은 2단계 과제임.
- `return_content`, 후보 수가 1을 넘는 단일 요청, 원본의 다른 provider-specific helper는 지원하지 않음. 전부 연결된 것으로 주장하지 않음.
- 1단계 구현에 필요한 경계 코드만 추가함. MTP 데이터의 경로 불일치·빈 본문, 검색 방식·원본 반복 정책 등은 수정하지 않음.
- 다음 단계는 MTP 실제 참고 데이터 연결 후 초기 생성 1개를 끝까지 수행하는 것임. 이번에는 2단계로 진행하지 않았음.
