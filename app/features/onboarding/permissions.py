from app.core.security.org_permission_registry import OrgPermission, register_org_permissions

ORG_STAFF_VIEW = OrgPermission("org_staff", "view", "Organization Staff", "View this organization's members")
ORG_STAFF_REMOVE = OrgPermission("org_staff", "remove", "Organization Staff", "Remove members from this organization")

ORG_ROLE_VIEW = OrgPermission("org_role", "view", "Organization Roles", "View this organization's roles")
ORG_ROLE_CREATE = OrgPermission("org_role", "create", "Organization Roles", "Create roles for this organization")
ORG_ROLE_EDIT = OrgPermission("org_role", "edit", "Organization Roles", "Edit this organization's roles")
ORG_ROLE_DELETE = OrgPermission("org_role", "delete", "Organization Roles", "Delete this organization's roles")

# Invite code/link and government verification documents are sensitive -
# regular members only see the organization's basic profile fields; this is
# what additionally unlocks invites + documents (viewing AND managing -
# upload/delete/regenerate) on that same page.
ORG_SETTINGS_MANAGE = OrgPermission(
    "org_settings", "manage", "Organization Settings",
    "Upload/delete government documents, view/regenerate the invite code and link",
)

# A narrower grant than ORG_SETTINGS_MANAGE - lets a role see and download
# the organization's submitted documents (e.g. for a compliance reviewer)
# without also handing them upload/delete and the invite code/link. The org
# owner already bypasses both (see org_permissions.is_org_owner).
ORG_DOCUMENT_VIEW = OrgPermission(
    "org_document", "view", "Organization Settings",
    "View and download this organization's submitted government documents",
)

register_org_permissions(
    ORG_STAFF_VIEW,
    ORG_STAFF_REMOVE,
    ORG_ROLE_VIEW,
    ORG_ROLE_CREATE,
    ORG_ROLE_EDIT,
    ORG_ROLE_DELETE,
    ORG_SETTINGS_MANAGE,
    ORG_DOCUMENT_VIEW,
)
