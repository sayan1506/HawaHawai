"""Approved bilingual language. The model can order it, never create safety claims."""
from copy import deepcopy
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

EXPLANATION_VERSION = "approved-bilingual-v1"

class ExplanationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision_id: str
    decision: Literal["GO_OUTDOORS", "MODIFIED_OUTDOORS", "INDOOR_ONLY", "DATA_INSUFFICIENT"]
    regulatory_state: Literal["VERIFIED_ACTIVE", "VERIFIED_INACTIVE", "UNKNOWN", "STALE", "CONFLICTING"]
    statement_ids: list[str] = Field(min_length=1, max_length=40)

VERDICTS = {
    "GO_OUTDOORS": ("Outdoor activities meet the documented prerequisites; this is not a guarantee of safe air.", "बाहर की गतिविधियों के लिए तय शर्तें पूरी हैं। यह हवा के सुरक्षित होने की गारंटी नहीं है।"),
    "MODIFIED_OUTDOORS": ("Modify outdoor activities: reduce exertion, allow breaks and offer suitable indoor alternatives.", "बाहर की गतिविधियों में बदलाव करें: मेहनत कम रखें, विश्राम दें और उपयुक्त अंदरूनी विकल्प उपलब्ध कराएँ।"),
    "INDOOR_ONLY": ("Use suitable indoor alternatives or reschedule activities. This is not automatically a school-closure order.", "गतिविधियाँ उपयुक्त अंदरूनी स्थान पर करें या उनका समय बदलें। इसका अर्थ अपने-आप स्कूल बंद करने का आदेश नहीं है।"),
    "DATA_INSUFFICIENT": ("Required evidence is incomplete. Verify before proceeding outdoors; use a suitable indoor alternative meanwhile.", "ज़रूरी जानकारी अधूरी है। बाहर की गतिविधि से पहले पुष्टि करें; तब तक उपयुक्त अंदरूनी विकल्प चुनें।"),
}
RULES = {
    "MANDATORY_SCHOOL_RESTRICTION": "लागू और सत्यापित स्कूल आदेश का पालन करें; अनुकूल पूर्वानुमान उसे नहीं बदल सकता।",
    "PREVIOUS_RESTRICTION_REVERIFY": "पहले की पाबंदी हटने की पुष्टि नहीं है। पुष्टि तक गतिविधि रोकने की सावधानी बरतें; इसे वर्तमान सत्यापित कानून न मानें।",
    "VERIFIED_GRAP_CHILDREN_ADVISORY": "सत्यापित GRAP सलाह में बच्चों को बाहर की गतिविधियों से बचने को कहा गया है; यह सावधानी है, स्कूल बंद करने का आदेश नहीं।",
    "US_AQI_INDOOR_PRECAUTION": "मान्य US AQI जानकारी 200 से अधिक है। अपनाई गई स्वास्थ्य नीति के अनुसार अंदरूनी विकल्प या समय परिवर्तन चुनें।",
    "US_AQI_MODIFY_PRECAUTION": "मान्य US AQI जानकारी 100 से अधिक है। अपनाई गई स्वास्थ्य नीति के अनुसार मेहनत कम करें, विश्राम दें और संवेदनशील बच्चों को विकल्प दें।",
    "POSITIVE_EVIDENCE_REQUIREMENTS_MET": "नियामक पुष्टि, ताज़ा प्रतिनिधि स्टेशन जानकारी और अगले तीन घंटों का पूर्वानुमान तय शर्तें पूरी करते हैं; सुरक्षा की गारंटी नहीं है।",
    "MISSING_REQUIRED_EVIDENCE": "ज़रूरी नियामक पुष्टि, प्रतिनिधि स्टेशन जानकारी या पूर्वानुमान अधूरा है। बाहर जाने से पहले पुष्टि करें।",
    "MANDATORY_SCHOOL_OPERATIONS": "सूचीबद्ध कक्षाओं के लिए सत्यापित संचालन संबंधी आदेश का पालन करें। हाइब्रिड कक्षाएँ अपने-आप बाहर की गतिविधि पर प्रतिबंध नहीं हैं।",
    "OFFICIAL_ADVISORY_REVIEW": "सलाह के मूल दस्तावेज़ में लागू गतिविधि और अवधि जाँचें; इसे सामान्य स्कूल-बंदी न मानें।",
    "ELEVATED_ACTIVITY_FORECAST": "अगले तीन घंटों में बढ़ा हुआ मॉडल-आधारित US AQI है। यह सावधानी का आधार है, आधिकारिक माप या GRAP लागू होने की पुष्टि नहीं।",
    "REGULATORY_VERIFY_STATUS": "आधिकारिक आदेशों की स्थिति अज्ञात, पुरानी या विरोधाभासी है। वर्तमान आदेशों की मानवीय पुष्टि ज़रूरी है।",
    "MISSING_STATION_OBSERVATIONS": "ताज़ा, मान्य स्टेशन जानकारी उपलब्ध नहीं है। केवल मॉडल के आधार पर बाहर जाने की सकारात्मक अनुमति नहीं दी जाती।",
    "MISSING_FRESH_ACTIVITY_FORECAST": "अगले तीन घंटों का पूरा और ताज़ा पूर्वानुमान उपलब्ध नहीं है।",
    "MODELED_CURRENT_UNAVAILABLE_OR_STALE": "वर्तमान मॉडल जानकारी अनुपलब्ध या पुरानी है; ताज़ा पूर्वानुमान केवल सावधानी का आधार हो सकता है।",
}
ACTION_HI = {
    "VERIFY_BEFORE_PROCEEDING": "बाहर की गतिविधि से पहले आदेश और अधूरी जानकारी की पुष्टि करें; तब तक उपयुक्त अंदरूनी विकल्प रखें।",
    "NORMAL_WITH_CAVEATS": "तय शर्तों के तहत गतिविधि करें; लक्षणों पर नज़र रखें और संवेदनशील बच्चों को विकल्प दें।",
    "MODIFY": "अवधि या मेहनत कम करें, विश्राम दें, लक्षणों पर नज़र रखें और अंदरूनी विकल्प दें।",
    "INDOOR_ALTERNATIVE": "उपयुक्त अंदरूनी विकल्प चुनें या समय बदलें; व्यायाम से पहले अंदर की हवा जाँचें।",
    "ASSESS_INDOOR_ALTERNATIVE": "अंदरूनी विकल्प से पहले वेंटिलेशन, कण-फ़िल्टर और बच्चों की ज़रूरतें जाँचें; अंदर की हवा मापी नहीं गई है।",
    "VERIFY_STATUS": "वर्तमान CAQM और दिल्ली स्कूल आदेशों की पुष्टि करें; गतिविधि की सलाह को स्कूल-बंदी का आदेश न मानें।",
    "REVIEW_ORDERS": "वर्तमान CAQM और दिल्ली स्कूल आदेशों तथा लागू अवधि की समीक्षा करें।",
    "FOLLOW_PHYSICAL_CLASS_ORDER": "भौतिक कक्षाएँ स्थगित हों तो स्कूल परिसर की अंदरूनी गतिविधि से आदेश न टालें। सूचीबद्ध कक्षाओं के मूल आदेश का पालन करें।",
    "REVIEW_SCHOOL_OPERATIONS": "गतिविधि से पहले कक्षा-विशिष्ट हाइब्रिड या प्रशासनिक आवश्यकताओं का पालन करें।",
    "STRUCTURED_REASONS_READY": "संदेश में इन्हीं तय कारणों, कार्रवाइयों और सीमाओं का उपयोग करें।",
    "HYBRID_CLASSES": "सूचीबद्ध कक्षाओं के लिए उद्धृत आदेश के अनुसार हाइब्रिड व्यवस्था का पालन करें।",
    "SUSPEND_OUTDOOR": "उद्धृत आदेश के दायरे और कक्षाओं के अनुसार बाहर की गतिविधियाँ स्थगित करें।",
    "SUSPEND_PHYSICAL_CLASSES": "उद्धृत आदेश के अनुसार सूचीबद्ध कक्षाओं की भौतिक पढ़ाई स्थगित करें।",
    "REVIEW_ORDER": "उद्धृत आदेश की ठीक शर्तें, कक्षाएँ और अवधि जाँचें।",
    "RESCHEDULE_SPORTS": "उद्धृत सलाह के अनुसार खेलों का समय बदलने की समीक्षा करें।",
    "AVOID_OUTDOOR_ADVISORY": "उद्धृत सलाह के अनुसार बाहर की गतिविधियों से बचने का विकल्प अपनाएँ; इसे अनिवार्य बंदी न मानें।",
}

