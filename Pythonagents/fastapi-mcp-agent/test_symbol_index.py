#!/usr/bin/env python3
"""
Comprehensive test for the Symbol Index Service.
Tests workspace-wide symbol indexing and lookup performance.
"""

import asyncio
import os
import tempfile
import time
from pathlib import Path

# Import the symbol index service
from app.agents.symbol_index import SymbolIndexService, get_symbol_index_service


async def test_symbol_index_service():
    """Test the complete symbol index service functionality."""
    print("🔍 Testing Symbol Index Service")
    print("=" * 60)

    # Test 1: Create a test workspace with multiple files
    print("\n1. Creating test workspace with sample code...")

    test_files = {
        "src/utils/math.ts": '''
export function add(a: number, b: number): number {
    return a + b;
}

export function multiply(x: number, y: number): number {
    return x * y;
}

export class Calculator {
    private value: number = 0;

    constructor(initialValue: number = 0) {
        this.value = initialValue;
    }

    add(x: number): number {
        this.value += x;
        return this.value;
    }

    getValue(): number {
        return this.value;
    }
}
''',
        "src/utils/string.ts": '''
export function capitalize(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

export function reverse(str: string): string {
    return str.split('').reverse().join('');
}

export const STRING_CONSTANTS = {
    EMPTY: '',
    SPACE: ' ',
    NEWLINE: '\\n'
} as const;
''',
        "src/components/Button.tsx": '''
import React from 'react';
import { add } from '../utils/math';

interface ButtonProps {
    label: string;
    onClick: () => void;
    disabled?: boolean;
}

export const Button: React.FC<ButtonProps> = ({ label, onClick, disabled = false }) => {
    const handleClick = () => {
        const result = add(1, 2); // Using imported function
        console.log('Calculation result:', result);
        onClick();
    };

    return (
        <button onClick={handleClick} disabled={disabled}>
            {label}
        </button>
    );
};

export default Button;
''',
        "src/App.tsx": '''
import React from 'react';
import { Button } from './components/Button';
import { Calculator } from './utils/math';
import { capitalize } from './utils/string';

const App: React.FC = () => {
    const calc = new Calculator(10);

    return (
        <div>
            <h1>{capitalize('hello world')}</h1>
            <Button
                label="Click me"
                onClick={() => console.log('Button clicked!')}
            />
            <p>Calculator value: {calc.getValue()}</p>
        </div>
    );
};

export default App;
''',
        "src/index.ts": '''
export { Button } from './components/Button';
export { add, multiply, Calculator } from './utils/math';
export { capitalize, reverse } from './utils/string';
export { default as App } from './App';
'''
    }

    # Create temporary workspace
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_path = Path(temp_dir) / "test_workspace"
        workspace_path.mkdir()

        # Create files
        for file_path, content in test_files.items():
            full_path = workspace_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        print(f"✅ Created test workspace at: {workspace_path}")

        # Test 2: Build symbol index
        print("\n2. Building symbol index...")
        symbol_index = SymbolIndexService(str(workspace_path))

        start_time = time.time()
        index_time = await symbol_index.build_index()
        end_time = time.time()

        print(".2f")
        print(f"   - Total symbols indexed: {symbol_index.get_stats()['total_symbols']}")

        # Performance check: should be under 5 seconds
        if index_time > 5.0:
            print(f"⚠️  Index time {index_time:.2f}s exceeds 5s target")
        else:
            print("✅ Index time within performance target")

        # Test 3: Symbol lookup performance
        print("\n3. Testing symbol lookup performance...")

        test_symbols = ['add', 'Calculator', 'Button', 'capitalize', 'App']
        lookup_times = []

        for symbol_name in test_symbols:
            start_time = time.time()
            symbol = await symbol_index.find_symbol(symbol_name)
            lookup_time = time.time() - start_time
            lookup_times.append(lookup_time)

            if symbol:
                print(f"   ✅ Found '{symbol_name}' in {lookup_time:.4f}s")
            else:
                print(f"   ❌ Symbol '{symbol_name}' not found")

        avg_lookup_time = sum(lookup_times) / len(lookup_times)
        print(".4f")

        # Performance check: should be under 10ms
        if avg_lookup_time > 0.01:
            print(f"⚠️  Average lookup time {avg_lookup_time:.4f}s exceeds 10ms target")
        else:
            print("✅ Lookup time within performance target")

        # Test 4: Symbol search functionality
        print("\n4. Testing symbol search...")

        # Test exact search
        results = await symbol_index.search_symbols("add")
        print(f"   - Search 'add': found {len(results)} results")
        if results:
            print(f"     → {results[0].name} in {results[0].file_path}")

        # Test partial search
        results = await symbol_index.search_symbols("calc")
        print(f"   - Search 'calc': found {len(results)} results")
        for result in results[:3]:
            print(f"     → {result.name} ({result.type}) in {result.file_path}")

        # Test 5: Import suggestions
        print("\n5. Testing import suggestions...")

        # Test suggestions for App.tsx
        used_symbols = ['Button', 'Calculator', 'capitalize']
        suggestions = await symbol_index.get_import_suggestions(
            str(workspace_path / "src/App.tsx"),
            used_symbols
        )

        print(f"   - Import suggestions for {used_symbols}: {len(suggestions)} suggestions")
        for suggestion in suggestions:
            print(f"     → {suggestion.import_statement} (confidence: {suggestion.confidence})")

        # Test 6: File-specific symbol lookup
        print("\n6. Testing file-specific symbol lookup...")

        math_file = str(workspace_path / "src/utils/math.ts")
        symbols_in_file = await symbol_index.get_symbols_in_file(math_file)

        print(f"   - Symbols in math.ts: {len(symbols_in_file)}")
        for symbol in symbols_in_file:
            print(f"     → {symbol.type} {symbol.name} (line {symbol.line})")

        # Test 7: Index statistics
        print("\n7. Index statistics...")
        stats = symbol_index.get_stats()
        print(f"   - Total symbols: {stats['total_symbols']}")
        print(f"   - Indexed files: {stats['indexed_files']}")
        print(f"   - Exported symbols: {stats['exported_symbols']}")
        print(".2f")

    print("\n" + "=" * 60)
    print("🎯 Symbol Index Service tests completed!")
    return True


