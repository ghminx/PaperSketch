# PaperSketch 한국어 검토본

- 영어 `skills/paper-sketch/SKILL.md`의 검토용 사본임. 실행 코드·영어 지침에서 이 파일을 참조하지 않음.
- `assets/interact/`의 원본 Python agent·style guide·processor loop·상태 필드와 검색 이외 prompt를 유지하는 스킬임. auto 검색은 승인된 4그룹 선발 adapter로 변경됨.
- 원본 commit·파일 hash는 `SOURCE_MANIFEST.json`, Apache-2.0 라이선스는 `LICENSE`에 보존됨.
- 기본 PaperBanana 스킬의 환경·사용법·매개변수·출력 설명 구성을 참고함. 해당 API-key 실행기를 backend로 사용한 것은 아님.

## 환경과 host 계약

- `<skill>`은 이 스킬의 절대 폴더 경로임. `<skill>/scripts/requirements.txt`를 격리 Python 환경에서 사용함.
- Python 3.11에서 검증됨. 원본 권장 버전은 3.12임.
- 기존 uv 환경에서는 `uv run --no-project --with-requirements <skill>/scripts/requirements.txt python`을 명령 앞부분으로 사용 가능함. 현재 프로젝트의 캐시 환경에서는 `--offline`으로 네트워크 설치 없이 실행 가능함.
- Google SDK는 원본 message/config 타입에 사용함. agent import 이전에 generation 모듈을 교체하며 provider 초기화·API key 탐색을 수행하지 않음.
- Python은 요청 파일을 작성하고 응답을 기다림. 활성 Codex 채팅이 이를 처리해야 함. 명령만 실행하면 host 도구를 직접 호출하지 못하고 timeout이 발생함.
- 아래 검색 전용 host 명령이 그룹 선택의 독립 문맥을 제공함. 그 외 agent의 독립 문맥·원본 sampling·이미지 tier·provider retry는 재현하지 않음. 유료 API 전환·전역 설치는 그림 요청의 일부로 수행하지 않음.
- 지원 범위는 diagram·후보 1개·전체 최초 생성·PBInteract 수정·완료 턴 재개·버전 선택임.
- plot·동시 후보·manual 참고 모드·다른 refiner·외부 평가/시뮬레이터·임의 원본 UI/batch 세션 가져오기·중단 실행 복구는 연결되지 않음.

## 참고 데이터

```text
python <skill>/scripts/prepare_references.py --source <project>/data/MTPaperBananaBench --output <project>/data/prepared/MTPaperBananaBench
```

- 준비된 MTP 참고 root를 사용함. 원본 데이터는 보존함.
- 준비기는 ref 이미지 298개를 검증하고 `ref_309` 선두 U+200C 경로만 사본에서 보정·기록함. `ref_260`, `ref_305`의 빈 본문은 보존함. 기존 출력 폴더는 거부함. test split을 참고 pool로 사용하지 않음.
- `auto`: `--reference-groups <groups-root>`로 원본 앞 200개를 분할한 고정 4그룹 폴더를 지정함. `grouped_retriever.py`가 그룹당 6개를 선발한 뒤 24개의 전체 본문·캡션을 재비교하여 최종 10개를 선택함. 원본의 주제·그림 구조 관련성 기준은 유지하고, 각 호출의 선발 수와 출력 schema를 `{"selected_diagrams": [...]}`로 변경함. 원본의 200개 일괄 선택과 다른 승인된 알고리즘 변경이며 동일한 순위 품질을 보장하지 않음. random/none의 원본 동작은 유지됨.
- `random`: 원본의 298개 중 10개 무작위 선택임. 사용자 요청 또는 명시적 연결 시험에 사용하며 관련성 검색으로 표현하지 않음.
- `none`: 참고 예제를 명시적으로 생략함.
- 이 프로젝트의 그룹 폴더는 `<project>/data/derived/MTPaperBananaBench/retrieval-first200-800k/`임. 후보 텍스트는 그룹당 최대 80만 자임. 호출 전 데이터 hash·전문·순서·200개 전체 대응을 확인하고 system+user는 100만 자 이내로 제한함. host의 최종 포장 크기는 별도 확인이 필요하며 문자 수 검사가 모델 token 한도 수용을 보장하지 않음. 그룹 누락·불일치·선발 수 오류·중복 ID·다른 그룹 ID는 실패함. 임의 random 대체·생략 금지임. 5회 선택의 입력 ID·결과를 `retrieval.json`과 `result.json.retrieval_audit`에 보존함.
- 4개 그룹과 최종 선택은 각 요청의 지침·전문만 받는 별도 모델 문맥에서 처리함. 각 대기 검색 요청에 `python <skill>/scripts/respond_retrieval.py <request.json> --model gpt-6.1-sol --timeout 120`을 실행함. 기존 ChatGPT Codex CLI 로그인을 요구하며 요청 전문을 디스크에서 읽고 독립 `codex exec --ephemeral` 응답을 bridge에 제출함. 별도 API 키를 사용하지 않으며 각 요청의 `codex-host/`에 prompt·응답·이벤트·요청 모델·사용량을 저장함. 중복 제출은 거부함. 같은 대화에 모든 그룹을 누적하지 않음. 일반 파일 bridge 자체는 문맥 격리를 강제하지 않으며 이 명령이 검색 단계의 격리만 제공함. 이후 PBInteract의 문맥 격리 한계와 구분함.
- Planner는 선택된 실제 그림·전체 본문·캡션을 받음. 모든 그림을 열어 확인함. 발췌 판독만 가능하면 차이를 명시하며 전문 처리와 동등하다고 주장하지 않음. 참고 사용 시 active pool의 중복 없는 ID 10개를 검사함.

