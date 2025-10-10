// frontend/auth.js
(() => {
  const REQUIRE_LOGIN = true;

  const overlayHTML = `
  <div id="authOverlay" aria-hidden="true">
    <div class="auth-shell" role="dialog" aria-modal="true" aria-labelledby="authTitle">
      <aside class="auth-hero">
        <div class="auth-brand">
          <div class="logo"></div>
          <h3>AI Notes</h3>
        </div>
        <h2 id="authTitle">Welcome back</h2>
        <p>Sign in to turn your notes into clean concepts, mindmaps, and flowcharts.</p>
        <ul class="auth-points">
          <li><span class="auth-dot"></span> High‑quality OCR with smart cleanup</li>
          <li><span class="auth-dot"></span> Topic extraction driven by Gemini</li>
          <li><span class="auth-dot"></span> Mindmap & Flowchart generation</li>
        </ul>
      </aside>

      <section class="auth-form">
        <div class="auth-tabs" role="tablist">
          <button class="auth-tab active" data-tab="login" role="tab" aria-selected="true">Login</button>
          <button class="auth-tab" data-tab="signup" role="tab" aria-selected="false">Sign up</button>
        </div>

        <div id="authError" class="alert" role="alert"></div>
        <div id="authSuccess" class="alert" role="status"></div>

        <form id="authLoginForm" class="active" autocomplete="on" novalidate>
          <div class="fg floating">
            <input id="loginIdentifier" type="text" name="identifier" placeholder=" " required />
            <label for="loginIdentifier">Email or Username</label>
          </div>
          <div class="fg floating">
            <input id="loginPassword" type="password" name="password" placeholder=" " required />
            <label for="loginPassword">Password</label>
            <button type="button" class="showpass" data-target="#loginPassword">Show</button>
          </div>
          <div class="row-inline">
            <label><input type="checkbox" id="loginRemember" checked /> Remember me</label>
            <button class="auth-btn" id="loginBtn" type="submit" disabled>Login</button>
          </div>
        </form>

        <form id="authSignupForm" autocomplete="on" novalidate>
          <div class="fg floating">
            <input id="signupEmail" type="email" name="email" placeholder=" " required />
            <label for="signupEmail">Email</label>
          </div>
          <div class="fg floating">
            <input id="signupUsername" type="text" name="username" placeholder=" " minlength="3" required />
            <label for="signupUsername">Username</label>
          </div>
          <div class="fg floating">
            <input id="signupPassword" type="password" name="password" placeholder=" " minlength="6" required />
            <label for="signupPassword">Password (min 6)</label>
            <button type="button" class="showpass" data-target="#signupPassword">Show</button>
            <div class="pw-meter" aria-hidden="true"><span id="pwBar"></span></div>
          </div>
          <div class="row-inline">
            <span></span>
            <button class="auth-btn" id="signupBtn" type="submit" disabled>Create Account</button>
          </div>
        </form>
      </section>
    </div>
  </div>

  <div id="userChip">
    <span id="userChipName" class="chip"></span>
    <button id="logoutBtn" class="logout-btn" style="display:none;">Logout</button>
  </div>`;

  // Mount
  const mount = document.createElement('div');
  mount.innerHTML = overlayHTML;
  document.body.appendChild(mount);

  const $ = (sel) => document.querySelector(sel);
  const authOverlay = $('#authOverlay');
  const authError = $('#authError');
  const authSuccess = $('#authSuccess');
  const loginForm = $('#authLoginForm');
  const signupForm = $('#authSignupForm');
  const loginBtn = $('#loginBtn');
  const signupBtn = $('#signupBtn');
  const userChip = $('#userChipName');
  const logoutBtn = $('#logoutBtn');

  // Block ESC; trap focus
  document.addEventListener('keydown', (e) => {
    if (!isVisible(authOverlay)) return;
    if (e.key === 'Escape') e.preventDefault();
    if (e.key === 'Tab') trapFocus(e);
  }, true);

  // Ignore background clicks (no close)
  authOverlay.addEventListener('click', (e) => {
    if (e.target === authOverlay) e.preventDefault();
  });

  // Event delegation for tabs + show password
  authOverlay.addEventListener('click', (e) => {
    const tab = e.target.closest('.auth-tab');
    if (tab) {
      document.querySelectorAll('.auth-tab').forEach(b => {
        const active = b === tab;
        b.classList.toggle('active', active);
        b.setAttribute('aria-selected', String(active));
      });
      const name = tab.dataset.tab;
      loginForm.classList.toggle('active', name === 'login');
      signupForm.classList.toggle('active', name === 'signup');
      clearAlerts();
      focusFirstField();
      validateLogin();
      validateSignup();
      return;
    }
    const sp = e.target.closest('.showpass');
    if (sp) {
      const input = document.querySelector(sp.getAttribute('data-target'));
      if (input) {
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        sp.textContent = show ? 'Hide' : 'Show';
        input.focus();
      }
    }
  });

  function isVisible(el) { return el && window.getComputedStyle(el).display !== 'none'; }
  function showOverlay() {
    clearAlerts();
    authOverlay.style.display = 'flex';
    document.body.classList.add('auth-locked');
    setTimeout(() => focusFirstField(), 0);
  }
  function hideOverlay() {
    authOverlay.style.display = 'none';
    document.body.classList.remove('auth-locked');
  }
  function focusFirstField() {
    const el = loginForm.classList.contains('active') ? $('#loginIdentifier') : $('#signupEmail');
    if (el) el.focus();
  }
  function clearAlerts() {
    authError.textContent = ''; authError.className = 'alert';
    authSuccess.textContent = ''; authSuccess.className = 'alert';
  }

  // Validation
  function validateLogin() {
    const idOk = ($('#loginIdentifier').value.trim().length >= 3);
    const pwOk = ($('#loginPassword').value.length >= 1);
    loginBtn.disabled = !(idOk && pwOk);
  }
  function strength(pw) {
    let s=0; if(pw.length>=6)s++; if(/[A-Z]/.test(pw))s++; if(/[a-z]/.test(pw))s++; if(/\d/.test(pw))s++; if(/[^A-Za-z0-9]/.test(pw))s++;
    return Math.min(s,5);
  }
  function validateSignup() {
    const email = $('#signupEmail').value.trim();
    const user = $('#signupUsername').value.trim();
    const pw = $('#signupPassword').value;
    const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    const userOk = user.length >= 3;
    const pwScore = strength(pw);
    const bar = $('#pwBar'); if (bar) bar.style.width = `${(pwScore/5)*100}%`;
    signupBtn.disabled = !(emailOk && userOk && pwScore >= 3);
  }
  document.addEventListener('input', (e) => {
    if (e.target.matches('#loginIdentifier, #loginPassword')) validateLogin();
    if (e.target.matches('#signupEmail, #signupUsername, #signupPassword')) validateSignup();
  });

  // Spinner anim
  const style = document.createElement('style');
  style.innerHTML = `@keyframes spin{to{transform:rotate(360deg)}}`;
  document.head.appendChild(style);
  function setBusy(btn, busy, text) {
    if (!btn) return;
    if (busy) {
      btn.dataset.label = btn.textContent;
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner" style="display:inline-block;width:16px;height:16px;border:2px solid #fff;border-right-color:transparent;border-radius:50%;margin-right:8px;vertical-align:-2px;animation:spin .7s linear infinite"></span>${text||'Please wait'}`;
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.label || 'Submit';
    }
  }

  async function fetchJSON(url, opts = {}) {
    const res = await fetch(url, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(opts.headers||{}) }, ...opts });
    let data=null; try { data = await res.json(); } catch {}
    if (!res.ok) throw new Error((data && (data.error||data.message)) || `HTTP ${res.status}`);
    return data;
  }
  async function authMe() {
    const r = await fetch('/auth/me', { credentials: 'same-origin' });
    let data=null; try { data = await r.json(); } catch {}
    return data && data.ok ? data.user : null;
  }

  // Recognize form/button and enable after login (even if DOM changes later)
  let loggedIn = false;
  function findUploadForm() {
    return document.querySelector('#uploadForm') ||
           document.querySelector('#ocrForm') ||
           document.querySelector('form[action="/api/process"]') ||
           document.querySelector('form');
  }
  function findProcessBtn() {
    return document.querySelector('#processBtn') ||
           findUploadForm()?.querySelector('button[type="submit"], input[type="submit"]');
  }
  function enableControlsIfPresent() {
    const btn = findProcessBtn();
    if (btn) btn.disabled = !loggedIn;
  }
  function observeControls() {
    const obs = new MutationObserver(() => enableControlsIfPresent());
    obs.observe(document.body, { childList: true, subtree: true });
    enableControlsIfPresent();
    setTimeout(() => obs.disconnect(), 8000);
  }

  function setLoggedIn(user) {
    loggedIn = !!user;
    const chip = document.getElementById('userChipName');
    if (user) {
      chip.textContent = `Signed in: ${user.username}`;
      chip.classList.add('show');
      logoutBtn.style.display = 'inline-flex';
      enableControlsIfPresent();
      hideOverlay();
    } else {
      chip.textContent = '';
      chip.classList.remove('show');
      logoutBtn.style.display = 'none';
      enableControlsIfPresent();
    }
  }

  // Submits
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (loginBtn.disabled) return;
    clearAlerts();
    const identifier = document.getElementById('loginIdentifier').value.trim();
    const password = document.getElementById('loginPassword').value;
    const remember = document.getElementById('loginRemember').checked;
    try {
      setBusy(loginBtn, true, 'Signing in');
      const data = await fetchJSON('/auth/login', { method: 'POST', body: JSON.stringify({ identifier, password, remember }) });
      setLoggedIn(data.user);
      authSuccess.textContent = 'Welcome back!'; authSuccess.className = 'alert ok';
    } catch (err) {
      authError.textContent = err.message || 'Login failed'; authError.className = 'alert error';
      setBusy(loginBtn, false);
    }
  });

  signupForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (signupBtn.disabled) return;
    clearAlerts();
    const email = document.getElementById('signupEmail').value.trim();
    const username = document.getElementById('signupUsername').value.trim();
    const password = document.getElementById('signupPassword').value;
    try {
      setBusy(signupBtn, true, 'Creating');
      const data = await fetchJSON('/auth/register', { method: 'POST', body: JSON.stringify({ email, username, password }) });
      setLoggedIn(data.user);
      authSuccess.textContent = 'Account created. You are now signed in.'; authSuccess.className = 'alert ok';
    } catch (err) {
      authError.textContent = err.message || 'Registration failed'; authError.className = 'alert error';
      setBusy(signupBtn, false);
    }
  });

  // Logout
  logoutBtn.addEventListener('click', async () => {
    try { await fetchJSON('/auth/logout', { method: 'POST' }); } catch {}
    setLoggedIn(null);
    if (REQUIRE_LOGIN) showOverlay();
  });

  // Gate form submission (server enforces too)
  const maybeForm = findUploadForm();
  if (maybeForm) {
    maybeForm.addEventListener('submit', async (e) => {
      if (!REQUIRE_LOGIN) return;
      const u = await authMe();
      if (!u) {
        e.preventDefault();
        setLoggedIn(null);
        showOverlay();
      }
    }, true);
  }

  // Focus trap
  function trapFocus(e) {
    const focusables = authOverlay.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    const arr = Array.from(focusables).filter(el => el.offsetParent !== null);
    if (!arr.length) return;
    const first = arr[0], last = arr[arr.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && active === first) { last.focus(); e.preventDefault(); }
    else if (!e.shiftKey && active === last) { first.focus(); e.preventDefault(); }
  }

  // Init
  document.addEventListener('DOMContentLoaded', async () => {
    observeControls();
    const u = await authMe();
    setLoggedIn(u);
    if (!u && REQUIRE_LOGIN) showOverlay();
    validateLogin();
    validateSignup();
  });
})();