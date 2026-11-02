# 4·5단계 최초 생성·PBInteract 수정 연결 결과

- 수행일: 2026-11-02임.
- 결론: 원본 Python processor·agent·prompt를 그대로 실행하며 텍스트 요청을 활성 Codex 채팅, 이미지 요청을 내장 imagegen으로 연결함. 초기 생성과 완료 결과에서 이어가는 피드백 수정을 실제 실행함.
- 검증 구분: `[코드]`는 소스 확인, `[fixture]`는 합성 응답·이미지로 제어 흐름 확인, `[실제]`는 Codex 추론·내장 imagegen 실행, `[한계]`는 미확인·미구현 항목임.

## 이전 단계 및 원본 보존 점검

| 점검 | 확인 결과 |
|---|---|
| 이전 계획 | 원본 코드 재사용·호출부 교체·실제 참고 데이터 연결 방향과 일치함 |
| 보존 파일 | `assets/interact/SOURCE_MANIFEST.json`의 30개 파일이 reference 원본과 byte·SHA-256 동일함 |
| papervizagent commit | `e088a8fff74cc363b6897c0843631fff76484908`이며 작업 트리 변경 없음 |
| PaperBanana commit | `f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3`이며 작업 트리 변경 없음 |
| Interact commit | `ed08ef7e427ce147194af91d8ae6326a6cbc9cbd`이며 작업 트리 변경 없음 |
| 참고 데이터 | 준비된 MTP ref 298개와 이미지 byte·순서 보존 회귀 검증 통과함. 원본 JSON·그림은 유지됨 |
| 기존 회귀 | 기존 10개 테스트 통과 후 전체 processor 검증 2개 추가함 |

- `[코드]` 전체 processor import에서 단일 agent 시험에 없던 `tqdm` 의존성 누락이 재현됨. 격리 requirements에 원본 의존성을 추가하여 해결함.
- `[코드]` 원본 `eval_toolkits`가 평가 비활성 상태에서도 Claude/OpenAI 호출 이름을 import함. bridge에 명시적 오류 함수를 제공하여 import 계약을 충족함. 해당 외부 API를 연결하거나 실행하지 않았음.
- `[코드]` 원본 `ExpConfig`의 provider 설정 초기화를 실행하지 않고, 원본 agent·processor가 실제 사용하는 필드로 실행 설정을 구성함. 핵심 agent·processor 코드를 수정한 것이 아님.
- `[코드]` bridge의 오래된 `Stage 1` 오류 문구를 현재 지원 범위 문구로 수정함. 원본 provider retry는 여전히 재현하지 않으며 설정 기록만 유지함.

## 최초 그림 생성 연결

- 실행기: `skills/paper-sketch/scripts/run.py`임.
- `make_processor`: 원본 `PaperVizProcessor`와 각 원본 agent·PBInteract를 구성함. `demo_full`, `codex-host`, `codex-image-host` 설정을 사용함.
- `generate`: 원본 `prepare_retrieval` → 유효 ID 10개 경계 검사 → 원본 `process_query_one(do_eval=False)` → 첫 assistant 이력 생성 순서임.
- 원본 호출: Retriever → Planner → Stylist → Visualizer → `_run_critic_iterations`임.
- Visualizer가 Planner·Stylist 설명에 대해 각각 이미지를 생성하는 원본 동작을 유지함.
- Critic의 수정 설명·재생성·`No changes needed.` 종료·최대 round·선택 이미지 field를 원본 processor가 관리함. 별도 루프를 새로 구현하지 않았음.
- 입력은 UTF-8 JSON의 방법론 `content`, 캡션·의도 `visual_intent`임. 비율 기본값은 `16:9`, Critic 기본 상한은 3회임.

## 피드백 수정 연결

