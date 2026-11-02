# PaperSketch의 PaperBanana-Interact 이식 충실성 검증

- 검증일: 2026-11-03, Asia/Seoul 기준임.
- 판정: **정상적인 단일 후보 diagram·PBInteract 제어 흐름은 충실하게 재사용됨. 원본 실행 조건과 실패 처리까지 동등한 이식으로 판정할 수는 없음.**
- 실제 스킬 위치: `C:/WIP/PaperSketch/skills/paper-sketch/`임. 영어 진입점은 `SKILL.md`, 실행기는 `scripts/run.py`임.
- 수행 범위: 정적 대조 → 기존 오프라인 회귀 → 원본/이식본 차등 실행 → 실패·저장 경계 재현 → 과거 실도구 기록 확인임.
- 새 모델 추론·imagegen·유료 API·외부 데이터 전송은 수행하지 않았음. 구현·기존 테스트·스킬 지침·분석 문서·reference·다운로드 데이터는 수정하지 않았음.
- 새 파일은 이 보고서와 `runs/fidelity-audit-2026-11-03/`의 검증 전용 harness·로그·JSON뿐임.

## 1. 근거의 구분과 전체 결과

| 표기 | 의미 |
|---|---|
| 코드 확인 | 현재 파일·함수·설정·Git 상태를 직접 읽어 확인한 사실임 |
| 오프라인 재현 | 외부 모델 없이 고정된 응답·fixture 이미지를 제공하여 실제 Python 경로를 실행한 결과임 |
| 과거 기록 | 2026-11-02의 대화 도구 기록 및 현재 보존된 요청/응답·생성 파일과의 대조임. 이번 재실행이 아님 |
| 추론 | 코드상 차이로 예상되는 영향이며 실제 품질 차이를 측정한 것이 아님 |
| 미확인 | 이번 제한 아래 확인하지 않은 내용임 |

- 코드 확인: 보존 파일 30개가 Interact 원본 및 `SOURCE_MANIFEST.json`과 byte·SHA-256 동일함.
- 오프라인 재현: 기존 테스트 19개가 전부 통과함. 데이터 의존 테스트의 skip은 없음.
- 오프라인 차등 재현: 실제 참고 pool을 연결한 최초 생성·Critic 재생성·피드백 2턴에서 **18개 호출의 정규화된 입력과 최종 전체 record가 원본/이식본 사이에서 일치함.**
- 차등 실행은 실제 `reference/PaperBanana-Interact` 클래스와 스킬의 보존 클래스를 별도 프로세스에서 로드함. 클래스 파일 경로도 검사함. 같은 사본을 두 번 실행한 비교가 아님.
- 한계: provider 설정·라우터·API 자체는 모의 경계로 대체함. 동일 설정·정해진 모의 응답에서 agent/processor 동작을 비교한 결과이며 실제 모델 의미 판단·품질 비교가 아님.
- 오프라인 실패 재현: 원본에서 마지막 그림을 유지하고 완료되는 실패 표현이 현재 bridge에서는 예외 중단으로 처리됨.
- 오프라인 저장 재현: 정상 JPEG로 바뀐 blob은 감지되지 않아 선택 export와 다음 수정 입력이 달라질 수 있음.

## 2. 발견 사항 — 영향도순

### F1. 높음 — 기본 auto와 Planner 전문 처리의 실모델 검증 공백

- 분류: 미검증 핵심 경로임. 데이터 연결이 가짜이거나 코드상 검색이 없는 경우는 아님.
- 발생 조건: 기본값인 `generate --retrieval auto`를 사용하거나 Planner가 다량의 참고 본문·그림을 처리하는 경우임.
- 관련 경로:
  - [원본 Retriever._retrieve_and_parse](C:/WIP/PaperSketch/reference/PaperBanana-Interact/agents/retriever_agent.py:128): 앞 200개 방법론·캡션을 한 요청으로 구성함.
  - [이식 generate](C:/WIP/PaperSketch/skills/paper-sketch/scripts/run.py:36), [기본 검색 설정](C:/WIP/PaperSketch/skills/paper-sketch/scripts/run.py:110).
  - [영어 스킬의 검색 한계](C:/WIP/PaperSketch/skills/paper-sketch/SKILL.md:28).
