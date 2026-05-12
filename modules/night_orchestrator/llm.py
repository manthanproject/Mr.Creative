"""
Night Orchestrator — LLM Utility
Central LLM caller: Gemini (preferred) → Groq (fallback).
All Night Ops modules use this instead of calling APIs directly.
"""

import logging

logger = logging.getLogger('night_ops')


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
            logger.warning(f"[LLM] Gemini failed: {e}, trying Groq...")

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

    models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']
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
            return (response.text or '').strip()
        except Exception as e:
            last_error = e
            if '429' in str(e):
                print(f"[LLM] {model_name} quota hit, trying next model...")
                continue
            raise

    raise last_error



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
