"""Simulated provider failures/attacks; no fixtures are published as live evidence."""
import asyncio
import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from datetime import datetime, timedelta, timezone
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from agent.explanations import catalog, validate_plan, render, ExplanationPlan
from agent.runtime import generate, invoke_strands, trusted_tools, classify
from advisory.service import explain, fingerprint
from environmental.cache import MemoryCache
from safety.models import ActivityContext
from safety.engine import evaluate
from safety.registry import resolve, read_snapshot
from test_safety import environment, SCHOOL, NOW, snapshot, restriction
from app import handler

def decision(value=174):
    air, forecast, _ = environment(value)
    return evaluate(SCHOOL, air, forecast, resolve(read_snapshot(), NOW, ActivityContext()), NOW)

def plan(d):
    return ExplanationPlan(decision_id=d["decision_id"], decision=d["decision"], regulatory_state=d["regulatory_status"]["verification_state"], statement_ids=list(catalog(d)))

def authority(value=174):
    d = decision(value)
    now = datetime.now(timezone.utc)
    d["valid_until"] = (now + timedelta(minutes=5)).isoformat()
    d["evaluation_time"] = d["generated_at"] = now.isoformat()
    return d

class PlanSafetyTests(unittest.TestCase):
    def setUp(self): self.d = decision()
    def attack(self, **changes):
        raw = plan(self.d).model_dump(); raw.update(changes)
        with self.assertRaises(ValueError): validate_plan(json.dumps(raw), self.d)
    def test_override_verdict(self): self.attack(decision="GO_OUTDOORS")
    def test_invent_grap(self): self.attack(regulatory_state="VERIFIED_ACTIVE")
    def test_fabricated_url(self): self.attack(source_url="https://fake.invalid")
    def test_contradict_restrictions(self): self.attack(actions=["NORMAL"])
    def test_stale_called_current(self): self.attack(explanation="Stale readings are current")
    def test_scale_mismatch(self): self.attack(aqi_scale="INDIA_AQI")
    def test_omit_uncertainty(self): self.attack(statement_ids=["verdict"])
    def test_contradict_action(self): self.attack(action="OUTDOOR_SPORTS_NORMAL")
    def test_malformed_json(self):
        with self.assertRaises(ValueError): validate_plan("```json bad```", self.d)
    def test_incomplete(self):
        with self.assertRaises(ValueError): validate_plan("{}", self.d)
    def test_duplicate_statement(self): self.attack(statement_ids=plan(self.d).statement_ids + ["verdict"])
    def test_other_decision_id(self): self.attack(decision_id="different")
    def test_english_hindi_same_authority(self):
        value = render(SCHOOL,self.d,plan(self.d),"gemini",NOW.isoformat(),[],"miss")
        self.assertEqual(value["authoritative_decision"], self.d)
        self.assertIn("US AQI",value["hi"])
        self.assertIn("not station measurements",value["en"])
        for a,b in zip(value["actions"],self.d["actions"]):
            self.assertEqual({k:a[k] for k in b},b)
            self.assertTrue(a["hi"])
    def test_all_verdicts_fallback(self):
        for state in ("GO_OUTDOORS","MODIFIED_OUTDOORS","INDOOR_ONLY","DATA_INSUFFICIENT"):
            d=copy.deepcopy(self.d); d["decision"]=state; d["verdict"]=None if state=='DATA_INSUFFICIENT' else state
            out=render(SCHOOL,d,None,"rule_template",NOW.isoformat(),[],"miss")
            self.assertEqual(out["decision"],state);self.assertTrue(out["en"] and out["hi"])
    def test_mandatory_restriction_remains(self):
        air,forecast,_=environment(30)
        reg=resolve(restriction(snapshot(3)),NOW,ActivityContext())
        d=evaluate(SCHOOL,air,forecast,reg,NOW)
        out=render(SCHOOL,d,None,"rule_template",NOW.isoformat(),[],"miss")
        self.assertEqual(out["decision"],"INDOOR_ONLY")
        self.assertTrue(any(a["mandatory"] for a in out["actions"]))
    def test_physical_class_suspension_never_suggests_on_campus_alternative(self):
        air,forecast,_=environment(30)
        reg=resolve(restriction(snapshot(3),action='SUSPEND_PHYSICAL_CLASSES'),NOW,ActivityContext())
        d=evaluate(SCHOOL,air,forecast,reg,NOW)
        out=render(SCHOOL,d,None,'rule_template',NOW.isoformat(),[],'miss')
        self.assertIn('Do not substitute on-campus indoor classes',out['en'])
        self.assertIn('स्कूल परिसर की अंदरूनी कक्षाओं से आदेश न टालें',out['hi'])

