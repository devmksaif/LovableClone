#!/usr/bin/env python3
"""
Comprehensive test for the Code Intelligence System integration.
Tests sandbox creation, automatic indexing, and code analysis tools.
"""

import asyncio
import os
import tempfile
import shutil
from pathlib import Path

# Import the code intelligence service
from app.agents.code_intelligence import CodeIntelligenceService
from app.sandbox_service import sandbox_service


async def test_code_intelligence_integration():
    """Test the complete code intelligence workflow."""
    print("🧪 Testing Code Intelligence System Integration")
    print("=" * 60)

    # Test 1: Create a test sandbox with sample code
    print("\n1. Creating test sandbox with sample code...")

    test_files = {
        "main.py": '''
import os
from utils import calculate_total

class Calculator:
    """A simple calculator class."""

    def __init__(self, base_value: int = 0):
        self.value = base_value

    def add(self, x: int) -> int:
        """Add x to the current value."""
        return self.value + x

    def multiply(self, factor: int) -> int:
        """Multiply current value by factor."""
        return self.value * factor

def main():
    calc = Calculator(10)
    result = calc.add(5)
    total = calculate_total([1, 2, 3, result])
    print(f"Total: {total}")

if __name__ == "__main__":
    main()
''',
        "utils.py": '''
from typing import List

def calculate_total(numbers: List[int]) -> int:
    """Calculate the sum of a list of numbers."""
    return sum(numbers)

def find_max(numbers: List[int]) -> int:
    """Find the maximum value in a list."""
    if not numbers:
        return 0
    return max(numbers)

CONSTANT_VALUE = 42
''',
        "test_main.py": '''
import pytest
from main import Calculator
from utils import calculate_total, find_max

def test_calculator():
    calc = Calculator(10)
    assert calc.add(5) == 15
    assert calc.multiply(2) == 20

def test_utils():
    assert calculate_total([1, 2, 3]) == 6
    assert find_max([1, 5, 3]) == 5
'''
    }

    # Create temporary directory for test sandbox
    with tempfile.TemporaryDirectory() as temp_dir:
        sandbox_path = Path(temp_dir) / "test_sandbox"
        sandbox_path.mkdir()

        # Create test files
        for filename, content in test_files.items():
            (sandbox_path / filename).write_text(content)

        print(f"✅ Created test sandbox at: {sandbox_path}")

        # Test 2: Index the project files
        print("\n2. Indexing project files...")
        code_intel = CodeIntelligenceService()

        try:
            await code_intel.index_project_files(str(sandbox_path))
            print("✅ Successfully indexed project files")
        except Exception as e:
            print(f"❌ Failed to index project files: {e}")
            return False

        # Test 3: Analyze individual files
        print("\n3. Analyzing individual files...")

        for filename in test_files.keys():
            file_path = sandbox_path / filename
            print(f"   Analyzing {filename}...")

            try:
                analysis = await code_intel.analyze_code_file(str(file_path))
                symbols = analysis.get('symbols', [])
                print(f"   ✅ Found {len(symbols)} symbols in {filename}")

                # Show some symbol details
                for symbol in symbols[:3]:  # Show first 3 symbols
                    print(f"      - {symbol['kind']}: {symbol['name']} (line {symbol['line']})")

            except Exception as e:
                print(f"   ❌ Failed to analyze {filename}: {e}")
                return False

        # Test 4: Test symbol reference finding
        print("\n4. Testing symbol reference finding...")

        # Find references to Calculator class
        try:
            refs = await code_intel.find_symbol_references(str(sandbox_path / "main.py"), "Calculator")
            print(f"✅ Found {len(refs)} references to 'Calculator'")
            for ref in refs:
                print(f"   - {ref['file']}:{ref['line']}: {ref['context']}")
        except Exception as e:
            print(f"❌ Failed to find symbol references: {e}")
            return False

        # Test 5: Test symbol info retrieval
        print("\n5. Testing symbol information retrieval...")

        try:
            symbol_info = await code_intel.get_symbol_info(str(sandbox_path / "utils.py"), "calculate_total")
            if symbol_info:
                print("✅ Retrieved symbol info for 'calculate_total':")
                print(f"   - Type: {symbol_info.get('type')}")
                print(f"   - Location: {symbol_info.get('file')}:{symbol_info.get('line')}")
                if symbol_info.get('docstring'):
                    print(f"   - Docstring: {symbol_info['docstring'][:50]}...")
            else:
                print("❌ No symbol info found for 'calculate_total'")
                return False
        except Exception as e:
            print(f"❌ Failed to get symbol info: {e}")
            return False

        # Test 6: Test cross-file dependency analysis
        print("\n6. Testing cross-file dependency analysis...")

        try:
            # Analyze main.py which imports from utils
            analysis = await code_intel.analyze_code_file(str(sandbox_path / "main.py"))
            imports = analysis.get('imports', [])
            print(f"✅ Found {len(imports)} imports in main.py:")
            for imp in imports:
                print(f"   - {imp['module']}: {imp.get('names', [])}")
        except Exception as e:
            print(f"❌ Failed dependency analysis: {e}")
            return False

        # Test 7: Performance test
        print("\n7. Testing performance (cached vs fresh analysis)...")

        import time

        # First analysis (should be slower)
        start_time = time.time()
        await code_intel.analyze_code_file(str(sandbox_path / "main.py"))
        first_duration = time.time() - start_time

        # Second analysis (should be faster due to caching)
        start_time = time.time()
        await code_intel.analyze_code_file(str(sandbox_path / "main.py"))
        second_duration = time.time() - start_time

        print(".2f")
        print(".2f")

        if second_duration < first_duration * 0.8:  # At least 20% faster
            print("✅ Caching is working effectively")
        else:
            print("⚠️  Caching may not be as effective as expected")

    print("\n" + "=" * 60)
    print("🎉 All Code Intelligence Integration Tests Passed!")
    return True


async def test_agent_tool_integration():
    """Test that the code intelligence tools are properly integrated with agents."""
    print("\n🔧 Testing Agent Tool Integration")
    print("=" * 60)

    # Import the local tools to check integration
    try:
        from app.agents.local_tools import LOCAL_TOOLS
        print(f"✅ Successfully imported LOCAL_TOOLS ({len(LOCAL_TOOLS)} tools)")

        # Check that our code intelligence tools are present
        tool_names = [tool.__name__ if hasattr(tool, '__name__') else str(tool) for tool in LOCAL_TOOLS]
        expected_tools = ['analyze_code_file', 'find_symbol_references', 'get_symbol_info', 'index_project_files']

        found_tools = []
        for expected in expected_tools:
            if any(expected in name for name in tool_names):
                found_tools.append(expected)
                print(f"✅ Found tool: {expected}")
            else:
                print(f"❌ Missing tool: {expected}")

        if len(found_tools) == len(expected_tools):
            print("✅ All code intelligence tools are properly integrated")
            return True
        else:
            print(f"❌ Only {len(found_tools)}/{len(expected_tools)} tools found")
            return False

    except ImportError as e:
        print(f"❌ Failed to import local_tools: {e}")
        return False


async def main():
    """Run all tests."""
    print("🚀 Starting Code Intelligence System Tests")
    print("=" * 80)

    success = True

    # Test integration
    if not await test_code_intelligence_integration():
        success = False

    # Test agent integration
    if not await test_agent_tool_integration():
        success = False

    print("\n" + "=" * 80)
    if success:
        print("🎯 ALL TESTS PASSED! Code Intelligence System is fully operational.")
        return 0
    else:
        print("❌ SOME TESTS FAILED! Please check the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)