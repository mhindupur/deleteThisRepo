from accusec.integration.aws_connector.types import accusec_entity_type, entity_from_aws_hit, format_aws_error, native_id_from_arn


def test_explorer_ec2_maps_to_catalog_type():
    entity = entity_from_aws_hit(
        resource_type="ec2:instance",
        arn="arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
        region="us-east-1",
        account_id="123456789012",
        tenant_id="tenant-1",
        workspace_id="aws-prod",
        display_name="web-1",
    )
    assert entity.entity_type == "aws.ec2.instance"
    assert entity.provider_entity_id == "i-abc123"
    assert entity.entity_id.startswith("accusec:aws:instance:")
    assert "web-1" not in entity.entity_id
    assert entity.source == "aws.resource-explorer"


def test_unknown_cfn_type_is_still_an_entity():
    assert accusec_entity_type("AWS::AppRunner::Service") == "aws.apprunner.service"
    assert native_id_from_arn("arn:aws:s3:::my-bucket") == "my-bucket"


def test_aws_error_uses_code_not_bare_clienterror():
    class Fake(Exception):
        response = {"Error": {"Code": "AccessDeniedException", "Message": "not authorized to perform: cloudcontrol:ListResources"}}

    assert "AccessDeniedException" in format_aws_error(Fake())
    assert "cloudcontrol:ListResources" in format_aws_error(Fake())