- 원본 동작: 실제 텍스트 모델이 해당 전체 후보 입력에서 ID를 선택하고, Planner가 선택된 전문·실제 그림을 함께 입력받음.
- 현재 동작: 동일한 후보 요청을 만들고 ID·이미지 연결까지 실행됨. 그러나 기본 auto의 실제 관련성 선택은 미검증임. 과거 실제 실행은 random 선택이며 host의 참고 본문 판독도 발췌였음.
- 검증 결과: 앞 200개 content/caption 합계는 2,967,946자임. 이번 sentinel 입력에서 완성된 auto user prompt는 2,984,500자였음. 모의 선택 ID 10개와 Planner 이미지 10개 연결은 원본/이식본에서 일치함.
- 사용자 영향: 참고 예제를 잘 선택하는 원본의 핵심 품질 조건이 유지됐다고 아직 판단할 수 없음. random 성공을 auto 성공으로 해석하면 안 됨. 현재 host가 이 전문을 끝까지 처리할 수 없다고 단정한 실험도 이번에는 수행하지 않았음.
- 수정·검증 방향: 원문을 유지한 host 처리 가능 여부와 전체 입력 소비를 먼저 검증할 필요가 있음. 처리 불가 시 범위 제한을 명시하거나, 후보 요약·분할 검색 등은 사용자 승인 아래 별도 알고리즘 변경으로 비교할 필요가 있음. 임의 random 대체는 부적절함.

### F2. 높음 — PBInteract의 요청별 문맥 격리가 보장되지 않음

- 분류: 의도된 host 연결 구조의 차이이며, 의미적 영향은 미측정임.
- 발생 조건: 같은 활성 Codex 채팅이 Planner·Stylist·Critic·문맥화·후속 수정 요청을 계속 처리하는 경우임.
- 관련 경로:
  - [원본 PBInteract.process](C:/WIP/PaperSketch/reference/PaperBanana-Interact/agents/refiner/pb_interact.py:224): Critic 요청에 현재 상세 설명을 제공하지 않고, [308행](C:/WIP/PaperSketch/reference/PaperBanana-Interact/agents/refiner/pb_interact.py:308)의 rewrite 호출에서만 제공함.
  - [원본 Gemini 요청 구성](C:/WIP/PaperSketch/reference/PaperBanana-Interact/utils/generation_utils.py:278).
  - [FileBridge.call](C:/WIP/PaperSketch/skills/paper-sketch/scripts/bridge.py:58), [host_context 기록](C:/WIP/PaperSketch/skills/paper-sketch/scripts/run.py:85), [스킬의 문맥 한계](C:/WIP/PaperSketch/skills/paper-sketch/SKILL.md:62).
- 원본 동작: 각 모델 호출에는 해당 요청의 contents/config만 전달하며, PBInteract의 Critic → 판단 → rewrite는 명시적으로 구성한 conversation을 전달함.
- 현재 동작: 요청 파일의 필드·user/model 순서와 설명 공개 시점은 유지함. 그러나 이를 처리하는 Codex는 이전 단계에서 상세 설명이나 다른 요구를 이미 읽었을 수 있음. system_instruction도 원본 API system 슬롯과 동일한 실행 위치가 아니라 host 지침 아래의 작업 지시임.
- 검증 결과: 이번 차등 검증에서 Critic/판단 요청에 설명이 없고 rewrite에만 설명이 포함되는 것은 일치함. 독립 host 기억은 생성·검증하지 않았으며 코드도 이를 보장하지 않음.
- 사용자 영향: 설명을 보지 않고 그림을 평가하도록 분리한 PBInteract의 통제 조건이 달라짐. 설명 의존 비평·이전 문맥 잔존에 따른 편향 가능성은 추론이며 실제 영향 크기는 미확인임.
- 수정·검증 방향: 요청별 입력만 받는 격리된 Codex 실행 경계를 검토하되, Critic → 판단 → rewrite 안의 의도된 논리 대화는 유지할 필요가 있음. 별도 context와 현재 활성 채팅 방식의 요구 이행·망각률을 비교해야 함.

### F3. 중간 — 이미지 실패 시 원본의 재시도·마지막 그림 유지와 다른 중단 동작

