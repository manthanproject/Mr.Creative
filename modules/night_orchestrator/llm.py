"""
Night Orchestrator — LLM Utility
Central LLM caller: Gemini (preferred) → Groq (fallback).
All Night Ops modules use this instead of calling APIs directly.
"""

import logging

logger = logging.getLogger('night_ops')
last_provider = 'groq'  # tracks which LLM was last used


def call_llm(prompt: str, system: str = '', temperature: float = 0.7, max_tokens: int = 3000) -> str:
    """
    Call the best available LLM.
    Priority: Gemini (free, high quality) → Groq (free, fast).
    Returns the response text.
    Raises Exception if all fail.
    """
    from config import Config

    # Try Gemini first
    gemini_key = Config.GEMINI_API_KEY
    if gemini_key:
        try:
            result = _call_gemini(gemini_key, prompt, system, temperature, max_tokens)
            if result:
                logger.info("[LLM] Response via Gemini")
                return result
        except Exception as e:
            logger.warning(f"[LLM] Gemini API failed: {e}, trying Gemini extension...")

    # Fallback to Groq
    groq_key = Config.GROQ_API_KEY
    if groq_key:
        try:
            result = _call_groq(groq_key, prompt, system, temperature, max_tokens)
            if result:
                logger.info("[LLM] Response via Groq")
                return result
        except Exception as e:
            logger.error(f"[LLM] Groq failed: {e}")
            raise

    raise Exception("No LLM API key configured. Set GEMINI_API_KEY or GROQ_API_KEY in .env")


def _call_gemini(api_key: str, prompt: str, system: str, temperature: float, max_tokens: int) -> str:
    """Call Google Gemini API with model rotation."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)

    models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-lite']
    last_error = None

    for model_name in models:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system if system else None,
                generation_config=genai.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
            response = model.generate_content(prompt)
            print(f"[LLM] Used {model_name}")
            global last_provider
            last_provider = model_name[:20]
            return (response.text or '').strip()
        except Exception as e:
            last_error = e
            if '429' in str(e):
                print(f"[LLM] {model_name} quota hit, trying next model...")
                continue
            raise

    raise last_error



def _call_gemini_extension(prompt, timeout=120):
    """Call Gemini via Chrome extension - no API quota limits."""
    import requests
    import uuid
    base = 'http://127.0.0.1:5000'
    job_id = f'llm_{uuid.uuid4().hex[:8]}'
    try:
        r = requests.post(f'{base}/api/ext/submit', json={
            'job_id': job_id, 'job_type': 'gemini', 'prompt_text': prompt,
        }, timeout=5)
        if not r.ok:
            raise Exception(f'Queue failed: {r.status_code}')
        print(f"[LLM] Gemini extension job queued: {job_id}")
    except Exception as e:
        raise Exception(f'Extension queue failed: {e}')
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(3)
        try:
            r = requests.get(f'{base}/api/ext/gemini-result/{job_id}', timeout=5)
            if r.ok:
                data = r.json()
                if data.get('result'):
                    global last_provider
                    last_provider = 'gemini-ext'
                    print("[LLM] Gemini extension returned result")
                    return data['result']
        except Exception:
            pass
    raise Exception(f'Extension timeout after {timeout}s')


def _call_groq(api_key: str, prompt: str, system: str, temperature: float, max_tokens: int) -> str:
    """Call Groq API (Llama 3.3 70B)."""
    from groq import Groq

    client = Groq(api_key=api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or '').strip()
