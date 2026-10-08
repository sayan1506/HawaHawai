"""Read-only credits/budget inspection with an explicit AWS profile."""
import json
from datetime import datetime, timezone
from pathlib import Path
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]


def main():
    session = boto3.Session(profile_name="hawahawai", region_name="us-east-1")
    config = Config(connect_timeout=10, read_timeout=20, retries={"max_attempts": 0})
    identity = session.client("sts", config=config).get_caller_identity()
    if identity["Account"] != "649437299529":
        raise RuntimeError("Wrong AWS account")
    results = {"budget_creation": "waived_by_user", "checked_at": datetime.now(timezone.utc).isoformat()}
    budgets = session.client("budgets", config=config)
    try:
        result = budgets.describe_budgets(AccountId=identity["Account"])
        results["existing_budgets"] = [{"name": x["BudgetName"], "limit": x["BudgetLimit"]} for x in result.get("Budgets", [])]
    except ClientError as error:
        results["budget_error"] = error.response["Error"]["Code"]
    billing = session.client("billing", config=config)
    if "GetCredits" not in billing.meta.service_model.operation_names:
        results["credit_error"] = "Installed SDK does not support GetCredits; console verification required"
    else:
        try:
            response = billing.get_credits(accountId=identity["Account"], startDate=datetime(2026, 10, 1, tzinfo=timezone.utc))
            results["credits"] = [{k: value for k, value in credit.items() if k in {"creditType", "initialAmount", "remainingAmount", "estimatedAmount", "applicableProductNames", "description", "startDate", "endDate", "creditStatus", "purchaseTypeApplications"}} for credit in response.get("credits", [])]
        except ClientError as error:
            results["credit_error"] = error.response["Error"]["Code"]
    target = ROOT / ".local" / "billing-check.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
