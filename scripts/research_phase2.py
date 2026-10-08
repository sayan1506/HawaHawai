"""Bounded read-only official-source probe. Raw artifacts remain ignored/local.

This collects research evidence, NOT a human verification or active-stage claim.
No retries, scraping loop, AI extraction, credentials or paid requests.
"""
import hashlib
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
DOCS = {
    "caqm-schedule-2025-11-21": "https://caqm.nic.in/WriteReadData/LINKS/GRAP%20Order47928aa8-d026-4478-9407-2eba0a328a2d.pdf",
    "delhi-school-circular-2026-01-20": "https://edustud.nic.in/upload/upload_2025_26/Schoolbranch_regardingresumptionofnormalclassesinschoolsforclasses6to9and11_dt_20012026_56.pdf",
    "delhi-revocation-2026-01-22": "https://edustud.nic.in/upload/upload_2025_26/Schoolbranch_RegardingRevocationofGRAPIIIMeasures_dt_22012026_62.pdf",
    "epa-school-guidance-2014": "https://document.airnow.gov/air-quality-and-outdoor-guidance-for-schools.pdf",
    "pib-grap-revision-2026-09-29": "https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=2316597&lang=2&reg=48",
}
CURRENT_DOCS = {
    "caqm-schedule-2026-09-29": "https://caqm.nic.in/FileUploadDomain/WebsiteDocument/GRAP/GRAP%20Schedule/01fcdebf-83e1-4cfe-bc0c-d0b1470a4d4e.pdf",
    "caqm-direction-104-2026-09-29": "https://caqm.nic.in/FileUploadDomain/WebsiteDocument/Advisories%20and%20Direction/Directions/fa4070ca-5b45-4161-b220-0871227ae9ea.pdf",
    "caqm-advisory-18-2026-09-10": "https://caqm.nic.in/FileUploadDomain/WebsiteDocument/Advisories%20and%20Direction/Advisories/a68ffad1-874d-4e7d-a366-e3ec9f97be0e.pdf",
}
HISTORY_DOCS = {
    "caqm-stage-i-invocation-2026-05-19": "https://caqm.nic.in/FileUploadDomain/WebsiteDocument/GRAP/GRAP%20Orders/GRAP%20Order%20dt%20190520264bc6a704-b069-4779-86d7-f0aeed5cd149.pdf",
    "caqm-stage-i-revocation-2026-05-29": "https://caqm.nic.in/FileUploadDomain/WebsiteDocument/GRAP/GRAP%20Orders/GRAP%20Stage%20I%20Revocation%20Order%2029052026996e5190-fa00-43c9-bb1c-6a0a70a548ee.pdf",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-only", action="store_true")
    parser.add_argument("--history-only", action="store_true")
    args = parser.parse_args()
    folder = ROOT / ".local/phase2-documents"
    folder.mkdir(parents=True, exist_ok=True)
    findings = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "human_verification": False, "documents": []}
    for identifier, url in (HISTORY_DOCS if args.history_only else CURRENT_DOCS if args.current_only else DOCS).items():
        record = {"document_id": identifier, "url": url}
        try:
            with urlopen(Request(url, headers={"User-Agent": "HawaHawai-hackathon-evidence-review/0.2"}), timeout=12) as response:
                body = response.read(12_000_001)
                assert len(body) <= 12_000_000
                pdf = body.startswith(b"%PDF-")
                record.update(http_status=response.status, content_type=response.headers.get("Content-Type"), final_url=response.url,
                              pdf=pdf, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
                if pdf:
                    target = folder / (identifier + ".pdf")
                    target.write_bytes(body)
                    # Optional read-only rendering dependency, isolated under .local.
                    try:
                        import fitz
                        document = fitz.open(stream=body, filetype="pdf")
                        record["pages"] = len(document)
                        pages = range(len(document)) if identifier == "epa-school-guidance-2014" else range(min(2, len(document)))
                        if identifier == "caqm-schedule-2026-09-29":
                            pages = (0, 13, 15, 16)
                        if identifier == "caqm-direction-104-2026-09-29":
                            pages = (0, 2, 3)
                        for page_number in pages:
                            document[page_number].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(folder / f"{identifier}-{page_number + 1}.png")
                        text = "\n".join(page.get_text() for page in document)
                        (folder / (identifier + ".txt")).write_text(text, encoding="utf-8")
                        record["text_characters"] = len(text)
                    except ImportError:
                        record["rendering"] = "PDF renderer unavailable"
        except Exception as error:
            record.update(error_type=type(error).__name__, http_status=error.code if isinstance(error, HTTPError) else None)
        findings["documents"].append(record)
        print(json.dumps({k: v for k, v in record.items() if k not in {"url", "final_url", "sha256"}}))
    output = "phase2-history-probe.json" if args.history_only else "phase2-current-regulations-probe.json" if args.current_only else "phase2-official-probe.json"
    (ROOT / ".local" / output).write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
