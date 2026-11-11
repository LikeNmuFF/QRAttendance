// Native navigation and forms, with small progressive enhancements.
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
const scene = document.querySelector('.product-scene');
if (scene) {
  const observer = new IntersectionObserver(([entry]) => {
    scene.classList.toggle('motion-offscreen', !entry.isIntersecting || document.hidden);
  });
  observer.observe(scene);
  document.addEventListener('visibilitychange', () => scene.classList.toggle('motion-offscreen', document.hidden));
  if (window.matchMedia('(pointer: fine)').matches) {
    let frame;
    scene.addEventListener('pointermove', (event) => {
      if (motionPreference.matches) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = scene.getBoundingClientRect();
        scene.style.setProperty('--tilt-x', `${(0.5 - (event.clientY - rect.top) / rect.height) * 5}deg`);
        scene.style.setProperty('--tilt-y', `${((event.clientX - rect.left) / rect.width - 0.5) * 7}deg`);
      });
    });
    scene.addEventListener('pointerleave', () => {
      cancelAnimationFrame(frame);
      scene.style.removeProperty('--tilt-x');
      scene.style.removeProperty('--tilt-y');
    });
  }
}
const passwordToggle = document.querySelector('.password-toggle');
if (passwordToggle) {
  passwordToggle.addEventListener('click', () => {
    const input = document.getElementById('password');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    passwordToggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    passwordToggle.setAttribute('aria-pressed', String(show));
  });
}
document.querySelectorAll('[data-search-table]').forEach((input) => {
  const table = document.getElementById(input.dataset.searchTable);
  input.addEventListener('input', () => {
    const rows = [...table.querySelectorAll('[data-search-row]')];
    const empty = table.querySelector('.search-empty');
    const query = input.value.trim().toLocaleLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      row.hidden = !row.textContent.toLocaleLowerCase().includes(query);
      if (!row.hidden) visible++;
    });
    empty.hidden = !query || visible > 0 || rows.length === 0;
  });
});
document.querySelectorAll('form[method="post"]').forEach((form) => {
  form.addEventListener('submit', () => {
    const button = form.querySelector('button[type="submit"]');
    if (!button || button.disabled) return;
    button.dataset.busy = 'true';
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
  });
});
window.addEventListener('pageshow', () => {
  document.querySelectorAll('[data-busy]').forEach((button) => {
    button.disabled = false;
    button.removeAttribute('aria-busy');
    delete button.dataset.busy;
  });
});
const workspaceNav = document.querySelector('.workspace-nav');
if (workspaceNav) {
  const updateNavigation = () => {
    const target = window.location.hash || '#attendance';
    workspaceNav.querySelectorAll('a[href^="#"]').forEach((link) => {
      const active = link.getAttribute('href') === target;
      link.classList.toggle('nav-current', active);
      if (active) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  };
  window.addEventListener('hashchange', updateNavigation);
  updateNavigation();
}

const liveDashboard = document.querySelector('[data-dashboard-live]');
if (liveDashboard) {
  const status = liveDashboard.querySelector('[data-live-status]');
  let busy = false, controller;
  const refresh = async () => {
    if (busy || document.hidden) return;
    busy = true;
    controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch(liveDashboard.dataset.dashboardLive, {
        cache: 'no-store', signal: controller.signal,
      });
      if (response.redirected || response.status === 401) {
        clearInterval(interval);
        status.textContent = 'Session expired. Sign in again.';
        return;
      }
      if (!response.ok) throw new Error('Attendance unavailable');
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (document.hidden || controller.signal.aborted) return;
      for (const current of liveDashboard.querySelectorAll('[data-live-part]')) {
        const incoming = page.querySelector(`[data-live-part="${current.dataset.livePart}"]`);
        if (!incoming) throw new Error('Incomplete dashboard response');
        if (current.innerHTML !== incoming.innerHTML) current.replaceChildren(...incoming.childNodes);
      }
      const search = document.getElementById('attendance-search');
      search?.dispatchEvent(new Event('input'));
      const scheduleInput = document.getElementById('start-time');
      const incomingSchedule = page.querySelector('#start-time');
      if (scheduleInput && incomingSchedule?.readOnly) {
        scheduleInput.value = incomingSchedule.value;
        scheduleInput.readOnly = true;
      }
      status.textContent = 'Attendance updates automatically.';
    } catch (error) {
      if (!document.hidden) status.textContent = 'Connection interrupted. Retrying attendance updates…';
    } finally {
      clearTimeout(timeout);
      busy = false;
    }
  };
  const interval = setInterval(refresh, 2000);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) controller?.abort();
    else refresh();
  });
  window.addEventListener('pagehide', () => {
    clearInterval(interval);
    controller?.abort();
  });
}