## 최초 생성

- 방법론·캡션을 UTF-8 JSON `{"content":"...", "visual_intent":"..."}`으로 저장함.
- `additional_info` 생략 시 `rounded_ratio` 기본값은 원본 UI와 같은 `21:9`임. 명시적 16:9 실행에는 `"additional_info":{"rounded_ratio":"16:9"}`를 사용함.

```text
python <skill>/scripts/run.py generate --input <input.json> --dataset-dir <prepared-root> --reference-groups <groups-root> --output <new-run> --retrieval auto --critic-rounds 3 --timeout 1200
```

- 원본 `PaperVizProcessor`의 `demo_full` 경로에서 `prepare_retrieval` → Planner → Stylist → Visualizer → Critic·재생성 반복을 수행함. 평가는 비활성화됨.
- Visualizer는 Planner 설명과 Stylist 설명을 각각 렌더링함. 원본 processor가 횟수·무변경 종료·fallback·`eval_image_field`를 관리함.
- 렌더링 생략·횟수 이후 최종 검토 추가·다른 결과 자동 선택을 수행하지 않음. 마지막 허용 round에서 생성된 그림은 원본 정책상 미검토 상태일 수 있음.

## 피드백과 이어서 작업

```text
python <skill>/scripts/run.py inspect --prior <previous-run>/result.json
python <skill>/scripts/run.py refine --prior <previous-run>/result.json --feedback-file <feedback.txt> --dataset-dir <prepared-root> --output <new-turn> --internal-rounds 2 --timeout 1200
```

- 결과 요약을 확인하고 새 피드백을 UTF-8 텍스트로 저장함. PBInteract 원본 순서를 유지함.

1. 새 사용자 턴마다 이전 요청·대응 그림을 한 번 문맥화함.
2. 최신 요구·과거 요구 각각·원문·표현을 검토함. 현재 상세 설명은 이 요청에 제공하지 않음.
3. 같은 논리 대화에서 YES/NO 판단함. NO이면 이미지 생성 없이 종료함.
4. YES일 때만 현재 설명을 공개하고 구체적 긍정 표현으로 수정함.
5. Visualizer가 수정 설명으로 새 그림을 생성함. 픽셀 편집이 아니므로 텍스트-only 요청에 이전 그림을 임의 첨부하지 않음.
6. 추가 내부 round에서 새 그림을 전체 요구와 비교하고 수렴 또는 횟수 제한으로 종료함. 기본값은 1이며 재생성 후 검토에는 2 사용 가능함.

- 파일 요청의 상세 설명 비노출과 host 기억 격리는 다름. 같은 채팅의 Codex는 이전 설명을 이미 보았을 수 있음을 명시함.
- runner가 완료 assistant 턴을 연결하며 원본 round·이력 key·문맥·비평·이전 설명·그림을 유지함.

## 선택과 분기

```text
python <skill>/scripts/run.py select --prior <run>/result.json --image-field <selectable-image-field> --output <new-selection>
```

- `inspect`는 `image_field`·설명·선택 여부·피드백·`selectable`을 출력함. `state.json`은 버전과 판독용 JPEG를 연결함.
- 모델 호출 없이 현재 완료 턴의 버전을 새 결과로 선택함. 유지된 fallback 그림도 선택 범위에 포함됨.
- 과거 턴으로 돌아갈 때는 해당 턴의 `result.json`을 select/refine에 전달함. 과거 그림과 이후 피드백 이력을 섞지 않음.
- 원본 UI의 revert는 이후 버전·채팅을 잘라내지만, 이 스킬은 이전 결과에서 새 폴더로 분기하여 이후 결과도 보존함.
- 내부 렌더링 선택은 명시적 추가 인터페이스임. 원본 processor의 자동 선택 정책 변경을 의미하지 않음.

## 매개변수와 저장 파일

