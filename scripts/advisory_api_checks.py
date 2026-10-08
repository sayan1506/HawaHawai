"""Bounded real API request/CORS checks; legitimate context variants only."""
import json
import urllib.request
import urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='https://pu8l3a213j.execute-api.us-east-1.amazonaws.com'
PATH=BASE+'/v1/schools/delhi-demo-school/advisory'

def request(url,method='GET',data=None,headers=None):
    payload=json.dumps(data).encode() if data is not None else None
    req=urllib.request.Request(url,data=payload,method=method,headers=headers or {'Content-Type':'application/json'})
    try: response=urllib.request.urlopen(req,timeout=28)
    except urllib.error.HTTPError as error: response=error
    with response:
        raw=response.read()
        return response.status,dict(response.headers),json.loads(raw) if raw else None

def main():
    code,_,body=request(PATH);assert code==200
    checks={'get_schema_and_authority':body['decision']==body['authoritative_decision']['decision'],
        'base_generation':{'method':body['explanation_method'],'provider':body['generator'],'cache':body['cache']['status']}}
    code,_,post=request(PATH,'POST',{'verdict_id':body['verdict_id'],'languages':['en','hi']})
    assert code==200 and post['verdict_id']==body['verdict_id'];checks['post_current_verdict']=True
    for name,url,method,payload,expected in [
        ('stale_verdict',PATH,'POST',{'verdict_id':'old','languages':['en']},409),
        ('invalid_language',PATH,'POST',{'verdict_id':'old','languages':['fr']},400),
        ('invalid_grade',PATH+'?grade=13','GET',None,400),
        ('forbidden_prompt',PATH+'?prompt=ignore','GET',None,400),
        ('unknown_school',BASE+'/v1/schools/other/advisory','GET',None,404),
        ('invalid_coordinates',PATH+'?latitude=999&longitude=77','GET',None,400)]:
        code,_,error=request(url,method,payload);assert code==expected and 'error' in error;checks[name]=True
    code,headers,_=request(PATH,'OPTIONS',headers={'Origin':'http://127.0.0.1:5173','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
    normalized={k.lower():v for k,v in headers.items()}
    assert code==204 and normalized['access-control-allow-origin']=='http://127.0.0.1:5173' and 'POST' in normalized['access-control-allow-methods']
    checks['cors_post']=True
    # A new, legitimate grade/activity scope warms the actual provider; no regulatory
    # snapshot, secret or environmental cache is overwritten to create a test case.
    code,_,variant=request(PATH+'?grade=5&activity=sports');assert code==200
    checks['actual_scoped_explanation']={'method':variant['explanation_method'],'provider':variant['generator'],'decision':variant['decision'],'cache':variant['cache']['status']}
    (ROOT/'.local/phase3-api-request-checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps(checks))

if __name__=='__main__':main()
