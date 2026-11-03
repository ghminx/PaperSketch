"""Diagram 앞 200개에서 기존 4그룹을 재현하는 오프라인 준비 명령."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from bridge import write_json
from reference_groups import GROUP_CHAR_BUDGET, PER_GROUP, candidate_text


def prepare_groups(dataset: Path, output: Path) -> dict:
    """원본 순서·전문을 보존하여 새 폴더에 검색 그룹 생성."""
    dataset, output = dataset.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f'Use a new groups directory: {output}')
    raw = (dataset / 'ref.json').read_bytes()
    active = json.loads(raw)[:200]
    if len(active) != 200 or len({row['id'] for row in active}) != 200:
        raise ValueError('Expected at least 200 references with distinct first-200 IDs')
    groups, rows, blocks = [], [], []
    chars = 0
    for index, row in enumerate(active, 1):
        block = candidate_text(index, row)
        if len(block) > GROUP_CHAR_BUDGET:
            raise ValueError(f'Reference cannot fit a group without truncation: {row["id"]}')
        if rows and chars + len(block) > GROUP_CHAR_BUDGET:
            groups.append((rows, ''.join(blocks)))
            rows, blocks, chars = [], [], 0
        rows.append(row)
        blocks.append(block)
        chars += len(block)
    groups.append((rows, ''.join(blocks)))
    if len(groups) != 4 or any(len(rows) < PER_GROUP for rows, _ in groups):
        raise ValueError('This dataset cannot reproduce the required four groups of at least six records')
    # 최종 후보 24개의 전문을 생략하지 않기 위한 예산 확인
    finalists = sum(sum(sorted((len(candidate_text(999, row)) for row in rows), reverse=True)[:PER_GROUP])
                    for rows, _ in groups)
    if finalists > GROUP_CHAR_BUDGET:
        raise ValueError('Twenty-four full finalists may exceed the candidate budget')
    manifest = {'source_ref': Path(os.path.relpath(dataset / 'ref.json', output)).as_posix(),
        'image_paths_relative_to': Path(os.path.relpath(dataset, output)).as_posix(),
        'source_ref_sha256': hashlib.sha256(raw).hexdigest(), 'records': 200, 'group_count': 4,
        'candidate_char_budget': GROUP_CHAR_BUDGET, 'policy': 'contiguous source order; full records',
        'per_group': PER_GROUP, 'finalists': 24, 'maximum_finalist_chars': finalists, 'groups': []}
    agent = Path(__file__).resolve().parents[1] / 'assets/interact/agents/retriever_agent.py'
    manifest['source_agent_sha256'] = hashlib.sha256(agent.read_bytes()).hexdigest()
    for index, (rows, text) in enumerate(groups, 1):
        manifest['groups'].append({'group': index, 'records': len(rows),
            'ids': [row['id'] for row in rows], 'json_file': f'group-{index:02d}.json',
            'text_file': f'group-{index:02d}.txt', 'candidate_chars': len(text),
            'text_sha256': hashlib.sha256(text.encode()).hexdigest()})
    if (dataset / 'ref.json').read_bytes() != raw:
        raise OSError('Reference data changed during group preparation')
    output.mkdir(parents=True)
    for entry, (rows, text) in zip(manifest['groups'], groups):
        write_json(output / entry['json_file'], rows)
        (output / entry['text_file']).write_text(text, encoding='utf-8', newline='')
    write_json(output / 'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare_groups(args.dataset_dir, args.output)
    print(json.dumps({'groups': manifest['group_count'], 'records': manifest['records'],
                      'group_sizes': [entry['records'] for entry in manifest['groups']]}))
