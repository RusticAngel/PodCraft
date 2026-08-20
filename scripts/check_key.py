# Validate a Gemini API key against the live API.
# Usage:
#   .venv\Scripts\python.exe scripts\check_key.py [KEY]
#   .venv\Scripts\python.exe scripts\check_key.py            # reads GEMINI_API_KEY from .env
# Exits 0 on success, 1 on failure. Also prints the key format sanity check.

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main():
    key = sys.argv[1] if len(sys.argv) > 1 else os.getenv("GEMINI_API_KEY")
    if not key:
        print("No key provided and GEMINI_API_KEY not set in .env")
        sys.exit(1)

    print(f"len={len(key)}  prefix={key[:4]!r}")
    if key.startswith("AIza"):
        print("format: looks like a valid Gemini API key (AIza... prefix)")
    else:
        print("format: WARNING - Gemini API keys normally start with 'AIza'. "
              "An 'AQ.' prefix is an OAuth token, not an API key.")

    from google import genai

    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
            contents="Reply with the single word: ok",
            config={"response_modalities": ["TEXT"]},
        )
        print("live call: OK ->", (resp.text or "")[:60].strip())
        sys.exit(0)
    except Exception as e:
        print("live call: FAIL ->", str(e)[:300])
        sys.exit(1)


if __name__ == "__main__":
    main()