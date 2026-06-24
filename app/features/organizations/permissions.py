from app.core.security.permission_registry import Permission, register_permissions

ORG_VIEW = Permission("organization", "view", "Organization Management", "View organizations")
ORG_CREATE = Permission("organization", "create", "Organization Management", "Create organizations")
ORG_EDIT = Permission("organization", "edit", "Organization Management", "Edit organizations")
ORG_DELETE = Permission("organization", "delete", "Organization Management", "Delete organizations")
ORG_APPROVE = Permission("organization", "approve", "Organization Management", "Approve or reject self-registered organizations")

register_permissions(ORG_VIEW, ORG_CREATE, ORG_EDIT, ORG_DELETE, ORG_APPROVE)
