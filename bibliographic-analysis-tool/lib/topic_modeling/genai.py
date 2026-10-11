import warnings
warnings.filterwarnings("ignore", category=FutureWarning, message=".*google.generativeai.*")

import google.generativeai as genai
from openai import OpenAI
import json
import re

import logging
import os
import traceback
import time
from utils.formatters import format_duration

# Set up logging for GenAI module
from utils.project_manager import get_project_dir
log_dir = get_project_dir("logs")
logger = logging.getLogger("genai_naming")
logger.setLevel(logging.INFO)

# Only add handler if it doesn't already exist to avoid duplicate logs in loops
if not logger.handlers:
    fh = logging.FileHandler(os.path.join(log_dir, 'genai_naming.log'), encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s'))
    logger.addHandler(fh)

# In-memory tracking of the last GenAI API error for UI presentation
_last_genai_error = None
_gemini_models_cache = {}


def set_last_genai_error(err_dict: dict):
    global _last_genai_error
    _last_genai_error = err_dict


def get_last_genai_error() -> dict | None:
    global _last_genai_error
    return _last_genai_error


def clear_last_genai_error():
    global _last_genai_error
    _last_genai_error = None


def parse_api_error(error) -> dict:
    """
    Extracts HTTP status codes, categorical causes, and concise user-facing
    resolution advice from provider exceptions (Gemini, Groq, OpenAI, Claude, Ollama).
    """
    err_str = str(error).strip()
    code = None

    # Inspect exception object attributes
    for attr in ['status_code', 'code', 'http_status']:
        val = getattr(error, attr, None)
        if val is not None and str(val).isdigit():
            code = str(val)
            break

    # Look for HTTP status codes in message text
    if not code:
        m = re.search(r'\b(400|401|403|404|429|500|502|503|504)\b', err_str)
        if m:
            code = m.group(1)

    lower_err = err_str.lower()

    if code == '429' or 'resourceexhausted' in lower_err or 'quota' in lower_err or 'rate limit' in lower_err:
        code = code or '429'
        category = 'Quota / Rate Limit Exceeded'
        advice = (
            "Your API rate limit or daily free tier quota has been exhausted. "
            "💡 **Recommended Action:** Switch provider to **Groq (LLaMA 3)** (free, ultra-fast, and generous rate limits at console.groq.com), "
            "or wait for your provider's daily quota to reset."
        )
    elif code in ['401', '403'] or any(k in lower_err for k in ['api_key_invalid', 'invalid api key', 'permission_denied', 'unauthorized']):
        code = code or '401'
        category = 'Invalid or Unauthorized API Key'
        advice = (
            "The provider rejected your API key. "
            "💡 **Recommended Action:** Double check that your API key is pasted accurately without extra spaces, "
            "and verify that it is active in your provider console (Google AI Studio, Groq Cloud, or OpenAI)."
        )
    elif code == '404' or 'notfound' in lower_err or 'not found' in lower_err:
        code = code or '404'
        category = 'Model Endpoint Not Available'
        advice = (
            "The requested model is not available for your API key/tier or region. "
            "💡 **Recommended Action:** The tool automatically attempts fallback models; if this persists, switch provider to **Groq (LLaMA 3)** or **OpenAI**."
        )
    elif any(k in lower_err for k in ['connection', 'refused', 'timeout', 'network']):
        code = code or 'CONN_ERR'
        category = 'Connection / Network Error'
        advice = (
            "Failed to reach the API server. "
            "💡 **Recommended Action:** Check your internet connection. If using **Ollama (Local)**, ensure Ollama is actively running (`ollama serve`)."
        )
    else:
        code = code or 'API_ERR'
        category = 'API Processing Error'
        advice = (
            "An unexpected error was returned by the provider. "
            "💡 **Recommended Action:** Review the technical error details below or try switching to another provider such as **Groq (LLaMA 3)**."
        )

    return {
        'code': code,
        'category': category,
        'message': err_str,
        'advice': advice
    }


def render_genai_error_card(error_info):
    """
    Renders an informative, user-friendly error callout in Streamlit
    displaying the API error code, explanation, and resolution guidance.
    """
    import streamlit as st

    if not error_info:
        return

    if not isinstance(error_info, dict):
        error_info = parse_api_error(error_info)

    code = error_info.get("code", "API Error")
    category = error_info.get("category", "Error")
    advice = error_info.get("advice", "")
    raw_msg = error_info.get("message", "")

    st.error(
        f"**🚨 API Error [{code}]: {category}**\n\n"
        f"{advice}"
    )

    with st.expander(f"🔍 Technical API Response Details (Code {code})", expanded=False):
        st.caption("Raw error message returned by the provider:")
        st.code(raw_msg, language="text")


def get_candidate_gemini_models(api_key: str) -> list[str]:
    """
    Returns an ordered list of Gemini model names to try.
    Attempts dynamic model discovery via genai.list_models() if possible,
    and falls back to a tested prioritized list of Gemini models.
    """
    global _gemini_models_cache
    if api_key in _gemini_models_cache:
        return _gemini_models_cache[api_key]

    fallback_candidates = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash-8b",
        "gemini-2.0-flash-exp",
        "gemini-pro",
        "gemini-1.5-pro",
        "gemini-3.6-flash"
    ]

    try:
        genai.configure(api_key=api_key)
        discovered = []
        for m in genai.list_models():
            methods = getattr(m, "supported_generation_methods", [])
            if "generateContent" in methods:
                name = m.name.replace("models/", "")
                discovered.append(name)
        if discovered:
            ordered = [c for c in fallback_candidates if c in discovered]
            for d in discovered:
                if d not in ordered and "flash" in d.lower():
                    ordered.append(d)
            for d in discovered:
                if d not in ordered:
                    ordered.append(d)
            _gemini_models_cache[api_key] = ordered
            return ordered
    except Exception as e:
        logger.warning(f"Could not query Gemini models list dynamically: {e}")

    _gemini_models_cache[api_key] = fallback_candidates
    return fallback_candidates


