/**
 * Odysseus UI Component Library
 * JavaScript utilities for shadcn/ui-inspired components
 * Built with vanilla JavaScript
 */

(function() {
  'use strict';

  // ============================================
  // Toast Notification System
  // ============================================

  const Toast = {
    container: null,

    init() {
      if (!this.container) {
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        document.body.appendChild(this.container);
      }
    },

    show(options) {
      this.init();

      const { title, message, type = 'info', duration = 4000 } = options;

      const toast = document.createElement('div');
      toast.className = `toast toast-${type}`;

      const icons = {
        info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
        success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>',
        warning: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        destructive: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
      };

      toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <div class="toast-content">
          ${title ? `<div class="toast-title">${title}</div>` : ''}
          ${message ? `<div class="toast-message">${message}</div>` : ''}
        </div>
        <button class="toast-close" aria-label="Close notification">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      `;

      const closeBtn = toast.querySelector('.toast-close');
      closeBtn.addEventListener('click', () => this.dismiss(toast));

      this.container.appendChild(toast);

      if (duration > 0) {
        setTimeout(() => this.dismiss(toast), duration);
      }

      return toast;
    },

    dismiss(toast) {
      toast.classList.add('toast-exit');
      setTimeout(() => toast.remove(), 300);
    },

    info(title, message) {
      return this.show({ title, message, type: 'info' });
    },

    success(title, message) {
      return this.show({ title, message, type: 'success' });
    },

    warning(title, message) {
      return this.show({ title, message, type: 'warning' });
    },

    error(title, message) {
      return this.show({ title, message, type: 'destructive' });
    }
  };

  // ============================================
  // Dialog/Modal System
  // ============================================

  const Dialog = {
    activeDialogs: [],

    create(options) {
      const { title, content, footer, onClose } = options;

      const overlay = document.createElement('div');
      overlay.className = 'dialog-overlay';

      overlay.innerHTML = `
        <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
          <div class="dialog-header">
            <h2 id="dialog-title">${title}</h2>
            <button class="dialog-close" aria-label="Close dialog">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <div class="dialog-body">${content}</div>
          ${footer ? `<div class="dialog-footer">${footer}</div>` : ''}
        </div>
      `;

      const closeBtn = overlay.querySelector('.dialog-close');
      const close = () => {
        overlay.classList.remove('open');
        setTimeout(() => {
          overlay.remove();
          this.activeDialogs = this.activeDialogs.filter(d => d !== overlay);
          if (onClose) onClose();
        }, 200);
      };

      closeBtn.addEventListener('click', close);
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
      });

      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && this.activeDialogs[this.activeDialogs.length - 1] === overlay) {
          close();
        }
      });

      document.body.appendChild(overlay);
      requestAnimationFrame(() => overlay.classList.add('open'));
      this.activeDialogs.push(overlay);

      return { close, overlay };
    },

    confirm(options) {
      const { title, message, confirmText = 'Confirm', cancelText = 'Cancel', onConfirm, onCancel, confirmClass = 'btn-primary' } = options;

      const footer = `
        <button class="btn btn-secondary dialog-cancel">${cancelText}</button>
        <button class="btn ${confirmClass} dialog-confirm">${confirmText}</button>
      `;

      const dialog = this.create({
        title,
        content: `<p style="margin:0">${message}</p>`,
        footer,
        onClose: onCancel
      });

      const cancelBtn = dialog.overlay.querySelector('.dialog-cancel');
      const confirmBtn = dialog.overlay.querySelector('.dialog-confirm');

      cancelBtn.addEventListener('click', () => {
        dialog.close();
        if (onCancel) onCancel();
      });

      confirmBtn.addEventListener('click', () => {
        dialog.close();
        if (onConfirm) onConfirm();
      });

      return dialog;
    }
  };

  // ============================================
  // Tabs Component
  // ============================================

  const Tabs = {
    init(container) {
      const tabTriggers = container.querySelectorAll('.tab-trigger');

      tabTriggers.forEach(trigger => {
        trigger.addEventListener('click', () => {
          const tabId = trigger.getAttribute('data-tab');

          // Deactivate all tabs
          tabTriggers.forEach(t => t.classList.remove('active'));
          container.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

          // Activate clicked tab
          trigger.classList.add('active');
          const tabContent = container.querySelector(`[data-tab-panel="${tabId}"]`);
          if (tabContent) tabContent.classList.add('active');
        });
      });
    }
  };

  // ============================================
  // Dropdown Component
  // ============================================

  const Dropdown = {
    init() {
      document.addEventListener('click', (e) => {
        // Toggle dropdown
        const trigger = e.target.closest('[data-dropdown-trigger]');
        if (trigger) {
          const dropdown = trigger.closest('.dropdown');
          const isOpen = dropdown.classList.contains('open');
          this.closeAll();
          if (!isOpen) {
            dropdown.classList.add('open');
          }
          e.preventDefault();
          return;
        }

        // Close if clicked outside
        if (!e.target.closest('.dropdown')) {
          this.closeAll();
        }
      });

      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          this.closeAll();
        }
      });
    },

    closeAll() {
      document.querySelectorAll('.dropdown.open').forEach(d => {
        d.classList.remove('open');
      });
    }
  };

  // ============================================
  // Form Components Helpers
  // ============================================

  const Form = {
    // Create a labeled input
    createInput(options) {
      const { id, label, type = 'text', placeholder, value, required, description, disabled } = options;

      const wrapper = document.createElement('div');
      wrapper.className = 'form-field';

      let html = '';
      if (label) {
        html += `<label class="input-label" for="${id}">${label}</label>`;
      }
      html += `<input type="${type}" id="${id}" class="input" placeholder="${placeholder || ''}" ${value ? `value="${value}"` : ''} ${required ? 'required' : ''} ${disabled ? 'disabled' : ''}>`;
      if (description) {
        html += `<span class="input-description">${description}</span>`;
      }

      wrapper.innerHTML = html;
      return wrapper;
    },

    // Create a labeled textarea
    createTextarea(options) {
      const { id, label, placeholder, value, rows = 4, required, description, disabled } = options;

      const wrapper = document.createElement('div');
      wrapper.className = 'form-field';

      let html = '';
      if (label) {
        html += `<label class="input-label" for="${id}">${label}</label>`;
      }
      html += `<textarea id="${id}" class="textarea" placeholder="${placeholder || ''}" rows="${rows}" ${required ? 'required' : ''} ${disabled ? 'disabled' : ''}>${value || ''}</textarea>`;
      if (description) {
        html += `<span class="input-description">${description}</span>`;
      }

      wrapper.innerHTML = html;
      return wrapper;
    },

    // Create a select
    createSelect(options) {
      const { id, label, options: opts, value, required, description, disabled } = options;

      const wrapper = document.createElement('div');
      wrapper.className = 'form-field';

      let html = '';
      if (label) {
        html += `<label class="input-label" for="${id}">${label}</label>`;
      }
      html += `<select id="${id}" class="select" ${required ? 'required' : ''} ${disabled ? 'disabled' : ''}>`;
      opts.forEach(opt => {
        const selected = opt.value === value ? 'selected' : '';
        html += `<option value="${opt.value}" ${selected}>${opt.label}</option>`;
      });
      html += `</select>`;
      if (description) {
        html += `<span class="input-description">${description}</span>`;
      }

      wrapper.innerHTML = html;
      return wrapper;
    },

    // Create a checkbox
    createCheckbox(options) {
      const { id, label, checked, disabled, onChange } = options;

      const wrapper = document.createElement('label');
      wrapper.className = 'checkbox-wrapper';

      wrapper.innerHTML = `
        <input type="checkbox" id="${id}" ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
        <span class="checkbox"></span>
        <span>${label}</span>
      `;

      if (onChange) {
        wrapper.querySelector('input').addEventListener('change', (e) => onChange(e.target.checked));
      }

      return wrapper;
    },

    // Create a switch/toggle
    createSwitch(options) {
      const { id, label, checked, disabled, onChange } = options;

      const wrapper = document.createElement('label');
      wrapper.className = 'checkbox-wrapper';

      wrapper.innerHTML = `
        <span>${label}</span>
        <span class="switch">
          <input type="checkbox" id="${id}" ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
          <span class="switch-slider"></span>
        </span>
      `;

      if (onChange) {
        wrapper.querySelector('input').addEventListener('change', (e) => onChange(e.target.checked));
      }

      return wrapper;
    }
  };

  // ============================================
  // Skeleton Loading Helpers
  // ============================================

  const Skeleton = {
    createCard() {
      const div = document.createElement('div');
      div.className = 'card';
      div.innerHTML = `
        <div class="card-header">
          <div class="skeleton skeleton-title"></div>
        </div>
        <div class="card-content">
          <div style="display:flex;gap:12px;margin-bottom:12px;">
            <div class="skeleton skeleton-avatar"></div>
            <div style="flex:1">
              <div class="skeleton skeleton-text" style="width:40%"></div>
              <div class="skeleton skeleton-text" style="width:60%"></div>
            </div>
          </div>
          <div class="skeleton skeleton-text"></div>
          <div class="skeleton skeleton-text" style="width:80%"></div>
        </div>
      `;
      return div;
    },

    createText(lines = 3) {
      const div = document.createElement('div');
      for (let i = 0; i < lines; i++) {
        const line = document.createElement('div');
        line.className = 'skeleton skeleton-text';
        line.style.width = `${60 + Math.random() * 40}%`;
        div.appendChild(line);
      }
      return div;
    }
  };

  // ============================================
  // Utility Functions
  // ============================================

  const Utils = {
    // Debounce function
    debounce(func, wait) {
      let timeout;
      return function executedFunction(...args) {
        const later = () => {
          clearTimeout(timeout);
          func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
      };
    },

    // Throttle function
    throttle(func, limit) {
      let inThrottle;
      return function executedFunction(...args) {
        if (!inThrottle) {
          func(...args);
          inThrottle = true;
          setTimeout(() => inThrottle = false, limit);
        }
      };
    },

    // Generate unique ID
    generateId() {
      return 'odysseus-' + Math.random().toString(36).substr(2, 9);
    }
  };

  // ============================================
  // Initialize Components
  // ============================================

  document.addEventListener('DOMContentLoaded', () => {
    // Initialize dropdowns
    Dropdown.init();

    // Initialize tabs in containers with .tabs class
    document.querySelectorAll('.tabs').forEach(tabContainer => {
      Tabs.init(tabContainer);
    });

    // Auto-initialize any elements with data-auto-init
    document.querySelectorAll('[data-auto-init="tabs"]').forEach(el => {
      Tabs.init(el);
    });
  });

  // ============================================
  // Export Public API
  // ============================================

  window.OdysseusUI = {
    Toast,
    Dialog,
    Tabs,
    Dropdown,
    Form,
    Skeleton,
    Utils
  };

})();