def catalog(decision):
    result = {"verdict": VERDICTS[decision["decision"]]}
    if any(a["recommendation"] == "FOLLOW_PHYSICAL_CLASS_ORDER" for a in decision["actions"]):
        result["verdict"] = ("Follow the physical-class suspension order for the listed grades. Do not substitute on-campus indoor classes; use only alternatives permitted by the exact order.",
            "सूचीबद्ध कक्षाओं की भौतिक पढ़ाई स्थगित करने वाले आदेश का पालन करें। स्कूल परिसर की अंदरूनी कक्षाओं से आदेश न टालें; केवल मूल आदेश में अनुमत विकल्प अपनाएँ।")
    reg = decision["regulatory_status"]
    state = reg["verification_state"]
    stage_en = reg['active_stage'] if reg['active_stage'] is not None else ('none (verified inactive)' if state == 'VERIFIED_INACTIVE' else 'not verified')
    stage_hi = reg['active_stage'] if reg['active_stage'] is not None else ('कोई नहीं (निष्क्रिय होने की पुष्टि)' if state == 'VERIFIED_INACTIVE' else 'पुष्टि नहीं')
    result["regulation"] = (
        f"Official GRAP verification: {state}; verified active stage: {stage_en}. Review the cited orders and their applicability.",
        f"आधिकारिक GRAP की पुष्टि: {state}; सत्यापित लागू चरण: {stage_hi}। उद्धृत आदेश और उनका दायरा जाँचें।")
    result["provenance"] = ("Modeled conditions and forecasts are not station measurements. US AQI is not Indian AQI and cannot activate GRAP.", "मॉडल जानकारी और पूर्वानुमान स्टेशन के माप नहीं हैं। US AQI भारतीय AQI नहीं है और उससे GRAP लागू होने का निर्णय नहीं होता।")
    q = decision["data_quality"]
    result["freshness"] = (f"Evidence freshness: current {q['current_freshness']}, forecast {q['forecast_freshness']}. Official observations available: {q['official_observations_available']}.",
        f"जानकारी की ताज़गी: वर्तमान { {'fresh':'ताज़ा','stale':'पुरानी','unavailable':'अनुपलब्ध'}.get(q['current_freshness'],q['current_freshness'])}, पूर्वानुमान { {'fresh':'ताज़ा','stale':'पुरानी','unavailable':'अनुपलब्ध'}.get(q['forecast_freshness'],q['forecast_freshness'])}। आधिकारिक माप उपलब्ध: {'हाँ' if q['official_observations_available'] else 'नहीं'}।")
    result["limitations"] = ("Forecasts are uncertain. Indoor air has not been measured. Follow exact grade-specific orders; this advice does not invent school closures or guarantee safety.", "पूर्वानुमान में अनिश्चितता है। अंदर की हवा मापी नहीं गई है। कक्षा-विशिष्ट मूल आदेशों का पालन करें; यह सलाह स्कूल-बंदी नहीं गढ़ती और सुरक्षा की गारंटी नहीं देती।")
    for rule in decision["rule_evaluations"]:
        result["rule:" + rule["rule_id"]] = (rule["message"], RULES.get(rule["rule_id"], "इस नियम की मूल व्याख्या और प्रमाण की समीक्षा करें; कोई अतिरिक्त अनुमति नहीं दी गई है।"))
    return result

