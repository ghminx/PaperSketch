# 4그룹 단계 검색 구현 및 실제 Codex 재시험

- 작업일: 2026-11-03, Asia/Seoul 기준임.
- 사용자 승인 사항: 고정 4개 그룹에서 각각 6개 선발 → 24개의 전문 재비교 → 최종 10개 선택 방식임.
- 결론: **승인된 검색 경로 연결 완료, 서로 다른 요청 5종의 실제 검색 25회 전부 성공함. 실제 선택 이미지 50건의 원본 Planner 요청 연결도 확인됨.**
- 별도 실제 확인: 실행용 검색 응답 명령 1회도 성공하여 전체 실제 Codex 호출은 26회임. 이미지 생성은 0회임.
- 한계: 원본 200개 일괄 비교와의 품질 동등성, 실제 Planner 추론 및 그림 생성 품질을 검증한 결과는 아님.

## 1. 원본 유지와 승인된 변경

| 구분 | 구현 내용 |
|---|---|
| 유지 | 원본 후보 앞 200개·전체 본문·캡션·ID·그림, 주제와 visual intent의 선택 우선순위, 최종 `top10_references` 계약임 |
| 변경 | auto의 단일 모델 호출을 예선 4회·최종 1회로 변경함. 예선은 6개, 최종은 10개 선발임 |
| 프롬프트 변경 | 원본 관련성 기준을 재사용하고 후보 수·선발 수·출력 형식을 현재 단계에 맞게 변경함. 각 응답은 `selected_diagrams` 배열임 |
| 모델 문맥 | 그룹별·최종 선택마다 독립 Codex CLI 문맥을 사용함. 활성 채팅에 200개 전체를 누적하는 방식이 아님 |
| 후속 경로 | 최종 ID 10개를 원본 Planner가 실제 전문·그림에 연결함. Stylist·Visualizer·Critic·PBInteract·저장 로직은 이번에 변경하지 않았음 |
| 다른 검색 모드 | random·none은 기존 원본 경로를 유지함 |
| 실패 정책 | 잘못된 그룹·부족/중복/범위 외 ID·과대 요청은 실패함. 임의 random·요약·누락으로 대체하지 않음 |

- 원본 `reference/`와 보존 사본 `assets/interact/`는 수정하지 않았음. 기존 30개 원본 파일 byte/hash 동일성 검사가 통과함.
- 원본 HEAD: Interact `ed08ef7e427ce147194af91d8ae6326a6cbc9cbd`, PaperBanana `f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3`, papervizagent `e088a8fff74cc363b6897c0843631fff76484908`임. 세 작업 트리 변경 없음이 확인됨.

## 2. 실제 코드와 사용 경로

- [GroupedRetrieverAgent](../skills/paper-sketch/scripts/grouped_retriever.py): 원본 Retriever를 상속하고 auto만 교체함. 그룹 전문·hash·순서·200개 무누락 확인, 단계별 요청·응답 계약 검사, 검색 기록 저장을 담당함.
- [run.make_processor](../skills/paper-sketch/scripts/run.py): auto에 새 adapter를 연결함. `generate --retrieval auto`에는 `--reference-groups`가 필요함.
- [respond_retrieval.py](../skills/paper-sketch/scripts/respond_retrieval.py): 단일 대기 검색 요청의 전문을 읽어 독립 Codex에 전달하고 bridge 응답을 작성함. 기존 ChatGPT 로그인을 요구하고 별도 API 키 환경변수를 자식 실행에서 제외함. 이미 응답했거나 시도한 요청은 재호출하지 않음.
- [reference_probe.py](../skills/paper-sketch/scripts/reference_probe.py): 같은 검색 adapter를 사용함. `--retrieval-only` 지정 시 실제 검색 후 종료하며 Planner 모델·이미지 도구를 호출하지 않음.
- 영어 SKILL.md와 실행에서 참조하지 않는 한국어 검토본에 동일한 실행법·승인된 알고리즘 차이·남은 한계를 반영함.

```text
python <skill>/scripts/run.py generate --input <input.json> --dataset-dir <prepared-root> --reference-groups <groups-root> --output <new-run> --retrieval auto

각 대기 검색 요청:
python <skill>/scripts/respond_retrieval.py <request.json> --model gpt-6.1-sol --timeout 120

검색만 시험:
python <skill>/scripts/reference_probe.py --input <input.json> --dataset-dir <prepared-root> --reference-groups <groups-root> --exchange-dir <new-run> --retrieval auto --retrieval-only
```

- Python runner만 실행하면 bridge 응답을 기다림. host가 검색 요청 5개를 각각 위 명령으로 처리하고, 이후 원본 Planner 등은 기존 스킬 절차대로 처리하는 구조임.
- CLI의 system 지시는 host의 작업 지시 안에 포함됨. 원본 provider의 system 슬롯·sampling·출력 token 설정과 완전히 동일한 실행 조건은 아님.
- 검색 단계에서 독립 문맥을 구현한 결과이며, PBInteract 검토 문맥 문제 전체를 해결한 것은 아님.

