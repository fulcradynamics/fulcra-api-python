import base64
import json
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from typing import Optional, Self


def _aware(dt: datetime) -> datetime:
    """
    Return `dt` with a timezone. A naive value is taken as local time, which is
    how older releases stamped and stored expirations.
    """
    return dt if dt.tzinfo is not None else dt.astimezone()


def _to_stored(dt: Optional[datetime]) -> Optional[str]:
    """
    Serialize an expiration for the credentials file.

    Written as naive local time, because older releases read this
    field and compare it with a naive `datetime.now()`; an offset would make
    them raise. Newer releases don't rely on it when the access token carries
    its own `exp` claim.
    """
    if dt is None:
        return None
    return _aware(dt).astimezone().replace(tzinfo=None).isoformat()


def _from_stored(value: Optional[str]) -> Optional[datetime]:
    """Parse an expiration from the credentials file into an aware datetime."""
    if not value:
        return None
    return _aware(datetime.fromisoformat(value))


def jwt_expiration(token: Optional[str]) -> Optional[datetime]:
    """
    The `exp` claim of a JWT as an aware UTC datetime, or None if `token`
    isn't a JWT with one. The signature is not checked: this is only used to
    decide when to refresh.
    """
    if not token or token.count(".") != 2:
        return None
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
        return datetime.fromtimestamp(float(exp), tz=timezone.utc)
    except (ValueError, KeyError, TypeError):
        return None


@dataclass
class FulcraCredentials:
    access_token: Optional[str] = None
    access_token_expiration: Optional[datetime] = None
    refresh_token: Optional[str] = None
    refresh_token_expiration: Optional[datetime] = None
    id_token: Optional[str] = None
    id_token_expiration: Optional[datetime] = None

    def expires_at(self) -> Optional[datetime]:
        """
        When the access token expires, as an aware datetime.

        The token's own `exp` claim wins over the stored expiration: older
        releases stored that as naive local time, which reads back wrong in a
        process running in a different timezone than the one that wrote it.
        """
        exp = jwt_expiration(self.access_token)
        if exp is not None:
            return exp
        if self.access_token_expiration is not None:
            return _aware(self.access_token_expiration)
        return None

    def is_expired(self, leeway: timedelta = timedelta(0)) -> bool:
        """
        return whether the held credentials are expired, or will be within
        `leeway`
        """
        if self.access_token is None:
            return True
        expires_at = self.expires_at()
        if expires_at is None:
            return True
        return expires_at <= datetime.now(timezone.utc) + leeway

    def to_json(self) -> str:
        """serialize the FulcraCredentials object to a JSON string"""
        return json.dumps(
            {
                "access_token": self.access_token,
                "access_token_expiration": _to_stored(self.access_token_expiration),
                "refresh_token": self.refresh_token,
                "refresh_token_expiration": _to_stored(self.refresh_token_expiration),
                "id_token": self.id_token,
                "id_token_expiration": _to_stored(self.id_token_expiration),
            }
        )

    @classmethod
    def from_json(cls, data: str | bytes) -> Self:
        """deserialize a FulcraCredentials object from a JSON string or bytes"""
        o = json.loads(data)

        for key in (
            "access_token_expiration",
            "refresh_token_expiration",
            "id_token_expiration",
        ):
            o[key] = _from_stored(o.get(key))

        # Ignore keys written by newer versions of this library so that a
        # credentials file is always readable by older releases.
        known_fields = {f.name for f in fields(cls)}
        return FulcraCredentials(
            **{k: v for k, v in o.items() if k in known_fields}
        )