- 분류: 문서에 명시된 의도적 변경이지만 원본 대비 기능 차이임.
- 발생 조건: 원본 provider가 재시도 후 `['Error']`를 반환하는 유형의 렌더링 실패가 host에서는 `--error`로 보고되는 경우임. 모든 원본 API 예외가 복구된다는 뜻은 아님.
- 관련 경로:
  - [원본 provider 재시도](C:/WIP/PaperSketch/reference/PaperBanana-Interact/utils/generation_utils.py:261), [실패 반환](C:/WIP/PaperSketch/reference/PaperBanana-Interact/utils/generation_utils.py:331).
  - [원본 Visualizer.process](C:/WIP/PaperSketch/reference/PaperBanana-Interact/agents/visualizer_agent.py:40), [변환 실패 처리](C:/WIP/PaperSketch/reference/PaperBanana-Interact/agents/visualizer_agent.py:134).
  - [원본 피드백 fallback](C:/WIP/PaperSketch/reference/PaperBanana-Interact/utils/paperviz_processor.py:305).
  - [bridge 오류/timeout](C:/WIP/PaperSketch/skills/paper-sketch/scripts/bridge.py:89), [완료 후에만 저장하는 run](C:/WIP/PaperSketch/skills/paper-sketch/scripts/run.py:94).
- 원본 동작: 지원 provider의 재시도·최종 오류 반환 이후 이미지 변환이 실패하면 processor가 마지막 유효 그림을 유지하고 피드백 턴을 반환할 수 있음.
- 현재 동작: retry_options를 기록만 하며 반복하지 않음. `response.error` 또는 timeout은 즉시 예외로 전파되어 현재 피드백 턴의 완료 result를 저장하지 않음.
- 재현 결과: 동일한 수정 단계에서 원본은 5회 모의 호출 후 `complete`, 선택 field는 이전 Stylist 그림으로 유지됨. 이식본은 5회 후 `RuntimeError: simulated image tool failure`로 중단됨.
- 위 5회는 문맥화·Critic·판단·rewrite·이미지의 단계별 요청 수임. provider 재시도 5회를 실제 실행한 시험이 아님. provider loop는 소스로 확인하고 최종 실패 반환만 모의 제공함.
- 사용자 영향: 이전 완료 폴더는 보존되지만 현재 수정 시도의 비평·실패 상태가 다음 턴으로 이어지는 완료 record는 만들어지지 않음. 일시적 실패도 자동 재시도되지 않음.
- 수정 방향: 복구 가능한 host 오류와 입력/계약 오류를 구분하고, 원본 fallback에 대응하는 실패 상태·마지막 유효 이미지·피드백 보존 정책을 설계할 필요가 있음. 모든 오류를 정상 성공으로 바꾸는 방식은 부적절함.

### F4. 중간 — 정상 이미지로 교체된 blob의 무결성 불일치를 감지하지 못함

- 분류: 재현된 저장 검증 공백임. 원본 helper에도 기존 blob 신뢰가 존재하므로 이식 과정에서 새로 생긴 회귀라고 단정하지 않음.
- 발생 조건: `result.json`·`state.json`은 그대로인데 `base64/<hash>` 내용이 다른 정상 JPEG의 base64로 바뀌는 경우임.
- 관련 경로:
  - [load_result](C:/WIP/PaperSketch/skills/paper-sketch/scripts/state.py:42): 53행에서 JSON hash를 확인하지만 67~70행은 base64·이미지 판독 가능 여부만 확인함.
  - [이미지 hash 저장](C:/WIP/PaperSketch/skills/paper-sketch/scripts/state.py:122): 버전별 hash를 저장하지만 load에서 대조하지 않음.
  - [원본 write_base64](C:/WIP/PaperSketch/reference/PaperBanana-Interact/utils/base64_rw_helper.py:36): 이미 존재하는 blob은 신뢰함.
  - [스킬의 손상 검출 설명](C:/WIP/PaperSketch/skills/paper-sketch/SKILL.md:97), 한국어 검토본의 동일 설명임.
