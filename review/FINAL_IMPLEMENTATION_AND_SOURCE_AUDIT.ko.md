# PaperSketch 구현 완료 점검 및 원본 대조

- 수행일: 2026-11-02임.
- 결론: 합의된 단일 후보 diagram·PBInteract·완료 결과 저장/선택/재개 범위의 로컬 스킬 구현이 완료됨. 핵심 원본 Python 코드·프롬프트·loop는 유지됨.
- 기능 연결과 원본 전체 기능·모델 성능 동등성은 구분됨. auto 전문 관련성 검색과 원본 API 대비 품질 비교는 미완료임.
- 전역 설치·설정 변경·커밋·업로드·모델 다운로드·API key 사용·별도 유료 API 호출은 수행하지 않았음.

## 1. 계획 대비 최종 결과

| 단계 | 역할 | 확인 결과 |
|---|---|---|
| 1. 로컬 스킬 구성 | 원본 코드·출처·영어 지침·한국어 검토본 구성 | 원본 파일 30개 및 Apache-2.0 라이선스 보존됨 |
| 2. 호출 연결 | 원본 요청을 Codex/imagegen에 전달하고 반환 계약 복원 | 활성 채팅 기반 파일 bridge로 연결됨. Python의 직접 host API 호출 구조는 아님 |
| 3. 참고 데이터 | 실제 ref JSON·그림을 Retriever·Planner에 연결 | 298개 연결 검증과 원본 random 실행 완료됨. auto 전문 관련성 선택은 미검증임 |
| 4. 최초 생성 | 원본 full processor 실행 | Planner·Stylist 각각 렌더링과 Critic 반복·종료·선택 계약이 유지됨 |
| 5. 피드백 수정 | 원본 PBInteract의 이력·요구별 검토·설명 재작성·재생성 | 실제 수정·재생성 후 검토와 이전 시험의 두 번째 턴 무변경 종료가 확인됨 |
| 6. 저장·이어가기 | 그림·설명·피드백·검토·선택 버전 보존 | 원본 blob 저장 재사용, 이동 가능한 결과, 버전 선택·과거 턴 분기 연결됨 |
| 7. SKILL 실행법 | 최초 생성·수정·저장 결과 재개 안내 | 영어 실행 지침과 실행에서 참조하지 않는 한국어 검토본이 갱신됨 |
| 8. 작은 테스트부터 실제 확인 | 상태·데이터 검증 후 후보 1개·피드백 시험 | 최종 회귀 19개·실제 후보 생성/복사본 재개/수정·모델 호출 없는 버전 선택 통과함 |

## 2. 이번 점검에서 발견·보완한 부분

- `[이전 구현]` 4·5단계는 전체 원본 record를 inline JSON으로 보존했지만 원본 content-addressed 저장은 아직 사용하지 않았음. 이번 단계에서 해당 원본 함수를 연결함.
- `[구현]` 새 `scripts/state.py`가 원본 `utils/base64_rw_helper.py`의 `offload_base64_fields`, `write_base64`, `read_base64`를 재사용함. 중복 blob 저장 방지·중첩 record 지원을 그대로 사용함.
- `[변경]` 원본 helper의 절대 경로를 저장 경계에서 상대 `base64/<hash>`로 변환함. 재개 시 원본 reader로 읽어 inline base64 계약을 복원함. 원본 helper 자체는 수정하지 않았음.
- `[구현]` `inspect`로 저장된 설명·피드백·선택 field·선택 가능 버전을 조회함. `select`는 모델 호출 없이 현재 턴 버전을 새 결과로 저장함.
- `[보완]` 단순 이력 길이 검사에서 assistant/user 전체 교대 순서와 과거 그림 field 존재 검사로 강화함. 과거 턴 그림과 나중 피드백을 섞는 선택은 거부하고, 해당 과거 결과 파일에서 분기하도록 연결함.
- `[보완]` 원본 UI 기본 비율은 21:9인데 이전 실행기 기본값은 16:9였음. `additional_info` 생략 시 21:9로 수정함. 원본 Visualizer 자체의 metadata 부재 fallback은 1:1이며 변경하지 않았음.
- `[보완]` `respond.py --prepare-image-prompt`가 원문 렌더링 지시를 유지하고 API aspect-ratio 설정만 텍스트 머리말로 전달함. imagegen에 같은 전용 인자가 없으므로 필요한 호출 adapter임.
- `[검증]` 기본 21:9가 실제 원본 Visualizer 요청과 준비된 tool prompt에 전달되는 CLI fixture를 추가함. 정확한 21:9 실출력은 미검증이며, 요청 비율과 실제 출력 크기를 같다고 주장하지 않음.
- `[의존성]` 기존 requirements·격리 캐시만 사용함. 이번 저장 구현에 새 라이브러리를 추가하지 않았음.

