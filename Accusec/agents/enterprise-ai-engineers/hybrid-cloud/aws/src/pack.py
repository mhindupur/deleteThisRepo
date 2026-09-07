from accusec.shared.domain.models import Entity

ALLOWED_SKILLS = ("aws.compute.instance.list", "aws.compute.instance.diagnose", "aws.compute.instance.stop")
ALLOWED_TOOLS = (
    "aws.sts.get_caller_identity",
    "aws.ec2.describe_instances",
    "aws.ec2.describe_instance_status",
    "aws.cloudwatch.get_metric_statistics",
    "aws.resourceexplorer.search",
    "aws.cloudcontrol.list_resources",
    "aws.ec2.stop_instances",
)


def summarize_list(entities: list[Entity]) -> dict:
    return {
        "count": len(entities),
        "instances": [
            {
                "entity_id": e.entity_id,
                "instance_id": e.provider_entity_id,
                "name": e.display_name,
                "instance_type": e.configuration.get("instance_type"),
                "region": e.region,
                "vpc_id": e.configuration.get("vpc_id"),
                "state": e.lifecycle_state,
            }
            for e in entities
        ],
    }
