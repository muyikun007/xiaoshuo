import os
import json
import requests
from google import genai
from google.genai import types

def load_api_key(provider="Gemini"):
    if provider == "Gemini":
        key_field = "api_key"
        env_var = "GEMINI_API_KEY"
        fallback_field = None
        fallback_env = None
    elif provider == "Doubao":
        key_field = "doubao_api_key"
        env_var = "DOUBAO_API_KEY"
        fallback_field = None
        fallback_env = None
    else:
        return None
    
    # Check config.json
    try:
        if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    key = (cfg.get(key_field) or "").strip()
                    if (not key) and fallback_field:
                        key = (cfg.get(fallback_field) or "").strip()
                    if key:
                        print(f"[{provider}] Found API Key in config.json")
                        return key
    except Exception as e:
        print(f"[{provider}] Error reading config.json: {e}")

    # Check Env Var
    key = os.environ.get(env_var, "").strip()
    if key:
        print(f"[{provider}] Found API Key in Environment Variable: {env_var}")
        return key
    if fallback_env:
        key = os.environ.get(fallback_env, "").strip()
        if key:
            print(f"[{provider}] Found API Key in Environment Variable: {fallback_env}")
            return key
    
    print(f"[{provider}] No API Key found (Checked config.json and {env_var})")
    return None

def test_gemini(api_key):
    print("\n--- Testing Gemini API ---")
    try:
        client = genai.Client(api_key=api_key)
        prompt = "Hello, respond with 'Gemini is working!' if you see this."
        print(f"Sending request to gemini-2.0-flash...")
        
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=prompt
        )
        if response.text:
            print(f"Response: {response.text}")
        else:
            print(f"Response text is empty. Full response: {response}")
            
        print("✅ Gemini API Call Successful")
        return True
    except Exception as e:
        print(f"❌ Gemini API Call Failed: {e}")
        return False

def test_doubao(api_key):
    print("\n--- Testing Doubao API ---")
    try:
        cfg = {}
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    cfg = json.load(f) or {}
        except Exception:
            cfg = {}

        base_url = (cfg.get("doubao_base_url") or os.environ.get("DOUBAO_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
        model_name = (os.environ.get("DOUBAO_MODEL") or cfg.get("doubao_model") or "").strip()
        if not model_name:
            print("Skipping Doubao test (No Endpoint ID; set doubao_model in config.json or DOUBAO_MODEL env var)")
            return False

        if base_url.lower().endswith("/chat/completions"):
            url = base_url
        else:
            url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Hello, respond with 'API is working!'"}],
            "stream": False,
        }
        print(f"Sending request to {data['model']} @ {base_url} ...")
        resp = requests.post(url, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        print(f"Response: {content}")
        print("✅ Doubao API Call Successful")
        return True
    except Exception as e:
        print(f"❌ Doubao API Call Failed: {e}")
        return False

def main():
    print("Starting API Diagnostics...")
    
    # 1. Test Gemini
    gemini_key = load_api_key("Gemini")
    if gemini_key:
        test_gemini(gemini_key)
    else:
        print("Skipping Gemini test (No Key)")

    # 2. Test Doubao
    doubao_key = load_api_key("Doubao")
    if doubao_key:
        test_doubao(doubao_key)
    else:
        print("Skipping Doubao test (No Key)")

if __name__ == "__main__":
    main()
