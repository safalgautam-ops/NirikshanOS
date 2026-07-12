// Page-specific JS for billing/esewa_redirect.html — auto-submits the
// server-built, signed payment form straight to eSewa. Kept out of an
// inline <script> since CSP's default-src 'self' (no unsafe-inline)
// blocks those in production.
document.getElementById("esewa-form").submit();
