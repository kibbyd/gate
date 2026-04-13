"""
Mongoose Library Plugin - Detects and extracts Mongoose schemas, models, and MongoDB patterns
"""
import os
import re
from typing import Dict, List, Any
from parser.base_plugin import LibraryPlugin, PluginMetadata


class MongoosePlugin(LibraryPlugin):
    """Detect and extract Mongoose schemas, models, and database patterns"""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="mongoose",
            category="library",
            language="javascript",
            file_extensions=[".js", ".ts"],
            package_indicators=["mongoose"]
        )

    def detect(self, file_content: str, file_path: str) -> bool:
        """
        Returns True if file contains Mongoose code

        Checks for:
        - require('mongoose') or import from 'mongoose'
        - new Schema()
        - mongoose.model()
        - Schema types
        """
        # Check for Mongoose import/require
        if re.search(r"require\s*\(\s*['\"]mongoose['\"]\s*\)", file_content):
            return True
        if re.search(r"from\s+['\"]mongoose['\"]", file_content):
            return True

        # Check for common Mongoose patterns
        if re.search(r'\bnew\s+Schema\s*\(', file_content):
            return True
        if re.search(r'mongoose\.model\s*\(', file_content):
            return True
        if re.search(r'Schema\.Types\.(ObjectId|String|Number|Date|Boolean)', file_content):
            return True

        return False

    def extract(self, file_content: str, file_path: str, root_dir: str) -> Dict[str, Any]:
        """
        Extract Mongoose-specific data from file

        Returns:
            {
                "schemas": [list of schema definitions],
                "models": [list of model definitions],
                "virtuals": [list of virtual properties],
                "methods": [list of instance methods]
            }
        """
        rel_path = os.path.relpath(file_path, root_dir)

        results = {
            "schemas": [],
            "models": [],
            "virtuals": [],
            "methods": []
        }

        # Extract schemas
        schemas = self._extract_schemas(file_content, rel_path)
        results["schemas"].extend(schemas)

        # Extract models
        models = self._extract_models(file_content, rel_path)
        results["models"].extend(models)

        # Extract virtuals
        virtuals = self._extract_virtuals(file_content, rel_path)
        results["virtuals"].extend(virtuals)

        # Extract methods
        methods = self._extract_methods(file_content, rel_path)
        results["methods"].extend(methods)

        return results

    def _extract_schemas(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract Mongoose schema definitions"""
        schemas = []

        # Pattern: const SchemaName = new Schema({ ... })
        schema_pattern = r'(?:const|let|var)\s+(\w+(?:Schema)?)\s*=\s*new\s+Schema\s*\(\s*\{'
        for match in re.finditer(schema_pattern, content):
            schema_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Extract schema definition block
            schema_block = self._extract_block(content, match.end() - 1)
            fields = self._extract_schema_fields(schema_block)

            schema = {
                "id": f"{file_path}:{schema_name}",
                "name": schema_name,
                "file": file_path,
                "line": line_num,
                "fields": fields,
                "timestamps": 'timestamps: true' in content[match.start():match.start() + 500]
            }
            schemas.append(schema)

        return schemas

    def _extract_schema_fields(self, schema_block: str) -> List[Dict[str, Any]]:
        """Extract field definitions from a schema"""
        fields = []

        # Pattern 1: Detailed field definition (fieldName: { type: String, required: true, ... })
        field_pattern = r'(\w+)\s*:\s*\{\s*type\s*:\s*([\w.]+)'
        for match in re.finditer(field_pattern, schema_block):
            field_name = match.group(1)
            field_type = match.group(2).replace('Schema.Types.', '').replace('mongoose.Schema.Types.', '')

            # Extract field properties
            field_block = self._extract_field_block(schema_block, match.start())

            field = {
                "name": field_name,
                "type": field_type,
                "required": 'required: true' in field_block,
                "unique": 'unique: true' in field_block,
                "default": self._extract_default(field_block),
                "ref": self._extract_ref(field_block),
                "index": 'index: true' in field_block,
                "enum": self._extract_enum(field_block)
            }
            fields.append(field)

        # Pattern 2: Simple field definition (fieldName: String)
        simple_pattern = r'(\w+)\s*:\s*(String|Number|Date|Boolean|ObjectId|Array|Buffer|Mixed)'
        for match in re.finditer(simple_pattern, schema_block):
            field_name = match.group(1)
            field_type = match.group(2)

            # Skip if already captured by detailed pattern
            if any(f['name'] == field_name for f in fields):
                continue

            field = {
                "name": field_name,
                "type": field_type,
                "required": False,
                "unique": False,
                "default": None,
                "ref": None,
                "index": False,
                "enum": None
            }
            fields.append(field)

        return fields

    def _extract_models(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract Mongoose model definitions"""
        models = []

        # Pattern: mongoose.model('ModelName', SchemaName)
        model_pattern = r"mongoose\.model\s*\(\s*['\"](\w+)['\"]\s*,\s*(\w+)"
        for match in re.finditer(model_pattern, content):
            model_name = match.group(1)
            schema_name = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            model = {
                "id": f"{file_path}:{model_name}",
                "name": model_name,
                "schemaName": schema_name,
                "file": file_path,
                "line": line_num,
                "collection": model_name.lower() + 's'  # Default collection name
            }
            models.append(model)

        # Pattern 2: export default mongoose.model(...)
        export_pattern = r"export\s+default\s+mongoose\.model\s*\(\s*['\"](\w+)['\"]"
        for match in re.finditer(export_pattern, content):
            model_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Skip if already captured
            if any(m['name'] == model_name for m in models):
                continue

            model = {
                "id": f"{file_path}:{model_name}",
                "name": model_name,
                "schemaName": "inline",
                "file": file_path,
                "line": line_num,
                "collection": model_name.lower() + 's'
            }
            models.append(model)

        return models

    def _extract_virtuals(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract virtual properties"""
        virtuals = []

        # Pattern: SchemaName.virtual('propertyName')
        virtual_pattern = r'(\w+)\.virtual\s*\(\s*[\'"](\w+)[\'"]\s*\)'
        for match in re.finditer(virtual_pattern, content):
            schema_name = match.group(1)
            virtual_name = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            virtual = {
                "id": f"{file_path}:{schema_name}:{virtual_name}",
                "schemaName": schema_name,
                "name": virtual_name,
                "file": file_path,
                "line": line_num
            }
            virtuals.append(virtual)

        return virtuals

    def _extract_methods(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """Extract instance and static methods"""
        methods = []

        # Pattern 1: SchemaName.methods.methodName = function() { ... }
        instance_method_pattern = r'(\w+)\.methods\.(\w+)\s*=\s*(?:async\s+)?function'
        for match in re.finditer(instance_method_pattern, content):
            schema_name = match.group(1)
            method_name = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            method = {
                "id": f"{file_path}:{schema_name}:{method_name}",
                "schemaName": schema_name,
                "name": method_name,
                "type": "instance",
                "file": file_path,
                "line": line_num
            }
            methods.append(method)

        # Pattern 2: SchemaName.statics.methodName = function() { ... }
        static_method_pattern = r'(\w+)\.statics\.(\w+)\s*=\s*(?:async\s+)?function'
        for match in re.finditer(static_method_pattern, content):
            schema_name = match.group(1)
            method_name = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            method = {
                "id": f"{file_path}:{schema_name}:{method_name}",
                "schemaName": schema_name,
                "name": method_name,
                "type": "static",
                "file": file_path,
                "line": line_num
            }
            methods.append(method)

        return methods

    def _extract_block(self, content: str, start: int) -> str:
        """Extract a code block starting from position"""
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
        return content[start:start+1000]

    def _extract_field_block(self, content: str, start: int) -> str:
        """Extract a field definition block"""
        open_braces = 0
        i = start
        found_open = False
        while i < len(content):
            if content[i] == '{':
                open_braces += 1
                found_open = True
            elif content[i] == '}':
                open_braces -= 1
                if found_open and open_braces == 0:
                    return content[start:i+1]
            i += 1
        return content[start:start+300]

    def _extract_default(self, field_block: str) -> Any:
        """Extract default value"""
        default_match = re.search(r"default\s*:\s*([^,}]+)", field_block)
        if default_match:
            return default_match.group(1).strip()
        return None

    def _extract_ref(self, field_block: str) -> str:
        """Extract ref (for ObjectId references)"""
        ref_match = re.search(r"ref\s*:\s*['\"](\w+)['\"]", field_block)
        if ref_match:
            return ref_match.group(1)
        return None

    def _extract_enum(self, field_block: str) -> List[str]:
        """Extract enum values"""
        enum_match = re.search(r"enum\s*:\s*\[([^\]]+)\]", field_block)
        if enum_match:
            values = enum_match.group(1).split(',')
            return [v.strip().strip("'\"") for v in values]
        return None
