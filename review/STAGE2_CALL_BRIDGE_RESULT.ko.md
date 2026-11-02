# 구현 순서 2번: Codex·imagegen 호출 연결 검증

- 수행일: 2026-11-02임.
- 사용자 인용 범위: Python이 만든 모델 요청 → Codex 처리 → 원본 반환 계약으로 응답 → 기존 Python 처리 재개임.
- 이번 범위는 참고 데이터 연결·전체 초기 생성 단계가 아님. 1단계의 파일 bridge에 실제 내장 imagegen 왕복을 추가 검증한 결과임.

## 구현 및 실행

- `probe.py --kind roundtrip --timeout 1200`을 추가함. 복사된 원본 Planner → Visualizer → Critic을 순서대로 호출함.
- 원본 30개 파일·프롬프트·이미지 후처리는 변경하지 않음. 원본 processor를 재구현하거나 full pipeline 실행기로 소개하지 않음.
- 합성 입력은 observations → encoder → predictor의 3단계 설명임. 참고 예제 목록은 빈 목록이며 데이터 검색·Stylist·재생성 loop는 이번 실행에 포함되지 않음.
- Planner 요청의 원본 system/user prompt를 Codex가 읽고 영어 상세 설명을 파일로 반환함.
- 원본 Visualizer가 만든 render prompt를 내장 imagegen에 전달함. 원본 요청의 비율 16:9를 tool prompt에 덧붙임. 별도의 색·구조·구성 요소를 host 단계에서 추가하지 않음.
- 내장 도구의 PNG를 작업 폴더에 복사한 후 `respond.py --image-file`로 제출함. 별도 API 키·외부 모델 API·CLI 이미지 생성은 사용하지 않음.
- bridge의 base64 반환 후 원본 Visualizer가 JPEG로 변환하고, 원본 Critic이 해당 JPEG를 새 요청에 첨부함.
- Codex가 Critic 입력 JPEG를 실제로 열어 확인하고 원본 JSON 형식으로 no-change 응답을 제출함. 원본 Critic이 JSON을 파싱한 뒤 Python 프로세스가 exit code 0으로 종료됨.

## 실제 검증 결과

| 항목 | 결과 |
|---|---|
| 원본 agent 호출 | Planner·Visualizer·Critic 각 1회임 |
| host 요청 순서 | text → image → text 총 3개임 |
| 실제 내장 imagegen 호출 | 새 이미지 생성 1회임. fixture가 아님 |
| 원본 tool 출력 | PNG, 1672×941 pixel임 |
| 원본 후처리 결과 | JPEG, 1672×941 pixel임 |
| Critic 이미지 연결 | 요청 이미지 byte가 Visualizer 결과 JPEG와 정확히 동일함 |
| Critic 응답 처리 | `critic_suggestions0`가 `No changes needed.`이며 `critic_desc0`에 기존 설명을 유지함 |
| 자동 회귀 검증 | 총 6개 통과함. 별도 Python subprocess에서 요청 3개를 처리하는 fixture 테스트를 추가함 |
| 원본 보존 | source manifest와 원본 30개 파일 byte 비교 테스트 통과함 |

- 실제 imagegen 결과와 fixture 자동 테스트를 분리함. 자동 테스트에서 이미지 도구를 재호출하지 않음.
- PNG SHA-256: `bd32f993956de9388a5af7bacfa43444408aad4fe2d8ffa70e1d2eff73ef2923`임.
- JPEG SHA-256: `5338ba43707bf84782b0a621524ece8a6007cb56705b20ba193c760b075d5a83`임.
- 이미지 판독상 3개 모듈·두 개의 오른쪽 화살표·요청 label을 확인함. 합성 표본 1개에 대한 host 관찰이며 benchmark 품질 평가가 아님.

## 검토 가능한 실행 자료

- [실제 tool prompt](../runs/stage2-roundtrip/imagegen-prompt.txt)
- [생성 PNG](../runs/stage2-roundtrip/imagegen-output.png)
- [원본 Visualizer 후처리 JPEG](../runs/stage2-roundtrip/visualizer-output.jpg)
- [검증 기록](../runs/stage2-roundtrip/verification.json)
- [원본 처리 결과](../runs/stage2-roundtrip/result.json)
- 개별 요청·응답은 같은 session의 UUID별 하위 폴더에 보존됨. 실행 자료 전체는 `runs/` Git 제외 규칙을 적용함.

## 차이 및 미검증 범위

- Python이 Codex를 API처럼 직접 호출하지 않음. 활성 채팅의 Codex가 요청 파일과 tool 결과를 연결하는 방식임.
- 원본의 독립 모델 context·temperature·token 예산과 동일한 실행을 보장하지 않음. 원본 요청의 `1k` tier와 실제 1672×941 출력도 동일한 크기 계약이 아님.
- 내장 imagegen 호출이 지원하는 입력·출력 계약만 확인함. Gemini와 품질·비용·속도·sampling이 동일하다는 주장이 아님.
- 데이터 retrieval·스타일 보강·전체 processor·Critic 재생성 반복·PBInteract 실제 사용자 수정·이미지 직접 편집·세션 재개는 미검증 상태임.
- 다음 구현 순서는 실제 MTP 참고 데이터 연결임. 이번 작업에서 해당 단계로 확장하지 않음.