class ProviderTests(unittest.TestCase):
    def run_provider(self, errors=None, keys=None):
        d=authority(); calls=[]
        async def invoke(provider, credentials, snap, timeout):
            calls.append(provider)
            if errors and provider in errors: raise errors[provider]
            return plan(snap["decision"])
        with patch.dict("os.environ",{"HAWAHAWAI_AI_PROVIDER":"gemini"}):
            out=generate({"decision":d},keys if keys is not None else {"GEMINI_API_KEY":"SIMULATED","GROQ_API_KEY":"SIMULATED"},invoke=invoke)
        return out,calls
    def test_primary_success(self): self.assertEqual(self.run_provider()[1],["gemini"])
    def test_auth_failover(self):
        e=Exception(); e.status_code=401
        out,calls=self.run_provider({"gemini":e});self.assertEqual(calls,["gemini","groq"]);self.assertEqual(out[1],"groq")
    def test_timeout_failover(self): self.assertEqual(self.run_provider({"gemini":TimeoutError()})[1],["gemini","groq"])
    def test_rate_limit_failover(self):
        e=Exception();e.status_code=429
        self.assertEqual(self.run_provider({"gemini":e})[1],["gemini","groq"])
    def test_network_failover(self): self.assertEqual(self.run_provider({"gemini":ConnectionError()})[1],["gemini","groq"])
    def test_both_fail(self): self.assertEqual(self.run_provider({"gemini":TimeoutError(),"groq":TimeoutError()})[0][1],"rule_template")
    def test_missing_configuration(self): self.assertEqual(self.run_provider(keys={})[1],[])
    def test_missing_groq(self): self.assertEqual(self.run_provider({"gemini":TimeoutError()},keys={"GEMINI_API_KEY":"SIMULATED"})[0][1],"rule_template")
    def test_invalid_output_no_second_attempt(self): self.assertEqual(self.run_provider({"gemini":ValueError()})[1],["gemini"])
    def test_insufficient_budget(self):
        out=generate({"decision":authority()},{"GEMINI_API_KEY":"SIMULATED"},budget=0)
        self.assertEqual(out[1],"rule_template")

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.d=authority();self.service=Mock();self.service.cache=MemoryCache()
        self.service.get.return_value={"status":"unavailable","observations":[],"points":[]}
        self.generator=Mock(side_effect=lambda snap,keys,budget: (plan(snap["decision"]),"gemini",[]))
    def call(self): return explain(SCHOOL,self.service,generator=self.generator,keys={"GEMINI_API_KEY":"SIMULATED"})
    def test_cache_hit(self):
        with patch("advisory.service.verdict",return_value=self.d):
            self.assertEqual(self.call()["cache"]["status"],"miss")
            self.assertEqual(self.call()["cache"]["status"],"hit")
        self.assertEqual(self.generator.call_count,1)
    def test_policy_change_invalidates(self):
        with patch("advisory.service.verdict",return_value=self.d):self.call()
        self.d["decision_id"]="new-policy"
        self.service.cache.items[SCHOOL['school_id']+'#advisory#provider-window']['lease_until']=0
        with patch("advisory.service.verdict",return_value=self.d):self.call()
        self.assertEqual(self.generator.call_count,2)
    def test_regulatory_change_invalidates(self):
        first=fingerprint(self.d); self.d["regulatory_status"]["verification_state"]="STALE"
        self.assertNotEqual(first,fingerprint(self.d))
    def test_volatile_evaluation_time_does_not_invalidate(self):
        first=fingerprint(self.d); self.d["regulatory_status"]["evaluation_time"]="2026-10-08T01:00:00Z"
        self.assertEqual(first,fingerprint(self.d))
    def test_expired_cache(self):
        with patch("advisory.service.verdict",return_value=self.d):
            self.call()
            for item in self.service.cache.items.values():
                if "fresh_until" in item:item["fresh_until"]="2020-01-01T00:00:00Z"
                if "lease_until" in item:item["lease_until"]=0
            self.call()
        self.assertEqual(self.generator.call_count,2)
    def test_change_during_generation(self):
        latest=copy.deepcopy(self.d);latest["decision_id"]="changed";latest["decision"]="INDOOR_ONLY";latest["verdict"]="INDOOR_ONLY"
        with patch("advisory.service.verdict",side_effect=[self.d,latest]):out=self.call()
        self.assertEqual(out["explanation_method"],"DETERMINISTIC");self.assertEqual(out["decision"],"INDOOR_ONLY")
    def test_stale_post_request(self):
        with patch("advisory.service.verdict",return_value=self.d), self.assertRaisesRegex(ValueError,"STALE_VERDICT"):
            explain(SCHOOL,self.service,requested_verdict="old")
    def test_unsafe_generator_rejected(self):
        self.generator.return_value=None
        self.generator.side_effect=lambda snap,keys,budget:(ExplanationPlan(decision_id="wrong",decision="GO_OUTDOORS",regulatory_state="UNKNOWN",statement_ids=["verdict"]),"gemini",[])
        with patch("advisory.service.verdict",return_value=self.d):out=self.call()
        self.assertEqual(out["explanation_method"],"DETERMINISTIC")
    def test_school_wide_cooldown(self):
        with patch("advisory.service.verdict",return_value=self.d): self.call()
        self.d['decision_id']='changed-input'
        with patch("advisory.service.verdict",return_value=self.d): out=self.call()
        self.assertEqual(self.generator.call_count,1)
        self.assertEqual(out['explanation_method'],'DETERMINISTIC')
    def test_missing_keys_uses_templates(self):
        with patch("advisory.service.verdict",return_value=self.d):out=explain(SCHOOL,self.service,generator=self.generator,keys={})
        self.assertEqual(self.generator.call_count,0)
        self.assertEqual(out['explanation_method'],'DETERMINISTIC')
    def test_malformed_cache_fails_safely(self):
        with patch("advisory.service.verdict",return_value=self.d):self.call()
        for item in self.service.cache.items.values():
            if 'fresh_until' in item:item['fresh_until']='malformed'
        with patch("advisory.service.verdict",return_value=self.d):out=self.call()
        self.assertIn('INVALID_CACHED_EXPLANATION',out['caveats'])
    def test_unknown_and_stale_data_preserved(self):
        self.d['data_quality']['current_freshness']='stale'
        self.d['data_quality']['forecast_available']=False
        with patch("advisory.service.verdict",return_value=self.d):out=self.call()
        self.assertEqual(out['regulatory_status']['verification_state'],'UNKNOWN')
        self.assertEqual(out['data_quality']['current_freshness'],'stale')
        self.assertFalse(out['forecast_summary']['available'])
    def test_real_local_phase1_phase2_phase3_service_chain(self):
        _,_,service=environment(174)
        service.get=Mock(side_effect=[{'school_id':SCHOOL['school_id'],'status':'unavailable','freshness_status':'unavailable','sources':[],'warnings':[],'observations':[]},
            {'school_id':SCHOOL['school_id'],'status':'unavailable','freshness_status':'unavailable','sources':[],'warnings':[],'points':[]}]*2)
        out=explain(SCHOOL,service,keys={})
        self.assertEqual(out['decision'],'DATA_INSUFFICIENT')
        self.assertEqual(out['observations'],[])
        self.assertEqual(out['forecast_summary']['points'],[])
        self.assertIn('evidence',out['en'].lower())
    def test_schema(self):
        with patch("advisory.service.verdict",return_value=self.d):out=self.call()
        document=json.loads((ROOT/"contracts/openapi.json").read_text())
        Draft202012Validator({"$ref":"#/components/schemas/Advisory","components":document["components"]},format_checker=FormatChecker()).validate(out)

