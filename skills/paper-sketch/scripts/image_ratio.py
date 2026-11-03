"""픽셀이나 캔버스 변경 없이 요청·실제 비율 비교."""
from fractions import Fraction


RATIO_RELATIVE_TOLERANCE = 0.005


def assess_ratio(width: int, height: int, requested: str | None) -> dict:
    """정확 일치와 0.5% 이내 반올림 오차를 구분한 측정 결과 반환."""
    actual = Fraction(width, height)
    report = {'requested_ratio': requested, 'width': width, 'height': height,
              'actual_ratio': f'{actual.numerator}:{actual.denominator}',
              'actual_ratio_value': float(actual), 'relative_tolerance': RATIO_RELATIVE_TOLERANCE,
              'exact_match': None, 'relative_error': None, 'status': 'not_requested', 'warning': None}
    if requested is None:
        return report
    parts = requested.split(':')
    if len(parts) != 2 or any(not part.strip().isdigit() or int(part) <= 0 for part in parts):
        raise ValueError('Expected a positive W:H image ratio')
    target = Fraction(int(parts[0]), int(parts[1]))
    error = float(abs(actual / target - 1))
    exact = actual == target
    status = 'exact' if exact else 'within_tolerance' if error <= RATIO_RELATIVE_TOLERANCE else 'mismatch'
    report.update(exact_match=exact, relative_error=error, status=status)
    if status == 'mismatch':
        report['warning'] = (f'Requested {requested}, received {width}x{height} '
                             f'({float(actual):.4f}:1). Aspect ratio mismatch; image left unchanged.')
    return report