- `refine`: 완료 턴의 이력 길이·마지막 assistant 검증 → 새 user 요청 추가 → 원본 `process_single_feedback(simulate_user=False, do_eval=False)` → assistant 이력 완성 순서임.
- 원본 PBInteract 흐름: 이전 그림별 이력 문맥화 → 최신·과거 각 요구·원문·표현 검토 → YES/NO 판단 → YES일 때만 상세 설명 공개·재작성 → Visualizer 재생성임.
- `j==0`의 최신 요청 우선 검토와 `j>0`의 재생성 후 전체 요구 재검토 정책을 그대로 유지함.
- NO에서는 rewrite·imagegen을 호출하지 않음. 내부 round 기본값은 1이며 실제 시험에서는 2로 지정하여 재생성 후 검토까지 확인함.
- 기존 이미지를 imagegen 편집 입력으로 전달하지 않음. 원본 주 경로처럼 수정 설명에서 새 이미지를 생성함.
- 이전 요구의 실제 충족 여부는 이미지·비평으로 판단함. 이력 field 전달만으로 충족을 보장한다고 주장하지 않음.

## 저장과 재개

- `save_result`: `eval_image_field`가 가리키는 JPEG를 판독 검증한 후 `final.jpg`, 원본 전체 record를 `result.json`으로 저장함.
- 실행 설정은 `run_config.json`, 원본 요청·응답·입력 이미지 sidecar는 `requests/`에 기록함.
- 이전 그림·설명·문맥 노트·요구별 비평·선택 ID·chat history·round index를 inline base64 record와 함께 보존함.
- 새 출력 폴더만 허용하여 완료 결과 덮어쓰기를 방지함. 이전 결과를 읽어 새 턴으로 이어가는 구조임.
- 중단 실행 복구·임의 Gradio 저장 파일 호환·원본 base64 파일 offload는 이번 연결 범위가 아님.

## 실제 실행 결과

| 실행 | 실제 텍스트 요청 | 실제 imagegen | 확인 결과 |
|---|---:|---:|---|
| `runs/stage4-generate-live` | 3회 | 2회 | 실제 참고 10개 → Planner → Stylist → 각각 렌더링 → Critic 무변경 종료함 |
| `runs/stage5-refine-live` | 6회 | 1회 | 문맥화·검토·YES·설명 재작성·재생성·내부 검토·NO 종료함 |
| `runs/stage5-second-turn-live` | 3회 | 0회 | 그림 2개와 이전 요청을 문맥화하고 `critique_prior_turn1`을 별도 검토한 후 NO 종료함 |

- `[실제]` 검색 모드는 **원본 random**임. 자동 관련성 검색으로 보고하지 않음. `ref_89`, `ref_155`, `ref_182`, `ref_94`, `ref_92`, `ref_251`, `ref_186`, `ref_275`, `ref_11`, `ref_64`가 선택됨.
- `[실제]` 실제 참고 그림 10개를 모두 열어 확인함. 요청에는 예제 전문이 보존되며 선택 이미지 byte와 본문·캡션의 포함 여부를 검사함. host의 예제 본문 판독은 발췌이며 전문 전체의 독립 일괄 추론 검증이 아님.
- `[실제]` 시험 입력은 참고 검색·계획·생성·검토·피드백 수정으로 구성된 과학 그림 작성 시스템의 방법론·캡션임. 사용자 실제 논문의 품질 평가가 아닌 연결용 표본임.
- `[실제]` 첫 피드백은 Critic을 주황색으로 바꾸되 모든 라벨·구조·루프·나머지 색 계열을 유지하는 요청임. 새 그림에서 주황색 Critic과 구조·라벨 유지가 확인됨.
- `[실제]` 재생성으로 아이콘·정확한 간격·thumbnail 표현은 달라짐. 픽셀 동일성·국소 편집 보장은 아님.
- `[실제]` 두 번째 피드백은 현재 주황색 결과를 그대로 유지하는 요청임. 과거 요청별 비평 필드 생성과 추가 이미지 호출 0회를 확인함.
- `[실제]` 최초 JPEG SHA-256은 `c2996eadf0f66a27c24f11ea9b7bdf4a47ad50136d35dca43f3be89dfaaff41a`임.
- `[실제]` 수정 JPEG SHA-256은 `7a814c65be4101fd4b837cbba163893f09afba8b2e9cfb8717c52c79f2fe881c`이며 두 번째 피드백 이후에도 동일함. 출력 크기는 모두 1672×941임.
- `[실제]` 원본 image config의 `1k`, 16:9 지시는 요청에 보존되나 내장 imagegen의 실제 크기·sampling과 동일하지 않음.
- 근거: `runs/stage45-verification.json`, 각 실행의 request/response·정확한 image prompt·생성 PNG·결과 JSON·선택 JPEG임. `runs/`는 Git 추적 제외이며 로컬에 보존됨.

