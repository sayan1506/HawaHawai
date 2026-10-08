"""One harmless backend-only Strands call. Prints no keys or provider error bodies."""
import os
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from agent.providers import ProviderNotConfigured, create_model


def main():
    load_dotenv(ROOT / "backend" / ".env", override=False)
    provider = os.environ.get("HAWAHAWAI_AI_PROVIDER", "gemini")
    try:
        model = create_model(provider)
    except ProviderNotConfigured as error:
        print(f"BLOCKED: {error}. Add the value in backend/.env and rerun.")
        return 2
    try:
        from strands import Agent
        previous_log_level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        agent = Agent(model=model, tools=[], callback_handler=None,
                      system_prompt="You are a connectivity test. Answer exactly HAWAHAWAI_OK. Do not give advice.")
        result = str(agent("Reply HAWAHAWAI_OK only."))
        if "HAWAHAWAI_OK" not in result:
            print("FAIL: provider returned an unexpected response")
            return 1
        print(f"PASS: Strands {provider} backend connectivity verified")
        return 0
    except Exception as error:
        print(f"FAIL: {provider} connectivity ({type(error).__name__}); error text suppressed to protect credentials")
        return 1
    finally:
        if 'previous_log_level' in locals():
            logging.disable(previous_log_level)


if __name__ == "__main__":
    raise SystemExit(main())