- 원본/현재 동작: 둘 다 정상 형식의 다른 그림으로 바뀐 파일을 내용 hash로 다시 검증하지 않음. PaperSketch가 추가한 result hash·JPEG hash도 이 경우를 차단하지 못함.
- 재현 결과: 임시 white 그림을 저장한 후 해당 blob만 red 그림으로 교체함. load는 성공했고 JSON hash는 계속 일치했음. `final.jpg`는 white이지만 다음 수정 입력은 red로 복원됨. 파일명 content hash와 버전 이미지 hash는 모두 실제 내용과 불일치했음.
- 사용자 영향: 사용자가 선택·확인한 export와 모델이 다음 턴에 받는 이미지가 조용히 달라질 수 있음. 임의 공격을 가정한 네트워크 시험이 아니라 로컬 저장 파일의 정상 이미지 교체를 이용한 재현임.
- 수정 방향: load 시 base64 내용의 content-address hash와 선택/과거 그림의 decoded-image hash를 검사할 필요가 있음. 판독 불가 손상 검출과 내용 동일성 보장을 지침에서도 구분할 필요가 있음.

### F5. 중간 — 최종 21:9 및 비율 머리말 경로의 실제 이미지 생성은 미검증임

- 분류: 확인된 prompt adapter 변경과 실도구 검증 공백임.
- 발생 조건: 현재 기본값 21:9 또는 `--prepare-image-prompt`를 사용하는 새 실행임.
- 관련 경로: [기본 비율](C:/WIP/PaperSketch/skills/paper-sketch/scripts/run.py:89), [image_prompt](C:/WIP/PaperSketch/skills/paper-sketch/scripts/respond.py:8), [원본 image config](C:/WIP/PaperSketch/reference/PaperBanana-Interact/agents/visualizer_agent.py:80).
- 원본 동작: 비율·image_size를 provider ImageConfig 인자로 전달함. 원본 UI 기본값은 21:9이며 Visualizer 자체의 metadata 부재 fallback은 1:1임.
- 현재 동작: UI 기본값 21:9를 사용하며 API 비율을 도구 prompt 머리말로 옮김. 렌더링 원문은 뒤에 보존되지만 최종 도구 prompt 전체가 원본과 byte 동일한 것은 아님. `1k`, temperature, max tokens 등은 내장 도구의 동일 인자로 강제되지 않음.
- 검증 결과: 기존 CLI fixture는 21:9 설정·머리말 전달과 원문 유지까지 확인함. 과거 실제 그림은 16:9 요청·1672×941 출력이며 저장된 실제 tool prompt에는 새 API 비율 머리말이 없었음.
- 사용자 영향: 기존 실제 그림 시험을 최종 21:9 경로의 검증으로 사용할 수 없음. 정확한 출력 비율·해상도·문자 가독성은 현재 도구에서 별도 확인이 필요함.
- 수정·검증 방향: 승인 후 최종 지침/준비기를 그대로 사용하여 실제 비율·크기를 측정할 필요가 있음. 설명에 다른 비율이 포함된 경우 설정과 충돌할 수 있으므로 이 조건도 별도 확인이 필요함. 실제 불일치가 확인되기 전 임의 crop이나 재설계는 부적절함.

### F6. 낮음 — 잘못된 Critic JSON의 무변경 종료와 마지막 round 미검토는 원본에서 승계됨

- 분류: 원본 동작 유지임. 이식 자체의 불일치가 아님.
- 발생 조건: 초기 Critic에 `{}` 또는 필수 필드 없는 응답이 오거나, 마지막 허용 round에서 재생성되는 경우임.
- 관련 경로: [원본 Critic 파싱/기본값](C:/WIP/PaperSketch/reference/PaperBanana-Interact/agents/critic_agent.py:126), [원본 반복 종료](C:/WIP/PaperSketch/reference/PaperBanana-Interact/utils/paperviz_processor.py:82), [PBInteract rewrite 기본값](C:/WIP/PaperSketch/reference/PaperBanana-Interact/agents/refiner/pb_interact.py:330).
- 원본/현재 동작: 필드가 없으면 `No changes needed.`로 취급될 수 있음. 최종 허용 round의 새 그림은 다음 검토 없이 선택될 수 있음.
- 검증 결과: `{}`를 반환하는 모의 응답에서 processor가 무변경 종료하고 기존 그림을 선택함. 최대 round의 추가 Critic 호출 부재는 기존 회귀에서 확인됨.
- 사용자 영향: 프로세스 성공·JSON 파싱 성공이 요구 충족 검토의 성공을 보장하지 않음. 텍스트가 비어 있지 않다는 bridge 검사만으로 이를 해결하지 못함.
- 수정 방향: 원본 충실성 범위에서는 승계 결함으로 명시할 필요가 있음. schema 검증·추가 최종 검토를 도입하려면 원본 대비 동작 변경으로 승인·분리 검증할 필요가 있음.

