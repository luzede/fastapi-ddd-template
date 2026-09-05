"""Cryptographic primitives for the auth module.

Everything here is pure and side-effect free so it can be reasoned about in isolation.
"""

import base64
import hashlib
import hmac
import json
import secrets
import string
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jwt.algorithms import get_default_algorithms
from pwdlib import PasswordHash

# --- Passwords -------------------------------------------------------------------------

_password_hasher = PasswordHash.recommended()  # argon2id


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Returns `(valid, upgraded_hash)`; `upgraded_hash` is set when the stored hash should be replaced."""
    return _password_hasher.verify_and_update(password, password_hash)


# --- Opaque tokens ---------------------------------------------------------------------


def generate_session_token() -> str:
    """32 random bytes → 43-char base64url. Comparable entropy to better-auth's `generateId(32)`."""
    return secrets.token_urlsafe(32)


def generate_verification_token() -> str:
    return secrets.token_urlsafe(32)


def sha256_base64url(value: str) -> str:
    """SHA-256 → unpadded base64url. Matches better-auth's `defaultKeyHasher`."""
    digest = hashlib.sha256(value.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def hmac_sha256_hex(secret: str, value: str) -> str:
    """Keyed hash for verification-token identifiers: a DB leak alone cannot forge a token."""
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# --- API keys --------------------------------------------------------------------------

_API_KEY_ALPHABET = string.ascii_letters + string.digits


def generate_api_key(length: int, prefix: str | None) -> str:
    body = "".join(secrets.choice(_API_KEY_ALPHABET) for _ in range(length))
    return f"{prefix}_{body}" if prefix else body


# --- Symmetric encryption (private JWKs at rest) ---------------------------------------


def _derive_aes_key(secret: str) -> bytes:
    # Fixed-context KDF: the secret is already high entropy; we only need a 256-bit key
    return hashlib.sha256(b"jwks-private-key:" + secret.encode()).digest()


def encrypt(secret: str, plaintext: str) -> str:
    """AES-256-GCM. Output: base64url(nonce || ciphertext||tag)."""
    key = _derive_aes_key(secret)
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt(secret: str, token: str) -> str:
    raw = base64.urlsafe_b64decode(token)
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_derive_aes_key(secret)).decrypt(nonce, ciphertext, None).decode()


# --- Asymmetric key pairs (JWKS) -------------------------------------------------------

type JwkDict = dict[str, Any]


def generate_key_pair(
    alg: str, *, crv: str = "Ed25519", rsa_modulus_length: int = 2048
) -> tuple[JwkDict, JwkDict]:
    """Returns `(private_jwk, public_jwk)` for the given JWS algorithm."""
    match alg:
        case "EdDSA":
            private_key = ed25519.Ed25519PrivateKey.generate()
        case "ES256":
            private_key = ec.generate_private_key(ec.SECP256R1())
        case "ES512":
            private_key = ec.generate_private_key(ec.SECP521R1())
        case "RS256" | "PS256":
            private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=rsa_modulus_length
            )
        case _:
            raise ValueError(f"Unsupported JWS algorithm: {alg}")

    algorithm = get_default_algorithms()[alg]
    private_jwk: JwkDict = json.loads(algorithm.to_jwk(private_key))
    public_jwk: JwkDict = json.loads(algorithm.to_jwk(private_key.public_key()))
    if alg == "EdDSA":
        private_jwk["crv"] = crv
        public_jwk["crv"] = crv
    return private_jwk, public_jwk


def load_private_key(alg: str, private_jwk: JwkDict) -> Any:
    return get_default_algorithms()[alg].from_jwk(json.dumps(private_jwk))


def load_public_key(alg: str, public_jwk: JwkDict) -> Any:
    return get_default_algorithms()[alg].from_jwk(json.dumps(public_jwk))