## 3. 입력 크기와 실제 실행 결과

- 고정 그룹의 후보 수·문자 수는 53개/790,542자, 51개/793,312자, 58개/797,945자, 38개/602,336자임.
- 원본 본문·캡션·ID 블록을 보존한 TXT와 원본 record 사본 JSON을 읽음. 데이터셋 hash와 그룹 내용이 다르면 모델 호출 전에 거부함.
- 후보 텍스트 상한은 800,000자, adapter의 system+user 상한은 1,000,000자임. 검색 host는 최종 포장된 CLI 입력도 기존 관찰 한도인 1,048,576자와 대조함.
- 실제 25개 호출의 최종 host 입력은 287,199~801,842자였으며 모두 정상 완료됨. 이전 약 299만 자 입력의 문자 수 거절은 이 경로에서 재현되지 않았음.
- 한도 검사는 문자 수 기준임. 임의의 사용자 입력·다른 모델의 token context 수용이나 품질을 보장하지 않음.

| 합성 요청 | 검색 호출 | 결과 | 실행 시간 | 최종 선택 ID |
|---|---:|---|---:|---|
| 멀티모달 융합 | 5 | 6·6·6·6 → 10개 성공함 | 77.81초 | ref_88, ref_140, ref_39, ref_85, ref_129, ref_4, ref_73, ref_65, ref_159, ref_45 |
| 다변량 시계열 | 5 | 성공함 | 88.45초 | ref_151, ref_141, ref_42, ref_87, ref_39, ref_172, ref_15, ref_170, ref_45, ref_85 |
| 의료 이미지 분할 | 5 | 성공함 | 90.72초 | ref_35, ref_88, ref_203, ref_59, ref_108, ref_1, ref_58, ref_4, ref_72, ref_41 |
| 검색 기반 QA | 5 | 성공함 | 87.12초 | ref_123, ref_176, ref_23, ref_107, ref_131, ref_193, ref_139, ref_116, ref_27, ref_130 |
| 계획·실행·검토 에이전트 | 5 | 성공함 | 90.45초 | ref_51, ref_166, ref_7, ref_139, ref_26, ref_27, ref_130, ref_50, ref_176, ref_47 |

- 5종 시험의 전체 경과 시간은 434.58초, 약 7분 15초임. 환경 준비·구현·로컬 검사 시간과는 구분됨.
- 최대 8분 조건을 적용하여 그래프 모델 요청과 전체 검색 반복 시험은 시작하지 않았음. 6종 전체나 요청당 2회 반복을 완료했다는 주장이 아님.
- 별도 실행용 host 명령은 같은 멀티모달 요청의 첫 그룹을 실제 재시험함. 원래와 동일한 6개 ID 집합을 반환했으나 일부 순서는 달랐음. 하나의 그룹 재시험이며 전체 검색 안정성의 증거로 일반화하지 않음.
- 기존 ChatGPT 인증, `gpt-6.1-sol` 요청, reasoning effort `high`, 독립 `codex exec --ephemeral`을 사용함. 실제 내부 모델 빌드는 확인하지 못함.
- 전송 범위: 공개 참고 후보의 본문·캡션·ID, 합성 방법론·캡션, 원본 기반 선택 지침 및 CLI의 통상 실행 문맥임. 사용자 비공개 논문·참고 이미지·생성 그림은 이번 모델 호출에 포함하지 않았음.
- 별도 유료 provider API·API 키 사용·이미지 생성은 없었으나 ChatGPT 계정의 Codex 사용량은 발생함. 25개 호출의 기록상 input_tokens 합계는 5,333,536이며 별도 host 확인 1회는 252,180임. token 기록은 모델 내부 사고나 원문 활용 정도의 증거가 아님.

## 4. 실제 데이터 전달과 선택 계약의 검증

- 5종 모두 네 그룹의 입력 ID가 고정 manifest와 일치함. 각 그룹 전문·캡션이 저장된 실제 Codex 프롬프트에 포함되고 prompt hash가 일치함.
- 각 예선 응답은 해당 그룹 안의 중복 없는 ID 6개이며, 최종 입력은 그 합집합인 24개임.
- 최종 10개가 24개 안에 포함되고 최종 record와 단계별 검색 기록이 일치함.
- 실제 반환한 최종 ID로 원본 Planner를 실행하여 요청 파일 생성까지 확인함. 5종 × 10개 = 50건 모두 본문·캡션·이미지 byte와 순서가 정확히 연결됨.
- Planner의 외부 모델 호출은 응답 대기 경계에서 취소함. 따라서 이번 Planner 확인은 **실제 선택 결과의 입력 연결 검사**이며 계획 설명 생성 품질 검증이 아님.
- 검사 결과는 `runs/grouped-retrieval-live-2026-11-03/verified-selections.json`에 보존됨.

## 5. 선택 관련성의 정성적 확인

