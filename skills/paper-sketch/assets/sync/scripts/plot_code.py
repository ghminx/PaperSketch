
"""확인된 Matplotlib collection clipping 순서 오류의 제한적 코드 보정."""
import time
import threading
import ast

def prepare_plot_code(raw: str) -> tuple[str, list[dict]]:
    """동일 collection의 연속 clip/add 호출만 재배치하고 보정 기록 반환."""
    from paperbanana_plot.utils.plot_execution import extract_plot_code
    code = extract_plot_code(raw)
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return (code, [])
    lines = code.splitlines(keepends=True)
    changes = []
    for node in ast.walk(tree):
        for _, body in ast.iter_fields(node):
            if not isinstance(body, list):
                continue
            for first, second in zip(body, body[1:]):
                if not (isinstance(first, ast.Expr) and isinstance(second, ast.Expr) and isinstance(first.value, ast.Call) and isinstance(second.value, ast.Call)):
                    continue
                clip, add = (first.value, second.value)
                if not (isinstance(clip.func, ast.Attribute) and clip.func.attr == 'set_clip_path' and isinstance(clip.func.value, ast.Name) and (len(clip.args) == 1) and isinstance(clip.args[0], ast.Name) and (not clip.keywords) and isinstance(add.func, ast.Attribute) and (add.func.attr == 'add_collection') and isinstance(add.func.value, ast.Name) and (len(add.args) == 1) and isinstance(add.args[0], ast.Name) and (clip.func.value.id == add.args[0].id) and (first.end_lineno < second.lineno)):
                    continue
                standalone = True
                for statement in (first, second):
                    prefix = lines[statement.lineno - 1].encode()[:statement.col_offset]
                    suffix = lines[statement.end_lineno - 1].encode()[statement.end_col_offset:].strip()
                    if prefix.strip() or (suffix and (not suffix.startswith(b'#'))):
                        standalone = False
                        break
                if not standalone:
                    continue
                changes.append((first, second, {'rule': 'clip_after_add_collection', 'source_line': first.lineno, 'collection': clip.func.value.id, 'clip': clip.args[0].id, 'axes': add.func.value.id}))
    for first, second, _ in sorted(changes, key=lambda item: item[0].lineno, reverse=True):
        start, middle = (first.lineno - 1, first.end_lineno)
        next_start, end = (second.lineno - 1, second.end_lineno)
        moved = lines[next_start:end]
        if moved and (not moved[-1].endswith('\n')):
            moved[-1] += '\n'
        lines[start:end] = moved + lines[middle:next_start] + lines[start:middle]
    return (''.join(lines).rstrip('\r\n'), [record for _, _, record in changes])
