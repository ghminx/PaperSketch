# Examples & Tips

PaperSketch는 **무엇을 그리는지 설명하는 방법론**과 **그림의 범위를 정하는 캡션**을 함께 입력받습니다. 아래에는 원본 프로젝트에 들어 있는 예제를 한국어로 정리하고, 실제 요청에 활용할 수 있는 양식을 덧붙였습니다.

원본 예제는 입력 형식을 이해하기 위한 자료입니다. 특정 문구를 사용하면 더 좋은 그림이 나온다고 비교 실험한 결과는 아닙니다.

## Tips from the Original Project

원본 README에서 안내하는 사용법은 다음과 같습니다.

- **방법론 본문과 그림 캡션을 함께 입력합니다.** 본문은 Markdown 형식을 권장합니다.
- **참고 예제 검색을 활성화합니다.** 원본은 검색된 예제의 그림 스타일을 활용하도록 안내합니다. PaperSketch의 자동 검색도 실제 참고 데이터를 사용합니다.
- **첫 그림을 본 뒤 피드백으로 다듬습니다.** 원본의 수정 흐름은 새 요구사항과 이전 요구사항을 함께 검토하도록 구성돼 있습니다.

방법론·캡션·참고 검색에 관한 안내는 [PaperBanana README의 Usage Tips 및 데모 사용법](https://github.com/dwzhu-pku/PaperBanana/blob/f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3/README.md#usage-tips), 반복 수정 흐름은 [수정 기능 설명](https://github.com/shirley-wu/PaperBanana-Interact/blob/ed08ef7e427ce147194af91d8ae6326a6cbc9cbd/README.md#architecture)에서 확인할 수 있습니다. 원본의 API 설정과 CLI 옵션은 PaperSketch의 실행 방식과 다릅니다.

## Example 1: Transformer Architecture

**원본 스킬에 포함된 간단한 아키텍처 예제입니다.** 구성 요소와 연결 관계를 짧게 설명하고, 캡션으로 전체 구조를 그리도록 요청합니다.

### Methodology

```text
Transformer 기반 encoder-decoder 아키텍처를 제안한다.
Encoder는 잔차 연결이 있는 self-attention 계층 12개로 구성된다.
Decoder는 encoder 출력에 cross-attention을 적용하고,
목표 시퀀스를 자기회귀적으로 생성한다.
```

### Caption

```text
제안한 Transformer 아키텍처의 전체 구조.
```

출처: [PaperBanana skill/SKILL.md의 Diagram 예제](https://github.com/dwzhu-pku/PaperBanana/blob/f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3/skill/SKILL.md#diagram). 위 본문과 캡션은 원문을 한국어로 옮긴 것입니다.

## Example 2: Short Framework Overview

**데모의 Load Example 버튼에 연결된 짧은 입력입니다.** 각 에이전트의 역할과 전체 순서를 한 문단으로 설명합니다.

### Methodology

```text
PaperBanana는 참고 예제를 활용해 학술 그림을 자동으로 생성하는 프레임워크다.
Retriever가 고정된 참고 자료에서 관련 예제를 선택한다.
Planner는 원문과 표현 의도를 바탕으로 상세한 그림 설명을 작성한다.
선택적으로 Stylist가 표현을 다듬고, Visualizer가 그림을 생성한다.
마지막으로 Critic이 그림을 원문과 비교하고 수정 사항을 제안한다.
Visualizer와 Critic은 이 과정을 반복하며 그림을 개선한다.
```

### Caption

```text
PaperBanana의 전체 흐름. 관련 예제를 검색하고 그림 설명을 설계·보완한 뒤,
이미지를 생성하고 Visualizer–Critic 반복으로 결과를 개선한다.
```

출처: [데모 app.py의 EXAMPLE_METHOD와 EXAMPLE_CAPTION](https://github.com/shirley-wu/PaperBanana-Interact/blob/ed08ef7e427ce147194af91d8ae6326a6cbc9cbd/app.py#L99). 위 내용은 한국어로 요약한 것이며, 원문의 품질에 대한 홍보 표현은 제외했습니다.

## Example 3: Detailed Framework Description

**PaperBanana의 Streamlit 데모에는 각 에이전트의 입출력을 소제목과 수식으로 풀어 쓴 긴 예제가 있습니다.** 아래는 그림 생성 부분을 중심으로 정리한 한국어 요약입니다. 원문의 통계 그래프 확장 설명은 여기서 생략했습니다.

### Methodology

```markdown
## Methodology: The PaperBanana Framework

PaperBanana는 원문과 그림의 표현 의도를 입력받아,
다섯 에이전트가 협력해 학술 그림을 생성하는 프레임워크다.

### Retriever
고정 참고 자료에서 연구 주제와 그림 유형이 비슷한 예제를 선택한다.
검색에는 예제의 본문과 캡션을 사용하며, 그림의 구조적 유사성을 우선한다.

### Planner
원문, 표현 의도, 선택한 예제의 본문·캡션·그림을 입력받아
목표 그림의 상세한 설명을 작성한다.

### Stylist
색상, 도형, 화살표, 배치, 글꼴 등을 다루는 스타일 가이드로
Planner의 설명을 다듬는다.

### Visualizer
상세 설명을 이미지 생성 모델에 전달해 그림을 만든다.
첫 그림에는 Stylist가 보완한 설명을 사용한다.

### Critic
생성된 그림을 원문과 캡션에 비교해 사실관계와 시각적 문제를 검토한다.
수정한 설명을 Visualizer에 전달해 그림을 다시 생성한다.
```

### Caption

```text
PaperBanana 프레임워크의 개요. 먼저 참고 예제를 검색하고,
스타일이 반영된 그림 설명을 작성한다.
이후 Visualizer와 Critic이 이미지 생성과 검토를 반복한다.
```

출처: [PaperBanana demo.py의 example_method와 example_caption](https://github.com/dwzhu-pku/PaperBanana/blob/f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3/demo.py#L680).

긴 방법론에는 이처럼 소제목을 붙여 역할과 처리 순서를 나눠 적을 수 있습니다. 원본 예제는 상세한 설명도 입력으로 받을 수 있음을 보여주며, 짧은 입력보다 항상 결과가 좋다는 의미는 아닙니다.

## A Template for PaperSketch

아래는 **앞의 원본 예제를 바탕으로 작성한 PaperSketch용 요청 양식**입니다. 원본에 그대로 실려 있는 예제는 아닙니다. 대괄호 부분을 자신의 방법론에 맞게 바꿔 사용할 수 있습니다.

```text
다음 방법론을 논문용 모델 아키텍처 그림으로 만들어 줘.

[방법론]
- 입력: ...
- 주요 모듈과 역할: ...
- 모듈 사이의 연결과 처리 순서: ...
- 최종 출력: ...
- 학습에만 사용하는 경로가 있다면: ...

[캡션]
이 그림은 ...의 전체 구조를 보여준다.
특히 ...의 관계를 명확하게 표현한다.

[표현 조건 — 필요한 경우 추가]
- 왼쪽에서 오른쪽으로 배치해 줘.
- 모듈 이름은 ...로 표기해 줘.
- 학습 전용 연결은 점선으로 표시해 줘.
- 설명에 없는 모듈이나 연결은 추가하지 마.
```

방법론에는 실제 구성과 데이터 흐름을, 캡션에는 그림이 전달해야 할 내용을 적으면 됩니다. 색상이나 배치처럼 꼭 필요한 조건이 있다면 함께 전달할 수 있습니다. 위 조건들은 예시이므로 모든 그림에 적용할 필요는 없습니다.

## Feedback Examples

아래는 **PaperSketch에서 활용할 수 있도록 새로 작성한 수정 요청 예제**입니다. 원본 데모의 문구를 인용한 것은 아닙니다.

| 바꾸고 싶은 부분 | 요청 예시 |
|---|---|
| 연결 관계 | “Tabular embedding에서 Cross-Attention으로 가는 선을 지워 줘. Tabular는 결합 단계에만 연결돼야 해.” |
| 모듈 강조 | “Fusion Module을 강조해 줘. 모듈 이름과 연결 관계는 유지해 줘.” |
| 가독성 | “모듈 이름을 더 크게 하고, 화살표가 글자를 가리지 않게 배치해 줘.” |
| 학습 경로 구분 | “Loss로 향하는 학습 전용 연결만 점선으로 바꿔 줘.” |
| 이전 수정 유지 | “앞에서 바꾼 Encoder 색상은 유지하고, 이번에는 출력 부분의 간격만 넓혀 줘.” |

어느 부분을 어떻게 바꿀지 구체적으로 적으면 수정 결과를 비교하기 쉽습니다. 유지해야 할 부분도 함께 적을 수 있습니다. 다만 피드백을 전달했다고 모든 요구가 충족됐다고 볼 수는 없으므로, 새 그림에서 반영 여부를 확인하는 것이 좋습니다.
