"""Verify already-generated real AI content in an explicit valid school scope."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from advisory_smoke import get, BASE

ROOT=Path(__file__).resolve().parents[1]
prefix=BASE+'/v1/schools/delhi-demo-school'
query='?grade=8&activity=sports'
data=get(prefix+'/advisory'+query)
contract=json.loads((ROOT/'contracts/openapi.json').read_text())
Draft202012Validator({'$ref':'#/components/schemas/Advisory','components':contract['components']},format_checker=FormatChecker()).validate(data)
assert data['explanation_method']=='AI' and data['generator']=='gemini', 'Live AI is not verified by fallback'
decision=get(prefix+'/verdict'+query)
assert data['verdict_id']==decision['decision_id'] and data['decision']==decision['decision']
assert data['en'] and data['hi']
assert len(data['statement_ids'])==len(set(data['statement_ids']))
assert all({k:a[k] for k in b}==b for a,b in zip(data['actions'],data['authoritative_decision']['actions']))
for reading in data['evidence']:
    assert reading['scale']=='US_AQI' and reading['source_type']=='model_forecast' and reading['timestamp']
(ROOT/'.local/phase3-aws-ai-response.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
result={'success':True,'method':data['explanation_method'],'provider':data['generator'],'cache':data['cache']['status'],
    'generated_at':data['generated_at'],'decision':data['decision'],'official_state':data['regulatory_status']['verification_state'],
    'languages':data['languages'],'endpoint':prefix+'/advisory'+query,'authority_matches_actual_verdict':True}
(ROOT/'.local/phase3-aws-ai-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