def generate_topic_name(api_key, provider, words, total_topics: int = None):
    """
    Generate a topic name and description using the specified LLM provider.
    Returns a dict with 'name' and 'description'.
    Prefers 2-word names when total topics <= 20; allows 3-word names when total topics > 20.
    """
    logger.info(f"--- New Request ---")
    logger.info(f"Provider: {provider}")
    logger.info(f"Input Words: {words}")
    
    if not api_key and provider != "Ollama (Local)":
        logger.warning("Request blocked: No API key provided for a provider that requires one.")
        err_info = {
            "code": "NO_KEY",
            "category": "API Key Required",
            "message": "No API key was provided.",
            "advice": "Please enter a valid API key for your chosen provider."
        }
        set_last_genai_error(err_info)
        return {"name": "Unnamed Topic", "description": "No API key provided.", "error_info": err_info}
        
    if total_topics is None or total_topics <= 20:
        word_limit_rule = "PREFER EXACTLY 2 WORDS (STRICTLY MAXIMUM 2 WORDS ONLY, e.g. 'Neural Networks', 'Gene Expression')"
        max_words_desc = "max 2 words"
    else:
        word_limit_rule = "PREFER 2 WORDS, but UP TO 3 WORDS are permitted when strictly necessary for taxonomic precision (STRICTLY MAXIMUM 3 WORDS ONLY, e.g. 'Deep Neural Networks')"
        max_words_desc = "max 3 words"

    prompt = f"""
    Given the following top words from a topic modeling algorithm: {', '.join(words)}.
    Please provide a concise, generic title that captures the central theme ({word_limit_rule}), 
    and a short 1-sentence description of the topic.
    
    CRITICAL GUARDRAILS AGAINST HALLUCINATION:
    - Your labels MUST be strictly grounded in established academic ontologies (e.g., Medical Subject Headings (MeSH), ACM Computing Classification System, or IEEE taxonomy).
    - Do NOT invent plausible-sounding but non-existent scientific domains.
    - Ensure the label strictly reflects the provided keywords without extrapolating beyond the provided context.

    Return ONLY a raw JSON object with the keys 'name' (string, {max_words_desc}) and 'description' (string). Do not use markdown blocks.
    """
    
    start_time = time.time()
    
    try:
        text = ""
        if provider == "Gemini":
            genai.configure(api_key=api_key)
            model_names_to_try = get_candidate_gemini_models(api_key)
            last_err = None
            for m_name in model_names_to_try:
                try:
                    model = genai.GenerativeModel(m_name)
                    response = model.generate_content(prompt)
                    text = response.text.strip()
                    break
                except Exception as ex:
                    last_err = ex
                    err_str = str(ex)
                    logger.warning(f"Single Gemini model '{m_name}' failed: {err_str}")
                    if any(auth_err in err_str.lower() for auth_err in ["api_key_invalid", "permission_denied", "unauthorized"]) or "401" in err_str or "403" in err_str:
                        break
                    continue
            if not text and last_err:
                raise last_err
            
        elif provider == "Groq (LLaMA 3)":
            client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=api_key
            )
            groq_models = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "llama3-8b-8192"]
            last_err = None
            for gm in groq_models:
                try:
                    response = client.chat.completions.create(
                        model=gm,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that labels academic topics."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    text = response.choices[0].message.content.strip()
                    break
                except Exception as ex:
                    last_err = ex
                    err_s = str(ex)
                    if "401" in err_s or "invalid_api_key" in err_s.lower():
                        break
                    continue
            if not text and last_err:
                raise last_err
            
        elif provider == "OpenAI":
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that labels academic topics."},
                    {"role": "user", "content": prompt}
                ]
            )
            text = response.choices[0].message.content.strip()
            
        elif provider == "Anthropic (Claude)":
            import urllib.request
            req_data = json.dumps({
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 300,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=req_data,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_payload = json.loads(resp.read().decode("utf-8"))
                text = resp_payload["content"][0]["text"].strip()

        elif provider == "Ollama (Local)":
            client = OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama" # required, but unused
            )
            response = client.chat.completions.create(
                model="llama3", # Default to llama3, could be configurable
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that labels academic topics."},
                    {"role": "user", "content": prompt}
                ]
            )
            text = response.choices[0].message.content.strip()
            
        else:
            logger.warning(f"Unknown provider selected: {provider}")
            return {"name": "Topic Not Named", "description": "Select a provider and provide an API key if required."}
            
        # Clean up potential markdown formatting
        if text.startswith('```json'):
            text = text[7:-3].strip()
        elif text.startswith('```'):
            text = text[3:-3].strip()
            
        latency = time.time() - start_time
        logger.info(f"Success ({format_duration(latency)}). Raw LLM Response: {text}")
        
        parsed_json = json.loads(text)
        return parsed_json
            
    except Exception as e:
        latency = time.time() - start_time
        error_info = parse_api_error(e)
        set_last_genai_error(error_info)

        logger.error(f"Failed after {format_duration(latency)}")
        logger.error(f"Exception Message: {error_info['message']}")
        logger.error(f"Stack Trace:\n{traceback.format_exc()}")
            
        return {
            "name": f"Error: {error_info['code']}",
            "description": error_info['message'],
            "error_info": error_info
        }


