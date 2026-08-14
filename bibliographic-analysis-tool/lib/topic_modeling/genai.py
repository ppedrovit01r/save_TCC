import google.generativeai as genai
from openai import OpenAI
import json

import logging
import os
import traceback
import time

# Set up logging for GenAI module
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
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
        logger.info(f"Success ({latency:.2f}s). Raw LLM Response: {text}")
        
        parsed_json = json.loads(text)
        return parsed_json
            
    except Exception as e:
        latency = time.time() - start_time
        error_msg = str(e)
        stack_trace = traceback.format_exc()
        
        logger.error(f"Failed after {latency:.2f}s")
        logger.error(f"Exception Message: {error_msg}")
        logger.error(f"Stack Trace:\n{stack_trace}")
        
        # Add a helpful hint for Connection errors
        if "Connection error" in error_msg or "Connection refused" in error_msg:
            error_msg += " (Make sure Ollama is actually running and the model is pulled!)"
            
        return {"name": "Error naming topic", "description": error_msg}
