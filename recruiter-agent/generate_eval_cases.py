
import json
import os
import google.generativeai as genai

GEN_MODEL = "gemini-1.5-flash"

def ensure_gemini_configured():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")
    genai.configure(api_key=api_key)

def generate_cases(n: int = 25):
    ensure_gemini_configured()
    prompt = f"""
Generate {n} synthetic test cases for evaluating a Recruiter AI Agent.

Each test case must be JSON of:
{{
  "role": "<string or empty>",
  "criteria": ["<string>", ...],
  "message": "<user message>",
  "tags": ["normal" | "adversarial" | "stress" | "cv_query"]
}}

Include:
- recruiter questions
- CV Q&A
- adversarial attempts
- stress/long/noisy prompts
Respond ONLY as a JSON list.
""".strip()

    model = genai.GenerativeModel(GEN_MODEL)
    resp = model.generate_content(prompt)
    text = getattr(resp, "text", "") or str(resp)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError("Gemini returned invalid JSON")

    out_path = "eval_cases.generated.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✔ Generated {len(data)} test cases → {out_path}")

if __name__ == "__main__":
    generate_cases()
