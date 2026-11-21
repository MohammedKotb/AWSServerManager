import json
import os
import re
from datetime import datetime, timezone, timedelta
import boto3
from botocore.exceptions import ClientError

ALLOWED_INSTANCE_IDS = {
    x.strip()
    for x in os.environ.get("ALLOWED_INSTANCE_IDS", "").split(",")
    if x.strip()
}
DEFAULT_REGION = os.environ.get("DEFAULT_AWS_REGION", "eu-central-1")
DEFAULT_HOURLY_RATE = float(os.environ.get("DEFAULT_HOURLY_RATE", "0.19"))
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

WINDOWS_INSTANCE_RATES = {
    "t3.micro": 0.015,
    "t3.small": 0.030,
    "t3.medium": 0.060,
    "t3.large": 0.120,
    "t3.xlarge": 0.240,
    "t3a.medium": 0.055,
    "t3a.large": 0.110,
    "m5.large": 0.188,
    "m5.xlarge": 0.376,
    "m6i.large": 0.188,
    "c5.large": 0.177,
    "r5.large": 0.218,
}

INSTANCE_ID_PATTERN = re.compile(r"^i-[a-f0-9]{8,17}$")
REGION_PATTERN = re.compile(r"^[a-z]{2}-[a-z]+-\d+$")


def build_response(status_code, body_dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Headers": "Content-Type,Authorization,x-api-key",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body_dict),
    }


def validate_instance_and_region(instance_id, region):
    if not instance_id or not INSTANCE_ID_PATTERN.match(instance_id):
        return "Invalid or missing EC2 instanceId."
    if ALLOWED_INSTANCE_IDS and instance_id not in ALLOWED_INSTANCE_IDS:
        return "Instance ID is not authorized for control."
    if not region or not REGION_PATTERN.match(region):
        return "Invalid AWS region."
    return None


def resolve_hourly_rate(instance_obj):
    for tag in instance_obj.get("Tags", []):
        if tag.get("Key") == "HourlyRate":
            try:
                return float(tag.get("Value"))
            except ValueError:
                pass
    instance_type = instance_obj.get("InstanceType", "")
    if instance_type in WINDOWS_INSTANCE_RATES:
        return WINDOWS_INSTANCE_RATES[instance_type]
    return DEFAULT_HOURLY_RATE


def handle_get_status(instance_id, region):
    ec2 = boto3.client("ec2", region_name=region)
    resp = ec2.describe_instances(InstanceIds=[instance_id])

    reservations = resp.get("Reservations", [])
    if not reservations or not reservations[0].get("Instances"):
        return build_response(404, {"error": "EC2 instance not found."})

    instance = reservations[0]["Instances"][0]
    state_name = instance.get("State", {}).get("Name", "unknown").lower()

    launch_time_iso = None
    if state_name == "running" and instance.get("LaunchTime"):
        dt = instance["LaunchTime"]
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        launch_time_iso = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    hourly_rate = resolve_hourly_rate(instance)

    return build_response(
        200,
        {
            "instanceId": instance_id,
            "state": state_name,
            "launchTime": launch_time_iso,
            "hourlyRate": round(hourly_rate, 4),
        },
    )


def handle_start(instance_id, region):
    ec2 = boto3.client("ec2", region_name=region)
    ec2.start_instances(InstanceIds=[instance_id])
    return build_response(200, {"success": True, "message": "EC2 start requested"})


def handle_stop(instance_id, region):
    ec2 = boto3.client("ec2", region_name=region)
    ec2.stop_instances(InstanceIds=[instance_id])
    return build_response(200, {"success": True, "message": "EC2 stop requested"})


def handle_get_cost():
    ce = boto3.client("ce", region_name="us-east-1")
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    tomorrow_str = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
    month_start_str = now_utc.replace(day=1).strftime("%Y-%m-%d")

    today_resp = ce.get_cost_and_usage(
        TimePeriod={"Start": today_str, "End": tomorrow_str},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )
    today_metric = (
        today_resp.get("ResultsByTime", [{}])[0]
        .get("Total", {})
        .get("UnblendedCost", {})
    )
    today_amount = float(today_metric.get("Amount", 0.0))
    currency = today_metric.get("Unit", "USD")

    month_resp = ce.get_cost_and_usage(
        TimePeriod={"Start": month_start_str, "End": tomorrow_str},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )
    month_metric = (
        month_resp.get("ResultsByTime", [{}])[0]
        .get("Total", {})
        .get("UnblendedCost", {})
    )
    month_amount = float(month_metric.get("Amount", 0.0))

    return build_response(
        200,
        {
            "today": round(today_amount, 2),
            "month": round(month_amount, 2),
            "currency": currency,
            "updatedAt": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )


def lambda_handler(event, context):
    http_method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod", "")
    ).upper()
    raw_path = event.get("rawPath") or event.get("path") or ""

    if http_method == "OPTIONS":
        return build_response(200, {"ok": True})

    query_params = event.get("queryStringParameters") or {}
    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except json.JSONDecodeError:
            return build_response(400, {"error": "Invalid JSON body."})

    try:
        if raw_path.endswith("/cost") and http_method == "GET":
            return handle_get_cost()

        instance_id = (body.get("instanceId") or query_params.get("instanceId") or "").strip()
        region = (body.get("region") or query_params.get("region") or DEFAULT_REGION).strip()

        validation_error = validate_instance_and_region(instance_id, region)
        if validation_error:
            return build_response(400, {"error": validation_error})

        if raw_path.endswith("/status") and http_method == "GET":
            return handle_get_status(instance_id, region)

        if raw_path.endswith("/start") and http_method == "POST":
            return handle_start(instance_id, region)

        if raw_path.endswith("/stop") and http_method == "POST":
            return handle_stop(instance_id, region)

        return build_response(404, {"error": "Route not found."})

    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "AWSClientError")
        if code == "InvalidInstanceID.NotFound":
            return build_response(404, {"error": "EC2 instance ID was not found in this region."})
        if code in ("UnauthorizedOperation", "AccessDeniedException"):
            return build_response(403, {"error": "Lambda IAM role lacks permission for this action."})
        return build_response(502, {"error": f"AWS service error ({code})."})
    except Exception:
        return build_response(500, {"error": "Unexpected internal server error."})
