"""
Path Safety Utility Module

This module provides comprehensive path validation and security controls
to prevent path traversal attacks and unauthorized file system access.
"""

import os
import logging
from pathlib import Path
from typing import List, Optional, Set, Union, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

class PathValidationError(Exception):
    """Custom exception for path validation errors."""
    pass

class AccessLevel(Enum):
    """Define different access levels for path validation."""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    RESTRICTED = "restricted"
    SANDBOX_ONLY = "sandbox_only"

class PathSafetyValidator:
    """
    Comprehensive path safety validator with configurable security policies.
    """
    
    def __init__(self, project_root: str):
        """
        Initialize the path safety validator.
        
        Args:
            project_root: The root directory for the project
        """
        self.project_root = Path(project_root).resolve()
        
        # Define allowed directories relative to project root (sandboxes directory)
        self.allowed_directories = {
            AccessLevel.READ_WRITE: {
                # Individual sandbox directories (e.g., sandbox_xyz123/)
                "sandbox_*",  # Pattern for sandbox directories
                # Common project directories within sandboxes
                "app",
                "components", 
                "lib",
                "pages",
                "public",
                "src",
                "docs",
                "tests",
                "assets",
                "cache",
                "logs",
                "temp",
                "chroma_db",
                # Configuration files
                "package.json",
                "vite.config.js",
                "tailwind.config.js",
                "postcss.config.js",
                "index.html"
            },
            AccessLevel.READ_ONLY: {
                "node_modules",
                ".next",
                "dist",
                "build",
                "coverage",
                "__pycache__",
                ".pytest_cache",
                "pnpm-lock.yaml"
            },
            AccessLevel.SANDBOX_ONLY: {
                # Allow access to any sandbox directory
                "*"
            }
        }
        
        # Define forbidden directories and files
        self.forbidden_patterns = {
            ".env",
            ".env.local", 
            ".env.production",
            "id_rsa",
            "id_ed25519",
            "private.key",
            "*.pem",
            "*.p12",
            "*.pfx",
            "password",
            "secret",
            "token",
            ".git",
            ".ssh",
            "node_modules/.bin",
            "__pycache__",
            "*.pyc",
            "venv",
            ".venv"
        }
        
        # Define dangerous file extensions
        self.dangerous_extensions = {
            ".exe", ".bat", ".cmd", ".com", ".scr", ".pif",
            ".sh", ".bash", ".zsh", ".fish",  # Allow but log
            ".ps1", ".psm1", ".psd1",
            ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh"
        }
        
        # System directories that should never be accessible
        self.system_directories = {
            "/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin",
            "/var", "/tmp", "/boot", "/dev", "/proc", "/sys", "/root",
            "/home", "/opt", "/mnt", "/media",
            "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
            "C:\\Users\\Administrator", "C:\\System32",
            "/System", "/Library", "/Applications", "/private"
        }

    def validate_path(self, 
                     file_path: Union[str, Path], 
                     access_level: AccessLevel = AccessLevel.READ_WRITE,
                     operation: str = "access") -> Tuple[bool, Path, Optional[str]]:
        """
        Comprehensive path validation with security checks.
        
        Args:
            file_path: The path to validate
            access_level: Required access level
            operation: Type of operation (read, write, delete, etc.)
            
        Returns:
            Tuple of (is_valid, resolved_path, error_message)
        """
        try:
            # Convert to Path object
            if isinstance(file_path, str):
                path = Path(file_path)
            else:
                path = file_path
            
            # SECURITY: Reject absolute paths immediately
            if path.is_absolute():
                return False, path, f"Absolute paths are not allowed: {file_path}"
            
            # Resolve the full path relative to project root
            full_path = (self.project_root / path).resolve()
            
            # 1. Check for symlink attacks
            if self._contains_symlink(path):
                return False, full_path, f"Symlink detected in path: {file_path}"
            
            # 2. Check if path escapes project root
            if not self._is_within_project_root(full_path):
                return False, full_path, f"Path escapes project root: {file_path}"
            
            # 3. Check for system directory access
            if self._is_system_directory(full_path):
                return False, full_path, f"Access to system directory denied: {file_path}"
            
            # 4. Check forbidden patterns
            if self._matches_forbidden_pattern(full_path):
                return False, full_path, f"Access to forbidden file/directory: {file_path}"
            
            # 5. Check dangerous file extensions
            if self._has_dangerous_extension(full_path):
                return False, full_path, f"Access to dangerous file extension denied: {file_path}"
            
            # 6. Check access level permissions
            if not self._check_access_level(full_path, access_level):
                return False, full_path, f"Insufficient permissions for {access_level.value}: {file_path}"
            
            # 7. Check operation-specific restrictions
            if not self._check_operation_permissions(full_path, operation, access_level):
                return False, full_path, f"Operation '{operation}' not allowed on: {file_path}"
            
            # Log successful validation
            logger.debug(f"Path validation successful: {file_path} -> {full_path}")
            return True, full_path, None
            
        except Exception as e:
            logger.error(f"Path validation error for {file_path}: {str(e)}")
            return False, Path(), f"Path validation failed: {str(e)}"

    def _contains_symlink(self, path: Path) -> bool:
        """Check if any component in the path is a symlink."""
        try:
            current_path = self.project_root
            for part in path.parts:
                current_path = current_path / part
                if current_path.exists() and current_path.is_symlink():
                    return True
            return False
        except (OSError, PermissionError):
            # If we can't check, assume it's unsafe
            return True

    def _is_within_project_root(self, full_path: Path) -> bool:
        """Check if the resolved path is within the project root."""
        try:
            # Use relative_to to check containment - will raise ValueError if not contained
            full_path.relative_to(self.project_root)
            return True
        except ValueError:
            return False

    def _is_system_directory(self, full_path: Path) -> bool:
        """Check if path points to a system directory."""
        path_str = str(full_path)
        return any(path_str.startswith(sys_dir) for sys_dir in self.system_directories)

    def _matches_forbidden_pattern(self, full_path: Path) -> bool:
        """Check if path matches any forbidden patterns."""
        path_str = str(full_path).lower()
        name = full_path.name.lower()
        
        for pattern in self.forbidden_patterns:
            if pattern.startswith('*'):
                # Handle wildcard patterns
                if name.endswith(pattern[1:]):
                    return True
            elif pattern in path_str or pattern == name:
                return True
        return False

    def _has_dangerous_extension(self, full_path: Path) -> bool:
        """Check if file has a potentially dangerous extension."""
        return full_path.suffix.lower() in self.dangerous_extensions

    def _check_access_level(self, full_path: Path, access_level: AccessLevel) -> bool:
        """Check if the path is allowed for the given access level."""
        try:
            relative_path = full_path.relative_to(self.project_root)
            path_parts = relative_path.parts
            
            if not path_parts:
                return False
            
            # Check if the top-level directory is allowed for this access level
            top_dir = path_parts[0]
            
            # For READ_WRITE access, check both READ_WRITE and READ_ONLY allowed dirs
            if access_level == AccessLevel.READ_WRITE:
                allowed_dirs = (self.allowed_directories[AccessLevel.READ_WRITE] | 
                              self.allowed_directories[AccessLevel.READ_ONLY])
            else:
                allowed_dirs = self.allowed_directories.get(access_level, set())
            
            # Check if any allowed directory matches the path
            for allowed_dir in allowed_dirs:
                # Handle wildcard patterns
                if "*" in allowed_dir:
                    if allowed_dir == "*":
                        # Allow any directory
                        return True
                    elif allowed_dir.endswith("*"):
                        # Pattern like "sandbox_*"
                        prefix = allowed_dir[:-1]
                        if top_dir.startswith(prefix):
                            return True
                    elif allowed_dir.startswith("*"):
                        # Pattern like "*.txt"
                        suffix = allowed_dir[1:]
                        if str(relative_path).endswith(suffix):
                            return True
                # Exact match or path starts with allowed directory
                elif str(relative_path).startswith(allowed_dir) or top_dir == allowed_dir:
                    return True
            
            return False
            
        except ValueError:
            return False

    def _check_operation_permissions(self, full_path: Path, operation: str, access_level: AccessLevel) -> bool:
        """Check operation-specific permissions."""
        # Read operations are generally allowed if path validation passes
        if operation in ["read", "list", "search"]:
            return True
        
        # Write operations require READ_WRITE access
        if operation in ["write", "create", "append", "update"]:
            return access_level in [AccessLevel.READ_WRITE, AccessLevel.SANDBOX_ONLY]
        
        # Delete operations are more restricted
        if operation in ["delete", "remove"]:
            # Only allow deletion in specific directories
            try:
                relative_path = full_path.relative_to(self.project_root)
                # Allow deletion in sandboxes and temp directories
                allowed_delete_dirs = {"sandboxes", "temp", "tmp", "cache"}
                return any(str(relative_path).startswith(d) for d in allowed_delete_dirs)
            except ValueError:
                return False
        
        # Execute operations are highly restricted
        if operation in ["execute", "run"]:
            return access_level == AccessLevel.SANDBOX_ONLY
        
        return True

    def get_safe_path(self, file_path: Union[str, Path], access_level: AccessLevel = AccessLevel.READ_WRITE) -> Path:
        """
        Get a validated safe path or raise an exception.
        
        Args:
            file_path: The path to validate
            access_level: Required access level
            
        Returns:
            Validated Path object
            
        Raises:
            PathValidationError: If path validation fails
        """
        is_valid, safe_path, error_msg = self.validate_path(file_path, access_level)
        
        if not is_valid:
            raise PathValidationError(f"Path validation failed: {error_msg}")
        
        return safe_path

    def is_safe_for_operation(self, file_path: Union[str, Path], operation: str) -> bool:
        """
        Quick check if a path is safe for a specific operation.
        
        Args:
            file_path: The path to check
            operation: The operation to perform
            
        Returns:
            True if safe, False otherwise
        """
        access_level = AccessLevel.READ_WRITE if operation in ["write", "create", "delete"] else AccessLevel.READ_ONLY
        is_valid, _, _ = self.validate_path(file_path, access_level, operation)
        return is_valid

    def get_allowed_directories(self, access_level: AccessLevel) -> Set[str]:
        """Get the set of allowed directories for an access level."""
        return self.allowed_directories.get(access_level, set()).copy()

    def add_allowed_directory(self, directory: str, access_level: AccessLevel):
        """Add a new allowed directory for an access level."""
        if access_level not in self.allowed_directories:
            self.allowed_directories[access_level] = set()
        self.allowed_directories[access_level].add(directory)
        logger.info(f"Added allowed directory: {directory} for {access_level.value}")

    def remove_allowed_directory(self, directory: str, access_level: AccessLevel):
        """Remove an allowed directory from an access level."""
        if access_level in self.allowed_directories:
            self.allowed_directories[access_level].discard(directory)
            logger.info(f"Removed allowed directory: {directory} from {access_level.value}")


