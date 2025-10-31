#!/usr/bin/env python3
"""
Comprehensive test suite for path safety implementation.
Tests various attack vectors and edge cases to ensure security.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.utils.path_safety import PathSafetyValidator, AccessLevel, PathValidationError

def test_path_traversal_attacks():
    """Test various path traversal attack patterns."""
    print("🔍 Testing path traversal attacks...")
    
    # Create a temporary project directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "test_project"
        project_root.mkdir()
        
        validator = PathSafetyValidator(str(project_root))
        
        # Test cases for path traversal attacks
        attack_patterns = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "....//....//....//etc/passwd",
            "..%2F..%2F..%2Fetc%2Fpasswd",
            "..%252F..%252F..%252Fetc%252Fpasswd",
            "..%c0%af..%c0%af..%c0%afetc%c0%afpasswd",
            "..\\/..\\/../etc/passwd",
            "../../../../../../../../../../etc/passwd",
            "file:///etc/passwd",
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\SAM",
            "\\\\server\\share\\file.txt",
            "..\\..\\..\\..\\..\\..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
        ]
        
        failed_attacks = []
        for pattern in attack_patterns:
            try:
                validator.validate_path(pattern, AccessLevel.READ_ONLY)
                failed_attacks.append(pattern)
                print(f"❌ SECURITY BREACH: Pattern '{pattern}' was allowed!")
            except PathValidationError:
                print(f"✅ Blocked: {pattern}")
        
        if failed_attacks:
            print(f"\n🚨 CRITICAL: {len(failed_attacks)} attack patterns were not blocked!")
            return False
        else:
            print("✅ All path traversal attacks successfully blocked!")
            return True

def test_symlink_attacks():
    """Test symlink-based attacks."""
    print("\n🔍 Testing symlink attacks...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "test_project"
        project_root.mkdir()
        
        # Create a symlink pointing outside the project
        external_file = Path(temp_dir) / "external_secret.txt"
        external_file.write_text("SECRET DATA")
        
        symlink_path = project_root / "innocent_file.txt"
        try:
            symlink_path.symlink_to(external_file)
        except OSError:
            print("⚠️  Symlink creation failed (may not be supported on this system)")
            return True
        
        validator = PathSafetyValidator(str(project_root))
        
        try:
            validator.validate_path(str(symlink_path), AccessLevel.READ_ONLY)
            print("❌ SECURITY BREACH: Symlink attack was allowed!")
            return False
        except PathValidationError:
            print("✅ Symlink attack successfully blocked!")
            return True

def test_dangerous_file_extensions():
    """Test blocking of dangerous file extensions."""
    print("\n🔍 Testing dangerous file extensions...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "test_project"
        project_root.mkdir()
        
        validator = PathSafetyValidator(str(project_root))
        
        dangerous_files = [
            "malware.exe",
            "script.bat",
            "command.cmd",
            "shell.sh",
            "program.com",
            "system.scr",
            "virus.pif",
            "trojan.msi",
            "backdoor.dll",
            "keylogger.jar",
        ]
        
        failed_blocks = []
        for filename in dangerous_files:
            # Use relative path to test dangerous extension detection
            try:
                validator.validate_path(filename, AccessLevel.READ_WRITE)
                failed_blocks.append(filename)
                print(f"❌ SECURITY BREACH: Dangerous file '{filename}' was allowed!")
            except PathValidationError:
                print(f"✅ Blocked dangerous file: {filename}")
        
        if failed_blocks:
            print(f"\n🚨 CRITICAL: {len(failed_blocks)} dangerous files were not blocked!")
            return False
        else:
            print("✅ All dangerous file extensions successfully blocked!")
            return True

def test_system_directory_access():
    """Test blocking access to system directories."""
    print("\n🔍 Testing system directory access...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "test_project"
        project_root.mkdir()
        
        validator = PathSafetyValidator(str(project_root))
        
        # Test both absolute paths (should be blocked immediately) 
        # and relative paths that could resolve to system directories
        system_paths = [
            "/etc/passwd",  # Absolute path - should be blocked
            "/root/.ssh/id_rsa",  # Absolute path - should be blocked
            "/var/log/auth.log",  # Absolute path - should be blocked
            "/proc/version",  # Absolute path - should be blocked
            "/sys/kernel/debug",  # Absolute path - should be blocked
            "C:\\Windows\\System32",  # Absolute path - should be blocked
            "C:\\Users\\Administrator",  # Absolute path - should be blocked
            "/System/Library/Frameworks",  # Absolute path - should be blocked
            "/usr/bin/sudo",  # Absolute path - should be blocked
            "/home/user/.ssh/authorized_keys",  # Absolute path - should be blocked
        ]
        
        blocked_count = 0
        failed_blocks = []
        
        for sys_path in system_paths:
            is_valid, _, error_msg = validator.validate_path(sys_path, AccessLevel.READ_ONLY)
            if not is_valid:
                blocked_count += 1
                print(f"✅ Blocked system path: {sys_path} ({error_msg})")
            else:
                failed_blocks.append(sys_path)
                print(f"❌ SECURITY BREACH: System path '{sys_path}' was allowed!")
        
        if failed_blocks:
            print(f"\n🚨 CRITICAL: {len(failed_blocks)} system paths were not blocked!")
            return False
        
        print(f"✅ All {blocked_count} system paths correctly blocked!")
        return True

def test_valid_operations():
    """Test that valid operations within the project are allowed."""
    print("\n🔍 Testing valid operations...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "sandboxes"
        project_root.mkdir()
        
        # Create a sandbox directory structure
        sandbox_dir = project_root / "sandbox_test123"
        sandbox_dir.mkdir()
        (sandbox_dir / "src").mkdir()
        (sandbox_dir / "src" / "main.py").write_text("print('Hello, World!')")
        (sandbox_dir / "index.html").write_text("<html></html>")
        (sandbox_dir / "package.json").write_text('{"version": "1.0"}')
        
        validator = PathSafetyValidator(str(project_root))
        
        valid_paths = [
            "sandbox_test123/src/main.py",
            "sandbox_test123/index.html",
            "sandbox_test123/package.json",
            "sandbox_test123/src/../index.html",  # Should resolve to index.html
            "./sandbox_test123/src/main.py",
        ]
        
        failed_validations = []
        for path in valid_paths:
            try:
                validator.validate_path(path, AccessLevel.READ_ONLY)
                print(f"✅ Valid path allowed: {path}")
            except PathValidationError as e:
                failed_validations.append((path, str(e)))
                print(f"❌ Valid path blocked: {path} - {e}")
        
        if failed_validations:
            print(f"\n⚠️  {len(failed_validations)} valid operations were incorrectly blocked!")
            return False
        else:
            print("✅ All valid operations correctly allowed!")
            return True

def test_access_level_restrictions():
    """Test access level restrictions."""
    print("\n🔍 Testing access level restrictions...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "sandboxes"
        project_root.mkdir()
        
        # Create a sandbox directory
        sandbox_dir = project_root / "sandbox_test456"
        sandbox_dir.mkdir()
        
        validator = PathSafetyValidator(str(project_root))
        
        # Test read-only access to a file that would require write permissions
        test_file = sandbox_dir / "test.txt"
        test_file.write_text("test content")
        
        try:
            # This should work - reading existing file
            validator.validate_path(str(test_file), AccessLevel.READ_ONLY)
            print("✅ Read access to existing file allowed")
        except PathValidationError:
            print("❌ Read access to existing file incorrectly blocked")
            return False
        
        try:
            # This should work - writing to file
            validator.validate_path(str(test_file), AccessLevel.READ_WRITE)
            print("✅ Write access to file allowed")
        except PathValidationError:
            print("❌ Write access to file incorrectly blocked")
            return False
        
        return True

def run_all_tests():
    """Run all security tests."""
    print("🛡️  Starting Path Safety Security Test Suite")
    print("=" * 50)
    
    tests = [
        test_path_traversal_attacks,
        test_symlink_attacks,
        test_dangerous_file_extensions,
        test_system_directory_access,
        test_valid_operations,
        test_access_level_restrictions,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ Test failed: {test.__name__}")
        except Exception as e:
            print(f"💥 Test crashed: {test.__name__} - {e}")
    
    print("\n" + "=" * 50)
    print(f"🏁 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Path safety implementation is secure.")
        return True
    else:
        print("🚨 SOME TESTS FAILED! Security vulnerabilities detected.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)