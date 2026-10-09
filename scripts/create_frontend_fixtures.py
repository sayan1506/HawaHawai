"""Isolated SIMULATION fixtures from the unchanged backend; never deploy these."""
import json
import sys
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend/tests'), str(ROOT / 'backend'), str(ROOT)]
from test_safety import decision, environment, snapshot, SCHOOL, NOW
from agent.explanations import render

target = ROOT / 'frontend/tests/fixtures'
target.mkdir(exist_ok=True)
contract = json.loads((ROOT / 'contracts/openapi.json').read_text())


def save(name, schema, value):
    check = {**contract, '$ref': '#/components/schemas/' + schema}
    Draft202012Validator(check, format_checker=FormatChecker()).validate(value)
    (target / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


save('school-simulation', 'SchoolProfile', SCHOOL)
cases = [decision(50, snapshot(), True), decision(174), decision(201), decision(50)]
for d in cases:
    save(d['decision'] + '-simulation', 'Verdict', d)
save('advisory-simulation', 'Advisory', render(SCHOOL, cases[1], None, 'rule_template', NOW.isoformat(), ['SIMULATION ONLY'], 'miss'))
air, forecast, _ = environment(174)
save('air-simulation', 'AirReading', air)
save('forecast-simulation', 'Forecast', forecast)
print('Created schema-validated simulation fixtures only; no network or AWS writes')
