#!/usr/bin/env python3

import requests
import os

def check_groq_models():
    # Get API key from environment
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        print("❌ GROQ_API_KEY not found in environment variables")
        return
    
    print(f"🔑 Using API key: {api_key[:20]}...")
    
    # Check available models
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get('https://api.groq.com/openai/v1/models', headers=headers)
        print(f"📡 Models API response status: {response.status_code}")
        
        if response.status_code == 200:
            models = response.json()
            print("✅ Available models:")
            for model in models.get('data', []):
                print(f"  - {model.get('id', 'Unknown')}")
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Exception occurred: {e}")

    # Test the specific model that's failing
    test_model = "openai/gpt-oss-120b"
    print(f"\n🧪 Testing model: {test_model}")
    
    test_payload = {
        "model": test_model,
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10
    }
    
    try:
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=test_payload
        )
        print(f"📡 Chat API response status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Model works!")
        else:
            print(f"❌ Model failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Exception occurred: {e}")

if __name__ == "__main__":
    check_groq_models()