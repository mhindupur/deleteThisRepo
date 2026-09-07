"""Secret references only — never raw values in prompts or audit."""

from __future__ import annotations

import json
import os
from pathlib import Path

from accusec.shared.domain.models import SecretSpec

FIXTURE_NAME = "aws/local-fixture"


def default_secrets_path() -> Path:
    raw = os.environ.get("ACCUSEC_SECRETS_PATH")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".accusec" / "secrets.json"


class SecretsManager:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_secrets_path()
        self._mem = {
            FIXTURE_NAME: SecretSpec(
                auth_mode="fixture",
                role_arn="arn:aws:iam::123456789012:role/AccuSecInventoryReader",
            )
        }
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text())
        for name, spec in payload.items():
            self._mem[name] = SecretSpec.model_validate(spec)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {name: spec.model_dump() for name, spec in self._mem.items() if name != FIXTURE_NAME}
        self.path.write_text(json.dumps(serializable, indent=2))
        os.chmod(self.path, 0o600)

    def put(self, name: str, spec: SecretSpec) -> str:
        if spec.auth_mode == "assume_role" and not spec.role_arn:
            raise ValueError("assume_role requires --role-arn")
        if spec.auth_mode == "profile" and not spec.profile:
            raise ValueError("profile requires --profile")
        if spec.auth_mode == "access_key" and not (spec.access_key_id and spec.secret_access_key):
            raise ValueError("access_key requires --access-key-id and --secret-access-key")
        self._mem[name] = spec
        self._save()
        return self.reference(name)

    def reference(self, name: str) -> str:
        self.resolve(name)
        return f"secret-ref:{name}"

    def resolve(self, name_or_ref: str) -> SecretSpec:
        name = name_or_ref.removeprefix("secret-ref:")
        if name not in self._mem:
            raise KeyError(f"unknown secret ref: {name}")
        return self._mem[name]

    def resolve_role_arn(self, name: str) -> str:
        spec = self.resolve(name)
        return spec.role_arn or ""

    def list_public(self) -> dict[str, dict]:
        return {name: spec.public_view() for name, spec in self._mem.items()}
