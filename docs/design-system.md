# NirikshanOS Design System

A shadcn-style component system built with **Tailwind CSS v4**, **Jinja2 macros**,
**Alpine.js** (small interactive bits) and **HTMX** (partial page updates).
Dark mode is the default theme.

## Build

Tailwind output is committed (`app/static/css/tailwind.css`) so the Quart app
needs no build step at runtime. Regenerate it after changing tokens or adding
new utility classes to templates:

```
npm install
npm run build:css     # one-shot build
npm run watch:css     # rebuild on change, for local dev
```

Source files:
- `app/static/css/input.css` - Tailwind import + design tokens (`@theme`, `:root`, `.dark`)
- `app/static/css/tailwind.css` - generated output, linked from `layouts/base.html`

## Design tokens

All colors are CSS variables defined in `app/static/css/input.css`, mapped to
Tailwind utilities via `@theme inline`. Use the **semantic** utility, never a
raw color:

| Token | Utility classes | Use for |
|---|---|---|
| `background` / `foreground` | `bg-background` `text-foreground` | page background/text |
| `card` / `card-foreground` | `bg-card` `text-card-foreground` | card surfaces |
| `primary` / `primary-foreground` | `bg-primary` `text-primary-foreground` | primary buttons |
| `secondary` / `secondary-foreground` | `bg-secondary` `text-secondary-foreground` | secondary buttons |
| `muted` / `muted-foreground` | `bg-muted` `text-muted-foreground` | subtle backgrounds, helper text |
| `accent` / `accent-foreground` | `bg-accent` `text-accent-foreground` | hover states |
| `destructive` / `destructive-foreground` | `bg-destructive` `text-destructive-foreground` | delete/danger |
| `success`, `warning` (+ `-foreground`) | `bg-success`, `bg-warning` ... | status badges |
| `border` / `input` / `ring` | `border-border` `border-input` `ring-ring` | borders, focus rings |
| `sidebar*` | `bg-sidebar` `text-sidebar-foreground` ... | sidebar nav |

`:root` defines the **dark** theme (default). `:root:not(.dark)` overrides for
light mode. The `<html>` element starts with `class="dark"`
(`layouts/base.html`); the theme toggle adds/removes that class and persists
the choice in `localStorage.theme`.

`--radius` controls corner rounding; `rounded-md`/`rounded-lg`/etc. derive from it.

## Layout

- `app/templates/layouts/base.html` - HTML shell: loads `tailwind.css`,
  Alpine.js, HTMX, applies the saved theme before paint. Pages `{% extends %}`
  this and override `block title` and `block body`.

## Components

### `components/ui/` - generic primitives (reusable across all features)

