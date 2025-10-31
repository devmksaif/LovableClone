#!/usr/bin/env python3
"""
Test script to verify Groq API key functionality
"""
import requests
import json

def test_groq_api_key(api_key):
    """Test the provided Groq API key"""
    
    # Groq API endpoint
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    # Headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Simple test payload
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "user",
                "content": "Hello! This is a test message. Please respond with 'API key is working!'"
            }
        ],
        "max_tokens": 50,
        "temperature": 0.1
    }
    
    try:
        print(f"Testing API key: {api_key[:20]}...")
        print("Making request to Groq API...")
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        print(f"Response status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            message = result['choices'][0]['message']['content']
            print("✅ SUCCESS: API key is valid!")
            print(f"Response: {message}")
            return True
        else:
            print("❌ FAILED: API key test failed")
            print(f"Error: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ FAILED: Network error - {e}")
        return False
    except Exception as e:
        print(f"❌ FAILED: Unexpected error - {e}")
        return False

if __name__ == "__main__":
    # Test the provided API key
    api_key = "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"
    
    print("=" * 50)
    print("GROQ API KEY TEST")
    print("=" * 50)
    
    success = test_groq_api_key(api_key)
    
    print("=" * 50)
    if success:
        print("✅ Your Groq API key is working correctly!")
    else:
        print("❌ Your Groq API key has issues. Please check:")
        print("   1. The API key is correct")
        print("   2. You have sufficient credits")
        print("   3. The API key has the right permissions")
    print("=" * 50)