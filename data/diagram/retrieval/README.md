# 고정 참고 후보 그룹

- `data/diagram/ref.json`의 앞 200개를 원본 순서·내용 그대로 분할한 파생 자료임.
- 그룹당 후보 텍스트 상한 800,000자 기준이며, 선택 지침·사용자 입력을 포함한 완성 요청이 아님.
- 그룹별 후보 수: 53개·51개·58개·38개임.
- TXT는 ID·본문·캡션 블록, JSON은 원본 record 사본임. 이미지 상대 경로의 기준은 기존 `data/diagram/`임.
- 후속 사용자 승인으로 그룹당 6개 → 24개 비교 → 최종 10개 선발이 확정됨. 실행기의 auto에 `--reference-groups <이 폴더>`를 지정하여 사용함.
- 출처·hash·ID·문자 수·검증 정보는 `manifest.json`에 기록됨. 재생성은 skills/paper-sketch/scripts/prepare_reference_groups.py 사용이 가능함.

- manifest의 source_ref·image_paths_relative_to는 이 retrieval 폴더 기준 상대 경로임. 데이터·후보·hash는 유지하고 현재 경로 안내만 갱신함.
