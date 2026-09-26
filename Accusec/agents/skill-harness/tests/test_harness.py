from accusec.agents.harness.harness import SkillHarness
from accusec.integration.aws_connector.connector import AwsConnector
from accusec.integration.aws_mcp.server import AwsMcpServer
import pytest


def test_harness_rejects_unregistered_tool():
    harness = SkillHarness(AwsMcpServer(AwsConnector("secret-ref:aws/local-fixture")))
    with pytest.raises(PermissionError):
        harness.invoke("aws.iam.delete_user", {})


def test_harness_readonly_identity_cannot_stop():
    harness = SkillHarness(AwsMcpServer(AwsConnector("secret-ref:aws/local-fixture")))
    harness.execution_context = {"identity_type": "READ_ONLY"}
    with pytest.raises(PermissionError, match="READ_ONLY"):
        harness.invoke("aws.ec2.stop_instances", {"instance_id": "i-aaa111", "region": "us-east-1"})
