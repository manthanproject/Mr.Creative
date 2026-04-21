/* ========================================
   MR.CREATIVE — Client-side JavaScript
   ======================================== */

// ---- Modal System ----
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
        document.body.style.overflow = '';
    }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(m => {
            m.classList.remove('active');
        });
        document.body.style.overflow = '';
    }
});

// ---- Staggered Animations on Scroll ----
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.animationPlayState = 'running';
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

document.querySelectorAll('[class*="animate-"]').forEach(el => {
    observer.observe(el);
});

// ---- Queue Badge Update ----
async function updateQueueBadge() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        const badge = document.getElementById('queueBadge');
        if (badge) {
            const total = (data.queued || 0) + (data.processing || 0);
            if (total > 0) {
                badge.textContent = total;
                badge.style.display = 'inline-flex';
            } else {
                badge.style.display = 'none';
            }
        }
    } catch (e) { /* silent fail */ }
}

// Poll queue every 10 seconds
if (document.getElementById('queueBadge')) {
    updateQueueBadge();
    setInterval(updateQueueBadge, 10000);
}

// ---- Tooltip System ----
document.querySelectorAll('[title]').forEach(el => {
    el.addEventListener('mouseenter', function () {
        this.dataset.tooltip = this.getAttribute('title');
        this.removeAttribute('title');
    });
    el.addEventListener('mouseleave', function () {
        if (this.dataset.tooltip) {
            this.setAttribute('title', this.dataset.tooltip);
        }
    });
});

// ---- Page Transition Effect ----
document.querySelectorAll('a[href]:not([target="_blank"]):not([onclick])').forEach(link => {
    link.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href && href.startsWith('/') && !href.startsWith('//')) {
            e.preventDefault();
            document.body.style.opacity = '0.97';
            document.body.style.transition = 'opacity 0.15s ease';
            setTimeout(() => {
                window.location = href;
            }, 100);
        }
    });
});

// ---- Sidebar Active State ----
document.addEventListener('DOMContentLoaded', () => {
    // Close mobile sidebar on link click
    document.querySelectorAll('.sidebar .nav-link').forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                document.querySelector('.sidebar').classList.remove('open');
            }
        });
    });
});

// ---- Utility: Relative Time ----
function timeAgo(dateStr) {
    const now = new Date();
    const date = new Date(dateStr);
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ---- Utility: Copy to Clipboard ----
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard!', 'success');
    }).catch(() => {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('Copied to clipboard!', 'success');
    });
}

// ---- Toast Notifications ----
function showToast(message, type = 'info') {
    const colors = { success: '#c1cd7d', error: '#f87171', info: '#c1cd7d', warning: '#fbbf24' };
    const icons = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };
    const toast = document.createElement('div');
    toast.className = 'flash-message ' + type;
    toast.onclick = () => toast.remove();
    toast.innerHTML = `<span style="color:${colors[type] || '#c1cd7d'}; font-weight:700;">${icons[type] || 'ℹ'}</span> ${message}`;

    const container = document.getElementById('flashContainer') || createFlashContainer();
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'toastOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function createFlashContainer() {
    const container = document.createElement('div');
    container.className = 'flash-container';
    container.id = 'flashContainer';
    document.body.appendChild(container);
    return container;
}

console.log('%c✦ Mr.Creative', 'color: #c1cd7d; font-size: 20px; font-weight: bold;');
console.log('%cAI Creative Engine — Powered by Pomelli & Gemini', 'color: #919282; font-size: 12px;');
