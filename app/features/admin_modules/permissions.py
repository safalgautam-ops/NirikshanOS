from app.core.security.permission_registry import Permission, register_permissions

MODULE_VIEW = Permission("modules", "view", "Analysis Modules", "View analysis modules")
MODULE_EDIT = Permission("modules", "edit", "Analysis Modules", "Edit module YAML definitions")
MODULE_CREATE = Permission("modules", "create", "Analysis Modules", "Create custom analysis modules")
MODULE_DELETE = Permission("modules", "delete", "Analysis Modules", "Delete analysis modules")

register_permissions(MODULE_VIEW, MODULE_EDIT, MODULE_CREATE, MODULE_DELETE)
