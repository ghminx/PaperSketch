
"""픽셀이나 캔버스 변경 없이 요청·실제 비율 비교."""
import time
import threading
from fractions import Fraction
RATIO_RELATIVE_TOLERANCE = 0.005

def canvas_instruction(ratio: str) -> str:
    """설계·검토·렌더링에 동일한 캔버스 우선 조건 전달."""
    assess_ratio(1, 1, ratio)
    return f'PaperSketch canvas constraint: the requested full-image aspect ratio is {ratio} (width:height). This explicit setting takes precedence over conflicting canvas ratios or full-canvas dimensions in reference examples, earlier descriptions, or earlier critique. Write and revise rendering descriptions for a {ratio} canvas; do not invent another canvas ratio. Preserve the required modules and connections. Review against this requested ratio, not an incompatible ratio invented by an earlier description. Reference selection must still follow its original relevance criteria. Generate on the requested canvas directly; do not crop, stretch or pad a finished image. Keep the response format required by the current agent step.'

def assess_ratio(width: int, height: int, requested: str | None) -> dict:
    """정확 일치와 0.5% 이내 반올림 오차를 구분한 측정 결과 반환."""
    actual = Fraction(width, height)
    report = {'requested_ratio': requested, 'width': width, 'height': height, 'actual_ratio': f'{actual.numerator}:{actual.denominator}', 'actual_ratio_value': float(actual), 'relative_tolerance': RATIO_RELATIVE_TOLERANCE, 'exact_match': None, 'relative_error': None, 'status': 'not_requested', 'warning': None}
    if requested is None:
        return report
    parts = requested.split(':')
    if len(parts) != 2 or any((not part.strip().isdigit() or int(part) <= 0 for part in parts)):
        raise ValueError('Expected a positive W:H image ratio')
    target = Fraction(int(parts[0]), int(parts[1]))
    error = float(abs(actual / target - 1))
    exact = actual == target
    status = 'exact' if exact else 'within_tolerance' if error <= RATIO_RELATIVE_TOLERANCE else 'mismatch'
    report.update(exact_match=exact, relative_error=error, status=status)
    if status == 'mismatch':
        report['warning'] = f'Requested {requested}, received {width}x{height} ({float(actual):.4f}:1). Aspect ratio mismatch; image left unchanged.'
    return report