### F7. 낮음 — 재개 run_config의 인자 기록과 실제 참고 선택 이력을 혼동할 수 있음

- 분류: provenance 해석상의 불일치 가능성임. 실제 재검색이 발생한 버그는 아님.
- 발생 조건: random으로 생성한 결과를 `refine`에서 `--retrieval` 생략으로 재개하는 경우임.
- 관련 경로: [설정 저장](C:/WIP/PaperSketch/skills/paper-sketch/scripts/run.py:84), [refine 경로](C:/WIP/PaperSketch/skills/paper-sketch/scripts/run.py:94), [기본값 auto](C:/WIP/PaperSketch/skills/paper-sketch/scripts/run.py:110).
- 원본/현재 동작: PBInteract 수정 단계는 기존 record의 선택 그림·설명·이력을 사용하며 Retriever를 다시 호출하지 않음.
- 검증 결과: 과거 `stage678-generate-live/run_config.json`은 random, `stage678-refine-live/run_config.json`은 auto임. 그러나 refine 요청 7개에는 Retriever 호출이 없고 이전 선택 ID가 유지됨.
- 사용자 영향: run_config의 auto를 실제 자동 검색 수행 증거로 잘못 해석할 수 있음. `codex-host`, `codex-image-host` 역시 실제 모델 버전이 아닌 adapter 식별명임.
- 수정 방향: 요청 인자와 effective 참고 선택 mode·부모 실행·실제 노출 가능한 model/tool 식별 정보를 구분해 기록할 필요가 있음. 미노출 모델 설정은 미확인으로 남겨야 함.

## 3. 원본 파일·커밋 및 이식 범위

| 저장소 | 실제 HEAD | 상태 |
|---|---|---|
| PaperBanana-Interact | `ed08ef7e427ce147194af91d8ae6326a6cbc9cbd` | 주 기준이며 작업 트리 변경 없음 |
| PaperBanana | `f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3` | 보조 참고이며 작업 트리 변경 없음 |
| papervizagent | `e088a8fff74cc363b6897c0843631fff76484908` | 원형 대조 기준이며 작업 트리 변경 없음 |

- 보존 파일 30개 전체 목록·hash는 `skills/paper-sketch/assets/interact/SOURCE_MANIFEST.json`과 검증 snapshot에 있음.
- 실제 활성 핵심: `agents/{retriever,planner,stylist,visualizer,critic}_agent.py`, `agents/refiner/pb_interact.py`, `utils/paperviz_processor.py`, `utils/{base64_rw_helper,image_utils}.py`, diagram style guide임.
- 복사됐으나 실행 대체됨: `utils/generation_utils.py`임. 파일은 동일하지만 `install_bridge`가 sys.modules에 대체 모듈을 등록하여 원본 provider 모듈 실행을 막음.
- 복사됐으나 주 경로 미사용: 다른 refiner, vanilla/polish의 process, plot style guide, guide 생성기, 모델 설정 template임. 평가/시뮬레이터 모듈 일부는 import되지만 평가·시뮬레이터 함수는 비활성화됨.
- 추가 구현: `scripts/{run,bridge,respond,state,prepare_references,probe,reference_probe}.py`, 축소 requirements, 영어 지침, 별도 한국어 검토본임.
- 미이식 entrypoint: 원본 `app.py`, `main_multiturn.py`, UI timeline/pin/revert 화면, benchmark CLI·시각화·전체 저장 포맷 import임. 단일 record 저장·재개 명령으로 범위를 제한함.
- PaperBanana의 `skill/SKILL.md`, `skill/run.py`는 구성 참고임. provider/key·자동 데이터 다운로드·다중 후보 runner를 재사용한 것이 아님. `critic_rounds.py`, plot·metaphor·figure-size 개선을 Interact에 자동 병합하지 않았음.
- 세 저장소의 5개 diagram system prompt 문자열은 동일하지만 각 agent·processor 파일 전체는 다름. Interact가 나머지 저장소의 모든 개선을 포함한다고 가정하지 않았음.