## 3. 저장·재개 계약

| 파일·함수 | 역할 |
|---|---|
| `scripts/state.py:load_result` | 상대 blob·호환되는 원본 절대 blob·이전 PaperSketch inline record를 원본 agent 입력으로 복원함 |
| `scripts/state.py:save_result` | 원본 blob helper로 전체 record·이전 그림을 별도 결과에 보존함 |
| `scripts/state.py:select_version` | 현재 턴의 명시적 버전 선택만 새 record에 반영함 |
| `result.json` | 원본 상태 key·설명·비평·문맥·feedback history·선택 이미지 key를 유지함 |
| `base64/` | 원본 SHA-256 기반 blob 중복 제거 저장임 |
| `state.json` | 그림↔설명↔판독용 JPEG·선택 여부·부모 경로/hash·결과 hash·원본 manifest hash를 보존함 |
| `images/`, `final.jpg`, `description.txt` | 중간 버전과 선택 결과를 직접 검토할 수 있게 내보냄 |
| `run_config.json`, `requests/` | 생성·수정 설정과 원본 요청/응답·입력 그림을 보존함 |

- 실행 폴더 전체를 이동·복사하면 재개 가능함. 부모 폴더는 provenance이며 재개의 파일 의존성이 아님. 저장 시 이전 blob을 현재 폴더에 다시 확보함.
- 현재 턴의 내부 버전을 선택하는 기능은 추가 인터페이스임. 자동 선택은 원본 processor 정책을 유지함.
- 과거 턴 복귀는 해당 턴의 결과에서 새 폴더로 분기함. 원본 UI처럼 이후 이력을 삭제하지 않고 기존 결과도 보존함.
- 기존 결과 덮어쓰기·누락 blob·손상 이미지·record/state hash 불일치를 오류로 처리함.
- 완료 턴 재개만 지원함. 임의 원본 batch 배열·Gradio 메모리 세션·중단된 모델 호출 복구는 구현 범위가 아님.

## 4. 작은 테스트와 실제 실행

- `[순서]` 모델 호출 없는 상태·데이터 회귀 16개 통과 후 실제 시험을 수행함. 이후 선택 이미지 전달·이전 형식·비율 회귀를 보강하여 최종 19개가 통과함.
- `[fixture]` 폴더 이동 후 부모 없이 복원, 중첩 blob dedup, 다른 색의 버전 선택, 선택 그림의 원본 PBInteract 문맥화 전달, hash 불일치·누락·손상 실패를 확인함.
- `[fixture]` 원본 생성 loop의 수정/재생성·수렴·최대 횟수, 두 피드백 턴·과거 요구 검토, 저장/복원, 실제 auto pool 200개 요청 구성과 선택 그림 byte 연결을 확인함.
- `[검사]` skill-creator 구조 검사·변경 Python 구문 검사를 통과함. 영어 지침·코드에서 한국어 사본 참조가 없음.
- `[검사]` 이미지 prompt 준비 CLI의 비율 전달·원문 유지·기존 출력 보존·잘못된 요청의 무출력 실패를 확인함.

