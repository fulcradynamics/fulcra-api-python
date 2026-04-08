import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Self


@dataclass
class FulcraCredentials:
    access_token: str
    access_token_expiration: datetime
    refresh_token: str
    refresh_token_expiration: Optional[datetime] = None

    def is_expired(self) -> bool:
        if (
            self.access_token is not None
            and self.access_token_expiration > datetime.now()
        ):
            return False
        return True

    def to_json(self) -> str:
        return json.dumps(
            {
                "access_token": self.access_token,
                "access_token_expiration": self.access_token_expiration.isoformat(),
                "refresh_token": self.refresh_token,
                "refresh_token_expiration": self.refresh_token_expiration.isoformat()
                if self.refresh_token_expiration
                else None,
            }
        )

    @classmethod
    def from_json(cls, data: str | bytes) -> Self:
        o = json.loads(data)

        o["access_token_expiration"] = datetime.fromisoformat(
            o["access_token_expiration"]
        )

        if o.get("refresh_token_expiration", None):
            o["refresh_token_expiration"] = datetime.fromisoformat(
                o["refresh_token_expiration"]
            )

        return FulcraCredentials(**o)
