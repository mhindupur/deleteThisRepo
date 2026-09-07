from accusec.integration.aws_connector.connector import AccountMismatchError, AwsConnector
import pytest


def test_connector_filters_region_and_type():
    connector = AwsConnector("secret-ref:aws/local-fixture")
    rows = connector.describe_instances(region="us-east-1", instance_type="t2.small")
    assert {r.provider_entity_id for r in rows} == {"i-aaa111", "i-bbb222"}


def test_sts_mismatch_refuses_connect():
    connector = AwsConnector("secret-ref:aws/local-fixture")
    with pytest.raises(AccountMismatchError, match="does not match"):
        connector.verify_account("000000000000")


def test_sts_match_returns_identity():
    connector = AwsConnector("secret-ref:aws/local-fixture")
    ident = connector.verify_account("123456789012")
    assert ident["Account"] == "123456789012"
    assert "AccuSecInventoryReader" in ident["Arn"]
