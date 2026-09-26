from accusec.shared.domain.models import Entity

ALLOWED_SKILLS = (
    "aws.compute.instance.list",
    "aws.compute.instance.diagnose",
    "aws.compute.instance.stop",
    "aws.compute.instance.start",
)
ALLOWED_TOOLS = (
    "aws.sts.get_caller_identity",
    "aws.ec2.describe_instances",
    "aws.ec2.describe_instance_status",
    "aws.ec2.describe_volumes",
    "aws.cloudwatch.get_metric_statistics",
    "aws.resourceexplorer.search",
    "aws.cloudcontrol.list_resources",
    "aws.ec2.modify_volume",
    "aws.ec2.stop_instances",
    "aws.ec2.start_instances",
)


def attached_instance_ids(entity: Entity) -> list[str]:
    ids: list[str] = []
    for attachment in entity.configuration.get("attachments") or []:
        instance_id = attachment.get("instance_id")
        if instance_id:
            ids.append(instance_id)
    for instance_id in entity.configuration.get("attached_instance_ids") or []:
        if instance_id not in ids:
            ids.append(instance_id)
    return ids


def summarize_volumes(entities: list[Entity], *, instance_id: str | None = None) -> dict:
    rows = []
    total = 0
    for entity in entities:
        attachments = entity.configuration.get("attachments") or []
        device = attachments[0].get("device") if attachments else entity.configuration.get("device")
        attached = attached_instance_ids(entity)
        size = entity.configuration.get("size")
        if isinstance(size, (int, float)):
            total += int(size)
        rows.append(
            {
                "volume_id": entity.provider_entity_id,
                "name": entity.display_name,
                "size_gb": size,
                "volume_type": entity.configuration.get("volume_type"),
                "device": device,
                "state": entity.lifecycle_state,
                "instance_id": instance_id or (attached[0] if attached else None),
                "region": entity.region,
            }
        )
    return {
        "count": len(rows),
        "volumes": rows,
        "total_size_gb": total,
        "instance_id": instance_id,
    }


def summarize_list(entities: list[Entity]) -> dict:
    if entities and entities[0].entity_type == "aws.ec2.volume":
        return summarize_volumes(entities)
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
