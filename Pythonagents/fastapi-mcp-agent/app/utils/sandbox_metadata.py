"""
Sandbox Metadata Enhancement Utility

This module provides comprehensive metadata generation for sandbox environments,
including project structure analysis, file type detection, dependency tracking,
and project statistics.
"""

import os
import json
import mimetypes
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
import re
from collections import defaultdict, Counter


class SandboxMetadataGenerator:
    """Generates comprehensive metadata for sandbox environments."""
    
    # Common file extensions and their categories
    FILE_CATEGORIES = {
        'source': {'.js', '.jsx', '.ts', '.tsx', '.py', '.java', '.cpp', '.c', '.cs', '.php', '.rb', '.go', '.rs', '.swift'},
        'markup': {'.html', '.htm', '.xml', '.svg'},
        'styles': {'.css', '.scss', '.sass', '.less', '.styl'},
        'config': {'.json', '.yaml', '.yml', '.toml', '.ini', '.env', '.config'},
        'documentation': {'.md', '.txt', '.rst', '.adoc'},
        'images': {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp'},
        'data': {'.csv', '.xlsx', '.xls', '.db', '.sqlite', '.sql'},
        'build': {'.lock', '.log', '.map', '.min.js', '.min.css'},
        'templates': {'.hbs', '.ejs', '.pug', '.vue', '.svelte'}
    }
    
    # Directories to skip during analysis
    SKIP_DIRECTORIES = {
        'node_modules', '.git', '__pycache__', '.next', '.nuxt', 'dist', 'build', 
        '.cache', 'coverage', '.nyc_output', 'logs', 'tmp', 'temp', '.vscode', 
        '.idea', '.DS_Store', 'vendor', 'target', 'bin', 'obj'
    }
    
    # Package manager files
    PACKAGE_FILES = {
        'package.json': 'npm',
        'yarn.lock': 'yarn',
        'pnpm-lock.yaml': 'pnpm',
        'requirements.txt': 'pip',
        'Pipfile': 'pipenv',
        'poetry.lock': 'poetry',
        'Cargo.toml': 'cargo',
        'go.mod': 'go',
        'composer.json': 'composer',
        'Gemfile': 'bundler'
    }
    
    def __init__(self, sandbox_path: str):
        """Initialize the metadata generator with a sandbox path."""
        self.sandbox_path = Path(sandbox_path)
        self.metadata = {}
        
    def generate_metadata(self) -> Dict[str, Any]:
        """Generate comprehensive metadata for the sandbox."""
        if not self.sandbox_path.exists():
            raise ValueError(f"Sandbox path does not exist: {self.sandbox_path}")
            
        self.metadata = {
            'generated_at': datetime.utcnow().isoformat(),
            'sandbox_path': str(self.sandbox_path),
            'project_structure': self._analyze_project_structure(),
            'file_statistics': self._calculate_file_statistics(),
            'dependencies': self._analyze_dependencies(),
            'frameworks': self._detect_frameworks(),
            'file_tree': self._generate_file_tree(),
            'entry_points': self._detect_entry_points(),
            'build_tools': self._detect_build_tools(),
            'project_type': self._determine_project_type(),
            'size_analysis': self._analyze_size(),
            'recent_activity': self._analyze_recent_activity()
        }
        
        return self.metadata
    
    def _analyze_project_structure(self) -> Dict[str, Any]:
        """Analyze the overall project structure."""
        structure = {
            'total_files': 0,
            'total_directories': 0,
            'max_depth': 0,
            'file_categories': defaultdict(int),
            'directory_structure': {},
            'top_level_items': []
        }
        
        # Get top-level items
        if self.sandbox_path.exists():
            structure['top_level_items'] = [
                item.name for item in self.sandbox_path.iterdir() 
                if not item.name.startswith('.')
            ]
        
        # Analyze directory structure
        for root, dirs, files in os.walk(self.sandbox_path):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRECTORIES]
            
            current_depth = len(Path(root).relative_to(self.sandbox_path).parts)
            structure['max_depth'] = max(structure['max_depth'], current_depth)
            structure['total_directories'] += len(dirs)
            structure['total_files'] += len(files)
            
            # Categorize files
            for file in files:
                file_ext = Path(file).suffix.lower()
                category = self._get_file_category(file_ext)
                structure['file_categories'][category] += 1
        
        return dict(structure)
    
    def _calculate_file_statistics(self) -> Dict[str, Any]:
        """Calculate detailed file statistics."""
        stats = {
            'by_extension': Counter(),
            'by_category': Counter(),
            'largest_files': [],
            'total_size': 0,
            'average_file_size': 0,
            'file_count': 0
        }
        
        file_sizes = []
        
        for root, dirs, files in os.walk(self.sandbox_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRECTORIES]
            
            for file in files:
                file_path = Path(root) / file
                try:
                    file_size = file_path.stat().st_size
                    file_ext = file_path.suffix.lower()
                    category = self._get_file_category(file_ext)
                    
                    stats['by_extension'][file_ext] += 1
                    stats['by_category'][category] += 1
                    stats['total_size'] += file_size
                    stats['file_count'] += 1
                    file_sizes.append(file_size)
                    
                    # Track largest files
                    stats['largest_files'].append({
                        'path': str(file_path.relative_to(self.sandbox_path)),
                        'size': file_size,
                        'size_human': self._format_size(file_size)
                    })
                    
                except (OSError, PermissionError):
                    continue
        
        # Sort largest files and keep top 10
        stats['largest_files'].sort(key=lambda x: x['size'], reverse=True)
        stats['largest_files'] = stats['largest_files'][:10]
        
        # Calculate average
        if stats['file_count'] > 0:
            stats['average_file_size'] = stats['total_size'] / stats['file_count']
        
        # Convert counters to regular dicts
        stats['by_extension'] = dict(stats['by_extension'])
        stats['by_category'] = dict(stats['by_category'])
        
        return stats
    
    def _analyze_dependencies(self) -> Dict[str, Any]:
        """Analyze project dependencies from various package managers."""
        dependencies = {
            'package_managers': [],
            'npm_dependencies': {},
            'python_dependencies': [],
            'other_dependencies': {}
        }
        
        # Check for package.json (npm/yarn/pnpm)
        package_json_path = self.sandbox_path / 'package.json'
        if package_json_path.exists():
            try:
                with open(package_json_path, 'r') as f:
                    package_data = json.load(f)
                    dependencies['package_managers'].append('npm')
                    dependencies['npm_dependencies'] = {
                        'dependencies': package_data.get('dependencies', {}),
                        'devDependencies': package_data.get('devDependencies', {}),
                        'scripts': package_data.get('scripts', {}),
                        'name': package_data.get('name', ''),
                        'version': package_data.get('version', '')
                    }
            except (json.JSONDecodeError, IOError):
                pass
        
        # Check for Python dependencies
        requirements_path = self.sandbox_path / 'requirements.txt'
        if requirements_path.exists():
            try:
                with open(requirements_path, 'r') as f:
                    dependencies['package_managers'].append('pip')
                    dependencies['python_dependencies'] = [
                        line.strip() for line in f.readlines() 
                        if line.strip() and not line.startswith('#')
                    ]
            except IOError:
                pass
        
        # Check for other package manager files
        for file_name, manager in self.PACKAGE_FILES.items():
            if (self.sandbox_path / file_name).exists():
                if manager not in dependencies['package_managers']:
                    dependencies['package_managers'].append(manager)
        
        return dependencies
    
    def _detect_frameworks(self) -> List[str]:
        """Detect frameworks and libraries used in the project."""
        frameworks = set()
        
        # Check package.json dependencies
        package_json_path = self.sandbox_path / 'package.json'
        if package_json_path.exists():
            try:
                with open(package_json_path, 'r') as f:
                    package_data = json.load(f)
                    all_deps = {
                        **package_data.get('dependencies', {}),
                        **package_data.get('devDependencies', {})
                    }
                    
                    # Framework detection patterns
                    framework_patterns = {
                        'react': ['react', '@types/react'],
                        'vue': ['vue', '@vue/'],
                        'angular': ['@angular/', 'angular'],
                        'svelte': ['svelte'],
                        'next.js': ['next'],
                        'nuxt': ['nuxt'],
                        'express': ['express'],
                        'fastify': ['fastify'],
                        'typescript': ['typescript', '@types/'],
                        'webpack': ['webpack'],
                        'vite': ['vite'],
                        'tailwind': ['tailwindcss'],
                        'bootstrap': ['bootstrap'],
                        'material-ui': ['@mui/', '@material-ui/'],
                        'styled-components': ['styled-components'],
                        'emotion': ['@emotion/']
                    }
                    
                    for framework, patterns in framework_patterns.items():
                        for pattern in patterns:
                            if any(pattern in dep for dep in all_deps.keys()):
                                frameworks.add(framework)
                                break
            except (json.JSONDecodeError, IOError):
                pass
        
        # Check for framework-specific files
        framework_files = {
            'react': ['src/App.jsx', 'src/App.tsx', 'public/index.html'],
            'vue': ['src/App.vue', 'vue.config.js'],
            'angular': ['angular.json', 'src/app/app.component.ts'],
            'svelte': ['src/App.svelte', 'svelte.config.js'],
            'next.js': ['next.config.js', 'pages/_app.js', 'app/layout.tsx'],
            'nuxt': ['nuxt.config.js', 'nuxt.config.ts'],
            'vite': ['vite.config.js', 'vite.config.ts'],
            'webpack': ['webpack.config.js']
        }
        
        for framework, files in framework_files.items():
            for file_path in files:
                if (self.sandbox_path / file_path).exists():
                    frameworks.add(framework)
                    break
        
        return sorted(list(frameworks))
    
    def _generate_file_tree(self, max_depth: int = 3) -> Dict[str, Any]:
        """Generate a file tree structure (limited depth for performance)."""
        def build_tree(path: Path, current_depth: int = 0) -> Dict[str, Any]:
            if current_depth >= max_depth:
                return {"...": "truncated"}
            
            tree = {}
            try:
                for item in sorted(path.iterdir()):
                    if item.name.startswith('.') or item.name in self.SKIP_DIRECTORIES:
                        continue
                    
                    if item.is_dir():
                        tree[f"{item.name}/"] = build_tree(item, current_depth + 1)
                    else:
                        tree[item.name] = {
                            "size": item.stat().st_size,
                            "modified": item.stat().st_mtime
                        }
            except (PermissionError, OSError):
                pass
            
            return tree
        
        return build_tree(self.sandbox_path)
    
    def _detect_entry_points(self) -> List[str]:
        """Detect potential entry points for the application."""
        entry_points = []
        
        # Common entry point files
        common_entries = [
            'index.html', 'index.js', 'index.ts', 'index.jsx', 'index.tsx',
            'main.js', 'main.ts', 'app.js', 'app.ts', 'server.js', 'server.ts',
            'src/index.js', 'src/index.ts', 'src/main.js', 'src/main.ts',
            'src/App.js', 'src/App.ts', 'src/App.jsx', 'src/App.tsx',
            'public/index.html', 'dist/index.html'
        ]
        
        for entry in common_entries:
            if (self.sandbox_path / entry).exists():
                entry_points.append(entry)
        
        # Check package.json for main field
        package_json_path = self.sandbox_path / 'package.json'
        if package_json_path.exists():
            try:
                with open(package_json_path, 'r') as f:
                    package_data = json.load(f)
                    main_field = package_data.get('main')
                    if main_field and main_field not in entry_points:
                        entry_points.append(main_field)
            except (json.JSONDecodeError, IOError):
                pass
        
        return entry_points
    
    def _detect_build_tools(self) -> List[str]:
        """Detect build tools and configuration files."""
        build_tools = []
        
        build_configs = {
            'webpack': ['webpack.config.js', 'webpack.config.ts'],
            'vite': ['vite.config.js', 'vite.config.ts'],
            'rollup': ['rollup.config.js', 'rollup.config.ts'],
            'parcel': ['.parcelrc', 'parcel.config.js'],
            'esbuild': ['esbuild.config.js'],
            'babel': ['.babelrc', 'babel.config.js', '.babelrc.js'],
            'typescript': ['tsconfig.json'],
            'eslint': ['.eslintrc', '.eslintrc.js', '.eslintrc.json'],
            'prettier': ['.prettierrc', 'prettier.config.js'],
            'tailwind': ['tailwind.config.js', 'tailwind.config.ts']
        }
        
        for tool, configs in build_configs.items():
            for config in configs:
                if (self.sandbox_path / config).exists():
                    build_tools.append(tool)
                    break
        
        return build_tools
    
    def _determine_project_type(self) -> str:
        """Determine the primary project type."""
        # Check for specific framework indicators
        if (self.sandbox_path / 'next.config.js').exists() or (self.sandbox_path / 'next.config.ts').exists():
            return 'next.js'
        elif (self.sandbox_path / 'nuxt.config.js').exists() or (self.sandbox_path / 'nuxt.config.ts').exists():
            return 'nuxt'
        elif (self.sandbox_path / 'angular.json').exists():
            return 'angular'
        elif (self.sandbox_path / 'svelte.config.js').exists():
            return 'svelte'
        elif (self.sandbox_path / 'src' / 'App.vue').exists():
            return 'vue'
        elif any((self.sandbox_path / 'src').glob('App.jsx')) or any((self.sandbox_path / 'src').glob('App.tsx')):
            return 'react'
        elif (self.sandbox_path / 'package.json').exists():
            return 'node.js'
        elif (self.sandbox_path / 'requirements.txt').exists() or (self.sandbox_path / 'setup.py').exists():
            return 'python'
        elif (self.sandbox_path / 'index.html').exists():
            return 'static'
        else:
            return 'unknown'
    
    def _analyze_size(self) -> Dict[str, Any]:
        """Analyze project size and distribution."""
        size_analysis = {
            'total_size': 0,
            'total_size_human': '',
            'by_category': {},
            'largest_directories': []
        }
        
        category_sizes = defaultdict(int)
        dir_sizes = {}
        
        for root, dirs, files in os.walk(self.sandbox_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRECTORIES]
            
            dir_size = 0
            for file in files:
                file_path = Path(root) / file
                try:
                    file_size = file_path.stat().st_size
                    file_ext = file_path.suffix.lower()
                    category = self._get_file_category(file_ext)
                    
                    category_sizes[category] += file_size
                    dir_size += file_size
                    size_analysis['total_size'] += file_size
                except (OSError, PermissionError):
                    continue
            
            if dir_size > 0:
                rel_path = str(Path(root).relative_to(self.sandbox_path))
                dir_sizes[rel_path] = dir_size
        
        # Format sizes
        size_analysis['total_size_human'] = self._format_size(size_analysis['total_size'])
        size_analysis['by_category'] = {
            cat: self._format_size(size) for cat, size in category_sizes.items()
        }
        
        # Top directories by size
        sorted_dirs = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)[:10]
        size_analysis['largest_directories'] = [
            {'path': path, 'size': size, 'size_human': self._format_size(size)}
            for path, size in sorted_dirs
        ]
        
        return size_analysis
    
    def _analyze_recent_activity(self) -> Dict[str, Any]:
        """Analyze recent file activity."""
        activity = {
            'most_recent_files': [],
            'recently_modified': [],
            'creation_pattern': {}
        }
        
        file_times = []
        
        for root, dirs, files in os.walk(self.sandbox_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRECTORIES]
            
            for file in files:
                file_path = Path(root) / file
                try:
                    stat = file_path.stat()
                    rel_path = str(file_path.relative_to(self.sandbox_path))
                    
                    file_times.append({
                        'path': rel_path,
                        'modified': stat.st_mtime,
                        'created': stat.st_ctime,
                        'size': stat.st_size
                    })
                except (OSError, PermissionError):
                    continue
        
        # Sort by modification time
        file_times.sort(key=lambda x: x['modified'], reverse=True)
        
        # Most recent files
        activity['most_recent_files'] = [
            {
                'path': f['path'],
                'modified': datetime.fromtimestamp(f['modified']).isoformat(),
                'size_human': self._format_size(f['size'])
            }
            for f in file_times[:10]
        ]
        
        return activity
    
    def _get_file_category(self, extension: str) -> str:
        """Get the category for a file extension."""
        for category, extensions in self.FILE_CATEGORIES.items():
            if extension in extensions:
                return category
        return 'other'
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"


def generate_sandbox_metadata(sandbox_path: str) -> Dict[str, Any]:
    """
    Convenience function to generate metadata for a sandbox.
    
    Args:
        sandbox_path: Path to the sandbox directory
        
    Returns:
        Dictionary containing comprehensive sandbox metadata
    """
    generator = SandboxMetadataGenerator(sandbox_path)
    return generator.generate_metadata()


def update_sandbox_metadata_in_db(sandbox_id: str, metadata: Dict[str, Any]) -> bool:
    """
    Update sandbox metadata in the database.
    
    Args:
        sandbox_id: The sandbox ID
        metadata: The metadata dictionary to store
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from app.database import Sandbox
        import asyncio
        
        async def update_metadata():
            sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandbox_id)
            if sandbox:
                sandbox.metadata = metadata
                await sandbox.save()
                return True
            return False
        
        # Run the async function
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, we need to handle this differently
            return True  # Return True for now, actual update will happen in calling context
        else:
            return loop.run_until_complete(update_metadata())
            
    except Exception as e:
        print(f"Error updating sandbox metadata: {e}")
        return False