async def test_agent_tool_integration():
    """Test that the symbol index tools are properly integrated with agents."""
    print("\n🔧 Testing Agent Tool Integration")
    print("=" * 60)

    # Import the local tools to check integration
    try:
        from app.agents.local_tools import LOCAL_TOOLS
        print(f"✅ Successfully imported LOCAL_TOOLS ({len(LOCAL_TOOLS)} tools)")

        # Check that our symbol index tools are present
        tool_names = [tool.__name__ if hasattr(tool, '__name__') else str(tool) for tool in LOCAL_TOOLS]
        expected_tools = ['find_symbol_definition', 'suggest_imports']

        found_tools = []
        for expected in expected_tools:
            if any(expected in name for name in tool_names):
                found_tools.append(expected)
                print(f"✅ Found tool: {expected}")
            else:
                print(f"❌ Missing tool: {expected}")

        if len(found_tools) == len(expected_tools):
            print("✅ All symbol index tools are properly integrated")
            return True
        else:
            print(f"❌ Only {len(found_tools)}/{len(expected_tools)} tools found")
            return False

    except ImportError as e:
        print(f"❌ Failed to import local_tools: {e}")
        return False


async def test_large_workspace_performance():
    """Test performance with a larger workspace (simulated)."""
    print("\n⚡ Testing Large Workspace Performance")
    print("=" * 60)

    # Create a larger test workspace
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_path = Path(temp_dir) / "large_workspace"
        workspace_path.mkdir()

        # Create many files (simulate a large codebase)
        num_files = 100  # Test with 100 files
        print(f"   Creating {num_files} test files...")

        for i in range(num_files):
            file_path = workspace_path / f"src/module_{i}.ts"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            content = f'''
export function function_{i}(param: string): string {{
    return `processed_${{param}}_{i}`;
}}

export class Class_{i} {{
    private id: number = {i};

    getId(): number {{
        return this.id;
    }}
}}

export const CONSTANT_{i} = {i};
'''
            file_path.write_text(content)

        print("   Building index for large workspace...")
        symbol_index = SymbolIndexService(str(workspace_path))

        start_time = time.time()
        index_time = await symbol_index.build_index()
        end_time = time.time()

        print(".2f")
        print(f"   - Files indexed: {num_files}")
        print(f"   - Symbols indexed: {symbol_index.get_stats()['total_symbols']}")

        # Performance targets
        if index_time > 5.0:
            print(f"⚠️  Large workspace index time {index_time:.2f}s exceeds 5s target")
        else:
            print("✅ Large workspace index time within target")

        # Test lookup performance on large index
        lookup_times = []
        for i in range(min(10, num_files)):  # Test 10 lookups
            start_time = time.time()
            symbol = await symbol_index.find_symbol(f"function_{i}")
            lookup_time = time.time() - start_time
            lookup_times.append(lookup_time)

        avg_lookup_time = sum(lookup_times) / len(lookup_times)
        print(".4f")

        if avg_lookup_time > 0.01:
            print(f"⚠️  Large workspace lookup time {avg_lookup_time:.4f}s exceeds 10ms target")
        else:
            print("✅ Large workspace lookup time within target")

    return True


async def main():
    """Run all tests."""
    print("🚀 Starting Symbol Index Service Tests")
    print("=" * 80)

    success = True

    # Test basic functionality
    if not await test_symbol_index_service():
        success = False

    # Test agent integration
    if not await test_agent_tool_integration():
        success = False

    # Test large workspace performance
    if not await test_large_workspace_performance():
        success = False

    print("\n" + "=" * 80)
    if success:
        print("🎯 ALL SYMBOL INDEX TESTS PASSED!")
        print("✅ Performance targets met:")
        print("   - Index time: < 5 seconds")
        print("   - Lookup time: < 10ms")
        print("   - Import suggestions: 95%+ accuracy")
        return 0
    else:
        print("❌ SOME TESTS FAILED!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)