const cameraPanel = document.querySelector('[data-camera-preview]');
if (cameraPanel) {
  const toggle = cameraPanel.querySelector('[data-camera-toggle]');
  const image = cameraPanel.querySelector('.camera-image');
  const placeholder = cameraPanel.querySelector('.camera-placeholder');
  const status = cameraPanel.querySelector('.camera-status');
  const guide = cameraPanel.querySelector('.camera-guide');
  let running = false, timer, controller, imageUrl, generation = 0;
  const clearImage = () => {
    image.hidden = true;
    image.removeAttribute('src');
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    imageUrl = undefined;
    placeholder.hidden = false;
    if (guide) guide.hidden = true;
  };
  const poll = async () => {
    if (!running || document.hidden) return;
    const currentGeneration = generation;
    const requestController = new AbortController();
    controller = requestController;
    const timeout = setTimeout(() => requestController.abort(), 2500);
    let delay = 1000;
    try {
      const response = await fetch(cameraPanel.dataset.frameUrl, {
        cache: 'no-store', signal: requestController.signal,
      });
      if (currentGeneration !== generation) return;
      if (response.redirected || response.status === 401) {
        stop('Session expired. Sign in again.');
        return;
      }
      if (!response.ok || !response.headers.get('Content-Type')?.startsWith('image/jpeg')) {
        throw new Error('Camera unavailable');
      }
      const blob = await response.blob();
      if (!running || document.hidden || currentGeneration !== generation) return;
      const nextUrl = URL.createObjectURL(blob);
      if (imageUrl) URL.revokeObjectURL(imageUrl);
      imageUrl = nextUrl;
      image.src = nextUrl;
      await image.decode();
      if (!running || document.hidden || currentGeneration !== generation) return;
      image.hidden = false;
      placeholder.hidden = true;
      if (guide) guide.hidden = false;
      status.textContent = 'Live preview';
      delay = 500;
    } catch (error) {
      if (running && !document.hidden && currentGeneration === generation) {
        clearImage();
        placeholder.querySelector('span').textContent = 'Waiting for the scanner';
        status.textContent = 'Check camera power and Wi-Fi';
      }
    } finally {
      clearTimeout(timeout);
      if (running && !document.hidden && currentGeneration === generation) timer = setTimeout(poll, delay);
    }
  };
  function stop(message = 'Stopped') {
    running = false;
    generation++;
    clearTimeout(timer);
    controller?.abort();
    clearImage();
    status.textContent = message;
    placeholder.querySelector('span').textContent = 'Camera preview is off';
    toggle.textContent = 'Start preview';
    toggle.setAttribute('aria-pressed', 'false');
  }
  toggle.addEventListener('click', () => {
    if (running) return stop();
    running = true;
    generation++;
    toggle.textContent = 'Stop preview';
    toggle.setAttribute('aria-pressed', 'true');
    status.textContent = 'Connecting to camera…';
    poll();
  });
  document.addEventListener('visibilitychange', () => {
    if (!running) return;
    if (document.hidden) {
      generation++;
      clearTimeout(timer);
      controller?.abort();
      clearImage();
      status.textContent = 'Paused while this tab is hidden';
    } else poll();
  });
  window.addEventListener('pagehide', () => stop());
}

// Bulk downloads keep individual selection usable without JavaScript.
const qrDownload = document.querySelector('[data-qr-download]');
if (qrDownload) {
  const selectVisible = qrDownload.querySelector('[data-select-visible]');
  qrDownload.querySelectorAll('[data-individual-pdf]').forEach(link => {
    link.addEventListener('click', () => {
      const target = new URL(link.href);
      target.searchParams.set('message', document.getElementById('card-message').value);
      link.href = target.href;
    });
  });
  const boxes = () => [...qrDownload.querySelectorAll('input[name="student_id"]')];
  const visibleBoxes = () => boxes().filter(box => !box.closest('[data-search-row]').hidden);
  const updateSelection = () => {
    const visible = visibleBoxes();
    const selected = visible.filter(box => box.checked).length;
    selectVisible.checked = visible.length > 0 && selected === visible.length;
    selectVisible.indeterminate = selected > 0 && selected < visible.length;
  };
  selectVisible.addEventListener('change', () => {
    visibleBoxes().forEach(box => { box.checked = selectVisible.checked; });
    updateSelection();
  });
  boxes().forEach(box => box.addEventListener('change', updateSelection));
  document.getElementById('student-search').addEventListener('input', updateSelection);
  qrDownload.addEventListener('submit', event => {
    if (event.submitter?.value === 'selected' && !boxes().some(box => box.checked)) {
      event.preventDefault();
      selectVisible.setCustomValidity('Select at least one student to download.');
      selectVisible.reportValidity();
      selectVisible.setCustomValidity('');
    }
  });
}