# Global instance - will be initialized when needed
_path_validator: Optional[PathSafetyValidator] = None

def get_path_validator(project_root: Optional[str] = None) -> PathSafetyValidator:
    """
    Get the global path validator instance.
    
    Args:
        project_root: Project root directory (only used for first initialization)
        
    Returns:
        PathSafetyValidator instance
    """
    global _path_validator
    
    if _path_validator is None:
        if project_root is None:
            # Use the sandboxes directory as the default project root
            project_root = os.environ.get('PROJECT_ROOT', '/Users/Apple/Desktop/NextLovable/sandboxes')
        _path_validator = PathSafetyValidator(project_root)
    
    return _path_validator

def validate_file_path(file_path: Union[str, Path], 
                      operation: str = "access",
                      access_level: AccessLevel = AccessLevel.READ_WRITE) -> Tuple[bool, Path, Optional[str]]:
    """
    Convenience function for path validation.
    
    Args:
        file_path: Path to validate
        operation: Operation to perform
        access_level: Required access level
        
    Returns:
        Tuple of (is_valid, resolved_path, error_message)
    """
    validator = get_path_validator()
    return validator.validate_path(file_path, access_level, operation)

def get_safe_file_path(file_path: Union[str, Path], 
                      operation: str = "access",
                      access_level: AccessLevel = AccessLevel.READ_WRITE) -> Path:
    """
    Get a validated safe file path or raise an exception.
    
    Args:
        file_path: Path to validate
        operation: Operation to perform  
        access_level: Required access level
        
    Returns:
        Validated Path object
        
    Raises:
        PathValidationError: If path validation fails
    """
    validator = get_path_validator()
    return validator.get_safe_path(file_path, access_level)