| 실제 실행 | 텍스트 요청 | imagegen | 확인 결과 |
|---|---:|---:|---|
| `runs/stage678-generate-live` | 3회 | 2회 | 실제 참고 10개 → Planner → Stylist → 각각 렌더링 → Critic 무변경 종료함 |
| `runs/stage678-relocated` | 0회 | 0회 | 위 폴더의 복사본임. 전체 record 복원 일치 및 이후 수정 입력 그림 byte 일치가 확인됨 |
| `runs/stage678-refine-live` | 6회 | 1회 | 복사본에서 재개 → 문맥화/검토/YES/설명 재작성 → 생성 → 재검토/NO 종료함 |
| `runs/stage678-selected-live` | 0회 | 0회 | 최초 턴의 Planner 버전을 새 폴더에 명시적으로 선택함. 부모 결과는 유지됨 |

- `[실제]` 방법론은 text/layout 두 branch를 concatenate하여 문서 class를 예측하는 합성 표본임. 사용자 실제 논문·benchmark 평가가 아님.
- `[실제]` 검색은 원본 random 모드임. 선택된 실제 그림 10개를 모두 판독함. 원본 요청에는 예제 전문이 유지되며 host의 예제 텍스트 판독은 발췌임.
- `[실제]` 첫 피드백은 Fusion만 lavender로 바꾸고 branch·Concatenate·모든 라벨·단일 Classifier 출력 경로를 유지하는 요청임. 새 그림에서 해당 조건을 시각적으로 확인함. 아이콘·간격 등은 재생성으로 변동됨.
- `[실제]` 초기 선택 JPEG hash는 `33833bf61eb807883e0284950c6eb76207f75fa57578e557d1cfadc260085a32`, 수정 JPEG hash는 `430a51c3ec68a828e8e01559780393e4235fd2ab48cdae399d210b48c167ea4f`임.
- `[실제]` 모델 호출 없는 Planner 선택 JPEG hash는 `80ff1ed84f1d4c7bc517f6d0a3b23a48ac85489cff978d8964288812ea6116b2`임. 각 버전 설명·이미지 연결을 검사함.
- `[조건]` 위 실제 시험은 기본 비율 정렬 전 16:9 설정으로 수행됐고 이미지 크기는 1672×941임. 최종 기본값 21:9 연결은 별도 CLI fixture로 확인함. 새 비율 머리말을 이용한 실제 21:9 출력은 아직 확인하지 않았음.
- `[근거]` machine-readable 대조 결과는 `runs/stage678-verification.json`임. 실행별 정확한 tool prompt·생성 PNG·원본 JPEG·상태·요청/응답도 각 폴더에 보존됨. `runs/`는 Git 제외됨.

## 5. reference 최종 대조

| 저장소 | 확인 commit | 작업 트리 |
|---|---|---|
| papervizagent | `e088a8fff74cc363b6897c0843631fff76484908` | 변경 없음 |
| PaperBanana | `f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3` | 변경 없음 |
| PaperBanana-Interact | `ed08ef7e427ce147194af91d8ae6326a6cbc9cbd` | 변경 없음 |

- `[코드]` 보존된 30개 파일 모두 Interact 원본·기존 SOURCE_MANIFEST hash와 byte 동일함. 실제 생성 processor·agent·PBInteract 클래스가 보존 파일에서 로드됨을 확인함.
- `[코드]` 세 저장소의 5-agent diagram system prompt 문자열과 diagram style guide는 동일함. 각 agent·processor 파일 전체는 저장소별로 다르므로 세 저장소 전체가 같은 구현이라고 판단하지 않음.
- `[기준]` 이식 기준은 Interact의 `demo_full` + 명시적 `pb_interact` 경로임. 원본 UI의 기본 refiner는 `pb_directrefine`, 시뮬레이션 CLI 기본은 `generative`이므로 기본 UI/CLI 실행 전체와 같다는 주장이 아님.
- `[출처]` 기본 PaperBanana의 `skill/SKILL.md`, `skill/run.py`는 환경·매개변수·출력 안내 참고용으로 검토함. provider/key·자동 다운로드·다중 후보 실행기를 통째로 가져오지 않았음. 원본 스킬의 MIT-0 메타데이터를 Apache 소스 전체에 적용하지 않았음.

