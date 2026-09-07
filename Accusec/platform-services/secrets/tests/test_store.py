from accusec.platform_services.secrets.store import SecretsManager
from accusec.shared.domain.models import SecretSpec
import pytest


def test_put_assume_role_public_view_hides_nothing_secret(tmp_path):
    mgr = SecretsManager(tmp_path / "secrets.json")
    mgr.put(
        "aws/operator",
        SecretSpec(
            auth_mode="assume_role",
            role_arn="arn:aws:iam::123456789012:role/AccuSecInventoryReader",
            external_id="accusec-local",
            profile="default",
        ),
    )
    view = mgr.list_public()["aws/operator"]
    assert view["auth_mode"] == "assume_role"
    assert view["role_arn"].endswith("AccuSecInventoryReader")
    assert view["has_access_key"] is False
    stored = (tmp_path / "secrets.json").read_text()
    assert "AccuSecInventoryReader" in stored


def test_access_key_rejected_without_secret(tmp_path):
    mgr = SecretsManager(tmp_path / "secrets.json")
    with pytest.raises(ValueError):
        mgr.put("aws/lab", SecretSpec(auth_mode="access_key", access_key_id="AKIAFAKE"))
