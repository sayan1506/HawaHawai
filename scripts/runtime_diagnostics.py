"""Read only the newest own Lambda stream; print secret-redacted diagnostics."""
import json
from pathlib import Path
import boto3
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
session=boto3.Session(profile_name='hawahawai',region_name='us-east-1')
keys=[v for k,v in dotenv_values(ROOT/'backend/.env').items() if k.endswith('API_KEY') and v]
logs=session.client('logs')
streams=logs.describe_log_streams(logGroupName='hawahawai-dev-health-logs',orderBy='LastEventTime',descending=True,limit=3)['logStreams']
for stream in streams:
    events=logs.get_log_events(logGroupName='hawahawai-dev-health-logs',logStreamName=stream['logStreamName'],limit=40)['events']
    for event in events:
        message=event['message']
        if any(s in message for s in ('ERROR','REPORT RequestId','ai_attempt','ai_usage','ai_stage','advisory_stage','Traceback','Error:','Runtime.')):
            for key in keys:message=message.replace(key,'[REDACTED]')
            print(message[:1800])
