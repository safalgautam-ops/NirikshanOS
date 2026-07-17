# NirikshanOS UI Component System

NirikshanOS uses Tailwind CSS v4, server-rendered Jinja macros, raw JavaScript, and
HTMX. Shared components live under `app/templates/components/ui/`.

## Tailwind

The frontend uses the same no-build approach as the CodeSandbox reference:

- `app/templates/layouts/base.html` loads `@tailwindcss/browser@4`.
- `app/templates/style.css` is included through a `text/tailwindcss` style block.
- Homepage-specific presentation rules are kept in `app/templates/style.css`.
- `app/static/css/vendor/` contains third-party styles.

There is no generated `tailwind.css`, Node package, or CSS build command.
NirikshanOS keeps its existing design tokens, so changing the delivery mechanism
does not replace the application’s visual identity.

## JavaScript

- `app/static/js/app.js` contains only cross-page behavior: theme persistence,
  CSRF access, shared macro behavior, toast handling, page search, and file-size
  validation.
- `app/static/js/pages/` contains behavior needed by one page only.
- `app/static/js/vendor/` contains third-party libraries.
- HTMX is loaded only by templates that declare `hx-*` attributes.
- CodeMirror is loaded only by the module IDE.
- The application is Flask/Jinja and has no client-side router.

## Component usage

Import a component file once and call its macro:

```jinja
{% import "components/ui/button.html" as button %}
{% import "components/ui/form.html" as form_ui %}
{% import "components/ui/input.html" as input %}
{% import "components/ui/label.html" as label_ui %}
{% import "components/ui/select-native.html" as select_native %}

{% call form_ui.form(method="post", action=url_for("cases.create_view")) %}
  {% call label_ui.label(for_id="title") %}Title{% endcall %}
  {{ input.input(id="title", name="title", required=true) }}
  {% call select_native.select_native(name="status") %}
    <option value="open">Open</option>
  {% endcall %}
  {% call button.button(type="submit") %}Save{% endcall %}
{% endcall %}
```

Core macros include:

- `form.form()`
- `button.button()` and `button.button_link()`
- `input.input()`, `input.hidden_input()`, and `input.file_input()`
- `label.label()` and `field.*`
- `textarea.textarea()`
- `select_native.select_native()`
- `checkbox.checkbox()`, `radio_group.*`, and `switch.switch()`
- `dialog.*` and `alert_dialog.*`
- `table.*` and `table_pagination.table_pagination()`

Compatibility parameters such as `unstyled=true`, `bare=true`, and explicit
classes preserve established page markup while still routing elements through
the component API.

## Rules

1. Page templates do not declare native buttons, inputs, selects, textareas,
   forms, labels, or table elements directly.
2. Preserve IDs, names, values, data/ARIA attributes, raw-JavaScript hooks, HTMX
   attributes, methods, actions, encodings, and CSRF fields during conversion.
3. Generic primitives belong in `components/ui/`; feature composition belongs
   beside the feature template.
4. Shared behavior belongs in `static/js/app.js`; page-specific behavior remains
   in one flat `static/js/pages/` directory.
5. Do not add a client-side router or duplicate server-rendered navigation.
