"""Hierarchical operation catalog. Extensible to every AWS (and other provider) service."""

from accusec.shared.domain.models import Operation, RiskLevel

# Entity types are catalog entries — collectors/MCP implementations grow over time.
AWS_ENTITY_TYPES = [
    "aws.ec2.instance",
    "aws.ec2.vpc",
    "aws.ec2.subnet",
    "aws.ec2.security-group",
    "aws.ec2.volume",
    "aws.s3.bucket",
    "aws.rds.db-instance",
    "aws.eks.cluster",
    "aws.iam.role",
    "aws.elasticloadbalancing.lb",
    "aws.autoscaling.group",
    "aws.lambda.function",
    "aws.cloudwatch.alarm",
]

OPERATIONS: dict[str, Operation] = {
    "inventory.sync": Operation(
        operation_id="inventory.sync",
        entity_type="*",
        read_or_write="read",
        risk_level=RiskLevel.READ,
        required_slots=["region"],
        required_context_types=["entity_configuration"],
        required_tools=["aws.resourceexplorer.search", "aws.ec2.describe_instances"],
    ),
    "provider.connect": Operation(
        operation_id="provider.connect",
        entity_type="*",
        read_or_write="read",
        risk_level=RiskLevel.LOW,
        required_slots=["account_id"],
        required_tools=["aws.sts.get_caller_identity"],
    ),
    "provider.read": Operation(
        operation_id="provider.read",
        entity_type="*",
        read_or_write="read",
        risk_level=RiskLevel.READ,
    ),
    "resource.read": Operation(
        operation_id="resource.read",
        entity_type="*",
        read_or_write="read",
        risk_level=RiskLevel.READ,
        required_context_types=["entity_configuration"],
    ),
    "compute.instance.list": Operation(
        operation_id="compute.instance.list",
        entity_type="aws.ec2.instance",
        read_or_write="read",
        risk_level=RiskLevel.READ,
        required_slots=[],
        required_context_types=["entity_configuration", "topology"],
        required_tools=["aws.ec2.describe_instances"],
    ),
    "compute.instance.read": Operation(
        operation_id="compute.instance.read",
        entity_type="aws.ec2.instance",
        read_or_write="read",
        risk_level=RiskLevel.READ,
        required_tools=["aws.ec2.describe_instances", "aws.ec2.describe_instance_status"],
    ),
    "compute.instance.stop": Operation(
        operation_id="compute.instance.stop",
        entity_type="aws.ec2.instance",
        read_or_write="write",
        risk_level=RiskLevel.DESTRUCTIVE,
        destructive=True,
        idempotent=True,
        approval_default=True,
        required_slots=["instance_id"],
        required_context_types=[
            "entity_configuration",
            "topology",
            "ownership",
            "policy",
        ],
        required_tools=["aws.ec2.describe_instances", "aws.ec2.stop_instances"],
        expected_postconditions=["lifecycle_state in {stopped, stopping}"],
    ),
}


def get_operation(operation_id: str) -> Operation:
    if operation_id not in OPERATIONS:
        raise KeyError(f"unknown operation: {operation_id}")
    return OPERATIONS[operation_id]