| 항목 | 원본과의 관계 | 근거·차이 |
|---|---|---|
| 입력 content·visual_intent·additional_info | 유지함 | 원본 full 입력 필드를 사용함. 누락 비율 기본값은 UI 21:9로 정렬함 |
| ref loader·pool·검색·Planner 그림 연결 | 원본 코드 유지함 | auto 앞 200개·random 298개·top10 계약 유지됨. 유효 ID 10개 경계 검사는 추가됨 |
| Planner·Stylist·style guide·Critic prompt | 원문 유지함 | byte·문자열 대조와 원본 요청 구성을 확인함 |
| 최초 생성·Critic loop | 원본 코드 유지함 | `prepare_retrieval`, `process_query_one`, `_run_critic_iterations`를 호출함. 새로 작성한 loop가 아님 |
| Planner·Stylist 렌더링 및 JPEG 변환 | 유지함 | 원본 Visualizer가 두 설명과 각 critic 설명을 렌더링함 |
| PBInteract 문맥화·요구별 검토·gating·rewrite | 원본 코드 유지함 | 설명 비노출 시점·최신/과거 요구 구분·NO 무생성·`i,j` 전이를 유지함 |
| 수정 방식 | 원본 주 경로 유지함 | 설명 기반 fresh generation임. 직접 이미지 편집 대안으로 바꾸지 않았음 |
| 텍스트/이미지 backend | 의도적 변경임 | 원본 provider router 대신 활성 Codex 요청 처리·내장 imagegen을 사용함 |
| 설정 생성·단일 후보·명시적 PBInteract | 범위 선택·변경임 | provider 초기화 없는 설정 객체를 구성함. 후보 1개이며 다른 refiner·평가/시뮬레이터는 미연결임 |
| 독립 context·max token·sampling·retry·이미지 tier | 동등성 미보장임 | 파일에 원본 설정을 기록하나 host가 같은 모델 실행 조건을 강제하지 못함 |
| 기본 비율·도구 전달 | 발견 후 보완함 | UI 21:9로 수정됨. API 비율을 tool prompt 머리말로 옮기는 adapter이며 실제 크기 보장은 아님 |
| 대화 완료·저장·버전 선택 | 원본 상태 계약 + 파일 인터페이스임 | 원본 UI의 assistant/user·선택 그림 대응을 유지함. 내부 렌더 선택과 비파괴 분기는 추가됨 |
| blob 저장 | 원본 helper + 경로 adapter임 | content hash·dedup·원본 reader 유지, 상대 경로·export·metadata/hash 검증 추가됨 |
| 원본 실패·종료 정책 | 핵심은 유지됨 | malformed JSON의 no-change 가능성·마지막 round 미검토를 유지함. host 오류/timeout은 명시적 중단이며 provider retry와 다름 |

## 6. 남은 검증과 완료 범위

- `[미검증]` auto 약 2,967,946자 전체를 처리한 실제 관련성 검색, Planner 예제 전문 전체의 독립 일괄 추론, 원본 API 기준선·독립 judge·반복 표본 품질 및 망각률 비교임.
- `[미보장]` 같은 활성 채팅 Codex는 이전 설명을 이미 보았을 수 있음. 원본 요청 파일의 설명 비노출과 독립 모델 기억 격리는 다름.
- `[미구현]` 전역 설치, plot, 다중 후보 동시 실행, 다른 refiner, benchmark simulator/evaluator, 임의 원본 세션 가져오기, 중단 실행 복구임.
- `[유지]` 원본 소스·프롬프트·데이터는 변경하지 않음. Apache 라이선스·출처를 보존하며 개별 논문 그림 권리가 코드 라이선스로 모두 해결됐다고 주장하지 않음.
- `[판정]` 합의된 로컬 실행·저장·재개·지침·연결 시험 범위는 완료됨. 전체 원본 기술·서비스 조건·논문 성능까지 동일하다는 판정은 아님.