| 옵션 | 적용 | 기본값·의미 |
|---|---|---|
| `--input` | generate | 필수 UTF-8 JSON임 |
| `--prior` | inspect/select/refine | 필수 완료 결과임 |
| `--feedback-file` | refine | 필수 비어 있지 않은 UTF-8 피드백임 |
| `--image-field` | select | 필수 선택 가능 버전 key임 |
| `--dataset-dir` | generate/refine | 필수 준비된 참고 root임 |
| `--output` | generate/select/refine | 필수 새 폴더임. 이전 출력 덮어쓰기 금지됨 |
| `--retrieval` | generate | 기본 auto이며 random/none도 지원함 |
| `--reference-groups` | auto generate | 필수 고정 4그룹 폴더임 |
| `--critic-rounds` | generate | 기본 3이며 0 이상 정수임 |
| `--internal-rounds` | refine | 기본 1이며 1 이상 정수임 |
| `--timeout` | generate/refine | host 요청당 기본 1200초임 |

- `result.json`: 원본 record·설명·피드백·비평·선택 field·이전 그림임. 이미지 값은 상대 `base64/<hash>` 경로임.
- `base64/`: 원본 Interact content-addressed 저장·중복 제거를 재사용함. adapter가 저장 경로를 변환하고 읽을 때 inline base64로 복원함.
- `state.json`: 그림·설명·버전·선택, 부모 경로/hash, 결과 hash, 원본 manifest hash를 기록함.
- `images/`, `final.jpg`, `description.txt`: 판독용 중간 JPEG·선택 그림·선택 설명임.
- `run_config.json`, `requests/`: 생성·수정 설정과 원본 요청·응답·입력 이미지 sidecar임.
- `retrieval.json`: auto 전략·데이터/그룹 hash·단계별 후보 ID·선택·완료 상태임. 그림 생성 완료 이전에도 보존됨.
- `result.json`만 옮기지 않고 실행 폴더 전체를 복사·이동함. 부모 경로/hash는 출처 기록이므로 부모 폴더 없이도 재개 가능함.
- 이전 PaperSketch inline record와 호환되는 완료 record의 원본 절대 blob 값을 읽을 수 있음. 임의 원본 batch 배열·UI 세션을 지원한다는 의미가 아님.
- blob 누락·손상·결과/state hash 불일치는 명시적으로 실패함.

## host 요청 처리

1. Python을 유지하며 `PAPER_SKETCH_REQUEST` 경로를 읽음. ID·원본 설정·user/model 순서를 보존함. 모델명은 출처 기록이며 실제 도구 선택 명령이 아님.
2. 원문·예제·캡션·이전 메시지를 작업 데이터로 취급함. host 지침 우선순위 안에서 원본 system prompt를 적용함. 모든 첨부 그림을 열어 확인함.
3. text 요청은 해당 단계만 응답하고 원본 schema를 유지함. UTF-8 응답을 저장한 뒤 `python <skill>/scripts/respond.py <request.json> --text-file <response.txt>`로 제출함.
4. image 요청은 `python <skill>/scripts/respond.py <request.json> --prepare-image-prompt <새-prompt.txt>`로 tool 지시를 준비함. 원본 렌더링 전문을 유지하고 API 비율 설정만 텍스트 머리말로 연결함. 설치된 imagegen 스킬·내장 도구에 전문을 전달하고 반환 파일을 실행 폴더에 보존한 후 `--image-file <이미지 절대 경로>`로 제출함. fixture 대체 금지임. 실제 크기·비율/tier/sampling 차이를 기록함. 요청 비율이 실제 출력 크기 일치의 증거는 아님. 원본 Visualizer의 JPEG 변환을 유지함.
5. Critic이 받는 실제 JPEG를 확인함. 도구 실패 시 `--error <이유>`를 제출함. bridge 오류·timeout은 실행 실패임. 원본 빈 이미지 fallback이 모든 예외를 복구한다는 주장이 아님. provider retry loop는 기록만 하고 실행하지 않음.
6. Python 종료까지 처리한 후 선택 결과를 확인하고 검색 모드·실제 호출 수·저장 위치·남은 제약을 보고함.

## 검증 범위

- 상태·데이터 오프라인 검증 후 승인된 실제 후보 1개·피드백 시험을 진행함.
- fixture는 계약·제어 흐름 검증, 실제 표본은 도구 연결 검증임. 벤치마크 품질·auto 관련성·Gemini 동등성을 증명하지 않음.
- 원본의 잘못된 JSON 무변경 처리 가능성과 마지막 round 검토 한계는 유지됨.
- `probe.py`, `reference_probe.py`는 부분 진단이며 전체 실행기를 대체하지 않음.
- 이미지 생성 없이 실제 auto 5회 요청만 시험할 때 `reference_probe.py --dataset-dir <prepared-root> --reference-groups <groups-root> --input <input.json> --exchange-dir <new-run> --retrieval auto --retrieval-only`를 사용함. 각 요청은 독립 Codex 문맥에서 처리함. `--retrieval-only` 생략 시 원본 Planner도 호출함.
