"""
Parser plugins for Beast

Each plugin is a self-contained detector/extractor for a specific framework or library.
"""
from parser.plugins.react_plugin import ReactPlugin
from parser.plugins.express_plugin import ExpressPlugin
from parser.plugins.sequelize_plugin import SequelizePlugin
from parser.plugins.mongoose_plugin import MongoosePlugin
from parser.plugins.materialui_plugin import MaterialUIPlugin
from parser.plugins.nextjs_plugin import NextJSPlugin
from parser.plugins.python_plugin import PythonParser
from parser.plugins.chefscript_plugin import ChefScriptPlugin

# Register all available plugins here
__all__ = [
    'ReactPlugin',
    'ExpressPlugin',
    'SequelizePlugin',
    'MongoosePlugin',
    'MaterialUIPlugin',
    'NextJSPlugin',
    'PythonParser',
    'ChefScriptPlugin',
]
