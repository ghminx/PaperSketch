# Installation

## Requirements

- Python 3.11 이상 및 [uv](https://docs.astral.sh/uv/getting-started/installation/) 명령 필요함. 실행 환경은 설치기가 Python 3.11·uv.lock 기준으로 별도 구성함.
- 텍스트 판단에는 Codex CLI와 기존 ChatGPT Codex 로그인 필요함. Diagram 생성에는 내장 imagegen을 사용할 수 있는 Codex 환경 필요함.
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

- 실패 시 대상 폴더와 `installation.json`의 `failed` 상태가 보존됨. 미완료 `SKILL.md`는 `.pending`으로 남겨 스킬 자동 발견을 방지함.
- 원인을 해결한 뒤 새로운 `--dest`로 다시 설치하거나, 실패 폴더의 진단 자료를 확인한 후 해당 폴더만 제거하고 재설치하는 방식임.
- 업데이트도 자동 덮어쓰기 대신 기존 설치를 별도로 보관한 후 새로 설치하는 방식임. 결과 폴더는 별도로 보존해야 함.
- `.venv`는 설치 절대 경로에 의존하므로 설치 폴더 이동 시 환경 재구성이 필요함. 파일 hash 검사는 내부 일관성 확인이며 배포자의 전자서명 검증은 아님.
- `scripts/requirements.txt`만 설치하는 일반 스킬 복사 방식은 데이터·잠금 환경까지 준비하지 않으므로 본 설치기 사용이 권장됨.

## Standalone Smoke Test

- Windows에서 개발 폴더 밖에 코드·데이터·uv 환경을 실제 설치하여 검증함. macOS/Linux 실기 검증은 미수행임.
- 자식 실행기의 개발 저장소 파일 접근을 차단하고 다른 작업 폴더에서 Diagram 자동 검색 5회·선택 이미지 10개의 Planner 전달·결과 저장·PBInteract 무변경 판단을 확인함.
- Plot은 실제 참고 후보·이미지 연결과 Matplotlib 코드 렌더링을 확인함. 모델 텍스트·Diagram 이미지는 모의 응답이며 실제 모델 호출·생성 품질 시험은 아님.
- 재현 도구는 저장소의 `tests/standalone_smoke.py`임. 설치된 Python으로 실행하며 `--skill <설치 폴더> --work <새 작업 폴더> --forbid <개발 저장소>` 지정이 필요함. 결과는 작업 폴더의 `report.json`에 저장됨.
