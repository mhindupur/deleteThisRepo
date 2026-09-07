from accusec.agents.harness.harness import SkillHarness
from accusec.integration.aws_connector.connector import AwsConnector
from accusec.integration.aws_mcp.server import AwsMcpServer
import pytest


def test_harness_rejects_unregistered_tool():
    harness = SkillHarness(AwsMcpServer(AwsConnector("secret-ref:aws/local-fixture")))
    with pytest.raises(PermissionError):
        harness.invoke("aws.iam.delete_user", {})
