// =====================================================
// AUTH ELEMENTS
// =====================================================

const authContainer = document.getElementById("auth-container");
const chatApp = document.getElementById("chat-app");

const loginUsernameInput = document.getElementById("login-username");
const loginPasswordInput = document.getElementById("login-password");
const loginBtn = document.getElementById("login-btn");
const loginError = document.getElementById("login-error");

const registerToggleBtn = document.getElementById("register-toggle-btn");

const registerForm = document.getElementById("register-form");
const registerUsernameInput = document.getElementById("register-username");
const registerPasswordInput = document.getElementById("register-password");
const registerPassword2Input = document.getElementById("register-password2");
const registerBtn = document.getElementById("register-btn");
const registerError = document.getElementById("register-error");

const loginToggleBtn = document.getElementById("login-toggle-btn");

const logoutBtn = document.getElementById("logout-btn");

// =====================================================
// CHAT ELEMENTS
// =====================================================

const chat = document.getElementById("chat");
const form = document.getElementById("composer");
const textarea = document.getElementById("message");
const statusBadge = document.getElementById("status");
const progressBar = document.getElementById("progress-bar");
const progressText = document.getElementById("progress-text");
const timerEl = document.getElementById("timer");

const initBtn = document.getElementById("init-model-btn");

// =====================================================
// STATE
// =====================================================

let timerId = null;
let startTime = null;
let currentAudio = null;

let sessionToken = localStorage.getItem("session_token") || null;
let modelReady = false;
let modelLoading = false;

// =====================================================
// UI HELPERS
// =====================================================

function setChatEnabled(enabled) {
  textarea.disabled = !enabled;
  form.querySelector("button").disabled = !enabled;
}

function setStatus(text) {
  statusBadge.textContent = text;
}

function showAuth() {
  authContainer.style.display = "flex";
  chatApp.style.display = "none";
}

function showApp() {
  authContainer.style.display = "none";
  chatApp.style.display = "flex";
}

// =====================================================
// MODEL STATUS
// =====================================================

async function checkModelStatus() {
  try {
    const res = await fetch("/api/model-status");
    const data = await res.json();

    modelReady = data.ready;
    modelLoading = data.loading;

    updateModelUI();
  } catch (e) {
    console.error("model status error", e);
  }
}

function updateModelUI() {
  if (modelLoading) {
    setStatus("🟡 AI sa načítava...");
    setChatEnabled(false);
    textarea.placeholder = "AI sa inicializuje...";
  }

  if (modelReady) {
    setStatus("🟢 AI pripravená");
    setChatEnabled(true);
    textarea.placeholder = "Napíš správu...";
  }

  if (!modelReady && !modelLoading) {
    setStatus("🔴 AI neinicializovaná");
    setChatEnabled(false);
    textarea.placeholder = "Najprv klikni na Inicializovať AI";
  }
}

// =====================================================
// INIT MODEL
// =====================================================

async function initModel() {
  try {
    setStatus("🟡 Inicializujem AI...");
    setChatEnabled(false);

    initBtn.disabled = true;

    const res = await fetch("/api/init-model", {
      method: "POST"
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || "Init failed");
    }

    modelReady = true;
    modelLoading = false;

    updateModelUI();

  } catch (err) {
    setStatus("🔴 Chyba inicializácie");
    console.error(err);
  } finally {
    initBtn.disabled = false;
  }
}

// =====================================================
// AUTH
// =====================================================

function showLoginForm() {
  registerForm.classList.add("hidden");
}

function showRegisterForm() {
  registerForm.classList.remove("hidden");
}

// TÁTO FUNKCIA TU CHÝBALA A SPÔSOBOVALA PÁD APLIKÁCIE
async function loadChatHistory() {
  // Zatiaľ slúži ako placeholder, aby JavaScript nepadal na ReferenceError.
  // Neskôr sem môžeš dopísať načítanie starých správ z backendu (ak ho máš implementovaný).
  console.log("loadChatHistory: História správ zatiaľ nie je prepojená s backendom.");
}

// LOGIN
async function handleLogin() {
  const username = loginUsernameInput.value.trim();
  const password = loginPasswordInput.value.trim();

  if (!username || !password) {
    loginError.textContent = "Vyplň všetko";
    return;
  }

  const res = await fetch("/api/login", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ username, password })
  });

  const data = await res.json();

  if (!res.ok) {
    loginError.textContent = data.error;
    return;
  }

  sessionToken = data.session_token;
  localStorage.setItem("session_token", sessionToken);

  await loadChatHistory();

  showApp();
  await checkModelStatus();
}

// REGISTER
async function handleRegister() {
  const username = registerUsernameInput.value.trim();
  const password = registerPasswordInput.value.trim();
  const password2 = registerPassword2Input.value.trim();

  if (password !== password2) {
    registerError.textContent = "Heslá sa nezhodujú";
    return;
  }

  const res = await fetch("/api/register", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ username, password })
  });

  const data = await res.json();

  if (!res.ok) {
    registerError.textContent = data.error;
    return;
  }

  registerError.textContent = "OK, teraz sa prihlás";
  showLoginForm();
}

// LOGOUT
async function handleLogout() {
  await fetch("/api/logout", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ session_token: sessionToken })
  });

  sessionToken = null;
  localStorage.removeItem("session_token");

  chat.innerHTML = "";
  showAuth();
}

// =====================================================
// CHAT
// =====================================================

function addBubble(text, type) {
  const div = document.createElement("div");
  div.className = `bubble ${type === "user" ? "user" : "ai"}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function startTimer() {
  startTime = performance.now();
  timerId = setInterval(() => {
    const elapsed = (performance.now() - startTime) / 1000;
    timerEl.textContent = `${elapsed.toFixed(1)} s`;
    progressBar.style.width = `${Math.min(95, elapsed * 10)}%`;
  }, 100);
}

function stopTimer() {
  clearInterval(timerId);
  progressBar.style.width = "100%";
}

// =====================================================
// SEND MESSAGE
// =====================================================

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  if (!modelReady) return;

  const message = textarea.value.trim();
  if (!message) return;

  textarea.value = "";
  setChatEnabled(false);

  addBubble(message, "user");

  setStatus("Generujem...");
  startTimer();

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        session_token: sessionToken,
        message
      })
    });

    const data = await res.json();

    if (!res.ok) throw new Error(data.error);

    addBubble(data.reply, "bot");
    setStatus("Hotovo");

  } catch (err) {
    addBubble("Chyba: " + err.message, "bot");
    setStatus("Chyba");
  } finally {
    stopTimer();
    setChatEnabled(modelReady);
  }
});

// =====================================================
// INIT BUTTON
// =====================================================

initBtn.addEventListener("click", initModel);

// =====================================================
// EVENTS
// =====================================================

loginBtn.addEventListener("click", handleLogin);
registerBtn.addEventListener("click", handleRegister);
logoutBtn.addEventListener("click", handleLogout);

loginToggleBtn.addEventListener("click", showLoginForm);
registerToggleBtn.addEventListener("click", showRegisterForm);

// ENTER LOGIN
loginPasswordInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") handleLogin();
});

// =====================================================
// STARTUP
// =====================================================

(async function start() {
  if (sessionToken) {
    showApp();
    await checkModelStatus();
    await loadChatHistory();
  } else {
    showAuth();
  }
})();