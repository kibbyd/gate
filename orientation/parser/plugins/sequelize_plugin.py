"""
Sequelize Library Plugin - Detects and extracts Sequelize models, associations, and database schema
"""
import os
import re
from typing import Dict, List, Any
from parser.base_plugin import LibraryPlugin, PluginMetadata


class SequelizePlugin(LibraryPlugin):
    """Detect and extract Sequelize models, associations, and schema"""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="sequelize",
            category="library",
            language="javascript",
            file_extensions=[".js", ".ts"],
            package_indicators=["sequelize"]
        )

    def detect(self, file_content: str, file_path: str) -> bool:
        """
        Returns True if file contains Sequelize code

        Checks for:
        - require('sequelize') or import from 'sequelize'
        - Model.init or sequelize.define
        - DataTypes usage
        - Model associations
        """
        # Check for Sequelize import/require
        if re.search(r"require\s*\(\s*['\"]sequelize['\"]\s*\)", file_content):
            return True
        if re.search(r"from\s+['\"]sequelize['\"]", file_content):
            return True

        # Check for common Sequelize patterns
        if re.search(r'\b(Model\.init|sequelize\.define|DataTypes\.)', file_content):
            return True

        # Check for associations
        if re.search(r'\b(hasMany|belongsTo|hasOne|belongsToMany)\s*\(', file_content):
            return True

        return False

    def extract(self, file_content: str, file_path: str, root_dir: str) -> Dict[str, Any]:
        """
        Extract Sequelize-specific data from file

        Returns:
            {
                "models": [list of model definitions],
                "associations": [list of model associations],
                "migrations": [list of migrations if found]
            }
        """
        rel_path = os.path.relpath(file_path, root_dir)

        results = {
            "models": [],
            "associations": [],
            "migrations": []
        }

        # Extract models
        models = self._extract_models(file_content, rel_path)
        results["models"].extend(models)

        # Extract associations
        associations = self._extract_associations(file_content, rel_path)
        results["associations"].extend(associations)

        # Extract migrations (if this is a migration file)
        if 'migrations' in file_path or 'migration' in file_path:
            migrations = self._extract_migrations(file_content, rel_path)
            results["migrations"].extend(migrations)

        return results

    def _extract_models(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract Sequelize model definitions"""
        models = []

        # Pattern 1: sequelize.define('ModelName', { ... })
        define_pattern = r"sequelize\.define\s*\(\s*['\"](\w+)['\"]\s*,\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}"
        for match in re.finditer(define_pattern, content, re.DOTALL):
            model_name = match.group(1)
            fields_block = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            fields = self._extract_fields(fields_block)

            model = {
                "id": f"{file_path}:{model_name}",
                "name": model_name,
                "file": file_path,
                "line": line_num,
                "type": "define",
                "fields": fields,
                "tableName": model_name.lower()
            }
            models.append(model)

        # Pattern 2: class ModelName extends Model { ... }
        class_pattern = r"class\s+(\w+)\s+extends\s+Model\s*\{"
        for match in re.finditer(class_pattern, content):
            model_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Find the init() method to extract fields
            init_start = content.find('init(', match.start())
            if init_start > 0:
                init_block = self._extract_block(content, init_start)
                fields = self._extract_fields(init_block)
            else:
                fields = []

            model = {
                "id": f"{file_path}:{model_name}",
                "name": model_name,
                "file": file_path,
                "line": line_num,
                "type": "class",
                "fields": fields,
                "tableName": self._to_snake_case(model_name)
            }
            models.append(model)

        return models

    def _extract_fields(self, fields_block: str) -> List[Dict[str, Any]]:
        """Extract field definitions from a model definition block"""
        fields = []

        # Pattern: fieldName: { type: DataTypes.STRING, ... }
        field_pattern = r'(\w+)\s*:\s*\{[^}]*type\s*:\s*DataTypes\.(\w+)'
        for match in re.finditer(field_pattern, fields_block):
            field_name = match.group(1)
            field_type = match.group(2)

            # Extract additional properties
            field_block = self._extract_field_block(fields_block, match.start())

            field = {
                "name": field_name,
                "type": field_type,
                "allowNull": 'allowNull: false' not in field_block,
                "primaryKey": 'primaryKey: true' in field_block,
                "unique": 'unique: true' in field_block,
                "autoIncrement": 'autoIncrement: true' in field_block,
                "defaultValue": self._extract_default_value(field_block)
            }
            fields.append(field)

        # Pattern 2: Simple field definition (fieldName: DataTypes.STRING)
        simple_pattern = r'(\w+)\s*:\s*DataTypes\.(\w+)'
        for match in re.finditer(simple_pattern, fields_block):
            field_name = match.group(1)
            field_type = match.group(2)

            # Skip if already captured by detailed pattern
            if any(f['name'] == field_name for f in fields):
                continue

            field = {
                "name": field_name,
                "type": field_type,
                "allowNull": True,
                "primaryKey": False,
                "unique": False,
                "autoIncrement": False,
                "defaultValue": None
            }
            fields.append(field)

        return fields

    def _extract_associations(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract model associations (hasMany, belongsTo, etc.)"""
        associations = []

        # Pattern: Model.hasMany(OtherModel, { ... })
        assoc_pattern = r'(\w+)\.(hasMany|belongsTo|hasOne|belongsToMany)\s*\(\s*(\w+)'
        for match in re.finditer(assoc_pattern, content):
            source_model = match.group(1)
            assoc_type = match.group(2)
            target_model = match.group(3)
            line_num = content[:match.start()].count('\n') + 1

            # Extract foreign key if present
            foreign_key = None
            assoc_block = content[match.start():match.start() + 200]
            fk_match = re.search(r"foreignKey\s*:\s*['\"](\w+)['\"]", assoc_block)
            if fk_match:
                foreign_key = fk_match.group(1)

            association = {
                "id": f"{file_path}:{source_model}:{assoc_type}:{target_model}",
                "sourceModel": source_model,
                "targetModel": target_model,
                "type": assoc_type,
                "file": file_path,
                "line": line_num,
                "foreignKey": foreign_key
            }
            associations.append(association)

        return associations

    def _extract_migrations(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract migration operations from migration files"""
        migrations = []

        # Pattern: createTable('tableName', { ... })
        create_table_pattern = r"createTable\s*\(\s*['\"](\w+)['\"]\s*,"
        for match in re.finditer(create_table_pattern, content):
            table_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            migration = {
                "id": f"{file_path}:createTable:{table_name}",
                "operation": "createTable",
                "tableName": table_name,
                "file": file_path,
                "line": line_num
            }
            migrations.append(migration)

        # Pattern: dropTable('tableName')
        drop_table_pattern = r"dropTable\s*\(\s*['\"](\w+)['\"]\s*\)"
        for match in re.finditer(drop_table_pattern, content):
            table_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            migration = {
                "id": f"{file_path}:dropTable:{table_name}",
                "operation": "dropTable",
                "tableName": table_name,
                "file": file_path,
                "line": line_num
            }
            migrations.append(migration)

        return migrations

    def _extract_block(self, content: str, start: int) -> str:
        """Extract a code block starting from position"""
        # Find matching braces
        open_braces = 0
        i = start
        while i < len(content):
            if content[i] == '{':
                open_braces += 1
            elif content[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    return content[start:i+1]
            i += 1
        return content[start:start+500]  # Fallback

    def _extract_field_block(self, content: str, start: int) -> str:
        """Extract a field definition block"""
        # Find the field's closing brace
        open_braces = 0
        i = start
        while i < len(content):
            if content[i] == '{':
                open_braces += 1
            elif content[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    return content[start:i+1]
            i += 1
        return content[start:start+200]

    def _extract_default_value(self, field_block: str) -> Any:
        """Extract default value from field definition"""
        default_match = re.search(r"defaultValue\s*:\s*([^,}]+)", field_block)
        if default_match:
            return default_match.group(1).strip()
        return None

    def _to_snake_case(self, name: str) -> str:
        """Convert PascalCase to snake_case"""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