- 확인 방법: 최종 선택 자료의 제목·캡션을 요청과 대조하고, 멀티모달 및 RAG의 선택 이미지 모음을 시각적으로 검토함. 일부 캡션은 확인 화면에서 발췌되므로 모든 원문을 독립적으로 재평가한 것으로 해석하지 않음.
- 결과: 요청에 따라 서로 다른 후보를 선택함. 최종 50건 중 고유 ID는 41개임. 이 수치는 선택 차이의 증거이며 품질 점수는 아님.

| 요청 | 관련성이 관찰된 사례 | 해석·한계 |
|---|---|---|
| 멀티모달 융합 | ref_88의 세 입력 encoder·정렬·융합, ref_140의 품질 지표·가중 집계, ref_129의 결측 view·정렬·융합임 | TriPath의 일부 핵심 구조와 대응됨. 입력 종류와 전체 예측 구조가 완전히 같은 예제는 아님 |
| 시계열 | ref_141의 EEG patch·시간 attention, ref_87의 시공간 예측 구조임 | 시간·채널 처리와 예측 구조를 참고할 수 있음. EEG 분석과 일반 다변량 예측은 다른 과제임 |
| 이미지 분할 | ref_35의 U-shaped 구조, ref_108의 segmentation encoder/decoder, ref_1의 microscopy segmentation임 | 주제 또는 encoder/decoder 표현이 대응됨. 일부는 복원·3D 생성 등 인접 과제임 |
| RAG | ref_123의 지식 구성→검색→생성, ref_176의 static indexing→dynamic retrieval임 | 오프라인 구축과 온라인 검색 표현에 직접 도움이 될 근거가 있음. 나머지 일부는 최적화·추천 등 주제 대응이 약하고 구조적 참고에 가까움 |
| 에이전트 | ref_51의 계획·실행 결과 feedback, ref_166의 Extractor/Solver/Checker, ref_26의 계획·실행 협업임 | 요구한 역할 분리·feedback 표현과 대응됨. 개별 도구·과제는 다름 |

- 원본 지침 자체가 동일 주제가 부족하면 같은 visual intent를 다음 우선순위로 허용함. 따라서 다른 연구 주제 선택만으로 오류라고 판정하지 않음.
- 동시에 위 사례만으로 최적의 10개 선택·전체 후보 대비 recall·원본보다 좋은 품질을 주장하지 않음.
- 미수행: 정답 ID 집합 구축, 독립 평가자/맹검, random·원본 backend 대비 정량 평가, 후보 순서 변경 및 전체 검색 반복, 선택 예제가 실제 그림 품질에 미치는 영향 측정임.

## 6. 회귀·형식 검사와 저장

- 전체 오프라인 unittest 23개 통과·skip 없음임. 외부 모델 응답과 이미지는 fixture를 사용한 시험임.
- 새 시험: 실제 그룹 전문→6개씩 선발→24개 전문→최종 10개→Planner 이미지 연결, ID 중복·범위 외·개수 부족 실패, 긴 target 사전 거절, dataset hash·그룹 변조 검출, 실제 generate CLI의 후속 원본 생성·검색 기록 저장임.
- 추가 host 검사: 실제 1회 응답·유효 ID 6개, 이전 실제 시험과 host prompt 동일성, 이미지/다중 턴 요청 거부, 중복 제출 시 모델 재호출 없이 기존 응답 보존을 확인함.
- skill-creator 형식 검사 통과, 영어·한국어 지침의 새 옵션·절차·제약 대응 확인, 영어 스킬/실행 코드에서 한국어 검토본 참조 없음 확인됨.
- 프로젝트 `.venv`에 기존 requirements를 설치하여 실제 SDK·Pillow·json-repair 등으로 검사함. 전역 설정은 변경하지 않았으며 `.venv/`는 Git ignore에 추가함.
- `retrieval.json`은 완료 이전에도 단계별 후보·선택 상태를 보존함. 최종 `result.json.retrieval_audit`에도 같은 검색 기록이 포함됨.
- host 요청별 `codex-host/`에 실제 prompt·응답·이벤트·모델 요청명·사용량을 보존함.

## 7. 근거 파일과 남은 범위

- 기존 거절 기록: `runs/retrieval-validation-2026-11-03/`임.
- 새 실제 시험: `runs/grouped-retrieval-live-2026-11-03/{summary.json,verified-selections.json}` 및 유형별 input·request·answer·이벤트·outcome임.
- 추가 실행용 명령 확인: 같은 폴더의 `host-command-smoke/{verification.json,response.json,codex-host/}`임.
- 오프라인 회귀: `runs/retrieval-group-preparation-2026-11-03/implementation-tests-final.log`임.
- 그룹 데이터: `data/derived/MTPaperBananaBench/retrieval-first200-800k/`임. 원본·준비된 기존 데이터는 변경하지 않았음.
- 이번 범위 밖: PBInteract 문맥 분리, 원본 재시도·이미지 실패 fallback, blob 내용 hash 재검증, 실제 21:9 출력, Critic 응답/마지막 반복 정책, 다른 단계의 실행 조건 기록 문제임. 이번 검색 변경으로 해결됐다고 주장하지 않음.
- 커밋·푸시·원격 저장소 생성·전역 스킬 설치·모델 다운로드·API 키 생성은 수행하지 않았음.
