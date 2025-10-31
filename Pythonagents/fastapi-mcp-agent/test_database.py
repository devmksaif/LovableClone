#!/usr/bin/env python3
"""
Test script to verify database integration in FastAPI backend
"""
import asyncio
import os
from app.database import init_database, get_or_create_session, add_conversation, get_conversations

async def test_database():
    """Test database operations."""
    try:
        print("🔄 Initializing database...")
        await init_database()
        print("✅ Database initialized successfully")

        # Test session creation
        print("🔄 Testing session creation...")
        session = await get_or_create_session("test_session_123", "/tmp/test")
        print(f"✅ Session created: {session.sessionId}")

        # Test adding conversations
        print("🔄 Testing conversation storage...")
        await add_conversation("test_session_123", "user", "Hello, can you help me?")
        await add_conversation("test_session_123", "assistant", "Yes, I can help you!")

        # Test retrieving conversations
        print("🔄 Testing conversation retrieval...")
        conversations = await get_conversations("test_session_123")
        print(f"✅ Retrieved {len(conversations)} conversations")

        for conv in conversations:
            print(f"  {conv.role}: {conv.content[:50]}...")

        print("🎉 All database tests passed!")

    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_database())
    exit(0 if success else 1)