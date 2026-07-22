# Odysseus UI Component Library

A shadcn/ui-inspired component library built with vanilla CSS and JavaScript, designed to work seamlessly with the existing Odysseus theme system.

## Overview

This component library provides accessible, customizable UI components that follow shadcn/ui's design principles while being fully compatible with the vanilla JavaScript/Flask architecture.

## Features

- ✅ **Theme-aware**: Automatically uses your existing CSS variables
- ✅ **Accessible**: WCAG 2.1 compliant with keyboard navigation
- ✅ **Responsive**: Mobile-first design with breakpoints
- ✅ **Customizable**: Built with CSS variables for easy theming
- ✅ **Zero dependencies**: Pure vanilla CSS and JavaScript

## Installation

Add the component files to your HTML:

```html
<!-- In your <head> -->
<link rel="stylesheet" href="/static/css/components.css">

<!-- Before closing </body> -->
<script src="/static/js/components.js"></script>
```

## Components

### Buttons

```html
<!-- Primary Button -->
<button class="btn btn-primary">Primary</button>

<!-- Secondary Button -->
<button class="btn btn-secondary">Secondary</button>

<!-- Ghost Button -->
<button class="btn btn-ghost">Ghost</button>

<!-- Destructive Button -->
<button class="btn btn-destructive">Delete</button>

<!-- Outline Button -->
<button class="btn btn-outline">Outline</button>

<!-- Sizes -->
<button class="btn btn-sm btn-primary">Small</button>
<button class="btn btn-lg btn-primary">Large</button>

<!-- With Icon -->
<button class="btn btn-primary">
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M12 5v14M5 12h14"/>
  </svg>
  Add Item
</button>

<!-- Disabled State -->
<button class="btn btn-primary" disabled>Disabled</button>
```

### Cards

```html
<div class="card">
  <div class="card-header">
    <h3>Card Title</h3>
    <p>Card description or subtitle</p>
  </div>
  <div class="card-content">
    <p>Card content goes here. This can include text, forms, or other components.</p>
  </div>
  <div class="card-footer">
    <button class="btn btn-secondary">Cancel</button>
    <button class="btn btn-primary">Save</button>
  </div>
</div>
```

### Form Inputs

```html
<!-- Text Input with Label -->
<div>
  <label class="input-label" for="email">Email</label>
  <input type="email" id="email" class="input" placeholder="Enter your email">
  <span class="input-description">We'll never share your email with anyone.</span>
</div>

<!-- Textarea -->
<div>
  <label class="input-label" for="message">Message</label>
  <textarea id="message" class="textarea" placeholder="Type your message..." rows="4"></textarea>
</div>

<!-- Select -->
<div>
  <label class="input-label" for="country">Country</label>
  <select id="country" class="select">
    <option value="">Select a country</option>
    <option value="us">United States</option>
    <option value="uk">United Kingdom</option>
    <option value="ca">Canada</option>
  </select>
</div>

<!-- With Validation States -->
<input type="email" class="input" style="border-color: #ef4444;" placeholder="Invalid email">
```

### Checkbox

```html
<label class="checkbox-wrapper">
  <input type="checkbox">
  <span class="checkbox"></span>
  <span>I agree to the terms and conditions</span>
</label>

<!-- Checked State -->
<label class="checkbox-wrapper">
  <input type="checkbox" checked>
  <span class="checkbox"></span>
  <span>Remember me</span>
</label>
```

### Switch/Toggle

```html
<label class="checkbox-wrapper">
  <span>Enable notifications</span>
  <span class="switch">
    <input type="checkbox" checked>
    <span class="switch-slider"></span>
  </span>
</label>

<!-- Unchecked -->
<label class="checkbox-wrapper">
  <span>Dark mode</span>
  <span class="switch">
    <input type="checkbox">
    <span class="switch-slider"></span>
  </span>
</label>
```

### Badges

```html
<span class="badge">Default</span>
<span class="badge badge-primary">Primary</span>
<span class="badge badge-secondary">Secondary</span>
<span class="badge badge-success">Success</span>
<span class="badge badge-warning">Warning</span>
<span class="badge badge-destructive">Error</span>
```

### Avatar

```html
<!-- With Initials -->
<div class="avatar">JD</div>

<!-- With Image -->
<div class="avatar">
  <img src="/path/to/avatar.jpg" alt="John Doe">
</div>

<!-- Sizes -->
<div class="avatar avatar-sm">JD</div>
<div class="avatar">JD</div>
<div class="avatar avatar-lg">JD</div>
```

