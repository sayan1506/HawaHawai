"""Private admin profile initialization/CAS update. Preview unless --write."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
from persistence.models import profile_record, profile_key, validate_profile, digest
from environmental.cache import encode_payload, decode_payload
TABLE = 'hawahawai-dev-environment-cache'

def initialize(client, profile, expected_fingerprint=None):
    validate_profile(profile)
    previous = client.get_item(TableName=TABLE, Key={'cache_key': {'S': profile_key()}}, ConsistentRead=True).get('Item')
    arguments = {'TableName': TABLE, 'Item': {'cache_key': {'S': profile_key()},
                 'payload': {'S': encode_payload(profile_record(profile, datetime.now(timezone.utc).isoformat()))}},
                 'ConditionExpression': 'attribute_not_exists(cache_key)'}
    if previous:
        old = decode_payload(previous['payload']['S'])
        if old.get('profile_fingerprint') == digest(profile) and old.get('profile') == profile: return 'unchanged'
        if expected_fingerprint is None or old.get('profile_fingerprint') != expected_fingerprint:
            raise ValueError('Explicit matching --expected-fingerprint is required for an existing record update')
        arguments.update(ConditionExpression='payload = :previous', ExpressionAttributeValues={':previous': previous['payload']})
    # No TTL on the school configuration. No delete or infrastructure/IAM change.
    client.put_item(**arguments)
    return 'updated' if previous else 'initialized'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile-file', default='contracts/demo-school.json')
    parser.add_argument('--expected-fingerprint')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    profile = validate_profile(json.loads((ROOT / args.profile_file).read_text(encoding='utf-8')))
    if not args.write:
        print(json.dumps({'preview': True, 'school_id': profile['school_id'], 'profile_fingerprint': digest(profile)})); return
    session = boto3.Session(profile_name='hawahawai', region_name='us-east-1')
    config = Config(connect_timeout=2, read_timeout=4, retries={'total_max_attempts':1})
    assert session.client('sts', config=config).get_caller_identity()['Account'] == '649437299529'
    resources = session.client('cloudformation', config=config).describe_stack_resources(StackName='HawaHawaiDev')['StackResources']
    assert any(r['ResourceType']=='AWS::DynamoDB::Table' and r['PhysicalResourceId']==TABLE for r in resources)
    result = initialize(session.client('dynamodb', config=config), profile, args.expected_fingerprint)
    print(json.dumps({'status':result,'school_id':profile['school_id'],'profile_fingerprint':digest(profile)}))
if __name__=='__main__':main()
