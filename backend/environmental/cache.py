"""Application freshness is independent of asynchronous DynamoDB TTL deletion."""
import copy
import json
import threading
import time
import uuid
import logging
import os
import gzip
import base64

LOG = logging.getLogger(__name__)


def cache_failure(code, error):
    LOG.error(json.dumps({"event": "environmental_cache_error", "code": code, "aws_error": getattr(error, "response", {}).get("Error", {}).get("Code", type(error).__name__)}))
    return CacheError(code)


def encode_payload(item):
    raw = json.dumps(item, allow_nan=False, separators=(",", ":")).encode()
    return "gzip:" + base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")


def decode_payload(raw):
    # Backward compatible with the first Phase 1 uncompressed entries.
    if raw.startswith("gzip:"):
        raw = gzip.decompress(base64.b64decode(raw[5:], validate=True)).decode()
    return json.loads(raw)


class CacheError(Exception):
    pass


class MemoryCache:
    def __init__(self):
        self.items = {}
        self.mutex = threading.Lock()

    def get(self, key):
        with self.mutex:
            return copy.deepcopy(self.items.get(key))

    def put(self, key, item):
        with self.mutex:
            self.items[key] = copy.deepcopy(item)

    def put_record(self, key, item, revision=None):
        with self.mutex:
            old = self.items.get(key)
            if old is not None and (revision is None or old.get("revision_epoch", 0) >= revision): return False
            self.items[key] = copy.deepcopy(item)
            return True

    def acquire(self, key, now):
        with self.mutex:
            if self.items.get(key, {}).get("lease_until", 0) > now:
                return None
            token = str(uuid.uuid4())
            self.items[key] = {"lease_until": now + 30, "owner": token}
            return token

    def release(self, key, token):
        with self.mutex:
            if self.items.get(key, {}).get("owner") == token:
                self.items[key]["lease_until"] = 0


class DynamoCache:
    def __init__(self, table, client=None):
        if not table.startswith("hawahawai-"):
            raise CacheError("INVALID_CACHE_TABLE")
        if client is None:
            import boto3
            from botocore.config import Config
            session = boto3.Session(profile_name=None if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else "hawahawai", region_name="us-east-1")
            client = session.client("dynamodb", config=Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 1}))
        self.client, self.table = client, table

    def get(self, key):
        try:
            item = self.client.get_item(TableName=self.table, Key={"cache_key": {"S": key}}, ConsistentRead=True).get("Item")
            return decode_payload(item["payload"]["S"]) if item and "payload" in item else None
        except Exception as error:
            raise cache_failure("CACHE_READ_FAILED", error) from None

    def put(self, key, item):
        try:
            self.client.put_item(TableName=self.table, Item={"cache_key": {"S": key}, "payload": {"S": encode_payload(item)}, "expires_at": {"N": str(int(time.time()) + 86400)}})
        except Exception as error:
            raise cache_failure("CACHE_WRITE_FAILED", error) from None

    def acquire(self, key, now):
        token = str(uuid.uuid4())
        try:
            self.client.update_item(TableName=self.table, Key={"cache_key": {"S": key}}, UpdateExpression="SET lease_until=:until, #owner=:owner, expires_at=:ttl", ConditionExpression="attribute_not_exists(lease_until) OR lease_until < :now", ExpressionAttributeNames={"#owner": "owner"}, ExpressionAttributeValues={":until": {"N": str(int(now) + 30)}, ":owner": {"S": token}, ":ttl": {"N": str(int(now) + 86400)}, ":now": {"N": str(int(now))}})
            return token
        except Exception as error:
            if getattr(error, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return None
            raise cache_failure("CACHE_LOCK_FAILED", error) from None

    def put_record(self, key, item, revision=None):
        values = {"cache_key": {"S": key}, "payload": {"S": encode_payload(item)},
                  "expires_at": {"N": str(int(time.time()) + 7 * 86400)}}
        arguments = {"TableName": self.table, "Item": values, "ConditionExpression": "attribute_not_exists(cache_key)"}
        if revision is not None:
            values["revision_epoch"] = {"N": str(revision)}
            arguments.update(ConditionExpression="attribute_not_exists(revision_epoch) OR revision_epoch < :revision",
                             ExpressionAttributeValues={":revision": {"N": str(revision)}})
        try:
            self.client.put_item(**arguments)
            return True
        except Exception as error:
            if getattr(error, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException": return False
            raise cache_failure("RECORD_WRITE_FAILED", error) from None

    def release(self, key, token):
        try:
            self.client.update_item(TableName=self.table, Key={"cache_key": {"S": key}}, UpdateExpression="SET lease_until=:zero", ConditionExpression="#owner=:owner", ExpressionAttributeNames={"#owner": "owner"}, ExpressionAttributeValues={":zero": {"N": "0"}, ":owner": {"S": token}})
        except Exception:
            # The lease expires automatically; failure must not replace a successful response.
            pass
