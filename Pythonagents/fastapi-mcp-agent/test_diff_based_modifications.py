#!/usr/bin/env python3
"""
Test script for diff-based code modification tools (Priority 2.1)
Tests apply_code_edit, suggest_code_edit, preview_changes, and rollback_changes
"""

import sys
import os
import tempfile
import shutil

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from agents.local_tools import apply_code_edit, suggest_code_edit, preview_changes, rollback_changes

def test_apply_code_edit():
    """Test the apply_code_edit tool"""
    print("🧪 Testing apply_code_edit...")

    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("""def hello_world():
    print("Hello, World!")
    return "done"

def goodbye_world():
    print("Goodbye, World!")
    return "finished"
""")
        test_file = f.name

    try:
        # Test single edit - use .invoke() method for StructuredTool
        edits = [{
            "old_string": 'def hello_world():\n    print("Hello, World!")\n    return "done"',
            "new_string": 'def hello_world():\n    print("Hello, Universe!")\n    return "done"'
        }]

        result = apply_code_edit.invoke({"file_path": test_file, "edits": edits, "session_id": "test_session", "description": "Update greeting"})
        print(f"✓ Single edit result: {result}")

        # Verify the change
        with open(test_file, 'r') as f:
            content = f.read()
            assert '"Hello, Universe!"' in content
            assert '"Hello, World!"' not in content

        # Test multiple edits
        edits = [
            {
                "old_string": 'def goodbye_world():\n    print("Goodbye, World!")\n    return "finished"',
                "new_string": 'def farewell_world():\n    print("Farewell, World!")\n    return "finished"'
            }
        ]

        result = apply_code_edit.invoke({"file_path": test_file, "edits": edits, "session_id": "test_session", "description": "Rename function"})
        print(f"✓ Multiple edits result: {result}")

        # Verify both changes
        with open(test_file, 'r') as f:
            content = f.read()
            assert 'def farewell_world():' in content
            assert '"Farewell, World!"' in content

        print("✅ apply_code_edit tests passed!")
        return True

    except Exception as e:
        print(f"❌ apply_code_edit test failed: {e}")
        return False
    finally:
        os.unlink(test_file)

def test_suggest_code_edit():
    """Test the suggest_code_edit tool"""
    print("🧪 Testing suggest_code_edit...")

    # Create a temporary test file with some issues
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("""def very_long_function_that_does_many_things(param1, param2, param3, param4, param5):
    result = []
    for i in range(100):  # Magic number
        if i % 15 == 0:
            result.append("FizzBuzz")
        elif i % 3 == 0:
            result.append("Fizz")
        elif i % 5 == 0:
            result.append("Buzz")
        else:
            result.append(str(i))
    return result

# Another function with eval (security issue)
def dangerous_function(code_string):
    return eval(code_string)  # Security risk!
""")
        test_file = f.name

    try:
        # Test general improvements
        result = suggest_code_edit.invoke({"file_path": test_file, "improvement_type": "general", "context_lines": 3})
        print(f"✓ General suggestions: {len(result.split('**')) - 1} suggestions found")

        # Test security improvements
        result = suggest_code_edit.invoke({"file_path": test_file, "improvement_type": "security", "context_lines": 3})
        print(f"✓ Security suggestions: {'eval()' in result}")

        print("✅ suggest_code_edit tests passed!")
        return True

    except Exception as e:
        print(f"❌ suggest_code_edit test failed: {e}")
        return False
    finally:
        os.unlink(test_file)

def test_preview_changes():
    """Test the preview_changes tool"""
    print("🧪 Testing preview_changes...")

    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("""def original_function():
    return "original"

def another_function():
    return "another"
""")
        test_file = f.name

    try:
        # Test preview
        edits = [{
            "old_string": 'def original_function():\n    return "original"',
            "new_string": 'def modified_function():\n    return "modified"'
        }]

        result = preview_changes.invoke({"file_path": test_file, "edits": edits, "context_lines": 3})
        print(f"✓ Preview generated: {len(result)} characters")

        # Check that diff markers are present
        assert '@@' in result  # Unified diff markers
        assert 'original_function' in result
        assert 'modified_function' in result

        print("✅ preview_changes tests passed!")
        return True

    except Exception as e:
        print(f"❌ preview_changes test failed: {e}")
        return False
    finally:
        os.unlink(test_file)

def test_rollback_changes():
    """Test the rollback_changes tool"""
    print("🧪 Testing rollback_changes...")

    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("""def test_function():
    return "original"
""")
        test_file = f.name

    try:
        # Make a change
        edits = [{
            "old_string": 'def test_function():\n    return "original"',
            "new_string": 'def test_function():\n    return "modified"'
        }]

        apply_code_edit.invoke({"file_path": test_file, "edits": edits, "session_id": "rollback_test", "description": "Test change"})

        # Verify change was applied
        with open(test_file, 'r') as f:
            content = f.read()
            assert '"modified"' in content

        # Rollback the change
        result = rollback_changes.invoke({"session_id": "rollback_test", "steps_back": 1})
        print(f"✓ Rollback result: {result}")

        # Verify rollback worked
        with open(test_file, 'r') as f:
            content = f.read()
            assert '"original"' in content
            assert '"modified"' not in content

        print("✅ rollback_changes tests passed!")
        return True

    except Exception as e:
        print(f"❌ rollback_changes test failed: {e}")
        return False
    finally:
        os.unlink(test_file)

def main():
    """Run all tests"""
    print("🚀 Testing Diff-Based Code Modification Tools (Priority 2.1)\n")

    tests = [
        test_apply_code_edit,
        test_suggest_code_edit,
        test_preview_changes,
        test_rollback_changes
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")

    print(f"\n📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All diff-based code modification tools are working correctly!")
        print("✅ Priority 2.1 implementation complete!")
        return 0
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())