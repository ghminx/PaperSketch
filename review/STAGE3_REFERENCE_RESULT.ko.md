# 이전 단계 점검 및 3단계 참고 데이터 연결

- 수행일: 2026-11-02임.
- 사용자 요청: 이전 구현을 계획과 대조·수정한 후 실제 MTP 참고 데이터를 연결하는 단계임.

## 이전 단계 점검

| 계획 항목 | 확인 결과 |
|---|---|
| Interact 원본 코드 최대한 유지 | 복사 파일 30개가 원본·manifest와 byte 동일함 |
| 모델 호출 경계만 교체 | agent 자체 변경 없이 provider 모듈 import 이전에 bridge 연결함 |
| 실제 내장 imagegen 왕복 | 2단계 생성 PNG·원본 JPEG 후처리·Critic 이미지 byte 일치 기록을 유지함 |
| 원본 PBInteract 대화 순서 | fixture에서 context·Critic·gating·rewrite 및 설명 공개 시점 검증 통과함 |
| 영어 스킬·한국어 검토본 분리 | 실행 코드·영어 지침에서 한국어 검토본을 참조하지 않음 |
| 검증 한계 명시 | 파일 기반 host 처리이며 독립 context·원본 sampling·full pipeline 동등성은 보장하지 않음 |

- 기존 단계의 기능상 이탈은 발견되지 않았음. 기존 6개 회귀 테스트 통과 후 바로 3단계로 진행함.
- 원본 processor 전체·사용자 수정이 아직 연결되지 않은 것은 계획상 후속 범위이며 이번에 완료로 주장하지 않음.
- 이번 공통 helper 수정은 준비된 ref list JSON도 기록할 수 있도록 `write_json`의 타입 표기를 `dict | list`로 확장한 것임. 기존 직렬화 동작은 유지됨.

## 구현 내용

- [준비기](../skills/paper-sketch/scripts/prepare_references.py): 다운로드 원본을 읽어 별도 실행용 ref 사본·이미지·manifest를 생성함. 원본에 쓰지 않음.
- 원본 root: `data/MTPaperBananaBench/`임.
- 실행용 root: `data/prepared/MTPaperBananaBench/`임. test split은 이 참고용 사본에 포함하지 않음.
- 원본 `ref.json` SHA-256: `d978569bbd46c1d312cde669475b87ace868d80bfb7ffb0484464dbc6b8f5d6a`임.
- 298개 record 순서·필드·본문·캡션을 유지함. 이미지 298개를 판독 검사하고 복사 후 hash 일치를 확인함.
- `ref_309` 경로의 U+200C 1개를 사본 JSON에서만 제거함. 보정 전후 경로·이유·원본 이미지 hash를 manifest에 기록함.
- 해당 실제 파일은 PB 동일 ID의 본문·캡션과 일치하며 이미지 SHA-256도 `f1fab239c4cdec8708e90451bd3632ea57a1ca8bfbd9fe489e182a1895e2af74`로 동일함. 그림의 의미를 추측하여 연결한 것이 아님.
- `ref_260`, `ref_305` 빈 본문은 제거·보충하지 않고 그대로 보존함. 이 두 record는 앞 200개 auto pool에는 포함되지 않음.
- [연결 실행기](../skills/paper-sketch/scripts/reference_probe.py): 입력 content·visual_intent → 원본 Retriever → 선택 ID 검증 → 원본 Planner → result 저장 순서임. 재구현한 Retriever나 Planner가 아님.
- runner 경계에서 선택 ID 10개의 개수·중복·active pool 소속을 검증함. 이는 원본의 잘못된 ID 조용한 생략을 명시적 오류로 바꾼 변경이며 유효 응답 동작은 유지됨.

## 실제 데이터·host 검증

| 검증 | 결과 |
|---|---|
| 실제 ref 298개 이미지 연결 | 298개 통과함. 원본 ref JSON은 변경되지 않음 |
| 원본 auto 요청 | 앞 200개로 구성되며 201번째 record가 포함되지 않음을 검사함 |
| auto 응답→Planner | fixture ID 10개 파싱 후 해당 실제 이미지 10개의 byte 일치를 검사함 |
| 실제 random→Planner | 원본 random mode가 선택한 실제 그림 10개를 이 채팅에서 전부 열어 확인함. Codex가 상세 설명을 제출한 후 Python 정상 종료됨 |
| Planner 예제 입력 보존 | 선택 ID 순서대로 전체 본문·캡션이 입력에 들어가고 이미지 hash 10개가 원본과 일치함 |
| 전체 회귀 테스트 | 10개 통과함. 기존 6개와 데이터 보존·오류·실제 입력 연결 4개임 |

- 실제 host 실행 자료: [선택·hash 기록](../runs/stage3-reference-live/retrieval.json), [검증 기록](../runs/stage3-reference-live/verification.json), [Planner 결과](../runs/stage3-reference-live/result.json)임.
- live 선택 ID: `ref_142`, `ref_43`, `ref_91`, `ref_127`, `ref_130`, `ref_208`, `ref_11`, `ref_194`, `ref_217`, `ref_65`임.
- 실제 host의 예제 본문 판독은 발췌와 그림 전체 확인으로 수행함. 원본 요청 파일에는 예제 전문이 유지됨. host가 모든 전문을 독립 문맥에서 일괄 처리했다는 주장이 아님.
- 이번 단계에서 이미지 생성 도구를 추가 호출하지 않았음. 그림 생성·평가 성능의 결과가 아님.

## auto 검색 관련 남은 한계

- 원본 앞 200개 본문·캡션의 합계는 2,967,946자임. 원본 프롬프트는 이를 한 요청으로 구성함.
- 임의 요약·후보 수 축소·분할 검색을 추가하지 않았음. host에서 전문 전체를 처리한 실제 auto 관련성 선택은 아직 검증되지 않음.
- 따라서 실제 데이터 연결과 random 모드 왕복은 완료되었으나, 원본 auto 검색 성능·긴 입력 처리까지 검증된 것으로 표현하면 안 됨.
- 다음 최초 그림 생성 단계에서 auto의 긴 입력 처리 방식을 먼저 결정·검증할 필요가 있음. random을 auto처럼 보고하거나 참고 ID를 임의로 만들어 진행하지 않음.
