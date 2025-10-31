import os
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import re

logger = logging.getLogger(__name__)

class ProjectContextService:
    """Service for gathering comprehensive project context information."""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.context = {}
    
    async def gather_full_context(self, max_depth: int = 3, include_file_contents: bool = True) -> Dict[str, Any]:
        """Gather comprehensive project context including structure, type, and metadata."""
        try:
            context = {
                "project_path": str(self.project_path),
                "structure": await self._get_directory_structure(max_depth),
                "app_type": await self._detect_app_type(),
                "technologies": await self._detect_technologies(),
                "package_info": await self._get_package_info(),
                "config_files": await self._get_config_files(),
                "entry_points": await self._find_entry_points(),
                "file_stats": await self._get_file_statistics(),
                "patterns": await self._detect_patterns()
            }
            
            if include_file_contents:
                context["key_files"] = await self._get_key_file_contents()
            
            return context
            
        except Exception as e:
            logger.error(f"Error gathering project context: {e}")
            return {"error": str(e), "project_path": str(self.project_path)}
    
    async def _get_directory_structure(self, max_depth: int = 3) -> Dict[str, Any]:
        """Get the directory structure as a nested dictionary."""
        def build_tree(path: Path, current_depth: int = 0) -> Dict[str, Any]:
            if current_depth >= max_depth or not path.exists():
                return {}
            
            tree = {"type": "directory", "children": {}}
            
            try:
                for item in sorted(path.iterdir()):
                    # Skip hidden files and common ignore patterns
                    if item.name.startswith('.') or item.name in ['node_modules', '__pycache__', 'venv', '.git']:
                        continue
                    
                    if item.is_dir():
                        tree["children"][item.name] = build_tree(item, current_depth + 1)
                    else:
                        tree["children"][item.name] = {
                            "type": "file",
                            "size": item.stat().st_size if item.exists() else 0,
                            "extension": item.suffix
                        }
            except PermissionError:
                tree["error"] = "Permission denied"
            
            return tree
        
        return build_tree(self.project_path)
    
    async def _detect_app_type(self) -> str:
        """Detect the type of application based on files and structure."""
        # Check for common framework indicators
        indicators = {
            "react": ["package.json", "src/App.js", "src/App.tsx", "public/index.html"],
            "nextjs": ["next.config.js", "next.config.mjs", "pages/", "app/"],
            "vue": ["vue.config.js", "src/main.js", "src/App.vue"],
            "angular": ["angular.json", "src/app/app.module.ts"],
            "fastapi": ["main.py", "app/main.py", "requirements.txt"],
            "django": ["manage.py", "settings.py", "wsgi.py"],
            "flask": ["app.py", "requirements.txt"],
            "express": ["package.json", "server.js", "app.js"],
            "spring": ["pom.xml", "build.gradle", "src/main/java"],
            "laravel": ["composer.json", "artisan", "app/Http"],
            "rails": ["Gemfile", "config/application.rb", "app/controllers"]
        }
        
        detected_types = []
        
        for app_type, files in indicators.items():
            score = 0
            for file_pattern in files:
                if self._file_exists(file_pattern):
                    score += 1
            
            if score > 0:
                detected_types.append((app_type, score))
        
        if detected_types:
            # Return the type with highest score
            detected_types.sort(key=lambda x: x[1], reverse=True)
            return detected_types[0][0]
        
        return "unknown"
    
    async def _detect_technologies(self) -> List[str]:
        """Detect technologies used in the project."""
        technologies = set()
        
        # Check package.json for JavaScript/Node.js technologies
        package_json = await self._read_json_file("package.json")
        if package_json:
            dependencies = {**package_json.get("dependencies", {}), **package_json.get("devDependencies", {})}
            
            # Map dependencies to technologies
            tech_mapping = {
                "react": "React",
                "vue": "Vue.js",
                "angular": "Angular",
                "next": "Next.js",
                "express": "Express.js",
                "fastify": "Fastify",
                "typescript": "TypeScript",
                "tailwindcss": "Tailwind CSS",
                "sass": "Sass",
                "webpack": "Webpack",
                "vite": "Vite"
            }
            
            for dep in dependencies:
                for key, tech in tech_mapping.items():
                    if key in dep.lower():
                        technologies.add(tech)
        
        # Check requirements.txt for Python technologies
        requirements = await self._read_file("requirements.txt")
        if requirements:
            python_mapping = {
                "fastapi": "FastAPI",
                "django": "Django",
                "flask": "Flask",
                "sqlalchemy": "SQLAlchemy",
                "pydantic": "Pydantic",
                "uvicorn": "Uvicorn",
                "gunicorn": "Gunicorn"
            }
            
            for line in requirements.split('\n'):
                package = line.split('==')[0].split('>=')[0].strip().lower()
                for key, tech in python_mapping.items():
                    if key in package:
                        technologies.add(tech)
        
        # Check for other technology indicators
        if self._file_exists("Dockerfile"):
            technologies.add("Docker")
        if self._file_exists("docker-compose.yml"):
            technologies.add("Docker Compose")
        if self._file_exists("tsconfig.json"):
            technologies.add("TypeScript")
        
        return list(technologies)
    
    async def _get_package_info(self) -> Optional[Dict[str, Any]]:
        """Get package information from package.json or similar files."""
        # Try package.json first
        package_json = await self._read_json_file("package.json")
        if package_json:
            return {
                "type": "npm",
                "name": package_json.get("name"),
                "version": package_json.get("version"),
                "description": package_json.get("description"),
                "scripts": package_json.get("scripts", {}),
                "dependencies": list(package_json.get("dependencies", {}).keys()),
                "devDependencies": list(package_json.get("devDependencies", {}).keys())
            }
        
        # Try pyproject.toml for Python projects
        pyproject = await self._read_file("pyproject.toml")
        if pyproject:
            return {"type": "python", "config": "pyproject.toml"}
        
        # Try requirements.txt
        requirements = await self._read_file("requirements.txt")
        if requirements:
            deps = [line.strip() for line in requirements.split('\n') if line.strip() and not line.startswith('#')]
            return {"type": "python", "dependencies": deps}
        
        return None
    
    async def _get_config_files(self) -> List[Dict[str, Any]]:
        """Get information about configuration files."""
        config_patterns = [
            "*.config.js", "*.config.mjs", "*.config.ts",
            "tsconfig.json", "jsconfig.json",
            ".env*", "*.yml", "*.yaml",
            "Dockerfile", "docker-compose.yml",
            ".gitignore", "README.md"
        ]
        
        config_files = []
        
        for pattern in config_patterns:
            files = list(self.project_path.glob(pattern))
            for file in files:
                if file.is_file():
                    config_files.append({
                        "name": file.name,
                        "path": str(file.relative_to(self.project_path)),
                        "size": file.stat().st_size
                    })
        
        return config_files
    
    async def _find_entry_points(self) -> List[str]:
        """Find likely entry points for the application."""
        entry_points = []
        
        common_entries = [
            "index.js", "index.ts", "main.js", "main.ts",
            "app.js", "app.ts", "server.js", "server.ts",
            "main.py", "app.py", "manage.py",
            "index.html", "App.js", "App.tsx"
        ]
        
        for entry in common_entries:
            if self._file_exists(entry) or self._file_exists(f"src/{entry}") or self._file_exists(f"app/{entry}"):
                entry_points.append(entry)
        
        return entry_points
    
    async def _get_file_statistics(self) -> Dict[str, Any]:
        """Get statistics about files in the project."""
        stats = {
            "total_files": 0,
            "total_directories": 0,
            "file_types": {},
            "total_size": 0
        }
        
        try:
            for item in self.project_path.rglob("*"):
                if any(ignore in str(item) for ignore in ['.git', 'node_modules', '__pycache__', 'venv']):
                    continue
                
                if item.is_file():
                    stats["total_files"] += 1
                    stats["total_size"] += item.stat().st_size
                    
                    ext = item.suffix.lower()
                    if ext:
                        stats["file_types"][ext] = stats["file_types"].get(ext, 0) + 1
                elif item.is_dir():
                    stats["total_directories"] += 1
        
        except Exception as e:
            logger.warning(f"Error calculating file statistics: {e}")
        
        return stats
    
    async def _detect_patterns(self) -> List[str]:
        """Detect common patterns and architectural decisions."""
        patterns = []
        
        # Check for common architectural patterns
        if self._file_exists("src/components") or self._file_exists("components"):
            patterns.append("Component-based architecture")
        
        if self._file_exists("src/pages") or self._file_exists("pages"):
            patterns.append("Page-based routing")
        
        if self._file_exists("src/api") or self._file_exists("api"):
            patterns.append("API layer separation")
        
        if self._file_exists("src/utils") or self._file_exists("utils"):
            patterns.append("Utility functions organization")
        
        if self._file_exists("src/hooks") or self._file_exists("hooks"):
            patterns.append("Custom hooks pattern")
        
        if self._file_exists("src/store") or self._file_exists("store"):
            patterns.append("State management")
        
        return patterns
    
    async def _get_key_file_contents(self, max_size: int = 2000) -> Dict[str, str]:
        """Get contents of key files (truncated for context)."""
        key_files = [
            "package.json", "requirements.txt", "README.md",
            "tsconfig.json", "next.config.js", "next.config.mjs",
            "tailwind.config.js", "postcss.config.js"
        ]
        
        contents = {}
        
        for file_name in key_files:
            content = await self._read_file(file_name)
            if content:
                # Truncate if too long
                if len(content) > max_size:
                    content = content[:max_size] + "... [truncated]"
                contents[file_name] = content
        
        return contents
    
    def _file_exists(self, file_path: str) -> bool:
        """Check if a file exists in the project."""
        full_path = self.project_path / file_path
        return full_path.exists() and full_path.is_file()
    
    async def _read_file(self, file_path: str) -> Optional[str]:
        """Read a file's content."""
        try:
            full_path = self.project_path / file_path
            if full_path.exists() and full_path.is_file():
                return full_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.warning(f"Could not read file {file_path}: {e}")
        return None
    
    async def _read_json_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Read and parse a JSON file."""
        content = await self._read_file(file_path)
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"Could not parse JSON file {file_path}: {e}")
        return None