def validate_plan(raw, decision):
    plan = ExplanationPlan.model_validate_json(raw)
    if (plan.decision_id != decision["decision_id"] or plan.decision != decision["decision"]
        or plan.regulatory_state != decision["regulatory_status"]["verification_state"]
        or len(plan.statement_ids) != len(set(plan.statement_ids)) or set(plan.statement_ids) != set(catalog(decision))):
        raise ValueError("UNSAFE_EXPLANATION_PLAN")
    return plan

def render(school, decision, plan, generator, generated_at, warnings, cache_status):
    approved = catalog(decision)
    order = plan.statement_ids if plan else list(approved)
    explanations = {lang: " ".join(approved[k][index] for k in order) for index, lang in enumerate(("en", "hi"))}
    actions = [{**deepcopy(a), "en": a["instruction"], "hi": ACTION_HI.get(a["recommendation"], "मूल आदेश और लागू कक्षाओं की समीक्षा करें।")} for a in decision["actions"]]
    for action in actions:
        if action["recommendation"] == "STRUCTURED_REASONS_READY":
            action["en"] = "Use these authoritative reasons and caveats in school communications; this advisory does not change them."
    return {"school_id": school["school_id"], "school_name": school["name"], "verdict_id": decision["decision_id"], "verdict": decision["verdict"],
        "decision": decision["decision"], "generated_at": generated_at, "valid_until": decision["valid_until"], "en": explanations["en"], "hi": explanations["hi"],
        "languages": ["en", "hi"], "generator": generator, "explanation_method": "DETERMINISTIC" if generator == "rule_template" else "AI",
        "explanation_version": EXPLANATION_VERSION, "generation_scope": "approved_statement_ordering", "statement_ids": order,
        "authoritative_decision": deepcopy(decision), "actions": actions, "evidence_ids": decision["evidence_ids"], "evidence": deepcopy(decision["evidence"]),
        "sources": deepcopy(decision["sources"] + decision["policy_sources"] + decision["regulatory_status"]["source_documents"]),
        "regulatory_status": deepcopy(decision["regulatory_status"]), "data_quality": deepcopy(decision["data_quality"]),
        "observations": deepcopy([e for e in decision["evidence"] if e["kind"] == "station_observation"]),
        "modeled_conditions": deepcopy([e for e in decision["evidence"] if e["kind"] == "modeled_current"]),
        "forecast_summary": {"scope": "Phase 2 next-three-hour activity window; full 48-hour outlook remains available at /forecast",
            "points": deepcopy([e for e in decision["evidence"] if e["kind"] == "activity_forecast"]),
            "available": decision["data_quality"]["forecast_available"]},
        "caveats": list(dict.fromkeys(decision["warnings"] + warnings)), "cache": {"status": cache_status}}
