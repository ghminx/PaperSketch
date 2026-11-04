
"""전용 작업 프로세스에서 원본 Matplotlib 실행 함수 호출."""
import time
import threading
import argparse
import base64
import json
from pathlib import Path
import sys

def main():
    """원본의 JPEG 반환값을 작업 폴더에 저장."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    job = args.job.resolve()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets'))
    from paperbanana_plot.utils.plot_execution import execute_plot_code_worker
    request = json.loads((job / 'request.json').read_text(encoding='utf-8'))
    raw = (job / 'code.py').read_text(encoding='utf-8')
    encoded = execute_plot_code_worker(raw, request['dpi'])
    if encoded:
        (job / 'figure.jpg').write_bytes(base64.b64decode(encoded, validate=True))
    import matplotlib
    import numpy
    (job / 'worker.json').write_text(json.dumps({'image_created': bool(encoded), 'matplotlib': matplotlib.__version__, 'numpy': numpy.__version__, 'backend': matplotlib.get_backend(), 'dpi': request['dpi']}, indent=2), encoding='utf-8')
if __name__ == '__main__':
    main()
