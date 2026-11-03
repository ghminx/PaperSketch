# PaperSketch

**논문에 들어갈 그림을 만들고, 피드백을 반영해 다듬는 Codex 스킬입니다.**

방법론과 그림 캡션을 전달하면 관련 참고 예제를 골라 그림의 구성을 잡고, 학술 그림 스타일에 맞춰 이미지를 생성합니다. 이후에는 “이 모듈을 강조해 줘”, “연결선을 바꿔 줘”처럼 요청하며 결과를 수정할 수 있습니다.

[PaperBanana](https://github.com/dwzhu-pku/PaperBanana)의 에이전트와 프롬프트, 그림 생성 흐름을 바탕으로 만들었습니다. 텍스트 판단과 코드 작성은 Codex가 담당하며, 구조도는 내장 imagegen으로, 통계 그래프는 Python·Matplotlib으로 생성합니다.

## Workflow

![PaperSketch 생성 및 피드백 수정 워크플로우](docs/images/papersketch-framework.png)

### Diagram Generation

```text
방법론 · 캡션 · 원하는 비율
          ↓
참고 예제 선택
          ↓
그림 구성 설계 → 스타일 적용 → 이미지 생성
          ↓
그림 검토 → 필요한 부분 수정·재생성
          ↓
결과 저장
```

| 단계 | 하는 일 |
|---|---|
| **Retriever** | 참고 후보 200개를 네 그룹으로 나눠 각각 6개를 고르고, 모인 24개 중 최종 10개를 선택합니다. |
| **Planner** | 선택한 그림과 본문·캡션을 참고해 모듈, 연결 관계, 배치를 설계합니다. |
| **Stylist** | 그림 설명에 학술 스타일 가이드를 적용해 색상과 형태, 시각적 구성을 다듬습니다. |
| **Visualizer** | Planner와 Stylist의 설명으로 각각 이미지를 생성합니다. |
| **Critic** | 생성된 그림을 방법론·캡션과 비교하고, 필요한 경우 설명을 고쳐 다시 생성합니다. |

### Plot Generation

실제 수치 데이터와 원하는 그래프를 설명하면 관련 그래프 예제를 선택하고, 구성·스타일을 정리한 뒤 Python·Matplotlib 코드를 생성해 렌더링함. 생성된 그래프는 원본 데이터·요청과 비교하여 필요한 경우 설명과 코드를 수정함.

막대·선 그래프 등 통계 그래프의 이미지와 생성 코드를 함께 저장함. Plot의 대화 기반 반복 수정은 현재 지원하지 않음.

### Iterative Refinement

```text
저장된 그림 + 새 요청
          ↓
이전 요청과 그림 이력 확인
          ↓
최신 요구사항과 이전 요구사항 검토
          ↓
수정 필요 판단 → 설명 수정 → 새 그림 생성
          ↓
새 버전 저장
```

Diagram은 현재 그림을 새 요청뿐 아니라 이전 요구사항과도 비교하고, 수정이 필요하면 상세 설명을 고쳐 새 그림을 생성합니다. 수정할 필요가 없으면 현재 결과를 유지합니다.

그림과 설명, 피드백 이력을 함께 저장하므로 다음 요청에서 작업을 이어갈 수 있습니다. 이전 결과도 남겨 두어 다른 버전에서 다시 시작할 수 있습니다.

## Examples & Tips

무엇을 입력하면 되는지 궁금하다면 [입력 예제와 사용 팁](docs/examples-and-tips.md)을 참고하세요. 원본 데모의 방법론·캡션 예제와 PaperSketch에서 바로 활용할 수 있는 요청 양식을 정리했습니다.

## Quick Start

Python 환경과 패키지는 uv로 관리함. 저장소 루트에서 아래 명령으로 잠금 파일에 기록된 환경을 준비함.

Windows에서는 참고 이미지의 긴 파일명을 위해 짧은 경로에 클론하는 것을 권장함. Git의 긴 경로 처리는 아래처럼 저장소 단위로 설정할 수 있으며 전역 설정 변경은 필요하지 않음.

```shell
git clone -c core.longpaths=true https://github.com/ghminx/PaperSketch.git
cd PaperSketch
```

```shell
uv sync --locked
```

Codex에서 [PaperSketch 스킬](skills/paper-sketch/SKILL.md)을 사용해 방법론·캡션 또는 실제 수치 데이터·그래프 요구사항을 전달함. 텍스트 처리는 기존 ChatGPT Codex CLI 로그인, Diagram 이미지 생성은 내장 imagegen 사용이 필요함. 별도 Google API 키는 사용하지 않음.

Python 실행기는 모델 요청을 파일로 전달하고 응답을 기다리는 구조임. 아래 명령만 실행하여 모델을 자동 호출하는 방식은 아니며, 요청별 host 처리는 스킬 지침에 따라 Codex가 수행함.

```shell
# 구조도
uv run --locked python skills/paper-sketch/scripts/run.py generate --input input.json --dataset-dir data/diagram --reference-groups data/diagram/retrieval --output runs/diagram --retrieval auto

# 통계 그래프
uv run --locked python skills/paper-sketch/scripts/run.py generate --task plot --input input.json --dataset-dir data/plot --output runs/plot --retrieval auto
```

입력 JSON은 `content`와 `visual_intent`를 사용함. Diagram은 방법론·캡션, Plot은 실제 수치·표현 의도를 각각 전달함. 출력 폴더는 실행마다 새 경로를 지정함.

```json
{"content":{"A":10,"B":15,"C":12},"visual_intent":"값을 표시한 세로 막대그래프, y축은 0부터 시작, 제목 없음"}
```

## Reference Data

- `data/diagram/`: 구조도 참고 이미지·본문·캡션 298개 및 자동 검색용 고정 그룹임.
- `data/plot/`: 통계 그래프 참고 이미지·원시 데이터·표현 의도 240개임.
- `data/sources/`: 데이터 출처·라이선스·원본 메타데이터임. 자세한 구성은 [데이터 안내](data/README.md) 기준임.

참고 데이터와 그룹을 저장소에 포함함. 새 Diagram 데이터 사본의 검색 그룹은 아래 명령으로 준비하며 기존 출력 폴더를 덮어쓰지 않음.

```shell
uv run --locked python skills/paper-sketch/scripts/prepare_reference_groups.py --dataset-dir data/diagram --output path/to/new-retrieval
```

## Tests

```shell
uv run --locked python -m unittest discover -s tests -v
```

외부 모델 호출 없는 모의 응답과 로컬 Matplotlib 실행으로 흐름·데이터·저장·오류 처리를 검증함. 생성 품질 또는 원본 모델과의 성능 동등성을 보장하는 시험은 아님.

## Acknowledgements

[PaperBanana](https://github.com/dwzhu-pku/PaperBanana)의 그림 생성 에이전트와 스킬 구성을 참고했습니다.

포함된 원본 코드의 저작권 표시와 [Apache-2.0 라이선스](skills/paper-sketch/assets/interact/LICENSE)를 유지하고 있습니다.