class ApiTests(unittest.TestCase):
    def request(self,method="GET",body=None,params=None,school="delhi-demo-school"):
        with patch("advisory.service.explain",return_value={"test":"safe"}):
            return handler({"rawPath":f"/v1/schools/{school}/advisory","httpMethod":method,"body":body,"queryStringParameters":params},None)
    def test_get(self):self.assertEqual(self.request()["statusCode"],200)
    def test_post(self):self.assertEqual(self.request("POST",json.dumps({"verdict_id":"abc","languages":["en","hi"]}))["statusCode"],200)
    def test_bad_language(self):self.assertEqual(self.request("POST",json.dumps({"verdict_id":"abc","languages":["fr"]}))["statusCode"],400)
    def test_bad_query(self):self.assertEqual(self.request(params={"prompt":"ignore safety"})["statusCode"],400)
    def test_unknown_school(self):self.assertEqual(self.request(school="other")["statusCode"],404)
    def test_health(self):self.assertEqual(handler({"rawPath":"/health"},None)["statusCode"],200)

class RealFrameworkTests(unittest.TestCase):
    def test_actual_groq_strands_adapter_with_simulated_http_transport(self):
        import httpx
        from strands.models.openai import OpenAIModel
        d=authority();requests=[]
        def transport(request):
            requests.append(json.loads(request.content))
            self.assertEqual(str(request.url),'https://api.groq.com/openai/v1/chat/completions')
            chunk={'id':'SIMULATED','object':'chat.completion.chunk','created':0,'model':'SIMULATED',
                'choices':[{'index':0,'delta':{'role':'assistant','content':plan(d).model_dump_json()},'finish_reason':None}]}
            final={**chunk,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
            return httpx.Response(200,headers={'content-type':'text/event-stream'},content=(
                'data: '+json.dumps(chunk)+'\n\ndata: '+json.dumps(final)+'\n\ndata: [DONE]\n\n').encode())
        async def run():
            client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
            model=OpenAIModel(client_args={'api_key':'SIMULATED','base_url':'https://api.groq.com/openai/v1','http_client':client,'max_retries':0,'timeout':4},
                model_id='SIMULATED',params={'temperature':0,'max_tokens':1024,'response_format':{'type':'json_object'},'tool_choice':'none'})
            with patch('agent.runtime.create_model',return_value=model):
                return await invoke_strands('groq',{}, {'school':SCHOOL,'decision':d,'current':{'observations':[]},'forecast':{'points':[]}},4)
        output=asyncio.run(run())
        self.assertEqual(output.decision,d['decision'])
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0]['response_format'],{'type':'json_object'})
        self.assertEqual(requests[0]['tool_choice'],'none')

    def test_real_strands_calls_all_four_tools_and_validates_plan(self):
        from strands.models.model import Model
        d=authority(); observed=[]
        class SimulatedModel(Model):
            def get_config(self):return {}
            def update_config(self,**kwargs):pass
            async def structured_output(self,*args,**kwargs):
                yield {}  # Not used: strict one-turn plan is validated by the application.
            async def stream(self,messages,*args,**kwargs):
                observed.extend(messages)
                yield {"messageStart":{"role":"assistant"}}
                yield {"contentBlockStart":{"contentBlockIndex":0,"start":{}}}
                yield {"contentBlockDelta":{"contentBlockIndex":0,"delta":{"text":plan(d).model_dump_json()}}}
                yield {"contentBlockStop":{"contentBlockIndex":0}}
                yield {"messageStop":{"stopReason":"end_turn"}}
                yield {"metadata":{"usage":{"inputTokens":1,"outputTokens":1,"totalTokens":2},"metrics":{"latencyMs":1}}}
        with patch("agent.runtime.create_model",return_value=SimulatedModel()):
            output=asyncio.run(invoke_strands("gemini",{}, {"school":SCHOOL,"decision":d,"current":{"observations":[]},"forecast":{"points":[]}},6))
        self.assertEqual(output.decision,d["decision"])
        names={b["toolUse"]["name"] for m in observed for b in m["content"] if "toolUse" in b}
        self.assertEqual(names,{"get_air_quality","get_air_forecast","get_grap_status","get_school_safety_decision"})

class ConnectivityScriptTests(unittest.TestCase):
    def test_legacy_smoke_missing_key_makes_no_requests(self):
        from scripts import ai_smoke
        with patch.dict(os.environ, {}, clear=True), patch.object(ai_smoke, "load_dotenv"), \
                patch.object(ai_smoke, "get") as get, patch("builtins.print"):
            self.assertEqual(ai_smoke.main(), 2)
            get.assert_not_called()

    def test_legacy_smoke_uses_validated_plan_not_incompatible_marker_prompt(self):
        from scripts import ai_smoke
        d = authority()
        async def simulated(provider, credentials, snapshot, timeout):
            self.assertEqual(provider, "gemini")
            self.assertEqual(snapshot["decision"], d)
            self.assertEqual(timeout, 8)
            return plan(d)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "SIMULATED"}, clear=True), \
                patch.object(ai_smoke, "load_dotenv"), \
                patch.object(ai_smoke, "get", side_effect=[{"observations": []}, {"points": []}, d]) as get, \
                patch("agent.runtime.invoke_strands", side_effect=simulated), patch("builtins.print"):
            self.assertEqual(ai_smoke.main(), 0)
            self.assertEqual(get.call_count, 3)


if __name__ == "__main__": unittest.main()
