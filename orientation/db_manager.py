"""
SQLite database manager for Beast - stores user's custom project templates
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional


class BeastDB:
    def __init__(self, db_path: str = None):
        """Initialize database connection"""
        if db_path is None:
            # Store in user's home directory
            home = os.path.expanduser("~")
            beast_dir = os.path.join(home, ".beast")
            os.makedirs(beast_dir, exist_ok=True)
            db_path = os.path.join(beast_dir, "templates.db")

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Return dict-like rows
        self._init_schema()

    def _init_schema(self):
        """Create tables if they don't exist"""
        cursor = self.conn.cursor()

        # User's custom project templates
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                languages JSON NOT NULL,
                frameworks JSON NOT NULL,
                libraries JSON NOT NULL,
                databases JSON,
                is_preset INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP
            )
        """)

        # Recent analyzed projects
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                project_name TEXT,
                template_id INTEGER,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(template_id) REFERENCES project_templates(id)
            )
        """)

        self.conn.commit()
        self._seed_default_presets()

    def _seed_default_presets(self):
        """Add default preset templates if they don't exist"""
        presets = [
            {
                "name": "React + Express + MongoDB",
                "description": "Full-stack MERN application",
                "languages": ["javascript", "typescript"],
                "frameworks": ["react", "express"],
                "libraries": ["material-ui", "mongoose"],
                "databases": ["mongodb"],
                "is_preset": 1
            },
            {
                "name": "Next.js Fullstack",
                "description": "Next.js App Router with API routes",
                "languages": ["typescript"],
                "frameworks": ["nextjs"],
                "libraries": ["material-ui", "mongoose"],
                "databases": ["mongodb"],
                "is_preset": 1
            },
            {
                "name": "Python Desktop (Tkinter)",
                "description": "Python GUI application",
                "languages": ["python"],
                "frameworks": ["tkinter"],
                "libraries": [],
                "databases": ["sqlite"],
                "is_preset": 1
            },
            {
                "name": "Express API + Sequelize",
                "description": "Node.js API with SQL database",
                "languages": ["javascript"],
                "frameworks": ["express"],
                "libraries": ["sequelize"],
                "databases": ["postgres", "mysql"],
                "is_preset": 1
            },
            {
                "name": "Java Desktop (JavaFX)",
                "description": "JavaFX desktop application",
                "languages": ["java"],
                "frameworks": ["javafx"],
                "libraries": [],
                "databases": ["sqlite"],
                "is_preset": 1
            },
            {
                "name": "Electron + React",
                "description": "Electron desktop app with React",
                "languages": ["javascript", "typescript"],
                "frameworks": ["electron", "react"],
                "libraries": ["material-ui"],
                "databases": ["sqlite"],
                "is_preset": 1
            }
        ]

        for preset in presets:
            try:
                self.save_template(
                    name=preset["name"],
                    description=preset["description"],
                    languages=preset["languages"],
                    frameworks=preset["frameworks"],
                    libraries=preset["libraries"],
                    databases=preset["databases"],
                    is_preset=preset["is_preset"]
                )
            except sqlite3.IntegrityError:
                # Template already exists, skip
                pass

    def save_template(self, name: str, description: str, languages: List[str],
                     frameworks: List[str], libraries: List[str],
                     databases: List[str] = None, is_preset: int = 0) -> int:
        """Save a new template or update existing"""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO project_templates
            (name, description, languages, frameworks, libraries, databases, is_preset)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description=excluded.description,
                languages=excluded.languages,
                frameworks=excluded.frameworks,
                libraries=excluded.libraries,
                databases=excluded.databases
        """, (
            name,
            description,
            json.dumps(languages),
            json.dumps(frameworks),
            json.dumps(libraries),
            json.dumps(databases or []),
            is_preset
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Get template by name"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM project_templates WHERE name = ?", (name,))
        row = cursor.fetchone()

        if row:
            return self._row_to_dict(row)
        return None

    def get_all_templates(self, include_presets: bool = True) -> List[Dict[str, Any]]:
        """Get all templates"""
        cursor = self.conn.cursor()

        if include_presets:
            cursor.execute("SELECT * FROM project_templates ORDER BY is_preset DESC, last_used DESC, name")
        else:
            cursor.execute("SELECT * FROM project_templates WHERE is_preset = 0 ORDER BY last_used DESC, name")

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def delete_template(self, name: str) -> bool:
        """Delete a custom template (cannot delete presets)"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM project_templates WHERE name = ? AND is_preset = 0", (name,))
        self.conn.commit()
        return cursor.rowcount > 0

    def update_template_usage(self, name: str):
        """Update last_used timestamp"""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE project_templates SET last_used = ? WHERE name = ?",
            (datetime.now().isoformat(), name)
        )
        self.conn.commit()

    def add_recent_project(self, path: str, template_name: str = None):
        """Record recently analyzed project"""
        cursor = self.conn.cursor()

        template_id = None
        if template_name:
            template = self.get_template(template_name)
            if template:
                template_id = template['id']

        project_name = os.path.basename(path)

        cursor.execute("""
            INSERT INTO recent_projects (path, project_name, template_id)
            VALUES (?, ?, ?)
        """, (path, project_name, template_id))

        self.conn.commit()

    def get_recent_projects(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently analyzed projects"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT rp.*, pt.name as template_name
            FROM recent_projects rp
            LEFT JOIN project_templates pt ON rp.template_id = pt.id
            ORDER BY rp.analyzed_at DESC
            LIMIT ?
        """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert SQLite row to dict with parsed JSON"""
        data = dict(row)
        # Parse JSON fields
        if 'languages' in data:
            data['languages'] = json.loads(data['languages'])
        if 'frameworks' in data:
            data['frameworks'] = json.loads(data['frameworks'])
        if 'libraries' in data:
            data['libraries'] = json.loads(data['libraries'])
        if 'databases' in data:
            data['databases'] = json.loads(data['databases'])
        return data

    def export_template(self, name: str, export_path: str):
        """Export template to JSON file"""
        template = self.get_template(name)
        if template:
            # Remove id and timestamps for portability
            export_data = {
                "name": template["name"],
                "description": template["description"],
                "languages": template["languages"],
                "frameworks": template["frameworks"],
                "libraries": template["libraries"],
                "databases": template["databases"]
            }
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2)
            return True
        return False

    def import_template(self, import_path: str):
        """Import template from JSON file"""
        with open(import_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return self.save_template(
            name=data["name"],
            description=data.get("description", ""),
            languages=data.get("languages", []),
            frameworks=data.get("frameworks", []),
            libraries=data.get("libraries", []),
            databases=data.get("databases", [])
        )

    def close(self):
        """Close database connection"""
        self.conn.close()


# Convenience functions for CLI usage
def get_db() -> BeastDB:
    """Get database instance"""
    return BeastDB()


if __name__ == "__main__":
    # Test the database
    db = BeastDB()
    print(f"Database initialized at: {db.db_path}")
    print(f"\nAvailable templates:")
    for template in db.get_all_templates():
        preset_marker = "[PRESET]" if template['is_preset'] else "[CUSTOM]"
        print(f"  {preset_marker} {template['name']}")
        print(f"     Languages: {', '.join(template['languages'])}")
        print(f"     Frameworks: {', '.join(template['frameworks'])}")
        print(f"     Libraries: {', '.join(template['libraries'])}")
        print()
    db.close()
