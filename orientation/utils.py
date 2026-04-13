"""
Beast utilities - File I/O and template management
"""
import os
import json


def save_json(data, path):
    """Save data to JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_template():
    """Load the AppMap template."""
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'appmap_v3_template.json')
    with open(template_path, 'r', encoding='utf-8') as f:
        return json.load(f)
