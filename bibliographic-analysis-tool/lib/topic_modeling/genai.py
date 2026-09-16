import google.generativeai as genai
from openai import OpenAI
import json

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

def generate_topic_name(api_key, provider, words):
    """
    Generate a topic name and description using the specified LLM provider.
    Returns a dict with 'name' and 'description'.
    """
    logger.info(f"--- New Request ---")
    logger.info(f"Provider: {provider}")
    logger.info(f"Input Words: {words}")
    
    if not api_key and provider != "Ollama (Local)":
        logger.warning("Request blocked: No API key provided for a provider that requires one.")
        return {"name": "Unnamed Topic", "description": "No API key provided."}
        
    prompt = f"""
    Given the following top words from a topic modeling algorithm: {', '.join(words)}.
    Please provide a concise, generic title that captures the central theme (STRICTLY MAXIMUM 3 WORDS ONLY), 
    and a short 1-sentence description of the topic.
    
    Return ONLY a raw JSON object with the keys 'name' (string, max 3 words) and 'description' (string). Do not use markdown blocks.
    """
    
    start_time = time.time()
    
    try:
        text = ""
        if provider == "Gemini":
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-3.6-flash')
            response = model.generate_content(prompt)
            text = response.text.strip()
            
        elif provider == "Groq (LLaMA 3)":
            client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=api_key
            )
            response = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that labels academic topics."},
                    {"role": "user", "content": prompt}
                ]
            )
            text = response.choices[0].message.content.strip()
            
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
        error_msg = str(e)
        stack_trace = traceback.format_exc()
        
        logger.error(f"Failed after {format_duration(latency)}")
        logger.error(f"Exception Message: {error_msg}")
        logger.error(f"Stack Trace:\n{stack_trace}")
        
        # Add a helpful hint for Connection errors
        if "Connection error" in error_msg or "Connection refused" in error_msg:
            error_msg += " (Make sure Ollama is actually running and the model is pulled!)"
            
        return {"name": "Error naming topic", "description": error_msg}


def generate_batch_topic_names(api_key: str, provider: str, topics_dict: dict, chunk_size: int = 25) -> dict:
    """
    Generate names and descriptions for topics in batched API calls to prevent rate limiting and prompt truncation.
    Splits into chunks of at most `chunk_size` topics per call to ensure reliable responses without exceeding prompt limits.
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
        You are an expert taxonomist. Analyze the following topic keyword clusters and generate a concise, academic title (STRICTLY MAXIMUM 3 WORDS ONLY) and a short 1-sentence description for EACH topic ID.

        Topic Clusters:
        {clusters_formatted}

        Return ONLY a raw, valid JSON object mapping each topic ID (as a string) to its 'name' and 'description'.
        Do not include markdown code block formatting (e.g. do not wrap in ```json).
        
        Expected JSON schema format:
        {{
          "0": {{"name": "Short Name", "description": "1-sentence summary."}},
          "1": {{"name": "Short Name", "description": "1-sentence summary."}}
        }}
        """

        start_time = time.time()
        chunk_res = {}

        try:
            text = ""
            if provider == "Gemini":
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(
                    model_name="gemini-3.6-flash",
                    generation_config={"response_mime_type": "application/json"}
                )
                response = model.generate_content(prompt)
                text = response.text.strip()

            elif provider == "Groq (LLaMA 3)":
                client = OpenAI(
                    base_url="https://api.groq.com/openai/v1",
                    api_key=api_key
                )
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "You are a helpful academic taxonomist that outputs strict JSON."},
                        {"role": "user", "content": prompt}
                    ]
                )
                text = response.choices[0].message.content.strip()

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
            logger.error(f"Batch chunk generation failed after {format_duration(latency)}: {e}")
            logger.error(traceback.format_exc())
            
            # Fallback to single calls if batch JSON parsing fails
            for t_id, words in sub_dict.items():
                chunk_res[t_id] = generate_topic_name(api_key, provider, words)

        all_results.update(chunk_res)

    return all_results