def generate_batch_topic_names(api_key: str, provider: str, topics_dict: dict, chunk_size: int = 25, total_topics: int = None) -> dict:
    """
    Generate names and descriptions for topics in batched API calls to prevent rate limiting and prompt truncation.
    Splits into chunks of at most `chunk_size` topics per call to ensure reliable responses without exceeding prompt limits.
    Prefers 2-word names when total topics <= 20; allows 3-word names when total topics > 20.
    topics_dict: {key: ['word1', 'word2', ...]}
    Returns: {key: {'name': '...', 'description': '...'}, ...}
    """
    logger.info("--- New Batch Request ---")
    logger.info(f"Provider: {provider}")
    logger.info(f"Topics to name: {len(topics_dict)}")

    if not api_key and provider != "Ollama (Local)":
        logger.warning("Request blocked: No API key provided.")
        return {
            t_id: {"name": f"Topic {t_id}", "description": "No API key provided."}
            for t_id in topics_dict
        }

    num_topics = total_topics if total_topics is not None else len(topics_dict)
    if num_topics <= 20:
        word_instruction = (
            "For EACH topic ID, generate a concise, academic title: "
            "PREFER EXACTLY 2 WORDS (STRICTLY MAXIMUM 2 WORDS ONLY, e.g., 'Cancer Therapy', 'Quantum Computing'). "
            "Do not exceed 2 words under any circumstance."
        )
        name_schema = "Short Name (max 2 words)"
    else:
        word_instruction = (
            "For EACH topic ID, generate a concise, academic title: "
            "PREFER 2 WORDS, but UP TO 3 WORDS are permitted when strictly necessary for taxonomic precision "
            "(STRICTLY MAXIMUM 3 WORDS ONLY, e.g., 'Deep Neural Networks'). Do not exceed 3 words."
        )
        name_schema = "Short Name (max 3 words)"

    # Split into chunks of chunk_size to never exceed model context or output limits
    items = list(topics_dict.items())
    all_results = {}

    for chunk_start in range(0, len(items), chunk_size):
        chunk_items = items[chunk_start:chunk_start + chunk_size]
        sub_dict = dict(chunk_items)

        # Format the prompt with topic keyword clusters
        clusters_formatted = "\n".join([
            f"- Topic {t_id}: {', '.join(words[:10])}"
            for t_id, words in sub_dict.items()
        ])

        prompt = f"""
        You are an expert taxonomist. Analyze the following topic keyword clusters.
        {word_instruction}
        Also provide a short 1-sentence description for EACH topic ID.
        
        CRITICAL GUARDRAILS AGAINST HALLUCINATION:
        - Your labels MUST be strictly grounded in established academic ontologies (e.g., Medical Subject Headings (MeSH), ACM Computing Classification System, or IEEE taxonomy).
        - Do NOT invent plausible-sounding but non-existent scientific domains.
        - Ensure the label strictly reflects the provided keywords without extrapolating beyond the provided context.

        Topic Clusters:
        {clusters_formatted}

        Return ONLY a raw, valid JSON object mapping each topic ID (as a string) to its 'name' and 'description'.
        Do not include markdown code block formatting (e.g. do not wrap in ```json).
        
        Expected JSON schema format:
        {{
          "0": {{"name": "{name_schema}", "description": "1-sentence summary."}},
          "1": {{"name": "{name_schema}", "description": "1-sentence summary."}}
        }}
        """

        start_time = time.time()
        chunk_res = {}

        try:
            text = ""
            if provider == "Gemini":
                genai.configure(api_key=api_key)
                model_names_to_try = get_candidate_gemini_models(api_key)
                last_err = None
                for m_name in model_names_to_try:
                    try:
                        model = genai.GenerativeModel(
                            model_name=m_name,
                            generation_config={"response_mime_type": "application/json"}
                        )
                        response = model.generate_content(prompt)
                        text = response.text.strip()
                        break
                    except Exception as ex:
                        last_err = ex
                        err_str = str(ex)
                        logger.warning(f"Batch Gemini model '{m_name}' failed: {err_str}")
                        if any(auth_err in err_str.lower() for auth_err in ["api_key_invalid", "permission_denied", "unauthorized"]) or "401" in err_str or "403" in err_str:
                            break
                        continue
                if not text and last_err:
                    raise last_err

            elif provider == "Groq (LLaMA 3)":
                client = OpenAI(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=api_key
                )
                groq_models = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "llama3-8b-8192"]
                last_err = None
                for gm in groq_models:
                    try:
                        response = client.chat.completions.create(
                            model=gm,
                            response_format={"type": "json_object"},
                            messages=[
                                {"role": "system", "content": "You are a helpful academic taxonomist that outputs strict JSON."},
                                {"role": "user", "content": prompt}
                            ]
                        )
                        text = response.choices[0].message.content.strip()
                        break
                    except Exception as ex:
                        last_err = ex
                        err_s = str(ex)
                        if "401" in err_s or "invalid_api_key" in err_s.lower():
                            break
                        continue
                if not text and last_err:
                    raise last_err

            elif provider == "OpenAI":
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a helpful academic taxonomist that outputs strict JSON."},
                        {"role": "user", "content": prompt}
                    ]
                )
                text = response.choices[0].message.content.strip()

            elif provider == "Anthropic (Claude)":
                import urllib.request
                req_data = json.dumps({
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 1500,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=req_data,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=40) as resp:
                    resp_payload = json.loads(resp.read().decode("utf-8"))
                    text = resp_payload["content"][0]["text"].strip()

            elif provider == "Ollama (Local)":
                client = OpenAI(
                    base_url="http://localhost:11434/v1",
                    api_key="ollama"
                )
                response = client.chat.completions.create(
                    model="llama3",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a helpful academic taxonomist that outputs strict JSON."},
                        {"role": "user", "content": prompt}
                    ]
                )
                text = response.choices[0].message.content.strip()

            else:
                for t_id in sub_dict:
                    chunk_res[t_id] = {"name": f"Topic {t_id}", "description": "Unknown provider selected."}
                all_results.update(chunk_res)
                continue

            # Strip markdown fences if present
            if text.startswith("```json"):
                text = text[7:-3].strip()
            elif text.startswith("```"):
                text = text[3:-3].strip()

            parsed = json.loads(text)
            latency = time.time() - start_time
            logger.info(f"Batch chunk generation success ({format_duration(latency)}).")
            
            # Map back preserving key types (int or str)
            for orig_key in sub_dict.keys():
                str_k = str(orig_key)
                if str_k in parsed:
                    chunk_res[orig_key] = parsed[str_k]
                elif orig_key in parsed:
                    chunk_res[orig_key] = parsed[orig_key]
                else:
                    chunk_res[orig_key] = {"name": f"Topic {orig_key}", "description": "Unlabeled"}

        except Exception as e:
            latency = time.time() - start_time
            error_info = parse_api_error(e)
            set_last_genai_error(error_info)
            logger.error(f"Batch chunk generation failed after {format_duration(latency)}: {e}")
            logger.error(traceback.format_exc())
            
            # If the error is an authentication error or quota limit, do not repeat single calls
            if error_info["code"] in ["401", "403", "429"]:
                for t_id in sub_dict:
                    chunk_res[t_id] = {
                        "name": f"Error: {error_info['code']}",
                        "description": error_info['message'],
                        "error_info": error_info
                    }
            else:
                # Fallback to single calls if batch JSON parsing or structure failed
                for t_id, words in sub_dict.items():
                    chunk_res[t_id] = generate_topic_name(api_key, provider, words, total_topics=num_topics)

        all_results.update(chunk_res)

    return all_results