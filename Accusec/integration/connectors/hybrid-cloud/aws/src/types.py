"""Map AWS resource types (CloudFormation / Resource Explorer) to AccuSec entity_type."""

from __future__ import annotations

from accusec.shared.domain.models import Entity, utcnow

CATALOG_CFN_TYPES = {
    "AWS::EC2::Instance": "aws.ec2.instance",
    "AWS::EC2::VPC": "aws.ec2.vpc",
    "AWS::EC2::Subnet": "aws.ec2.subnet",
    "AWS::EC2::SecurityGroup": "aws.ec2.security-group",
    "AWS::EC2::Volume": "aws.ec2.volume",
    "AWS::S3::Bucket": "aws.s3.bucket",
    "AWS::RDS::DBInstance": "aws.rds.db-instance",
    "AWS::EKS::Cluster": "aws.eks.cluster",
    "AWS::IAM::Role": "aws.iam.role",
    "AWS::ElasticLoadBalancingV2::LoadBalancer": "aws.elasticloadbalancing.lb",
    "AWS::AutoScaling::AutoScalingGroup": "aws.autoscaling.group",
    "AWS::Lambda::Function": "aws.lambda.function",
    "AWS::CloudWatch::Alarm": "aws.cloudwatch.alarm",
}

EXPLORER_TO_CFN = {
    "ec2:instance": "AWS::EC2::Instance",
    "ec2:vpc": "AWS::EC2::VPC",
    "ec2:subnet": "AWS::EC2::Subnet",
    "ec2:security-group": "AWS::EC2::SecurityGroup",
    "ec2:volume": "AWS::EC2::Volume",
    "s3:bucket": "AWS::S3::Bucket",
    "rds:db": "AWS::RDS::DBInstance",
    "eks:cluster": "AWS::EKS::Cluster",
    "iam:role": "AWS::IAM::Role",
    "elasticloadbalancing:loadbalancer": "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "autoscaling:autoScalingGroup": "AWS::AutoScaling::AutoScalingGroup",
    "lambda:function": "AWS::Lambda::Function",
    "cloudwatch:alarm": "AWS::CloudWatch::Alarm",
}

GLOBAL_TYPES = {"aws.iam.role", "aws.s3.bucket"}


def format_aws_error(exc: BaseException) -> str:
    """Vendor error for skip lists — code + short message, never secret material."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        err = response.get("Error") or {}
        code = str(err.get("Code") or exc.__class__.__name__)
        message = " ".join(str(err.get("Message") or "").split())[:180]
        if message:
            return f"{code}: {message}"
        return code
    return exc.__class__.__name__


def canonical_cfn_type(resource_type: str) -> str:
    raw = (resource_type or "").strip()
    if raw.startswith("AWS::"):
        return raw
    mapped = EXPLORER_TO_CFN.get(raw) or EXPLORER_TO_CFN.get(raw.lower())
    if mapped:
        return mapped
    if ":" in raw and not raw.startswith("arn:"):
        service, kind = raw.split(":", 1)
        parts = [p.capitalize() for p in kind.replace("_", "-").split("-")]
        return f"AWS::{service.upper()}::{''.join(parts)}"
    return raw or "AWS::Unknown::Resource"


def accusec_entity_type(resource_type: str) -> str:
    cfn = canonical_cfn_type(resource_type)
    if cfn in CATALOG_CFN_TYPES:
        return CATALOG_CFN_TYPES[cfn]
    if cfn.startswith("AWS::"):
        parts = cfn.split("::")[1:]
        slug = ".".join(p.lower().replace("_", "-") for p in parts)
        return f"aws.{slug}"
    return f"aws.unknown.{resource_type.lower().replace(':', '.')}"


def native_id_from_arn(arn: str) -> str:
    if not arn:
        return ""
    if arn.startswith("arn:aws:s3:::"):
        return arn.split(":::", 1)[1]
    resource = arn.split(":", 5)[-1] if arn.startswith("arn:") else arn
    if "/" in resource:
        return resource.rsplit("/", 1)[-1]
    return resource


def region_for(entity_type: str, region: str | None) -> str:
    if entity_type in GLOBAL_TYPES:
        return "global"
    return region or "global"


def entity_from_aws_hit(
    *,
    resource_type: str,
    arn: str,
    region: str | None,
    account_id: str,
    tenant_id: str,
    workspace_id: str,
    display_name: str | None = None,
    extra: dict | None = None,
    source: str = "aws.resource-explorer",
) -> Entity:
    entity_type = accusec_entity_type(resource_type)
    native_id = native_id_from_arn(arn) or display_name or arn
    resolved_region = region_for(entity_type, region)
    cfg = {"arn": arn, "provider_type": canonical_cfn_type(resource_type)}
    if extra:
        cfg.update(extra)
    return Entity(
        entity_id=Entity.make_id("aws", entity_type, tenant_id, account_id, resolved_region, native_id),
        provider_entity_id=native_id[:512],
        entity_type=entity_type,
        provider="aws",
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        display_name=(display_name or native_id)[:255],
        account_id=account_id,
        region=resolved_region,
        lifecycle_state="unknown",
        configuration=cfg,
        source=source,
        last_observed_at=utcnow(),
        freshness_status="fresh",
    )