### Alerts

```html
<div class="alert alert-info">
  <span class="alert-icon">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
    </svg>
  </span>
  <div class="alert-content">
    <div class="alert-title">Heads up!</div>
    <div class="alert-description">This is an informational message.</div>
  </div>
</div>

<div class="alert alert-success">
  <span class="alert-icon">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/>
    </svg>
  </span>
  <div class="alert-content">
    <div class="alert-title">Success!</div>
    <div class="alert-description">Your changes have been saved.</div>
  </div>
</div>

<div class="alert alert-warning">
  <span class="alert-icon">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  </span>
  <div class="alert-content">
    <div class="alert-title">Warning</div>
    <div class="alert-description">Please review your input before continuing.</div>
  </div>
</div>

<div class="alert alert-destructive">
  <span class="alert-icon">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/>
      <line x1="9" y1="9" x2="15" y2="15"/>
    </svg>
  </span>
  <div class="alert-content">
    <div class="alert-title">Error</div>
    <div class="alert-description">Something went wrong. Please try again.</div>
  </div>
</div>
```

### Progress

```html
<div class="progress">
  <div class="progress-bar" style="width: 60%"></div>
</div>
```

### Skeleton Loading

```html
<!-- Skeleton Card -->
<div class="card">
  <div class="card-header">
    <div class="skeleton skeleton-title"></div>
  </div>
  <div class="card-content">
    <div class="skeleton skeleton-text"></div>
    <div class="skeleton skeleton-text" style="width: 80%"></div>
    <div class="skeleton skeleton-text" style="width: 60%"></div>
  </div>
</div>

<!-- Skeleton Text Lines -->
<div class="skeleton skeleton-text"></div>
<div class="skeleton skeleton-text" style="width: 90%"></div>
<div class="skeleton skeleton-text" style="width: 70%"></div>
```

### Tabs

```html
<div class="tabs">
  <div class="tabs-list">
    <button class="tab-trigger active" data-tab="tab1">Account</button>
    <button class="tab-trigger" data-tab="tab2">Password</button>
    <button class="tab-trigger" data-tab="tab3">Settings</button>
  </div>
  
  <div class="tab-content active" data-tab-panel="tab1">
    <p>Account settings content...</p>
  </div>
  <div class="tab-content" data-tab-panel="tab2">
    <p>Password settings content...</p>
  </div>
  <div class="tab-content" data-tab-panel="tab3">
    <p>General settings content...</p>
  </div>
</div>
```

### Dialog/Modal

```html
<!-- Trigger Button -->
<button class="btn btn-primary" onclick="showDialog()">Open Dialog</button>

<script>
function showDialog() {
  const dialog = OdysseusUI.Dialog.create({
    title: 'Edit Profile',
    content: `
      <div class="form-field">
        <label class="input-label" for="name">Name</label>
        <input type="text" id="name" class="input" value="John Doe">
      </div>
    `,
    footer: `
      <button class="btn btn-secondary" onclick="this.closest('.dialog-overlay').querySelector('.dialog-close').click()">Cancel</button>
      <button class="btn btn-primary">Save Changes</button>
    `,
    onClose: () => console.log('Dialog closed')
  });
}
</script>

<!-- Confirmation Dialog -->
<button class="btn btn-destructive" onclick="showConfirm()">Delete Item</button>

<script>
function showConfirm() {
  OdysseusUI.Dialog.confirm({
    title: 'Delete Item',
    message: 'Are you sure you want to delete this item? This action cannot be undone.',
    confirmText: 'Delete',
    cancelText: 'Cancel',
    confirmClass: 'btn-destructive',
    onConfirm: () => {
      console.log('Item deleted');
      // Perform delete action
    },
    onCancel: () => {
      console.log('Deletion cancelled');
    }
  });
}
</script>
```

## JavaScript API

### Toast Notifications

```javascript
// Basic toast
OdysseusUI.Toast.show({
  title: 'Success',
  message: 'Your changes have been saved.',
  type: 'success', // 'info', 'success', 'warning', 'destructive'
  duration: 4000 // milliseconds, 0 for persistent
});

// Convenience methods
OdysseusUI.Toast.info('Info', 'This is an info message');
OdysseusUI.Toast.success('Success', 'Operation completed');
OdysseusUI.Toast.warning('Warning', 'Please review your input');
OdysseusUI.Toast.error('Error', 'Something went wrong');
```

### Dialog API

