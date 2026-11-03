# PaperSketch Maintenance

- PaperBanana 계열의 원본 에이전트·프롬프트·처리 흐름을 유지하는 Codex 스킬임. 원본과의 기능·성능 동등성을 근거 없이 주장하지 않음.
- `skills/paper-sketch/`: 영어 실행 지침·Python 실행기·원본 코드 사본·라이선스 위치임. 출처·커밋·hash·연결 변경은 각 assets/SOURCE_MANIFEST.json 기준임.
- `data/diagram/`: 참고 298개 및 retrieval/의 앞 200개 고정 4그룹임. `data/plot/`: 참고 240개임. `data/sources/`의 출처·라이선스·원본 JSON 보존이 필요함.
- Diagram은 Codex·imagegen·PBInteract 수정을 지원함. Plot은 Codex 코드 생성·Matplotlib 실행·Critic 반복을 지원하며 PBInteract는 미지원임.
- 환경 준비는 `uv sync --locked`, 검증은 `uv run --locked python -m unittest discover -s tests -v` 사용이 원칙임. 의존성 변경 시 pyproject.toml·uv.lock·스킬의 scripts/requirements.txt를 함께 확인함.
- 실행은 `uv run --locked python skills/paper-sketch/scripts/run.py --help`에서 시작함. 파일 bridge의 모델 요청을 Codex host가 처리해야 함. 상세 지침은 SKILL.md 및 references/plot.md 기준임.
- 수정 전 입력·출력·호출 관계를 확인하고 최소 변경·관련 회귀 검증을 수행함. 원본 사본·데이터·프롬프트·수치·라이선스를 임의 변경하지 않음.
- 테스트는 외부 모델 없는 fixture·로컬 실행이 기본임. 모델 호출·외부 데이터 전송·유료 API·전역 설정·커밋·푸시는 사용자 승인 범위에서 수행함.
- 실패 기록과 생성 결과를 구분하고 반복 상한을 유지함. 저장된 코드·그림을 조용히 덮어쓰지 않음.
- 주석·docstring은 간결한 한국어 명사형, 공식 한국어 문서는 객관적 개조식 문체 사용이 원칙임.
