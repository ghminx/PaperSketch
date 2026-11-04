# Installation

## Requirements

- Python 3.11 이상 및 [uv](https://docs.astral.sh/uv/getting-started/installation/) 명령 필요함. 실행 환경은 설치기가 Python 3.11·uv.lock 기준으로 별도 구성함.
- 텍스트 판단에는 Codex CLI와 기존 ChatGPT Codex 로그인 필요함. Diagram 생성에는 내장 imagegen을 사용할 수 있는 Codex 환경 필요함.
- 생성·수정에 필요한 입력·공개 참고 자료·관련 그림 이력은 Codex 추론 및 내장 imagegen 처리 대상임. 최초 모델 사용 전 처리 범위를 한 번 확인하며, 이미 해당 범위의 명시적 사용자 승인이 있으면 재확인하지 않음. 같은 범위의 후속 그림·검토·수정에는 반복 질문하지 않음. 사용자 제한과 실제 승인 검토 결과의 준수가 필요함.
- 비공개 저장소에는 Git 읽기 권한 필요함. 기존 Git 인증 사용이 가능하며 인증 정보의 문서·프롬프트 기재는 불필요함.
- 저장소 다운로드와 uv 패키지 설치에는 네트워크 사용이 발생함. 설치 중 모델 호출·그림 생성·사용자 연구 데이터 전송은 없음.

## Install

Windows의 긴 참고 이미지 파일명을 고려하여 짧은 임시 경로 사용을 권장함. 아래 `<checkout>`은 새 다운로드 폴더를 의미함.

```shell
git clone -c core.longpaths=true https://github.com/ghminx/PaperSketch.git <checkout>
python <checkout>/scripts/install.py
python <checkout>/scripts/install.py --apply
```

- 첫 명령은 저장소 다운로드, 두 번째는 설치 위치·용량·복사 범위 확인, 세 번째는 실제 설치임.
- 기본 설치 위치는 `~/.agents/skills/paper-sketch/`임. `~`는 현재 사용자 홈 디렉터리임.
- 기존 설치 폴더는 덮어쓰지 않음. 다른 경로 시험에는 `--dest <새 절대 경로>` 사용이 가능함.
- uv 자체가 없으면 설치를 중단함. 위 공식 안내에 따른 uv 준비 후 재실행이 필요함.
- uv는 `--locked --no-dev --python 3.11`로 설치 위치 안에 `.venv`를 새로 구성함. Python 3.11이 없으면 uv의 Python 다운로드가 발생할 수 있음.
- 완료 후 Codex 재시작 또는 새 대화에서 `$paper-sketch` 인식 확인이 필요함. 자동 인식 여부는 실제 앱에서 별도 확인 대상임.

## Installed Layout

```text
~/.agents/skills/paper-sketch/
├── SKILL.md
├── scripts/
├── assets/                 # 원본 에이전트·프롬프트·라이선스
├── references/
├── data/                   # Diagram 298개·Plot 240개·검색 그룹·출처
├── pyproject.toml
├── uv.lock
├── .python-version
├── .venv/
└── installation.json       # 복사 파일별 hash·설치 상태
```

저장소 전체를 넣는 방식이 아님. `.git`, 개발 문서, tests, 개발용 `.venv`, 실험 결과는 복사하지 않음. 실행기·데이터·설정은 설치 폴더 안에서 연결되므로 설치 완료 후 다운로드용 `<checkout>` 폴더 없이도 실행이 가능함. 용량은 참고 데이터 약 166MB에 Python 환경 용량이 추가되는 구조임.

스킬 설치 폴더와 결과 저장 폴더는 별개임. 결과는 사용자 지정 위치를 우선하며, 미지정 시 현재 대화의 실제 작업 폴더 아래 `outputs/papersketch/<새 작업>/` 사용이 원칙임.

## Verify

기본 실행기는 순차 동기 방식임. `asyncio` 초기화·로컬 socketpair·비동기 사전 검사를 사용하지 않음. 원본 사본은 출처 및 회귀 비교용으로 보존하며, `assets/sync/`의 실행 사본을 설치함. 해당 사본과 원본의 hash 연결도 설치 검증 대상임.

Windows PowerShell 예시임. 별도 가상환경 활성화는 불필요함.

```powershell
$skillPath = Join-Path $env:USERPROFILE '.agents/skills/paper-sketch'
& "$skillPath/.venv/Scripts/python.exe" -B "$skillPath/scripts/verify_install.py"
& "$skillPath/.venv/Scripts/python.exe" -B "$skillPath/scripts/run.py" --help
```

macOS/Linux에서는 설치 폴더의 `.venv/bin/python` 사용이 필요함.

- 검사 범위: 복사 파일 hash, 원본 코드 manifest, 참고 이미지 538개, Diagram 고정 4그룹, 설치된 에이전트 import 경로 및 전용 환경 확인임.
- Codex CLI 위치는 확인 가능하나 로그인·실제 추론·imagegen 사용 가능 여부·생성 품질은 검사하지 않음. 확인되지 않은 조건은 `unverified`로 보고됨.
- Python 실행기는 요청 파일을 쓰고 기다리는 구조임. Codex가 SKILL.md에 따라 요청별 응답을 처리해야 하며, `run.py` 단독 실행은 전체 자동 생성 명령이 아님.

## Recovery & Updates

### Execution Approvals

- Codex 텍스트 host는 사용자 출력 폴더 외에 자체 상태 DB·임시 파일·app-server 접근과 서비스 연결 권한이 필요함. 로컬 실행기와 `codex login status`의 성공만으로 실제 `codex exec` 시작 성공을 보장하지 않음.
- 치명적 접근 거부는 `host_permission_denied`, `retryable=false`, 발생 단계로 기록함. DB 열기 실패 일반 메시지나 비치명적 경고만으로 권한 오류로 단정하지 않음.
- 해당 요청은 재제출하지 않으며 동일 권한에서 새 그림 실행을 반복하지 않음. 구체적인 host 명령에 필요한 실행 권한을 앱의 승인 절차로 해결한 뒤 새 실행을 시작해야 함. 같은 연구 처리 범위에 대한 동의 재질문과는 별개임. 전역 설정·인증 정보는 자동 변경하지 않음.

- 실제 ACT 생성 시험에서 거부된 명령은 설치된 Python의 `scripts/run.py generate ... --retrieval auto --critic-rounds 3 --timeout 1200` 실행이었음. `respond_text.py`나 imagegen 호출 단계의 거부는 아니었음.
- 자동 검토 결과는 `risk_level=high`, `user_authorization=medium`, `outcome=deny`였음. 사유는 비공개일 수 있는 ACT 연구 입력의 외부 모델 전송과 목적지에 대한 명시적 승인 부족이었음.
- `test_local_launch.py`는 합성 입력으로 Diagram auto 시작 경로를 검사함. 동기 실행의 설치 후 검증은 `tests/sync_smoke.py`에서 소켓 생성 자체를 금지하여 수행함.
- SKILL.md에 최초 처리 범위 확인과 동일 범위의 승인 재사용, 로컬 실행기와 실제 Codex·imagegen 처리 경계, 실제 승인 거부 준수 지침을 명시함. 승인 우회나 승인 결과 보장은 포함하지 않음.
- 실제 승인 검토의 재통과·Codex 추론·그림 생성은 이번 수정 시험에서 검증하지 않음. 기존 ACT 거부 명령은 재실행하지 않음.

처리 범위는 사용자가 생성·수정을 요청하며 제공한 비공개 포함 연구 입력·그림, 필요한 공개 참고 자료 및 관련 이력과 기존 ChatGPT 인증의 Codex·내장 imagegen을 기준으로 확인함. Plot 코드는 로컬 실행 대상임. 승인 내용은 대화에서 간결하게 확인하며 설치 기록이나 전역 동의 플래그를 승인 근거로 사용하지 않음.

| 상황 | 지침상 처리 |
|---|---|
| 최초 모델 작업·기존 승인 없음 | 한 번 질문하고 사용자 답변 대기 |
| 기존 대화에 같은 범위의 명시적 승인 있음 | 추가 질문 없이 진행 |
| 같은 범위의 새 방법론·그림·피드백·검토 반복 | 추가 질문 없이 진행 |
| 다른 서비스·계정·무관한 로컬 파일로 범위 확대 | 확대되는 부분만 확인 |
| 거절·승인 철회 | 해당 모델 처리 중단 |
| 새 채팅·적용 가능한 승인 근거 없음 | 새 채팅에서 한 번 확인 |
| 앱의 실제 승인 거부 | 재시도·우회 없이 구체적 사유 보고 |

위 표는 지침 검토 기준임. 형식 검사와 오프라인 테스트만으로 실제 에이전트의 질문 횟수나 앱 승인 결과를 입증하지 않음.

### Reinstallation

- 실패 시 대상 폴더와 `installation.json`의 `failed` 상태가 보존됨. 미완료 `SKILL.md`는 `.pending`으로 남겨 스킬 자동 발견을 방지함.
- 원인을 해결한 뒤 새로운 `--dest`로 다시 설치하거나, 실패 폴더의 진단 자료를 확인한 후 해당 폴더만 제거하고 재설치하는 방식임.
- 업데이트도 자동 덮어쓰기 대신 기존 설치를 별도로 보관한 후 새로 설치하는 방식임. 결과 폴더는 별도로 보존해야 함.
- `.venv`는 설치 절대 경로에 의존하므로 설치 폴더 이동 시 환경 재구성이 필요함. 파일 hash 검사는 내부 일관성 확인이며 배포자의 전자서명 검증은 아님.
- `scripts/requirements.txt`만 설치하는 일반 스킬 복사 방식은 데이터·잠금 환경까지 준비하지 않으므로 본 설치기 사용이 권장됨.

## Standalone Smoke Test

- Windows에서 개발 폴더 밖에 코드·데이터·uv 환경을 실제 설치하여 검증함. macOS/Linux 실기 검증은 미수행임.
- 기존 독립 설치 시험은 개발 폴더 접근을 차단하여 수행함. 동기 실행은 별도 `tests/sync_smoke.py`에서 소켓 생성 자체를 차단한 CLI로 검증함.
- Plot은 실제 참고 후보·이미지 연결과 Matplotlib 코드 렌더링을 확인함. 모델 텍스트·Diagram 이미지는 모의 응답이며 실제 모델 호출·생성 품질 시험은 아님.
- 재현 도구는 저장소의 `tests/standalone_smoke.py`임. 설치된 Python으로 실행하며 `--skill <설치 폴더> --work <새 작업 폴더> --forbid <개발 저장소>` 지정이 필요함. 결과는 작업 폴더의 `report.json`에 저장됨.

## Synchronous Runtime Maintenance

- `assets/interact/`, `assets/paperbanana_plot/`의 원본 사본과 프롬프트 보존이 원칙임.
- 동기 실행 사본은 개발 저장소의 `python scripts/build_sync_runtime.py`로 재생성함. 실행용 함수는 실제 동기 함수이며 coroutine을 별도 해석하는 방식은 아님.
- `assets/sync/SYNC_MANIFEST.json`에 변환 전후 hash가 기록됨. 원본 연결 코드 수정 후 사본을 재생성하지 않으면 검증에서 실패함.
- `tests/sync_smoke.py --skill <설치 폴더> --work <새 작업 폴더>`는 설치된 Python으로 실행함. 모델·이미지 응답은 모의 값이며 실제 데이터, Matplotlib, 상태 저장, 조회·선택·피드백 유지·수정·실패 복구는 실제 코드로 검증함.
- 기본 샌드박스에서 socket 생성이 금지된 상태의 동작 확인이 필요함. 동기화만으로 모델 서비스 네트워크 권한이나 생성 품질이 보장되는 것은 아님.
- 전체 unittest에는 원본 async 사본을 직접 호출하는 비교 시험이 포함됨. 해당 비교 시험에는 초기화 가능한 환경이 필요하며, 기본 샌드박스의 실제 실행 검증은 동기 smoke 도구로 구분하여 수행함.
