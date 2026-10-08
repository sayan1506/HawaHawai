"""Capture and compare secret-free Docker, CloudFormation, and Git baselines.

This script only invokes read APIs. Snapshot files are generated evidence under .local.
"""
import argparse
import hashlib
import itertools
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"


def run(*args):
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=90,
                            env={**os.environ, "AWS_PAGER": "", "GIT_OPTIONAL_LOCKS": "0"})
    if result.returncode:
        raise RuntimeError(f"Read-only command failed: {' '.join(args[:3])} (exit {result.returncode})")
    return result.stdout.strip()


def aws(*args):
    return json.loads(run("aws", *args, "--profile", "hawahawai", "--region", "us-east-1", "--output", "json", "--no-cli-pager"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def docker_snapshot():
    containers = {}
    for container_id in run("docker", "ps", "-aq", "--no-trunc").splitlines():
        info = json.loads(run("docker", "inspect", container_id))[0]
        if info["Name"].lstrip("/").startswith("hawahawai-"):
            continue
        containers[container_id] = {
            "name": info["Name"].lstrip("/"), "image": info["Image"],
            "config_hash": digest(info["Config"]), "host_config_hash": digest(info["HostConfig"]),
            "state": info["State"]["Status"], "started_at": info["State"]["StartedAt"],
            "restart_count": info["RestartCount"], "mounts_hash": digest(info["Mounts"]),
        }
    images = {}
    for image_id in sorted(set(run("docker", "image", "ls", "-aq", "--no-trunc").splitlines())):
        info = json.loads(run("docker", "image", "inspect", image_id))[0]
        images[image_id] = {"tags": sorted(info.get("RepoTags") or []), "digests": sorted(info.get("RepoDigests") or [])}
    networks = {}
    for network_id in run("docker", "network", "ls", "-q", "--no-trunc").splitlines():
        info = json.loads(run("docker", "network", "inspect", network_id))[0]
        if info["Name"].startswith("hawahawai-"):
            continue
        networks[network_id] = {"name": info["Name"], "hash": digest(info)}
    volumes = {}
    for volume_name in run("docker", "volume", "ls", "-q").splitlines():
        volumes[volume_name] = digest(json.loads(run("docker", "volume", "inspect", volume_name))[0])
    return {"containers": containers, "images": images, "networks": networks, "volumes": volumes}


def aws_snapshot():
    identity = aws("sts", "get-caller-identity")
    if identity["Account"] != "649437299529":
        raise RuntimeError("Wrong AWS account")
    stacks = {}
    for item in aws("cloudformation", "describe-stacks")["Stacks"]:
        name = item["StackName"]
        if name.startswith("HawaHawai"):
            continue
        resources = aws("cloudformation", "describe-stack-resources", "--stack-name", name)["StackResources"]
        template = aws("cloudformation", "get-template", "--stack-name", name)["TemplateBody"]
        event = aws("cloudformation", "describe-stack-events", "--stack-name", name)["StackEvents"][0]["EventId"]
        lambdas = {}
        for resource in resources:
            if resource["ResourceType"] == "AWS::Lambda::Function":
                config = aws("lambda", "get-function-configuration", "--function-name", resource["PhysicalResourceId"])
                lambdas[resource["PhysicalResourceId"]] = digest(config)
        stacks[name] = {"stack_hash": digest(item), "resources_hash": digest(resources), "template_hash": digest(template), "latest_event": event, "lambda_config_hashes": lambdas}
    return {"account": identity["Account"], "stacks": stacks}


def snapshot():
    return {"captured_at": datetime.now(timezone.utc).isoformat(), "docker": docker_snapshot(), "aws": aws_snapshot(),
            "git": {"head": run("git", "rev-parse", "HEAD"), "reflog": run("git", "reflog", "--format=%H %gs"),
                    "index_hash": hashlib.sha256((ROOT / ".git" / "index").read_bytes()).hexdigest()}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["before", "after"])
    parser.add_argument("--phase", default="", choices=["", "phase1", "phase2"])
    args = parser.parse_args()
    LOCAL.mkdir(exist_ok=True)
    current = snapshot()
    prefix = f"{args.phase}-" if args.phase else ""
    target = LOCAL / f"{prefix}isolation-{args.mode}.json"
    if args.mode == "before" and target.exists():
        raise RuntimeError("Baseline already exists; refusing to overwrite it")
    target.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {args.mode}: {len(current['docker']['containers'])} containers, {len(current['docker']['images'])} images, {len(current['docker']['networks'])} networks, {len(current['docker']['volumes'])} volumes")
    if args.mode == "after":
        before = json.loads((LOCAL / f"{prefix}isolation-before.json").read_text(encoding="utf-8"))
        differences = []
        order_only_differences = []
        for category, records in before["docker"].items():
            for key, value in records.items():
                observed = current["docker"][category].get(key)
                if observed != value:
                    # Docker may enumerate identical mounts in a different order.
                    # Preserve the original baseline and require cryptographic proof
                    # that a permutation of the current full definitions reproduces it.
                    if category == "containers" and observed is not None:
                        changed = {field for field in value if value[field] != observed.get(field)}
                        if changed == {"mounts_hash"}:
                            mounts = json.loads(run("docker", "inspect", key))[0]["Mounts"]
                            if len(mounts) <= 8 and any(digest(list(order)) == value["mounts_hash"] for order in itertools.permutations(mounts)):
                                order_only_differences.append(f"Container {value['name']}: same complete mount definitions, reordered by Docker")
                                continue
                    differences.append(f"Docker {category}: {key}")
        for category in ("aws", "git"):
            if current[category] != before[category]:
                differences.append(category)
        for category in ("containers", "images", "networks", "volumes"):
            for key, value in current["docker"][category].items():
                if key in before["docker"][category]:
                    continue
                names = value["tags"] if category == "images" else [value["name"]] if category != "volumes" else [key]
                if not names or any(not name.startswith("hawahawai-") for name in names):
                    differences.append(f"New Docker resource lacks prefix: {category} {key}")
        result = {"passed": not differences, "differences": differences, "order_only_differences": order_only_differences}
        (LOCAL / f"{prefix}isolation-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
        return int(bool(differences))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