## 4. 최초 생성 경로의 실제 연결

| 단계 | 실제 경로·입력·출력 | 대조 결과 |
|---|---|---|
| 사용자 입력 | run.py 88~92행이 UTF-8 JSON content·visual_intent·additional_info를 원본 record로 구성함 | 원본 app의 방법론·캡션 입력 의미 유지됨. PDF 자동 추출은 없음 |
| 검색 준비 | run.generate → 원본 prepare_retrieval → Retriever.process임 | 검색 1회 후 top10_references가 같은 record로 이어짐 |
| auto | 원본 `_retrieve_and_parse`가 실제 ref.json 앞 200개 전문·캡션을 구성함 | 모의 ID 반환에서 요청·파싱 일치함. 실제 관련성은 F1 범위임 |
| Planner | 원본 Planner.process 43~115행이 선택 ID를 ref record에 연결하고 실제 이미지 byte·본문·캡션을 prompt에 추가함 | 차등 입력에서 그림 10개의 hash·순서·텍스트가 일치함 |
| Stylist | 원본 Stylist.process 41~82행이 Planner 설명과 고정 guide·원문·캡션을 입력받음 | 전문 guide와 출력 field가 일치함 |
| Visualizer | 원본 process가 Planner·Stylist 설명 및 미생성 critic 설명을 렌더링함 | 처음 두 이미지 생성·JPEG quality 95 변환이 유지됨 |
| Critic | 원본 Critic.process가 처음 Stylist 그림, 이후 이전 critic 그림·설명·원문·캡션을 검토함 | 수정 시 재생성·무변경 조기 종료·상한·최종 field가 일치함 |

- 원본 데이터 root는 `data/MTPaperBananaBench/`, 실제 실행용 사본은 `data/prepared/MTPaperBananaBench/`임. 원본 `ref.json`만 경로를 지정하는 것이 아니라 실제 사본 그림에 연결됨.
- 원본·사본 ref 298개 순서·본문·캡션이 동일함. 유일한 record 차이는 `ref_309.path_to_gt_image`의 선두 U+200C 제거임. 원본 파일은 유지됨.
- 사본의 실제 그림 298개·hash 연결은 기존 데이터 테스트로 확인함. `ref_260`, `ref_305` 빈 본문은 그대로 유지됨. test split은 참고 검색에 쓰지 않음.
- 의도된 차이: 사본 manifest가 필요하며 auto/random의 유효 ID 10개를 강제함. 원본의 데이터 미존재 fallback 또는 잘못된 ID 조용한 생략과 동일하지 않음. 실제 검색 실패를 검색 성공처럼 감추지 않으려는 정책임.

## 5. 피드백 경로의 실제 연결

1. `load_result`가 선택 field·과거 이미지·설명·문맥·비평을 inline 계약으로 복원함.
2. `refine`이 user 요청을 추가하고 원본 `process_single_feedback`을 호출함. 최초 정수 round에서 `[1,0]`, 이후 `[i+1,j]`로 진행함.
3. 원본 `format_chat_history_with_images`가 prior_preferred_candidates와 현재 eval_image_field를 assistant 버전별로 대응시킴. 새 user 턴마다 context_diagramN/context_user_turnN을 구성함.
4. `j==0`은 최신 요청을 우선 검토하고 prior request별 `critique_prior_turnN`도 구성함. `j>0`은 이미 수정한 그림을 전체 요구와 대조함.
5. Critic → YES/NO → YES에서만 설명 공개·rewrite → Visualizer fresh generation 순서가 유지됨. 별도 Refiner 모델을 새로 만든 것이 아니라 PBInteract 내부 3단계임.
6. NO는 생성 없이 종료하고, 성공한 새 이미지가 있으면 eval_image_field를 전진시킴. 마지막 그림은 prior_preferred_candidates에 보존됨. runner가 assistant 턴을 완성함.
7. 현재 턴 내부 이미지 선택은 추가 인터페이스임. 과거 턴은 해당 결과 파일에서 새 폴더로 분기함. 원본 UI의 이후 이력 삭제 방식과는 다르며 현재/과거 요구를 섞지 않는 목적임.

