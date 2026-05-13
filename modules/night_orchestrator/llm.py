"""
Night Orchestrator — LLM Utility
Chain: Gemini API (3 models) → Gemini Extension (no quota) → Groq (last resort)
"""

import logging
import time

logger = logging.getLogger('night_ops')
last_provider = 'unknown'


def call_llm(prompt, system='', temperature=0.7, max_tokens=3000, image_url=None):
    """Call best available LLM. Returns response text."""
    from config import Config
    global last_provider

    # 1. Try Gemini API (3 models, 60 RPD free)
    gemini_key = Config.GEMINI_API_KEY
    if gemini_key:
        try:
            result = _call_gemini_api(gemini_key, prompt, system, temperature, max_tokens)
            if result:
                return result
        except Exception as e:
            print(f"[LLM] Gemini API exhausted: {e}")

    # 2. Try Gemini Extension (no quota limits)
    try:
        result = _call_gemini_extension(prompt, image_url=image_url)
        if result:
            return result
    except Exception as e:
        print(f"[LLM] Gemini Extension failed: {e}")

    # 3. Groq as last resort
    groq_key = Config.GROQ_API_KEY
    if groq_key:
        try:
            result = _call_groq(groq_key, prompt, system, temperature, max_tokens)
            if result:
                return result
        except Exception as e:
            print(f"[LLM] Groq failed: {e}")
            raise

    raise Exception("All LLM providers failed")


def _call_gemini_api(api_key, prompt, system, temperature, max_tokens):
    """Gemini API with model rotation."""
    import google.generativeai as genai
    global last_provider

    genai.configure(api_key=api_key)
    models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-lite']

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
            last_provider = model_name[:20]
            print(f"[LLM] Used {model_name}")
            return (response.text or '').strip()
        except Exception as e:
            if '429' in str(e):
                print(f"[LLM] {model_name} quota hit, trying next...")
                continue
            raise
    raise Exception("All Gemini API models exhausted")


def _call_gemini_extension(prompt, timeout=300, image_url=None):
    """Gemini via Chrome extension — no API quota. Direct queue."""
    import uuid
    global last_provider

    job_id = f'llm_{uuid.uuid4().hex[:8]}'

    # Import extension state directly (no HTTP to self)
    from routes.extension import _state, _lock, gemini_results

    # Find profile with gemini capability
    routed = False
    with _lock:
        for pid, info in _state.get('profiles', {}).items():
            caps = info.get('capabilities', [])
            print(f"[LLM-EXT] Profile {pid}: caps={caps}")
            if 'gemini' in caps:
                job = {
                    'job_id': job_id,
                    'job_type': 'gemini',
                    'prompt_text': prompt,
                    'image_url': image_url,
                    'image_filename': 'product.jpg',
                }
                _state['job_data'][job_id] = job
                _state['pending_commands'][pid] = job
                routed = True
                print(f"[LLM-EXT] Job {job_id} routed to {pid}")
                break

    if not routed:
        raise Exception("No profile with gemini capability found")

    # Poll for result
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(3)
        entry = gemini_results.get(job_id)
        if entry and entry.get('result'):
            try:
                del gemini_results[job_id]
            except KeyError:
                pass
            last_provider = 'gemini-ext'
            print(f"[LLM-EXT] Got result ({len(entry['result'])} chars)")
            return entry['result']
        # Also check completed jobs
        with _lock:
            cj = _state.get('completed_jobs', {}).get(job_id)
            if cj and cj.get('gemini_result'):
                last_provider = 'gemini-ext'
                print(f"[LLM-EXT] Got result from completed_jobs")
                return cj['gemini_result']

    raise Exception(f"Gemini extension timeout ({timeout}s)")


def _call_groq(api_key, prompt, system, temperature, max_tokens):
    """Groq Llama 3.3 70B — last resort."""
    from groq import Groq
    global last_provider

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
    last_provider = 'groq'
    print("[LLM] Used Groq")
    return (response.choices[0].message.content or '').strip()
