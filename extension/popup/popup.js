const SERVER = 'http://localhost:5000';

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
  checkStatus();
  loadQueue();
  setInterval(checkStatus, 3000);
  setInterval(loadQueue, 5000);
});

// ── Check server + polling status ──
async function checkStatus() {
  const dot = document.getElementById('statusDot');
  const msg = document.getElementById('statusMsg');
  const btn = document.getElementById('toggleBtn');

  // Check background polling state
  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
    if (res && res.polling) {
      btn.textContent = '⏸ Pause';
      btn.classList.add('active');
    } else {
      btn.textContent = '▶ Start';
      btn.classList.remove('active');
    }
  });

  // Check server connection
  try {
    const res = await fetch(`${SERVER}/api/ext/status`);
    if (res.ok) {
      const data = await res.json();
      dot.classList.add('active');
      msg.textContent = data.message || 'Connected to server';

      if (data.current_job) {
        document.getElementById('currentJob').textContent =
          `${data.current_job.type} — ${data.current_job.state || 'running'}`;
      } else {
        document.getElementById('currentJob').textContent = 'No active job';
      }
    }
  } catch (e) {
    dot.classList.remove('active');
    msg.textContent = 'Server offline — start Mr.Creative first';
  }
}

// ── Load queue ──
async function loadQueue() {
  try {
    const res = await fetch(`${SERVER}/api/ext/queue`);
    if (!res.ok) return;
    const jobs = await res.json();

    const container = document.getElementById('queueList');
    if (!jobs.length) {
      container.innerHTML = '<div style="font-size: 11px; color: #555; padding: 4px;">No pending jobs</div>';
      return;
    }

    container.innerHTML = jobs.map(j => `
      <div class="queue-item">
        <div class="queue-dot ${j.status}"></div>
        <span>${j.type} — ${j.name || j.prompt?.substring(0, 30) || 'Untitled'}</span>
      </div>
    `).join('');
  } catch (e) { /* server offline */ }
}

// ── Toggle polling ──
function togglePolling() {
  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
    const msgType = res?.polling ? 'STOP_POLLING' : 'START_POLLING';
    chrome.runtime.sendMessage({ type: msgType }, () => checkStatus());
  });
}

// ── Open dashboard ──
function openDashboard() {
  chrome.tabs.create({ url: `${SERVER}/generate/` });
}

// ── Stop current job ──
async function stopJob() {
  try {
    await fetch(`${SERVER}/api/ext/stop`, { method: 'POST' });
    document.getElementById('currentJob').textContent = 'Stopped';
  } catch (e) { /* ignore */ }
}
