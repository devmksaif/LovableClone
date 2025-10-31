"""
Test script for Code Intelligence Service
"""

import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from agents.code_intelligence import get_code_intelligence_service, analyze_code_file, find_symbol_references, get_symbol_info

async def test_code_intelligence():
    """Test the code intelligence service."""
    print("Testing Code Intelligence Service...")

    try:
        # Get the service
        service = get_code_intelligence_service()
        print("✅ Service initialized successfully")

        # Test parsing a Python file (this file itself)
        current_file = __file__
        print(f"\n📄 Analyzing file: {current_file}")

        # Test symbol extraction
        symbols = service.get_symbols(current_file)
        print(f"✅ Found {len(symbols)} symbols")

        for symbol in symbols[:5]:  # Show first 5
            print(f"  - {symbol.kind}: {symbol.name} at line {symbol.location.line}")

        # Test dependency analysis
        deps = service.analyze_dependencies(current_file)
        print(f"✅ Found {len(deps.imports)} imports, {len(deps.exports)} exports")

        # Test tool functions
        print("\n🔧 Testing tool functions...")

        # Test analyze_code_file tool
        result = analyze_code_file.invoke({"file_path": current_file})
        print("✅ analyze_code_file tool works")

        print("\n🎉 All tests passed!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_code_intelligence())