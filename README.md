# PaperSketch

**논문에 들어갈 그림을 만들고, 피드백을 반영해 다듬는 Codex 스킬입니다.**

방법론과 그림 캡션을 전달하면 관련 참고 예제를 골라 그림의 구성을 잡고, 학술 그림 스타일에 맞춰 이미지를 생성합니다. 이후에는 “이 모듈을 강조해 줘”, “연결선을 바꿔 줘”처럼 요청하며 결과를 수정할 수 있습니다.

[PaperBanana](https://github.com/dwzhu-pku/PaperBanana)와 [PaperBanana-Interact](https://github.com/shirley-wu/PaperBanana-Interact)의 에이전트, 프롬프트, 생성·수정 흐름을 활용했습니다. 텍스트 판단은 Codex가, 이미지 생성은 내장 imagegen이 담당합니다.

## 워크플로우

![PaperSketch 생성 및 피드백 수정 워크플로우](docs/images/papersketch-framework.png)

### 그림 생성

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

### 피드백 반영

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

PaperBanana-Interact의 **PBInteract**가 이 과정을 담당합니다. 현재 그림을 새 요청뿐 아니라 이전 요구사항과도 비교하고, 수정이 필요하면 상세 설명을 고쳐 새 그림을 생성합니다. 수정할 필요가 없으면 현재 결과를 유지합니다.

그림과 설명, 피드백 이력을 함께 저장하므로 다음 요청에서 작업을 이어갈 수 있습니다. 이전 결과도 남겨 두어 다른 버전에서 다시 시작할 수 있습니다.

## 기반 프로젝트

- [PaperBanana-Interact](https://github.com/shirley-wu/PaperBanana-Interact): 최초 생성부터 사용자 피드백에 따른 반복 수정까지의 주요 흐름을 활용했습니다.
- [PaperBanana](https://github.com/dwzhu-pku/PaperBanana): 그림 생성 에이전트와 스킬 구성을 참고했습니다.
- [PaperVizAgent](https://github.com/google-research/papervizagent): 공통 에이전트 구조와 초기 구현을 참고했습니다.

포함된 원본 코드의 저작권 표시와 [Apache-2.0 라이선스](skills/paper-sketch/assets/interact/LICENSE)를 유지하고 있습니다.
