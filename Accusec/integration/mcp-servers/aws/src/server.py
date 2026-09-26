"""Registered AWS MCP tools. Discovery is not trust — harness allowlists these names."""

from __future__ import annotations

from accusec.integration.aws_connector.connector import AwsConnector
from accusec.shared.domain.models import Entity

READ_TOOLS = {
    "aws.sts.get_caller_identity",
    "aws.ec2.describe_instances",
    "aws.ec2.describe_instance_status",
    "aws.ec2.describe_volumes",
    "aws.cloudwatch.get_metric_statistics",
    "aws.resourceexplorer.search",
    "aws.cloudcontrol.list_resources",
}

WRITE_TOOLS = {"aws.ec2.stop_instances", "aws.ec2.start_instances", "aws.ec2.modify_volume"}

ALL_TOOLS = READ_TOOLS | WRITE_TOOLS


class AwsMcpServer:
    def __init__(self, connector: AwsConnector) -> None:
        self.connector = connector

    def call(self, tool: str, arguments: dict) -> dict | list[Entity] | Entity:
        if tool not in ALL_TOOLS:
            raise PermissionError(f"unregistered tool: {tool}")
        if tool == "aws.sts.get_caller_identity":
            return self.connector.get_caller_identity()
        if tool == "aws.resourceexplorer.search":
            hits, skipped = self.connector.search_resources(
                region=arguments["region"],
                query=arguments.get("query") or "*",
            )
            return {"entities": hits, "skipped": skipped}
        if tool == "aws.cloudcontrol.list_resources":
            hits, skipped = self.connector.search_resources(
                region=arguments["region"],
                query=arguments.get("query") or "*",
            )
            return {"entities": hits, "skipped": skipped}
        if tool == "aws.ec2.describe_instances":
            return self.connector.describe_instances(
                region=arguments.get("region"),
                instance_ids=arguments.get("instance_ids"),
                instance_type=arguments.get("instance_type"),
            )
        if tool == "aws.ec2.describe_volumes":
            return self.connector.describe_volumes(
                region=arguments["region"],
                instance_ids=arguments.get("instance_ids"),
                volume_ids=arguments.get("volume_ids"),
            )
        if tool == "aws.ec2.modify_volume":
            return self.connector.modify_volume(
                volume_id=arguments["volume_id"],
                size_gb=int(arguments["size_gb"]),
                region=arguments["region"],
            )
        if tool == "aws.ec2.describe_instance_status":
            instances = self.connector.describe_instances(
                region=arguments.get("region"),
                instance_ids=arguments.get("instance_ids"),
            )
            return [
                {
                    "instance_id": i.provider_entity_id,
                    "state": i.lifecycle_state,
                    "cpu": i.configuration.get("cpu_utilization"),
                }
                for i in instances
            ]
        if tool == "aws.cloudwatch.get_metric_statistics":
            instances = self.connector.describe_instances(
                instance_ids=arguments.get("instance_ids"),
            )
            return [
                {
                    "instance_id": i.provider_entity_id,
                    "cpu_utilization": i.configuration.get("cpu_utilization"),
                }
                for i in instances
            ]
        if tool == "aws.ec2.stop_instances":
            return self.connector.stop_instances(
                arguments["instance_id"],
                idempotency_key=arguments.get("idempotency_key"),
                region=arguments.get("region"),
            )
        if tool == "aws.ec2.start_instances":
            return self.connector.start_instances(
                arguments["instance_id"],
                idempotency_key=arguments.get("idempotency_key"),
                region=arguments.get("region"),
            )
        raise ValueError(tool)
