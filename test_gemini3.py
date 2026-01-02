import os
import json
from google import genai
from google.genai import types

def load_api_key():
    # Check config.json
    try:
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
                key = (cfg.get("api_key") or "").strip()
                if key:
                    return key
    except Exception as e:
        print(f"Error reading config.json: {e}")

    # Check Env Var
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key

def test_gemini_3():
    api_key = load_api_key()
    if not api_key:
        print("❌ No API Key found.")
        return

    print(f"--- Testing Gemini Model: gemini-3-pro-preview ---")
    try:
        client = genai.Client(api_key=api_key)
        prompt = "Hello, respond with 'Gemini 3 is working!' if you see this."
        print(f"Sending request...")
        
        response = client.models.generate_content(
            model="gemini-3-pro-preview", 
            contents=prompt
        )
        
        if response.text:
            print(f"Response: {response.text}")
            print("✅ Gemini 3 Preview API Call Successful")
        else:
            print(f"⚠️ Response text is empty. Full response object: {response}")
            
    except Exception as e:
        print(f"❌ Gemini API Call Failed: {e}")

if __name__ == "__main__":
    test_gemini_3()