- 정상 차등 시험의 첫 수정은 YES·재생성·내부 NO 종료, 두 번째 수정은 과거 요구별 검토·NO·이미지 0회로 구성됨. 원본과 record·입력 동일함.
- 이전 그림을 imagegen의 편집 대상으로 넣지 않음. 원본 PBInteract의 설명 기반 재생성을 유지함.
- 일반 저장/선택/재개는 기존 테스트로 확인됐지만 모델 오류의 턴 완료 정책은 F3, blob 내용 동일성은 F4 한계가 있음.

## 6. Codex·이미지 도구 연결의 실제 수준

```text
원본 agent → 대체 generation_utils → request.json + 이미지 sidecar
         → 활성 Codex가 읽고 추론 또는 imagegen 도구 사용
         → respond.py → response.json → FileBridge 반환 → 원본 agent/processor 계속 실행
```

- 텍스트는 비어 있지 않은 list[str], 이미지는 검증한 파일의 base64 list로 원본에 반환됨. Visualizer가 이후 JPEG 변환함.
- PBInteract의 generic user parts와 SDK model Content를 ordered turns로 직렬화함. ID 불일치·지원하지 않는 part·후보 수·host 오류·timeout은 실패함.
- Python 안에 Codex model client나 imagegen tool dispatcher가 있는 것은 아님. 실제 도구 호출은 스킬을 수행하는 활성 Codex의 작업임. 무인 Python 명령 단독 실행은 응답 대기만 수행함.
- 이번에는 모든 모델 경계가 모의 응답이었음. 실제 참고 그림은 로컬에서 읽어 hash를 비교했으며 외부 모델로 전송하지 않았음.
- 과거 생성 기록: stage4 생성은 text 3/image 2, stage5 첫 수정은 text 6/image 1, 두 번째 수정은 text 3/image 0임. stage678 생성은 text 3/image 2, 수정은 text 6/image 1임. 이는 당시 기록이며 이번 호출 수는 0임.
- 과거 생성 PNG·원본 JPEG·Critic 입력·저장 결과는 연결 증거임. 원본 provider 기준선이나 현재 최종 비율 경로의 재실행 증거는 아님.
- 실제 host 모델 버전·token 제한·sampling·독립 문맥·모든 tool 내부 설정은 기록만으로 확정할 수 없음. 원본 설정이 JSON에 있다고 같은 값으로 실행됐다고 판단하지 않음.

## 7. 스킬 문서·테스트·무수정 검증

- 영어 SKILL.md의 generate/refine/inspect/select, 필수 인자·기본값·host 처리 순서가 현재 parser와 일치함.
- 한국어 검토본은 영어 본문의 실행법·제약·경로·매개변수를 의미상 반영함. 중대한 번역 누락이나 반대 의미는 발견하지 못함. F4의 손상 검출 한계는 양쪽 문서에 공통임.
- 영어 스킬·실행 코드에서 `SKILL.ko` 또는 `review/` 참조 없음이 rg로 확인됨. 한국어 사본은 실행 의존성이 아님.
- skill-creator `quick_validate.py`는 통과함. 이는 frontmatter·구조 검사 결과이며 동작 성공의 근거로 사용하지 않았음.

| 검증 | 결과·한계 |
|---|---|
| 기존 unittest discover | 19개 통과·skip 없음. 외부 모델 미호출임 |
| original normal / ported normal | 각각 18개 호출, 정규화된 trace 전체와 record 전체 일치함 |
| original failure / ported failure | 원본 complete/이전 그림 유지, 이식본 error임. F3 재현됨 |
| 상태 blob 교체 probe | 정상 JPEG 교체를 load가 수용하고 export와 재개 이미지가 달라짐. F4 재현됨 |
| Critic `{}` probe | 무변경 종료함. 원본 승계 동작임 |
| 실제 데이터 비교 | 298개·유일한 경로 보정·200개 후보 본문 크기 확인함 |
| 형식·문서 대조 | 형식 통과·영한 의미 대응·한국어 비참조 확인함 |
| 새 실제 추론/imagegen | 실행하지 않았음. 사용자 확인 필요 범위임 |

