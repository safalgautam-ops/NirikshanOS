from app.core.security.org_permission_registry import OrgPermission, register_org_permissions

CASE_CREATE = OrgPermission("case", "create", "Cases", "Create cases for this organization")
CASE_EDIT = OrgPermission("case", "edit", "Cases", "Edit case details and members")
CASE_DELETE = OrgPermission("case", "delete", "Cases", "Delete cases")

EVIDENCE_UPLOAD = OrgPermission("evidence", "upload", "Cases", "Upload evidence to a case")
EVIDENCE_DELETE = OrgPermission("evidence", "delete", "Cases", "Delete evidence from a case")
EVIDENCE_ANALYZE = OrgPermission("evidence", "analyze", "Cases", "Run analysis modules against evidence")

register_org_permissions(
    CASE_CREATE,
    CASE_EDIT,
    CASE_DELETE,
    EVIDENCE_UPLOAD,
    EVIDENCE_DELETE,
    EVIDENCE_ANALYZE,
)
