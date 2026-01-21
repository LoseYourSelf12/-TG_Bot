from __future__ import annotations

import base64
import uuid


def uuid_to_short(u: uuid.UUID) -> str:
    # 16 bytes -> base64url без '=' => 22 символа
    return base64.urlsafe_b64encode(u.bytes).decode("ascii").rstrip("=")


def short_to_uuid(s: str) -> uuid.UUID:
    padded = s + "=" * ((4 - len(s) % 4) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    return uuid.UUID(bytes=raw)
