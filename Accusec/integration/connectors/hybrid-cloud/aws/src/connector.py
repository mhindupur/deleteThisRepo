"""AWS connector. boto3 lives only here; tests use fixtures."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from accusec.integration.aws_connector.types import (
    CATALOG_CFN_TYPES,
    entity_from_aws_hit,
    format_aws_error,
    region_for,
)
from accusec.platform_services.secrets.store import SecretsManager
from accusec.shared.domain.models import Entity, SecretSpec, utcnow


TENANT = "tenant-1"
WORKSPACE = "aws-prod"
ACCOUNT = "123456789012"


class AccountMismatchError(ValueError):
    """STS account does not match the registered connection account."""


def _instance(
    instance_id: str,
    name: str,
    instance_type: str,
    region: str,
    vpc_id: str,
    state: str,
    cpu: float,
) -> Entity:
    return Entity(
        entity_id=Entity.make_id("aws", "aws.ec2.instance", TENANT, ACCOUNT, region, instance_id),
        provider_entity_id=instance_id,
        entity_type="aws.ec2.instance",
        provider="aws",
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        display_name=name,
        account_id=ACCOUNT,
        region=region,
        lifecycle_state=state,
        configuration={
            "instance_type": instance_type,
            "vpc_id": vpc_id,
            "cpu_utilization": cpu,
        },
        source="aws.fixture",
        last_observed_at=utcnow(),
    )


def fixture_inventory() -> list[Entity]:
    return [
        _instance("i-aaa111", "web-1", "t2.small", "us-east-1", "vpc-east", "running", 12.0),
        _instance("i-bbb222", "web-2", "t2.small", "us-east-1", "vpc-east", "running", 81.0),
        _instance("i-ccc333", "batch-1", "t2.medium", "us-east-1", "vpc-east", "running", 5.0),
        _instance("i-ddd444", "west-app", "t2.small", "us-west-2", "vpc-west", "running", 9.0),
    ]


class AwsConnector:
    """Controlled AWS API boundary. Fixture mode never reads env credentials."""

    def __init__(
        self,
        secret_ref: str,
        *,
        secrets: SecretsManager | None = None,
        fixture_mode: bool | None = None,
        tenant_id: str = TENANT,
        workspace_id: str = WORKSPACE,
        account_id: str | None = None,
        identity_override: dict[str, str] | None = None,
    ) -> None:
        self.secret_ref = secret_ref
        self.secrets = secrets or SecretsManager()
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.account_id = account_id
        self.identity_override = identity_override
        spec = self._spec()
        if fixture_mode is None:
            fixture_mode = spec.auth_mode == "fixture" or secret_ref.endswith("local-fixture")
        self.fixture_mode = fixture_mode
        self._live = {e.provider_entity_id: deepcopy(e) for e in fixture_inventory()}
        self._session = None

    def _spec(self) -> SecretSpec:
        try:
            return self.secrets.resolve(self.secret_ref)
        except KeyError:
            return SecretSpec(auth_mode="fixture")

    def _boto3_session(self):
        if self._session is not None:
            return self._session
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("Live AWS requires: pip install 'accusec[aws]'") from exc
        spec = self._spec()
        if spec.auth_mode == "profile":
            self._session = boto3.Session(profile_name=spec.profile)
        elif spec.auth_mode == "assume_role":
            base = boto3.Session(profile_name=spec.profile) if spec.profile else boto3.Session()
            sts = base.client("sts")
            kwargs: dict[str, Any] = {
                "RoleArn": spec.role_arn,
                "RoleSessionName": "accusec-inventory",
            }
            if spec.external_id:
                kwargs["ExternalId"] = spec.external_id
            creds = sts.assume_role(**kwargs)["Credentials"]
            self._session = boto3.Session(
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
        elif spec.auth_mode == "access_key":
            self._session = boto3.Session(
                aws_access_key_id=spec.access_key_id,
                aws_secret_access_key=spec.secret_access_key,
            )
        else:
            raise RuntimeError(f"cannot build AWS session for auth_mode={spec.auth_mode}")
        return self._session

    def _client(self, service: str, region: str | None = None):
        session = self._boto3_session()
        if region:
            return session.client(service, region_name=region)
        return session.client(service)

    def get_caller_identity(self) -> dict:
        if self.identity_override:
            return dict(self.identity_override)
        if self.fixture_mode:
            return {
                "Account": self.account_id or ACCOUNT,
                "Arn": "arn:aws:sts::123456789012:assumed-role/AccuSecInventoryReader",
            }
        ident = self._client("sts").get_caller_identity()
        return {"Account": ident["Account"], "Arn": ident["Arn"], "UserId": ident.get("UserId")}

    def verify_account(self, expected_account: str) -> dict:
        ident = self.get_caller_identity()
        actual = ident.get("Account")
        if actual != expected_account:
            raise AccountMismatchError(
                f"STS account {actual} does not match registered account {expected_account}"
            )
        return ident

    def describe_instances(
        self,
        *,
        region: str | None = None,
        instance_ids: list[str] | None = None,
        instance_type: str | None = None,
    ) -> list[Entity]:
        if self.fixture_mode:
            return self._describe_instances_fixture(region, instance_ids, instance_type)
        return self._describe_instances_live(region, instance_ids, instance_type)

    def _stamp(self, entity: Entity) -> Entity:
        entity.tenant_id = self.tenant_id
        entity.workspace_id = self.workspace_id
        if self.account_id:
            entity.account_id = self.account_id
            entity.entity_id = Entity.make_id(
                "aws",
                entity.entity_type,
                self.tenant_id,
                self.account_id,
                entity.region or "global",
                entity.provider_entity_id,
            )
        return entity

    def _describe_instances_fixture(
        self,
        region: str | None,
        instance_ids: list[str] | None,
        instance_type: str | None,
    ) -> list[Entity]:
        out: list[Entity] = []
        for entity in self._live.values():
            if region and (entity.region or "").lower() != region.lower():
                continue
            if instance_ids and entity.provider_entity_id not in instance_ids:
                continue
            if instance_type and entity.configuration.get("instance_type", "").lower() != instance_type.lower():
                continue
            snap = self._stamp(deepcopy(entity))
            snap.source = "aws.api"
            snap.last_observed_at = utcnow()
            snap.freshness_status = "fresh"
            out.append(snap)
        return out

    def _describe_instances_live(
        self,
        region: str | None,
        instance_ids: list[str] | None,
        instance_type: str | None,
    ) -> list[Entity]:
        if not region:
            raise ValueError("region is required for live DescribeInstances")
        client = self._client("ec2", region)
        kwargs: dict[str, Any] = {}
        if instance_ids:
            kwargs["InstanceIds"] = instance_ids
        filters = []
        if instance_type:
            filters.append({"Name": "instance-type", "Values": [instance_type]})
        if filters:
            kwargs["Filters"] = filters
        paginator = client.get_paginator("describe_instances")
        out: list[Entity] = []
        for page in paginator.paginate(**kwargs):
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    out.append(self._instance_from_api(inst, region))
        return out

    def _instance_from_api(self, inst: dict[str, Any], region: str) -> Entity:
        instance_id = inst["InstanceId"]
        name = instance_id
        for tag in inst.get("Tags") or []:
            if tag.get("Key") == "Name":
                name = tag.get("Value") or instance_id
        account = self.account_id or ACCOUNT
        entity = Entity(
            entity_id=Entity.make_id("aws", "aws.ec2.instance", self.tenant_id, account, region, instance_id),
            provider_entity_id=instance_id,
            entity_type="aws.ec2.instance",
            provider="aws",
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            display_name=name,
            account_id=account,
            region=region,
            lifecycle_state=(inst.get("State") or {}).get("Name", "unknown"),
            configuration={
                "instance_type": inst.get("InstanceType"),
                "vpc_id": inst.get("VpcId"),
                "subnet_id": inst.get("SubnetId"),
                "arn": inst.get("InstanceArn")
                or f"arn:aws:ec2:{region}:{account}:instance/{instance_id}",
                "provider_type": "AWS::EC2::Instance",
            },
            source="aws.api",
            last_observed_at=utcnow(),
            freshness_status="fresh",
        )
        return entity

    def search_resources(self, *, region: str, query: str = "*") -> tuple[list[Entity], list[str]]:
        """Enumerate resources in a region. Returns (entities, skipped_reasons)."""
        if self.fixture_mode:
            return self._search_fixture(region), []
        skipped: list[str] = []
        hits, explorer_error = self._search_resource_explorer(region, query)
        if explorer_error:
            skipped.append(explorer_error)
        if hits:
            return hits, skipped
        native_hits, native_skipped = self._search_native(region)
        skipped.extend(native_skipped)
        got = {e.entity_type for e in native_hits}
        cloud_hits, cloud_skipped = self._search_cloudcontrol(region, skip_types=got)
        skipped.extend(cloud_skipped)
        return native_hits + cloud_hits, skipped

    def _search_fixture(self, region: str) -> list[Entity]:
        out: list[Entity] = []
        for entity in self.describe_instances(region=region):
            hit = deepcopy(entity)
            hit.source = "aws.resource-explorer"
            out.append(hit)
        return out

    def _search_resource_explorer(self, region: str, query: str) -> tuple[list[Entity], str | None]:
        try:
            client = self._client("resource-explorer-2", region)
            paginator = client.get_paginator("search")
            hits: list[Entity] = []
            for page in paginator.paginate(QueryString=query or "*"):
                for resource in page.get("Resources", []):
                    hits.append(
                        entity_from_aws_hit(
                            resource_type=resource.get("ResourceType") or "AWS::Unknown::Resource",
                            arn=resource.get("Arn") or "",
                            region=resource.get("Region") or region,
                            account_id=resource.get("OwningAccountId") or self.account_id or ACCOUNT,
                            tenant_id=self.tenant_id,
                            workspace_id=self.workspace_id,
                            extra={"properties": resource.get("Properties") or []},
                            source="aws.resource-explorer",
                        )
                    )
            return hits, None
        except Exception as exc:  # noqa: BLE001 — connector translates vendor errors
            return [], f"resource-explorer: {format_aws_error(exc)}"

    def _search_cloudcontrol(
        self, region: str, skip_types: set[str] | None = None
    ) -> tuple[list[Entity], list[str]]:
        skipped: list[str] = []
        hits: list[Entity] = []
        skip_types = skip_types or set()
        try:
            client = self._client("cloudcontrol", region)
        except Exception as exc:  # noqa: BLE001
            return [], [f"cloudcontrol: {format_aws_error(exc)}"]
        for cfn_type, entity_type in CATALOG_CFN_TYPES.items():
            if entity_type in skip_types:
                continue
            try:
                paginator = client.get_paginator("list_resources")
                for page in paginator.paginate(TypeName=cfn_type):
                    for resource in page.get("ResourceDescriptions", []):
                        ident = resource.get("Identifier") or ""
                        hits.append(
                            entity_from_aws_hit(
                                resource_type=cfn_type,
                                arn=ident,
                                region=region,
                                account_id=self.account_id or ACCOUNT,
                                tenant_id=self.tenant_id,
                                workspace_id=self.workspace_id,
                                display_name=ident,
                                extra={"identifier": ident, "properties": resource.get("Properties")},
                                source="aws.cloudcontrol",
                            )
                        )
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"{entity_type}: cloudcontrol {format_aws_error(exc)}")
        return hits, skipped

    def _search_native(self, region: str) -> tuple[list[Entity], list[str]]:
        hits: list[Entity] = []
        skipped: list[str] = []
        hydrators = (
            ("aws.ec2.instance", lambda: self.describe_instances(region=region)),
            ("aws.ec2.vpc", lambda: self.describe_vpcs(region)),
            ("aws.ec2.subnet", lambda: self.describe_subnets(region)),
            ("aws.ec2.security-group", lambda: self.describe_security_groups(region)),
            ("aws.ec2.volume", lambda: self.describe_volumes(region)),
            ("aws.elasticloadbalancing.lb", lambda: self.describe_load_balancers(region)),
            ("aws.autoscaling.group", lambda: self.describe_auto_scaling_groups(region)),
            ("aws.cloudwatch.alarm", lambda: self.describe_alarms(region)),
            ("aws.s3.bucket", lambda: self.describe_buckets(region)),
            ("aws.rds.db-instance", lambda: self.describe_db_instances(region)),
            ("aws.eks.cluster", lambda: self.describe_eks_clusters(region)),
            ("aws.iam.role", lambda: self.describe_iam_roles(region)),
            ("aws.lambda.function", lambda: self.describe_lambda_functions(region)),
        )
        for entity_type, loader in hydrators:
            try:
                hits.extend(loader())
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"{entity_type}: {format_aws_error(exc)}")
        return hits, skipped

    def _observed(
        self,
        *,
        entity_type: str,
        native_id: str,
        region: str,
        display_name: str,
        state: str,
        configuration: dict,
        source: str = "aws.api",
    ) -> Entity:
        account = self.account_id or ACCOUNT
        resolved = region_for(entity_type, region)
        cfg = dict(configuration)
        return Entity(
            entity_id=Entity.make_id("aws", entity_type, self.tenant_id, account, resolved, native_id),
            provider_entity_id=native_id[:512],
            entity_type=entity_type,
            provider="aws",
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            display_name=display_name[:255],
            account_id=account,
            region=resolved,
            lifecycle_state=state,
            configuration=cfg,
            source=source,
            last_observed_at=utcnow(),
            freshness_status="fresh",
        )

    def describe_vpcs(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("ec2", region)
        out: list[Entity] = []
        for page in client.get_paginator("describe_vpcs").paginate():
            for vpc in page.get("Vpcs", []):
                vpc_id = vpc["VpcId"]
                name = vpc_id
                for tag in vpc.get("Tags") or []:
                    if tag.get("Key") == "Name":
                        name = tag.get("Value") or vpc_id
                out.append(
                    self._observed(
                        entity_type="aws.ec2.vpc",
                        native_id=vpc_id,
                        region=region,
                        display_name=name,
                        state="available" if vpc.get("State") == "available" else vpc.get("State", "unknown"),
                        configuration={"cidr": vpc.get("CidrBlock"), "provider_type": "AWS::EC2::VPC", "vpc_id": vpc_id},
                    )
                )
        return out

    def describe_subnets(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("ec2", region)
        out: list[Entity] = []
        for page in client.get_paginator("describe_subnets").paginate():
            for subnet in page.get("Subnets", []):
                subnet_id = subnet["SubnetId"]
                out.append(
                    self._observed(
                        entity_type="aws.ec2.subnet",
                        native_id=subnet_id,
                        region=region,
                        display_name=subnet_id,
                        state=subnet.get("State", "unknown"),
                        configuration={
                            "vpc_id": subnet.get("VpcId"),
                            "cidr": subnet.get("CidrBlock"),
                            "availability_zone": subnet.get("AvailabilityZone"),
                            "provider_type": "AWS::EC2::Subnet",
                        },
                    )
                )
        return out

    def describe_security_groups(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("ec2", region)
        out: list[Entity] = []
        for page in client.get_paginator("describe_security_groups").paginate():
            for sg in page.get("SecurityGroups", []):
                group_id = sg["GroupId"]
                out.append(
                    self._observed(
                        entity_type="aws.ec2.security-group",
                        native_id=group_id,
                        region=region,
                        display_name=sg.get("GroupName") or group_id,
                        state="available",
                        configuration={"vpc_id": sg.get("VpcId"), "provider_type": "AWS::EC2::SecurityGroup"},
                    )
                )
        return out

    def describe_volumes(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("ec2", region)
        out: list[Entity] = []
        for page in client.get_paginator("describe_volumes").paginate():
            for vol in page.get("Volumes", []):
                volume_id = vol["VolumeId"]
                out.append(
                    self._observed(
                        entity_type="aws.ec2.volume",
                        native_id=volume_id,
                        region=region,
                        display_name=volume_id,
                        state=vol.get("State", "unknown"),
                        configuration={
                            "size": vol.get("Size"),
                            "volume_type": vol.get("VolumeType"),
                            "provider_type": "AWS::EC2::Volume",
                        },
                    )
                )
        return out

    def describe_load_balancers(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("elbv2", region)
        out: list[Entity] = []
        for page in client.get_paginator("describe_load_balancers").paginate():
            for lb in page.get("LoadBalancers", []):
                name = lb.get("LoadBalancerName") or lb.get("LoadBalancerArn", "")
                out.append(
                    self._observed(
                        entity_type="aws.elasticloadbalancing.lb",
                        native_id=name,
                        region=region,
                        display_name=name,
                        state=lb.get("State", {}).get("Code", "unknown") if isinstance(lb.get("State"), dict) else "unknown",
                        configuration={
                            "arn": lb.get("LoadBalancerArn"),
                            "vpc_id": lb.get("VpcId"),
                            "scheme": lb.get("Scheme"),
                            "provider_type": "AWS::ElasticLoadBalancingV2::LoadBalancer",
                        },
                    )
                )
        return out

    def describe_auto_scaling_groups(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("autoscaling", region)
        out: list[Entity] = []
        for page in client.get_paginator("describe_auto_scaling_groups").paginate():
            for group in page.get("AutoScalingGroups", []):
                name = group["AutoScalingGroupName"]
                out.append(
                    self._observed(
                        entity_type="aws.autoscaling.group",
                        native_id=name,
                        region=region,
                        display_name=name,
                        state="active",
                        configuration={
                            "arn": group.get("AutoScalingGroupARN"),
                            "min_size": group.get("MinSize"),
                            "max_size": group.get("MaxSize"),
                            "desired": group.get("DesiredCapacity"),
                            "provider_type": "AWS::AutoScaling::AutoScalingGroup",
                        },
                    )
                )
        return out

    def describe_alarms(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("cloudwatch", region)
        out: list[Entity] = []
        for page in client.get_paginator("describe_alarms").paginate():
            for alarm in page.get("MetricAlarms", []):
                name = alarm["AlarmName"]
                out.append(
                    self._observed(
                        entity_type="aws.cloudwatch.alarm",
                        native_id=name,
                        region=region,
                        display_name=name,
                        state=alarm.get("StateValue", "unknown"),
                        configuration={
                            "arn": alarm.get("AlarmArn"),
                            "metric": alarm.get("MetricName"),
                            "provider_type": "AWS::CloudWatch::Alarm",
                        },
                    )
                )
        return out

    def describe_buckets(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("s3", region)
        out: list[Entity] = []
        for bucket in client.list_buckets().get("Buckets", []):
            name = bucket["Name"]
            out.append(
                self._observed(
                    entity_type="aws.s3.bucket",
                    native_id=name,
                    region=region,
                    display_name=name,
                    state="available",
                    configuration={"provider_type": "AWS::S3::Bucket"},
                )
            )
        return out

    def describe_db_instances(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("rds", region)
        out: list[Entity] = []
        for page in client.get_paginator("describe_db_instances").paginate():
            for db in page.get("DBInstances", []):
                ident = db["DBInstanceIdentifier"]
                out.append(
                    self._observed(
                        entity_type="aws.rds.db-instance",
                        native_id=ident,
                        region=region,
                        display_name=ident,
                        state=db.get("DBInstanceStatus", "unknown"),
                        configuration={
                            "engine": db.get("Engine"),
                            "class": db.get("DBInstanceClass"),
                            "provider_type": "AWS::RDS::DBInstance",
                        },
                    )
                )
        return out

    def describe_eks_clusters(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("eks", region)
        out: list[Entity] = []
        names = []
        for page in client.get_paginator("list_clusters").paginate():
            names.extend(page.get("clusters", []))
        for name in names:
            desc = client.describe_cluster(name=name).get("cluster") or {}
            out.append(
                self._observed(
                    entity_type="aws.eks.cluster",
                    native_id=name,
                    region=region,
                    display_name=name,
                    state=desc.get("status", "unknown"),
                    configuration={"arn": desc.get("arn"), "version": desc.get("version"), "provider_type": "AWS::EKS::Cluster"},
                )
            )
        return out

    def describe_iam_roles(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("iam", "us-east-1")
        out: list[Entity] = []
        for page in client.get_paginator("list_roles").paginate():
            for role in page.get("Roles", []):
                name = role["RoleName"]
                out.append(
                    self._observed(
                        entity_type="aws.iam.role",
                        native_id=name,
                        region=region,
                        display_name=name,
                        state="available",
                        configuration={"arn": role.get("Arn"), "provider_type": "AWS::IAM::Role"},
                    )
                )
        return out

    def describe_lambda_functions(self, region: str) -> list[Entity]:
        if self.fixture_mode:
            return []
        client = self._client("lambda", region)
        out: list[Entity] = []
        for page in client.get_paginator("list_functions").paginate():
            for fn in page.get("Functions", []):
                name = fn["FunctionName"]
                out.append(
                    self._observed(
                        entity_type="aws.lambda.function",
                        native_id=name,
                        region=region,
                        display_name=name,
                        state=fn.get("State", "Active"),
                        configuration={
                            "arn": fn.get("FunctionArn"),
                            "runtime": fn.get("Runtime"),
                            "provider_type": "AWS::Lambda::Function",
                        },
                    )
                )
        return out

    def stop_instances(self, instance_id: str, idempotency_key: str | None = None) -> Entity:
        if not self.fixture_mode:
            raise PermissionError("live stop is not enabled in this slice")
        entity = self._live[instance_id]
        if entity.lifecycle_state in {"stopped", "stopping"}:
            return deepcopy(entity)
        entity.lifecycle_state = "stopping"
        entity.last_observed_at = utcnow()
        entity.source = "aws.api"
        entity.configuration["last_stop_key"] = idempotency_key
        return deepcopy(entity)
