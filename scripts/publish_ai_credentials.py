"""Populate ONLY the CDK-owned HawaHawai secret from ignored local configuration."""
import json
from pathlib import Path
import boto3
from botocore.config import Config
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

def main():
    session=boto3.Session(profile_name="hawahawai",region_name="us-east-1")
    config=Config(connect_timeout=2,read_timeout=4,retries={"total_max_attempts":1})
    assert session.client("sts",config=config).get_caller_identity()["Account"]=="649437299529"
    resources=session.client("cloudformation",config=config).describe_stack_resources(StackName="HawaHawaiDev")["StackResources"]
    owned=[r["PhysicalResourceId"] for r in resources if r["ResourceType"]=="AWS::SecretsManager::Secret" and r["LogicalResourceId"]=="AiCredentials"]
    assert len(owned)==1 and ":secret:hawahawai-dev-ai-credentials-" in owned[0]
    values=dotenv_values(ROOT/"backend/.env")
    data={k:values.get(k,"").strip() for k in ("GEMINI_API_KEY","GROQ_API_KEY")}
    assert data["GEMINI_API_KEY"], "Missing local Gemini configuration"
    session.client("secretsmanager",config=config).put_secret_value(SecretId=owned[0],SecretString=json.dumps(data))
    print("Populated CDK-owned HawaHawai AI credential secret; values are not displayed.")

if __name__=="__main__":main()
