"""AWS skills: how-to, not boto3. Tools run only through the harness."""

SKILLS = {
    "aws.compute.instance.list": {
        "operation_id": "compute.instance.list",
        "tools": ["aws.ec2.describe_instances"],
        "uses_llm": False,
    },
    "aws.compute.instance.diagnose": {
        "operation_id": "compute.instance.read",
        "tools": ["aws.ec2.describe_instances", "aws.cloudwatch.get_metric_statistics"],
        "uses_llm": False,
    },
    "aws.compute.instance.stop": {
        "operation_id": "compute.instance.stop",
        "tools": ["aws.ec2.describe_instances", "aws.ec2.stop_instances"],
        "uses_llm": False,
    },
}