- 런타임: Python 3.11.0, google-genai 1.75.0, Pillow 13.0.0, json-repair 0.64.3, aiofiles 25.1.0, tqdm 4.70.1임. 원본 권장 Python 3.12 전체 실행 환경과 같다는 주장이 아님.
- 실행은 기존 uv 캐시의 `--offline --no-project --with-requirements` 환경을 사용함. 새 모델·의존성을 다운로드하지 않았음.
- reference import에는 `-B`와 PYTHONDONTWRITEBYTECODE를 적용하여 bytecode 생성도 막음.
- 추가 차등·저장 경계 검증 전후 보호 대상 소스·기존 테스트·문서·raw/prepared 데이터 1,579개 파일 hash와 reference Git 상태를 비교함. 최종 결과는 `after.json`에 보존함.
- 증거: `runs/fidelity-audit-2026-11-03/{existing-tests.log,differential-summary.json,state-probes.json,static-data-audit.json,historical-records.json,inherited-and-runtime.json,before.json,after.json}`임. original/ported 각 checked 폴더에 trace·outcome·실제 클래스 경로가 보존됨.

## 8. 최종 구분과 다음 실제 시험

### 코드·테스트로 일치가 확인된 범위

- Interact 핵심 보존 파일·원문 prompt·style guide와 정상 단일 후보 diagram/PBInteract 호출 순서임.
- 실제 ref JSON/그림 연결, Planner 이미지 전달, 초기 Critic 재생성·조기 종료, 피드백 2턴·요구별 schema·설명 공개 시점·NO 무생성·정상 상태 전이임.
- 정상 저장·이동·선택·완료 턴 재개의 원본 상태 key·이미지/설명 대응임. 무결성 보장 전체는 F4와 구분됨.

### 의도적으로 변경된 범위

- provider 호출 → 활성 Codex/file bridge·내장 imagegen, 설정 객체 초기화, 단일 후보·명시적 PBInteract·평가 비활성화임.
- 유효 참고 ID 10개 강제·manifest 요구, 오류 즉시 중단·retry 미구현, 상대 blob 경로·hash metadata·export, 내부 버전 선택·비파괴 분기임.
- 원본 UI 21:9 기본값 적용과 API 비율의 tool prompt 머리말 변환임.

### 미구현·미검증 범위

- 실제 auto 관련성·Planner 전문 전체 처리, 독립 모델 문맥, 원본 provider retry/fallback와의 동등성, 최종 비율·해상도 실도구 검증, 원본 API 대비 품질·요구 이행·망각률 비교임.
- manual·동시 다중 후보·다른 refiner·benchmark 평가/시뮬레이터·임의 원본 UI/batch 세션 import·중단 요청 복구·전역 설치임. plot은 이식 대상 Interact의 주 diagram 경로와 구분되는 보조 PaperBanana 기능임.

### 사용자 확인 후 가능한 다음 실제 시험

1. 최종 지침 그대로 합성 text/layout classifier 방법론·캡션과 공개 참고 데이터 random 모드로 후보 1개를 생성하고 색 변경 피드백 1회를 수행할 수 있음. 초기 Critic 상한 1·내부 수정 상한 2로 제한하면 imagegen은 통상 3회, 최대 5회이며 텍스트 요청은 최대 10회임. 마지막 상한 출력의 미검토는 원본 규칙으로 별도 표시할 필요가 있음.
2. 전송 범위는 합성 방법론·캡션, 선택된 공개 참고 10개의 전문·이미지, 원본 prompt/style guide, 생성 그림·피드백 이력임. imagegen에는 상세 설명과 비율 머리말이 전달됨. private 사용자 논문은 필요하지 않음.
3. auto 시험은 별도 확인이 필요함. 원문 기준 약 297만 자 후보 텍스트와 target이 Codex 입력에 들어가며, 처리 가능성을 확인하기 전 random 시험과 묶어 auto 성공을 주장하면 안 됨. 현재 제약 아래 전송·실제 선택은 하지 않았음.
4. 원본 모델과 성능을 비교하려면 고정 원본 backend·동일 pool/선택 ID·모델/도구 버전·후보 및 round 예산·반복 표본·독립 평가 조건을 추가로 정해야 함. 원본 API는 별도 승인 범위임.

- 이번 작업에서 위 실제 시험이나 수정 방향을 실행하지 않았음. 테스트 통과·파일 동일성만으로 원본과 성능이 같다는 결론을 내리지 않음.