## 검증 결과

- `[fixture]` 총 12개 테스트 통과함. 원본·데이터 보존, 실제 auto pool 구성·선택 그림 전달, SDK 대화 역할·설명 공개 시점, bridge 오류·timeout, 이미지 변환, 별도 Python 왕복, 전체 생성과 2회 피드백, 마지막 허용 round의 재생성 후 종료를 포함함.
- `[fixture]` 최초 Critic이 실제 수정안을 반환하면 재생성 후 다음 Critic으로 연결되는 분기를 확인함. 실제 최초 표본의 Critic은 무변경 종료였으므로 두 검증을 구분함.
- `[fixture]` 두 번째 턴에 이미지 2개·과거 요구사항·요구별 schema가 전달되고 NO에서 새 이미지가 생성되지 않음을 확인함.
- `[fixture]` 저장·복원 record와 선택 이미지 byte 일치를 확인함.
- `[검사]` `skill-creator`의 `quick_validate.py` 통과함. 수정 Python 구문 검사 통과함. 영어 지침·실행 코드에서 한국어 검토본 참조 없음이 확인됨.
- 실행 명령: 격리 requirements 환경에서 `python -m unittest discover -s tests -v`임.
- 사용 스킬: `diagnosing-bugs`로 누락 import 경계를 진단함. `skill-creator`로 실행 지침·지원 범위를 정리하고 구조 검사함. `imagegen`으로 내장 이미지 생성 경로를 검증함.

## 남은 한계와 후속 조건

- `[한계]` auto의 앞 200개 전문 약 2,967,946자를 host가 모두 처리하여 관련성을 선택하는 실제 시험은 미완료임. random 연결 성공으로 이를 대체하지 않음. 임의 요약·분할 검색은 원본과 다른 변경이므로 별도 결정·비교가 필요함.
- `[한계]` 각 요청의 파일 입력에서 상세 설명 비노출·대화 역할을 유지하지만, 동일 활성 채팅 Codex는 이전 단계 설명을 이미 보았을 수 있음. 독립 API 문맥·비평 편향 동등성을 보장하지 않음.
- `[한계]` provider retry·동일 sampling·정확한 provider 이미지 tier·독립 모델 문맥은 재현하지 않음. host 오류는 실패로 전파됨. 원본 빈 이미지 fallback을 모든 실패 복구로 표현하지 않음.
- `[한계]` 잘못된 Critic JSON을 원본이 무변경으로 취급할 가능성과 마지막 허용 round 출력의 미검토 동작을 변경하지 않음. 후속 수정 시 별도 원본 대비 차이로 관리할 필요가 있음.
- `[한계]` 원본 API 실행 기준선·독립 평가자·동일 논문 표본의 반복 생성·요구별 이행 및 망각률 비교를 수행하지 않았음. 기능 연결 완료를 논문 figure 품질·성능 유지 입증과 구분함.
- `[범위]` 전역 설치·설정 변경·모델 다운로드·API key 사용·별도 유료 API 호출·커밋·업로드는 수행하지 않았음. 승인된 내장 imagegen 호출 3회를 수행함.
