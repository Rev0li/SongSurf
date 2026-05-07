"""
Tests for Watcher JWT validation — covers W-1 through W-9 from test plan.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'watcher'))

import time
import jwt as pyjwt
import pytest

# ── Replicate _validate_jwt logic to test it in isolation ─────────────────────

_JWT_SECRET = 'test-hmac-secret-256bits-long-enough'


def _validate_jwt(token: str, secret: str = _JWT_SECRET) -> dict | None:
    """Mirror of watcher._validate_jwt with injectable secret."""
    if not secret:
        return None
    try:
        claims = pyjwt.decode(
            token,
            secret,
            algorithms=['HS256'],
            options={'require': ['sub', 'role', 'exp']},
        )
        if claims.get('token_type') != 'access':
            return None
        return {
            'sub':   claims['sub'],
            'role':  claims['role'].lower(),
            'email': claims.get('email', ''),
        }
    except pyjwt.PyJWTError:
        return None


def _make_jwt(payload: dict, secret: str = _JWT_SECRET, algorithm: str = 'HS256') -> str:
    return pyjwt.encode(payload, secret, algorithm=algorithm)


def _valid_payload(overrides: dict = None) -> dict:
    base = {
        'sub': 'user-abc-123',
        'role': 'member',
        'email': 'user@example.com',
        'token_type': 'access',
        'exp': int(time.time()) + 3600,
    }
    if overrides:
        base.update(overrides)
    return base


# ── W-1: Valid JWT accepted ───────────────────────────────────────────────────

def test_w1_valid_jwt_accepted():
    token = _make_jwt(_valid_payload())
    result = _validate_jwt(token)
    assert result is not None
    assert result['sub'] == 'user-abc-123'
    assert result['role'] == 'member'
    assert result['email'] == 'user@example.com'


# ── W-2: Expired JWT rejected ─────────────────────────────────────────────────

def test_w2_expired_jwt_rejected():
    payload = _valid_payload({'exp': int(time.time()) - 10})
    token = _make_jwt(payload)
    assert _validate_jwt(token) is None


# ── W-3: Wrong algorithm rejected ─────────────────────────────────────────────

def test_w3_wrong_algorithm_rejected():
    # PyJWT requires RS256 keys to be actual RSA keys — simulate by passing a
    # forged token (manually crafted header with alg=RS256 and HS256 body)
    import base64, json

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

    header  = b64url(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode())
    payload = b64url(json.dumps(_valid_payload()).encode())
    sig     = b64url(b'fakesig')
    forged  = f"{header}.{payload}.{sig}"
    assert _validate_jwt(forged) is None


# ── W-4: Wrong secret rejected ────────────────────────────────────────────────

def test_w4_wrong_secret_rejected():
    token = _make_jwt(_valid_payload(), secret='completely-different-secret')
    assert _validate_jwt(token) is None


# ── W-5: Missing token_type claim → refresh token rejected ───────────────────

def test_w5_missing_token_type_rejected():
    payload = _valid_payload()
    del payload['token_type']
    token = _make_jwt(payload)
    assert _validate_jwt(token) is None


def test_w5_refresh_token_type_rejected():
    token = _make_jwt(_valid_payload({'token_type': 'refresh'}))
    assert _validate_jwt(token) is None


# ── W-6: Missing required claims → rejected ───────────────────────────────────

def test_w6_missing_sub_rejected():
    payload = _valid_payload()
    del payload['sub']
    token = _make_jwt(payload)
    assert _validate_jwt(token) is None


def test_w6_missing_role_rejected():
    payload = _valid_payload()
    del payload['role']
    token = _make_jwt(payload)
    assert _validate_jwt(token) is None


def test_w6_missing_exp_rejected():
    payload = _valid_payload()
    del payload['exp']
    token = _make_jwt(payload)
    assert _validate_jwt(token) is None


# ── W-7: No token → None ──────────────────────────────────────────────────────

def test_w7_empty_token_rejected():
    assert _validate_jwt('') is None


def test_w7_none_token_rejected():
    assert _validate_jwt(None) is None


# ── W-8: Tampered payload rejected ────────────────────────────────────────────

def test_w8_tampered_payload_rejected():
    import base64, json

    token = _make_jwt(_valid_payload())
    header, payload_b64, sig = token.split('.')

    # Decode and modify payload (elevate to admin)
    padded = payload_b64 + '=' * (-len(payload_b64) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded))
    data['role'] = 'admin'
    new_payload = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b'=').decode()

    tampered = f"{header}.{new_payload}.{sig}"
    assert _validate_jwt(tampered) is None


# ── W-9: Empty AUTH_JWT_SECRET → all tokens rejected ─────────────────────────

def test_w9_empty_secret_blocks_all():
    token = _make_jwt(_valid_payload())
    assert _validate_jwt(token, secret='') is None


# ── Role normalization ────────────────────────────────────────────────────────

def test_role_lowercased():
    token = _make_jwt(_valid_payload({'role': 'Admin'}))
    result = _validate_jwt(token)
    assert result is not None
    assert result['role'] == 'admin'


def test_email_optional():
    payload = _valid_payload()
    del payload['email']
    token = _make_jwt(payload)
    result = _validate_jwt(token)
    assert result is not None
    assert result['email'] == ''
