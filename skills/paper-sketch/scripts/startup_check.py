"""모델 호출 전 비동기 초기화의 제한 시간 검사와 진단."""
import argparse
import json
import subprocess
import sys
import time

PROBE_MARKER = '--papersketch-asyncio-probe'
PROBE = '''import asyncio, faulthandler, sys
print("ASYNCIO_PROBE_STARTED", flush=True)
faulthandler.dump_traceback_later(float(sys.argv[1]))
asyncio.run(asyncio.sleep(0))
faulthandler.cancel_dump_traceback_later()
print("ASYNCIO_PROBE_OK", flush=True)
'''


def check_asyncio(timeout: float = 5) -> dict:
    """실행 환경과 같은 Python에서 초기화만 검사하고 실제 근거 반환."""
    started = time.monotonic()
    command = [sys.executable, '-I', '-B', '-u', '-c', PROBE,
               str(timeout / 2), PROBE_MARKER]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        stdout = (error.stdout or b'').decode('utf-8', errors='replace')
        stderr = (error.stderr or b'').decode('utf-8', errors='replace')
        if 'socketpair' in stderr and ('in accept' in stderr or 'in connect' in stderr):
            diagnosis = 'loopback_initialization_stalled'
            message = ('Windows asyncio internal socketpair initialization stalled. '
                       'Check local loopback/runtime permissions in this sandbox; '
                       'no reference retrieval or model inference has started.')
        elif 'ASYNCIO_PROBE_STARTED' in stdout:
            diagnosis = 'asyncio_initialization_timeout'
            message = 'Asyncio initialization timed out; inspect the captured stack. The cause is not confirmed.'
        else:
            diagnosis = 'python_startup_timeout'
            message = 'The probe did not report Python startup before the timeout; the cause is not confirmed.'
        status = 'failed'
        code = None
    except OSError as error:
        stdout, stderr = '', str(error)
        status, diagnosis, code = 'failed', 'probe_launch_failed', None
        message = 'The local Python probe could not start; check the interpreter and execution permissions.'
    else:
        stdout = result.stdout.decode('utf-8', errors='replace')
        stderr = result.stderr.decode('utf-8', errors='replace')
        code = result.returncode
        status = 'passed' if code == 0 and 'ASYNCIO_PROBE_OK' in stdout else 'failed'
        diagnosis = 'ready' if status == 'passed' else 'probe_failed'
        message = 'Asyncio initialization completed.' if status == 'passed' else 'The local asyncio probe failed; inspect stderr.'
    return {'status': status, 'diagnosis': diagnosis, 'message': message,
            'python': sys.executable, 'timeout_seconds': timeout,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'returncode': code, 'stdout': stdout, 'stderr': stderr,
            'model_calls': 0}


def require_asyncio(timeout: float = 5, *, stream=None) -> None:
    """즉시 진행 상태를 출력하고 초기화 실패 시 기존 흐름 진입 차단."""
    print('PAPER_SKETCH_STARTUP ' + json.dumps({'status': 'checking', 'timeout_seconds': timeout}), file=stream, flush=True)
    result = check_asyncio(timeout)
    print('PAPER_SKETCH_STARTUP ' + json.dumps(result, ensure_ascii=False), file=stream, flush=True)
    if result['status'] != 'passed':
        print('PaperSketch stopped before async execution: ' + result['message']
              + ' No automatic retry or permission escalation was performed.', file=sys.stderr, flush=True)
        raise SystemExit(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=5)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    require_asyncio(args.timeout)
