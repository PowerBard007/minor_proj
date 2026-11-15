"""Application freshness checks; these are NOT authentication or encryption."""
import math

def validate_shape(c):
    if not isinstance(c, dict):
        return 'payload_not_object'
    for field in ('job_id', 'command_id'):
        if not isinstance(c.get(field), str) or not 1 <= len(c[field]) <= 80:
            return 'invalid_' + field
    for field in ('dose', 'issued_at'):
        v = c.get(field)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return 'invalid_' + field
    if not 0 < c['dose'] <= 11:
        return 'dose_out_of_lab_range'
    return None

def rejection(c, *, mode, job_id, phase, now, seen, max_age=1.0):
    bad = validate_shape(c)
    if bad:
        return bad
    if phase != 'READY':
        return 'not_ready'
    if mode == 'weak':
        return None
    if c['job_id'] != job_id:
        return 'wrong_job'
    age = now - c['issued_at']
    if age < -0.1:
        return 'future_timestamp'
    if age > max_age:
        return 'expired'
    if seen:
        return 'duplicate_command'
    return None
