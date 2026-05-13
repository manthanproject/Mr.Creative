

// ══════════════════════════════════════════════
// PJAX — SPA-like navigation without framework
// ══════════════════════════════════════════════
(function() {
    var _pjaxEnabled = true;
    var _mainSelector = '.main-content, main, .content-area';

    function getMain() {
        return document.querySelector(_mainSelector);
    }

    function swapContent(html, url) {
        var parser = new DOMParser();
        var doc = parser.parseFromString(html, 'text/html');
        var newMain = doc.querySelector(_mainSelector);
        var main = getMain();
        if (!newMain || !main) { window.location.href = url; return; }

        // Update title
        var newTitle = doc.querySelector('title');
        if (newTitle) document.title = newTitle.textContent;

        // Update active sidebar link
        document.querySelectorAll('.sidebar a, .nav-link').forEach(function(a) {
            a.classList.remove('active');
            var href = a.getAttribute('href');
            if (href && url.startsWith(href) && href !== '/') {
                a.classList.add('active');
            }
        });

        // Swap content with animation
        main.style.transition = 'opacity 0.1s ease-out, transform 0.1s ease-out';
        main.style.opacity = '0';
        main.style.transform = 'translateY(4px)';

        setTimeout(function() {
            main.innerHTML = newMain.innerHTML;

            // Copy any new CSS from head
            doc.querySelectorAll('style, link[rel=stylesheet]').forEach(function(s) {
                var id = s.id || s.getAttribute('href');
                if (id && !document.querySelector('[id="'+id+'"], [href="'+id+'"]')) {
                    document.head.appendChild(s.cloneNode(true));
                }
            });

            // Execute inline scripts
            main.querySelectorAll('script').forEach(function(old) {
                var s = document.createElement('script');
                if (old.src) { s.src = old.src; }
                else { s.textContent = old.textContent; }
                old.parentNode.replaceChild(s, old);
            });

            // Fade in
            main.style.opacity = '1';
            main.style.transform = 'translateY(0)';

            // Update URL
            history.pushState({pjax: true, url: url}, '', url);

            // Scroll to top
            main.scrollTop = 0;
            window.scrollTo(0, 0);
        }, 100);
    }

    // Intercept sidebar link clicks
    document.addEventListener('click', function(e) {
        if (!_pjaxEnabled) return;

        var link = e.target.closest('a[href]');
        if (!link) return;

        var href = link.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('http') || href.startsWith('javascript')) return;
        if (link.target === '_blank') return;
        if (e.ctrlKey || e.metaKey || e.shiftKey) return;
        if (link.hasAttribute('data-no-pjax')) return;

        // Only PJAX internal navigation links
        if (!href.startsWith('/')) return;

        // Skip API calls, static files, auth
        if (href.match(/^\/(api|static|auth|login|logout)\//)) return;

        e.preventDefault();

        // Don't reload same page
        if (href === window.location.pathname) return;

        var main = getMain();
        if (main) {
            main.style.transition = 'opacity 0.08s';
            main.style.opacity = '0.3';
        }

        fetch(href, { headers: { 'X-PJAX': '1' } })
            .then(function(r) {
                if (!r.ok) throw new Error(r.status);
                return r.text();
            })
            .then(function(html) { swapContent(html, href); })
            .catch(function() { window.location.href = href; });
    });

    // Handle back/forward buttons
    window.addEventListener('popstate', function(e) {
        if (e.state && e.state.pjax) {
            fetch(e.state.url, { headers: { 'X-PJAX': '1' } })
                .then(function(r) { return r.text(); })
                .then(function(html) { swapContent(html, e.state.url); })
                .catch(function() { window.location.reload(); });
        }
    });

    // Save initial state
    history.replaceState({pjax: true, url: window.location.href}, '');
})();

// ══════════════════════════════════════════════
// Soft Reload System — no white flash, instant feel
// ══════════════════════════════════════════════

// Override location.reload globally
(function() {
    var _origReload = location.reload.bind(location);

    // Soft reload: fetch current page, swap main content with fade
    window.softReload = function(callback) {
        var main = document.querySelector('.main-content') || document.querySelector('main') || document.querySelector('.content-area');
        if (!main) { _origReload(); return; }

        // Fade out
        main.style.transition = 'opacity 0.12s ease-out';
        main.style.opacity = '0.3';

        fetch(window.location.href, { headers: { 'X-Soft-Reload': '1' } })
            .then(function(r) { return r.text(); })
            .then(function(html) {
                var parser = new DOMParser();
                var doc = parser.parseFromString(html, 'text/html');
                var newMain = doc.querySelector('.main-content') || doc.querySelector('main') || doc.querySelector('.content-area');

                if (newMain) {
                    main.innerHTML = newMain.innerHTML;
                    // Re-run any inline scripts
                    main.querySelectorAll('script').forEach(function(oldScript) {
                        var newScript = document.createElement('script');
                        if (oldScript.src) { newScript.src = oldScript.src; }
                        else { newScript.textContent = oldScript.textContent; }
                        oldScript.parentNode.replaceChild(newScript, oldScript);
                    });
                }

                // Fade in
                main.style.opacity = '1';
                if (callback) callback();
            })
            .catch(function() { _origReload(); });
    };

    // Soft navigate: go to new page without white flash
    window.softNavigate = function(url) {
        var main = document.querySelector('.main-content') || document.querySelector('main') || document.querySelector('.content-area');
        if (!main) { window.location.href = url; return; }

        main.style.transition = 'opacity 0.1s ease-out';
        main.style.opacity = '0';
        setTimeout(function() { window.location.href = url; }, 100);
    };
})();


// ── Instant Navigation ──
// Prefetch pages on hover, show loading indicator on click
document.addEventListener('DOMContentLoaded', function() {
    // Prefetch on hover
    document.querySelectorAll('.sidebar a[href]').forEach(function(link) {
        link.addEventListener('mouseenter', function() {
            var href = this.getAttribute('href');
            if (href && href.startsWith('/') && !document.querySelector('link[href="'+href+'"]')) {
                var pf = document.createElement('link');
                pf.rel = 'prefetch';
                pf.href = href;
                document.head.appendChild(pf);
            }
        });
        // Instant fade-out on click
        link.addEventListener('click', function() {
            var main = document.querySelector('.main-content') || document.querySelector('main') || document.querySelector('.content');
            if (main) {
                main.style.transition = 'opacity 0.1s';
                main.style.opacity = '0.4';
            }
        });
    });
});

// ── Smart Reload Helper ──
// Use instead of location.reload() — updates only the changed element
function smartUpdate(selector, html) {
    var el = document.querySelector(selector);
    if (el) {
        el.style.transition = 'opacity 0.15s';
        el.style.opacity = '0';
        setTimeout(function() {
            el.innerHTML = html;
            el.style.opacity = '1';
        }, 150);
    }
}
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
