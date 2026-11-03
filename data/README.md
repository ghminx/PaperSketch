# Reference Data

```text
data/
├── diagram/             # 구조도 참고 자료 298개
│   ├── ref.json         # 본문·캡션·이미지 상대 경로
│   ├── images/          # 참고 이미지 298개
│   ├── reference_manifest.json
│   └── retrieval/       # 자동 검색용 4그룹
├── plot/                # 그래프 참고 자료 240개
│   ├── ref.json
│   └── images/          # 참고 이미지 240개
├── sources/             # 원본 JSON·출처·라이선스·다운로드 기록
└── README.md
```

- 현재 diagram 실행 인자: `--dataset-dir <project>/data/diagram --reference-groups <project>/data/diagram/retrieval`임.
- 자동 검색은 diagram의 원본 순서 앞 200개를 사용하며 4그룹에서 각각 6개 → 24개 중 10개 선발 방식임.
- 새 그룹 준비 명령은 `python skills/paper-sketch/scripts/prepare_reference_groups.py --dataset-dir <새-diagram-root> --output <새-diagram-root>/retrieval`임. 오프라인으로 기존 후보·전문 hash를 재현하며 기존 출력 폴더는 거부함.
- Plot은 `--task plot --dataset-dir <project>/data/plot`으로 원본 PaperBanana의 전체 참고 검색·설계·스타일·Matplotlib 코드 생성/실행·Critic 반복에 연결됨. Plot PBInteract 수정은 미연결 상태임.
- sources의 mt 접두 파일은 MTPaperBananaBench, paperbanana 접두 파일은 PaperBananaBench 출처임.
- `sources/mt-ref.original.json`은 원본 대조 시험에서 사용함. 실행용 diagram/ref.json에는 기존 ref_309 파일명 U+200C 보정만 적용된 상태임.
- 이미지·본문·캡션·그룹 후보 내용을 보존함. 실행용 원본 코드 사본과 출처 hash는 skills/paper-sketch/assets/에 포함됨.
- reference_manifest.json 및 sources/download_manifest.json의 과거 절대 경로는 최초 다운로드·준비 이력임. 현재 이미지 경로는 ref.json의 상대 경로로 해석함.
- 참고 데이터·그룹·출처 자료를 저장소에 포함함. 출처와 이용 조건은 sources/의 dataset 문서·라이선스 기준임.