| File | Macro(s) | Notes |
|---|---|---|
| `button.html` | `button(label, variant, size, tag, type, href, attrs, extra_classes)` | variants: `primary`, `secondary`, `outline`, `ghost`, `destructive`, `link`; sizes: `sm`, `md`, `lg`, `icon`. `tag="a"` renders an `<a>`. |
| `card.html` | `card_open`, `card_close`, `card_header`, `card_title`, `card_description`, `card_content`, `card_footer` | open/close pattern so any markup can go inside |
| `badge.html` | `badge(label, variant)` | variants: `primary`, `secondary`, `outline`, `success`, `warning`, `destructive` |
| `avatar.html` | `avatar(src, initials, size)` | falls back to initials if `src` is empty |
| `input.html` | `input(name, type, value, placeholder, required, attrs, extra_classes)` | `attrs` for raw HTMX/Alpine attributes |
| `separator.html` | `separator(orientation)` | `horizontal` (default) or `vertical` |
| `theme-toggle.html` | `theme_toggle()` | sun/moon button, Alpine-driven |
| `label.html` | `label(text, for, extra_classes)` | form field label |
| `textarea.html` | `textarea(name, value, placeholder, rows, required, attrs, extra_classes)` | multi-line input |
| `checkbox.html` | `checkbox(name, label, checked, value, attrs, extra_classes)` | peer pattern, native `<input type=checkbox>` under a styled box |
| `switch.html` | `switch(name, checked, value, attrs, extra_classes)` | on/off toggle, peer pattern |
| `radio-group.html` | `radio_group(name, options, value, extra_classes)` | `options` is a list of `(value, label)` |
| `toggle.html` | `toggle(label, pressed, variant, size, extra_classes)` | Alpine-driven pressed state; variants `default`/`outline` |
| `alert.html` | `alert(description, title, variant, extra_classes)` | variants: `default`, `error`, `info`, `success`, `warning` |
| `progress.html` | `progress(value, label, extra_classes)` | `value` is 0-100 |
| `skeleton.html` | `skeleton(extra_classes)` | loading placeholder block (size via `extra_classes`, e.g. `h-4 w-32`) |
| `kbd.html` | `kbd(text)`, `kbd_group(items)` | keyboard shortcut hints |
| `spinner.html` | `spinner(extra_classes)` | animated loading icon |
| `tooltip.html` | `tooltip(trigger, text, side)` | Alpine-driven hover/focus popup; `trigger` is raw safe HTML |
| `table.html` | `table_open`, `table_close`, `thead`, `tbody`, `th(label)`, `td(content)` | data table shell |
| `breadcrumb.html` | `breadcrumb(items)` | `items` is a list of `(label, href)`, `href=None` for current page |
| `pagination.html` | `pagination(page, base_url)` | `page` is a `Page` from `app/core/db/pagination.py` |
| `tabs.html` | `tabs_open(default_tab)`, `tabs_close`, `tabs_list`, `tab_trigger(value, label)`, `tab_panel(value)` | Alpine-driven |
| `accordion.html` | `accordion_open`, `accordion_close`, `accordion_item(index, title)` | Alpine-driven, single item open (requires `@alpinejs/collapse` plugin, loaded in `base.html`) |
| `dialog.html` | `dialog()` (use with `{% call %}`) | modal overlay; needs an ancestor `x-data="{ open: false }"` and `@alpinejs/focus` plugin (loaded in `base.html`) |
| `menu.html` | `menu(trigger, align)` (use with `{% call %}`), `menu_item(label, href, variant)`, `menu_separator()` | Alpine-driven dropdown |
| `select.html` | `select(name, options, value, attrs, extra_classes)` | native `<select>` styled to match |

### Not yet ported

The following `next-app/components/ui/*` components are **not yet ported**
(no current page needs them) - port on demand when a feature requires one,
following the patterns above (native HTML element + Tailwind tokens + Alpine
for interactivity, no portal/positioner libraries):
`accordion` variants beyond single-open, `alert-dialog`, `autocomplete`,
`calendar`, `checkbox-group`, `collapsible`, `combobox`, `command`,
`context-menu`, `drawer`, `empty`, `fieldset`, `field`, `form`, `frame`,
`group`, `input-group`, `meter`, `number-field`, `otp-field`, `popover`,
`preview-card`, `scroll-area`, `sheet`, `toggle-group`, `toolbar`.

### `dashboard/components/` - dashboard-specific composition

| File | Macro | Notes |
|---|---|---|
| `sidebar.html` | `sidebar(active)` | fixed nav, highlights the item matching `active` |
| `topbar.html` | `topbar(title)` | page title, search input, theme toggle, avatar |
| `stat_card.html` | `stat_card(label, value, change)` | wraps `card_open/close` for metric tiles |

`dashboard/dashboard.html` assembles these inside `layouts/base.html`'s
`body` block.

## Conventions

- **No duplicated markup**: if two pages need the same visual pattern, it
  becomes a macro under `components/ui/` (generic) or
  `<feature>/components/` (feature-specific composition), not copy-pasted HTML.
- **Semantic tokens only** - don't use raw Tailwind colors (`bg-neutral-900`,
  `text-red-500`) in page/feature templates; use the token utilities above so
  dark/light mode and future theme changes apply everywhere automatically.
- **Accessibility** - interactive elements use real `<button>`/`<a>` tags,
  visible focus rings (`focus-visible:ring-2 focus-visible:ring-ring`), and
  `aria-*`/`role` attributes where semantics aren't implicit (e.g.
  `separator.html`).
- **New component checklist**: before adding a new macro, check
  `components/ui/` and the current feature's `components/` for something
  reusable. If you add one, document it in this file (table above).
