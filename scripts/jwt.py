#!/usr/bin/env python3
"""Mint JWTs (HS256) for the auth tests and benchmarks.  usage: jwt.py <kind>
kinds: valid | expired | badsig | wrongsecret | none | malformed | nosub | floatexp | rs256
       all   prints every kind as kind=token lines (one process instead of one per token)
Secret comes from $JWT_SECRET (default matches infra/compose.yaml)."""
import base64
import hashlib
import hmac
import json
import os
import sys
import time

SECRET = os.environ.get("JWT_SECRET", "bench-jwt-secret-local-only").encode()


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def mint(header, payload, secret=SECRET, tamper=False):
    h = b64(json.dumps(header, separators=(",", ":")).encode())
    p = b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret, f"{h}.{p}".encode(), hashlib.sha256).digest()
    if tamper:
        sig = bytes([sig[0] ^ 1]) + sig[1:]
    return f"{h}.{p}.{b64(sig)}"


def main(kind):
    now = int(time.time())
    hdr = {"alg": "HS256", "typ": "JWT"}
    ok = {"sub": "bench", "exp": now + 24 * 3600}
    if kind == "valid":
        return mint(hdr, ok)
    if kind == "expired":
        return mint(hdr, {"sub": "bench", "exp": now - 60})
    if kind == "badsig":
        return mint(hdr, ok, tamper=True)
    if kind == "wrongsecret":
        return mint(hdr, ok, secret=b"not-the-secret")
    if kind == "none":   # alg=none, empty signature
        return b64(json.dumps({"alg": "none", "typ": "JWT"}).encode()) + "." + b64(json.dumps(ok).encode()) + "."
    if kind == "malformed":
        return "not.a.jwt.at.all"
    if kind == "nosub":
        return mint(hdr, {"exp": now + 3600})
    if kind == "floatexp":
        return mint(hdr, {"sub": "bench", "exp": now + 3600.5})
    if kind == "rs256":  # header claims RS256 but signed with HMAC: must be rejected (algorithm confusion)
        return mint({"alg": "RS256", "typ": "JWT"}, ok)
    sys.exit(__doc__)


KINDS = ("valid", "expired", "badsig", "wrongsecret", "none", "malformed", "nosub", "floatexp", "rs256")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    if sys.argv[1] == "all":
        for k in KINDS:
            print(f"{k}={main(k)}")
    else:
        print(main(sys.argv[1]))