```javascript
// Create custom dialog
const dialog = OdysseusUI.Dialog.create({
  title: 'My Dialog',
  content: '<p>Dialog content here</p>',
  footer: '<button class="btn btn-primary">OK</button>',
  onClose: () => console.log('Closed')
});

// Close programmatically
dialog.close();

// Confirmation dialog
OdysseusUI.Dialog.confirm({
  title: 'Confirm Action',
  message: 'Are you sure?',
  onConfirm: () => console.log('Confirmed'),
  onCancel: () => console.log('Cancelled')
});
```

### Form Helpers

```javascript
// Create input
const input = OdysseusUI.Form.createInput({
  id: 'email',
  label: 'Email Address',
  type: 'email',
  placeholder: 'you@example.com',
  required: true,
  description: 'We\'ll never share your email.'
});
document.getElementById('form-container').appendChild(input);

// Create textarea
const textarea = OdysseusUI.Form.createTextarea({
  id: 'bio',
  label: 'Bio',
  placeholder: 'Tell us about yourself...',
  rows: 4
});

// Create select
const select = OdysseusUI.Form.createSelect({
  id: 'role',
  label: 'Role',
  options: [
    { value: '', label: 'Select a role' },
    { value: 'admin', label: 'Administrator' },
    { value: 'user', label: 'User' }
  ],
  value: 'user'
});

// Create checkbox
const checkbox = OdysseusUI.Form.createCheckbox({
  id: 'terms',
  label: 'I agree to the terms',
  checked: false,
  onChange: (checked) => console.log('Checked:', checked)
});

// Create switch
const switchEl = OdysseusUI.Form.createSwitch({
  id: 'notifications',
  label: 'Enable notifications',
  checked: true,
  onChange: (checked) => console.log('Notifications:', checked ? 'on' : 'off')
});
```

### Tabs API

```javascript
// Initialize tabs (auto-initialized for .tabs containers)
const tabContainer = document.querySelector('.tabs');
OdysseusUI.Tabs.init(tabContainer);
```

### Skeleton Helpers

```javascript
// Create skeleton card
const skeletonCard = OdysseusUI.Skeleton.createCard();
container.appendChild(skeletonCard);

// Create skeleton text lines
const skeletonText = OdysseusUI.Skeleton.createText(3);
container.appendChild(skeletonText);
```

### Utility Functions

```javascript
// Debounce
const handleResize = OdysseusUI.Utils.debounce(() => {
  console.log('Window resized');
}, 250);
window.addEventListener('resize', handleResize);

// Throttle
const handleScroll = OdysseusUI.Utils.throttle(() => {
  console.log('Scrolled');
}, 100);
window.addEventListener('scroll', handleScroll);

// Generate unique ID
const id = OdysseusUI.Utils.generateId();
console.log(id); // "odysseus-abc123def"
```

## Theming

All components use CSS variables that integrate with the existing Odysseus theme system:

```css
/* Core colors */
--bg: Background color
--fg: Foreground/text color
--panel: Panel/card background
--border: Border color
--red: Accent color (default primary)
--accent-primary: Primary accent color

/* Form inputs */
--input-bg: Input background
--input-border: Input border color

/* Toggles */
--toggle-bg: Toggle background (off state)
--toggle-active: Toggle background (on state)
```

### Customizing Component Styles

```css
/* Override specific component colors */
.btn-primary {
  background-color: #your-color;
  border-color: #your-color;
}

/* Add custom component variants */
.btn-custom {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
}

.btn-custom:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}
```

## Accessibility

All components follow WCAG 2.1 guidelines:

- **Keyboard Navigation**: All interactive elements are focusable and operable via keyboard
- **Focus Indicators**: Visible focus states with `:focus-visible`
- **ARIA Attributes**: Proper roles, labels, and descriptions
- **Color Contrast**: Meets AA standards for text contrast
- **Screen Reader Support**: Semantic HTML and ARIA live regions for dynamic content

### Keyboard Shortcuts

- `Tab` / `Shift+Tab`: Navigate between interactive elements
- `Enter` / `Space`: Activate buttons, checkboxes
- `Escape`: Close dialogs, dropdowns, cancel actions
- `Arrow Keys`: Navigate within tabs, dropdowns

## Browser Support

- Chrome/Edge 88+
- Firefox 78+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome for Android)

## Contributing

When adding new components:

1. Follow the existing naming conventions
2. Use CSS variables for theming
3. Ensure accessibility (keyboard nav, ARIA)
4. Add responsive styles
5. Document usage examples
6. Test across browsers

## License

MIT License - same as the main Odysseus project.