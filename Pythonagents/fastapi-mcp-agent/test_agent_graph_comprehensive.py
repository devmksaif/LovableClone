#!/usr/bin/env python3
"""
Comprehensive test suite for the AgentGraph with complex scenarios.
Tests various edge cases, error handling, and multi-step workflows.
"""

import asyncio
import os
import sys
import json
from typing import Dict, Any, List

# Add the app directory to the path
sys.path.insert(0, '/Users/Apple/Desktop/NextLovable/Pythonagents/fastapi-mcp-agent')

from app.agents.agent_graphs import create_agent_graph, execute_agent_graph


class AgentGraphTester:
    """Comprehensive tester for AgentGraph functionality."""

    def __init__(self, api_keys: Dict[str, str]):
        self.api_keys = api_keys
        self.test_results = []

    async def run_all_tests(self):
        """Run all test cases."""
        print("🚀 Starting AgentGraph Comprehensive Tests")
        print("=" * 60)

        test_cases = [
            self.test_simple_function,
            self.test_complex_algorithm,
            self.test_error_handling,
            self.test_code_with_issues,
            self.test_multi_file_project,
            self.test_api_integration,
            self.test_performance_optimization,
        ]

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📋 Test {i}: {test_case.__name__}")
            print("-" * 40)

            try:
                result = await test_case()
                self.test_results.append({
                    'test': test_case.__name__,
                    'status': 'PASS' if result else 'FAIL',
                    'details': result if isinstance(result, dict) else {}
                })
                print(f"✅ {test_case.__name__}: {'PASS' if result else 'FAIL'}")
            except Exception as e:
                self.test_results.append({
                    'test': test_case.__name__,
                    'status': 'ERROR',
                    'details': str(e)
                })
                print(f"❌ {test_case.__name__}: ERROR - {e}")

        self.print_summary()

    async def test_simple_function(self):
        """Test simple function generation."""
        graph = create_agent_graph(self.api_keys)

        test_data = {
            'user_request': 'Create a Python function that calculates the factorial of a number using recursion',
            'session_id': 'test-factorial',
            'model': 'groq/openai/gpt-oss-120b',
            'sandbox_context': {},
            'sandbox_id': 'test-sandbox',
            'available_tools': [],
            'tool_results': []
        }

        result = await execute_agent_graph(graph, test_data)

        # Validate results
        code = result.get('generated_code', '')
        review = result.get('review_feedback', {})

        success = (
            'def factorial' in code and
            'return' in code and
            isinstance(review, dict) and
            len(review.get('issues_found', [])) == 0
        )

        return {
            'success': success,
            'code_length': len(code),
            'has_factorial': 'factorial' in code,
            'has_recursion': 'factorial(n-1)' in code,
            'review_clean': len(review.get('issues_found', [])) == 0
        }

    async def test_complex_algorithm(self):
        """Test complex algorithm implementation."""
        graph = create_agent_graph(self.api_keys)

        test_data = {
            'user_request': 'Implement a binary search algorithm in Python with proper error handling and documentation',
            'session_id': 'test-binary-search',
            'model': 'groq/openai/gpt-oss-120b',
            'sandbox_context': {},
            'sandbox_id': 'test-sandbox',
            'available_tools': [],
            'tool_results': []
        }

        result = await execute_agent_graph(graph, test_data)

        code = result.get('generated_code', '')
        review = result.get('review_feedback', {})

        success = (
            'def binary_search' in code and
            'while' in code and
            'mid =' in code and
            'return' in code and
            'docstring' in code.lower() or '"""' in code
        )

        return {
            'success': success,
            'code_length': len(code),
            'has_binary_search': 'binary_search' in code,
            'has_loop': 'while' in code,
            'has_documentation': '"""' in code or 'docstring' in code.lower(),
            'review_issues': len(review.get('issues_found', []))
        }

    async def test_error_handling(self):
        """Test error handling in generated code."""
        graph = create_agent_graph(self.api_keys)

        test_data = {
            'user_request': 'Create a Python function that reads a file and handles all possible errors (file not found, permission denied, encoding issues)',
            'session_id': 'test-error-handling',
            'model': 'groq-openai/gpt-oss-120b',
            'sandbox_context': {},
            'sandbox_id': 'test-sandbox',
            'available_tools': [],
            'tool_results': []
        }

        result = await execute_agent_graph(graph, test_data)

        code = result.get('generated_code', '')

        success = (
            'try:' in code and
            'except' in code and
            ('FileNotFoundError' in code or 'IOError' in code or 'OSError' in code) and
            'with open' in code
        )

        return {
            'success': success,
            'has_try_except': 'try:' in code,
            'has_file_errors': any(err in code for err in ['FileNotFoundError', 'IOError', 'OSError']),
            'has_with_statement': 'with open' in code,
            'code_length': len(code)
        }

    async def test_code_with_issues(self):
        """Test code that should trigger the fixer agent."""
        graph = create_agent_graph(self.api_keys)

        test_data = {
            'user_request': 'Create a Python function with intentional bugs: divide by zero, undefined variable, and syntax error. Make sure the review agent catches these issues.',
            'session_id': 'test-buggy-code',
            'model': 'groq/openai/gpt-oss-120b',
            'sandbox_context': {},
            'sandbox_id': 'test-sandbox',
            'available_tools': [],
            'tool_results': []
        }

        result = await execute_agent_graph(graph, test_data)

        review = result.get('review_feedback', {})
        progress = result.get('progress_updates', [])

        # Check if issues were found and potentially fixed
        issues_found = review.get('issues_found', []) if isinstance(review, dict) else []
        fixer_called = any('fixer' in str(update) for update in progress)

        return {
            'issues_detected': len(issues_found) > 0,
            'fixer_called': fixer_called,
            'review_type': type(review).__name__,
            'progress_steps': len(progress),
            'has_issues': len(issues_found) > 0
        }

    async def test_multi_file_project(self):
        """Test generating a multi-file project structure."""
        graph = create_agent_graph(self.api_keys)

        test_data = {
            'user_request': 'Create a simple Flask web application with the following structure: app.py (main app), models.py (database models), routes.py (API routes), and requirements.txt',
            'session_id': 'test-flask-app',
            'model': 'groq/openai/gpt-oss-120b',
            'sandbox_context': {},
            'sandbox_id': 'test-sandbox',
            'available_tools': [],
            'tool_results': []
        }

        result = await execute_agent_graph(graph, test_data)

        code = result.get('generated_code', '')

        success = (
            'app.py' in code or 'Flask' in code and
            ('models.py' in code or 'SQLAlchemy' in code or 'database' in code.lower()) and
            ('routes.py' in code or 'route' in code.lower()) and
            'requirements.txt' in code
        )

        return {
            'success': success,
            'has_main_app': 'Flask' in code or 'app.py' in code,
            'has_models': 'models.py' in code or 'SQLAlchemy' in code,
            'has_routes': 'routes.py' in code or '@app.route' in code,
            'has_requirements': 'requirements.txt' in code,
            'code_length': len(code)
        }

    async def test_api_integration(self):
        """Test API integration code generation."""
        graph = create_agent_graph(self.api_keys)

        test_data = {
            'user_request': 'Create a Python script that fetches data from a REST API (https://jsonplaceholder.typicode.com/posts), handles errors, and saves the data to a JSON file',
            'session_id': 'test-api-integration',
            'model': 'groq/openai/gpt-oss-120b',
            'sandbox_context': {},
            'sandbox_id': 'test-sandbox',
            'available_tools': [],
            'tool_results': []
        }

        result = await execute_agent_graph(graph, test_data)

        code = result.get('generated_code', '')

        success = (
            ('requests' in code or 'urllib' in code) and
            'json' in code and
            ('try:' in code or 'except' in code) and
            ('.json()' in code or 'json.load' in code) and
            ('open(' in code or 'with open' in code)
        )

        return {
            'success': success,
            'has_http_client': 'requests' in code or 'urllib' in code,
            'has_json_handling': 'json' in code,
            'has_error_handling': 'try:' in code or 'except' in code,
            'has_file_operations': 'open(' in code or 'with open' in code,
            'code_length': len(code)
        }

    async def test_performance_optimization(self):
        """Test performance optimization suggestions."""
        graph = create_agent_graph(self.api_keys)

        test_data = {
            'user_request': 'Optimize this inefficient Python code for better performance: [paste inefficient list comprehension with nested loops and redundant operations]',
            'session_id': 'test-performance',
            'model': 'groq/openai/gpt-oss-120b',
            'sandbox_context': {},
            'sandbox_id': 'test-sandbox',
            'available_tools': [],
            'tool_results': []
        }

        result = await execute_agent_graph(graph, test_data)

        code = result.get('generated_code', '')
        review = result.get('review_feedback', {})

        # Check for optimization suggestions
        optimization_keywords = ['efficient', 'optimize', 'performance', 'faster', 'complexity', 'O(n)']

        success = (
            any(keyword in code.lower() for keyword in optimization_keywords) or
            any(keyword in str(review).lower() for keyword in optimization_keywords)
        )

        return {
            'success': success,
            'has_optimization_suggestions': any(keyword in code.lower() for keyword in optimization_keywords),
            'review_has_performance_notes': any(keyword in str(review).lower() for keyword in optimization_keywords),
            'code_length': len(code)
        }

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in self.test_results if r['status'] == 'PASS')
        failed = sum(1 for r in self.test_results if r['status'] == 'FAIL')
        errors = sum(1 for r in self.test_results if r['status'] == 'ERROR')

        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"🔥 Errors: {errors}")
        print(f"📈 Success Rate: {(passed / len(self.test_results)) * 100:.1f}%")

        print("\n📋 Detailed Results:")
        for result in self.test_results:
            status_emoji = {
                'PASS': '✅',
                'FAIL': '❌',
                'ERROR': '🔥'
            }.get(result['status'], '❓')

            print(f"{status_emoji} {result['test']}: {result['status']}")

            if result['status'] != 'PASS' and result['details']:
                if isinstance(result['details'], dict):
                    for key, value in result['details'].items():
                        print(f"   - {key}: {value}")
                else:
                    print(f"   - {result['details']}")


async def main():
    """Main test runner."""
    # Get API key from environment
    groq_key = os.getenv('GROQ_API_KEY')
    if not groq_key:
        print("❌ GROQ_API_KEY environment variable not set")
        return

    print(f"🔑 API key found (length: {len(groq_key)})")

    # Initialize tester
    tester = AgentGraphTester({'groq': groq_key})

    # Run all tests
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())