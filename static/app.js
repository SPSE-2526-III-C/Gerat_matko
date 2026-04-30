// Auth elements
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

// Chat elements
const chat = document.getElementById("chat");
const form = document.getElementById("composer");
const textarea = document.getElementById("message");
const statusBadge = document.getElementById("status");
const progressBar = document.getElementById("progress-bar");
const progressText = document.getElementById("progress-text");
const timerEl = document.getElementById("timer");

let timerId = null;
let startTime = null;
let currentAudio = null;
let sessionToken = localStorage.getItem("session_token") || null;

// ============= AUTH FUNCTIONS =============

function showLoginForm() {
  registerForm.style.display = "none";
  loginError.textContent = "";
}

function showRegisterForm() {
  registerForm.style.display = "block";
  loginError.textContent = "";
  registerError.textContent = "";
}

async function handleLogin() {
  const username = loginUsernameInput.value.trim();
  const password = loginPasswordInput.value.trim();

  if (!username || !password) {
    loginError.textContent = "Vyplň používateľa a heslo.";
    return;
  }

  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();

    if (!response.ok) {
      loginError.textContent = data.error || "Chyba pri prihlásení.";
      return;
    }

    // Save session token
    sessionToken = data.session_token;
    localStorage.setItem("session_token", sessionToken);

    // Load chat history
    await loadChatHistory();

    // Show chat app
    authContainer.classList.remove("active");
    chatApp.style.display = "block";
  } catch (err) {
    loginError.textContent = `Chyba: ${err.message}`;
  }
}

async function handleRegister() {
  const username = registerUsernameInput.value.trim();
  const password = registerPasswordInput.value.trim();
  const password2 = registerPassword2Input.value.trim();

  if (!username || !password || !password2) {
    registerError.textContent = "Vyplň všetky polia.";
    return;
  }

  if (password !== password2) {
    registerError.textContent = "Heslá sa nezhodujú.";
    return;
  }

  try {
    const response = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();

    if (!response.ok) {
      registerError.textContent = data.error || "Chyba pri registrácii.";
      return;
    }

    registerError.textContent = ""; // Clear error
    loginUsernameInput.value = username;
    loginPasswordInput.value = password;
    showLoginForm();
    loginError.textContent = "Registrácia úspešná! Prihlás sa.";
  } catch (err) {
    registerError.textContent = `Chyba: ${err.message}`;
  }
}

async function handleLogout() {
  try {
    await fetch("/api/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_token: sessionToken }),
    });
  } catch (err) {
    console.error("Logout error:", err);
  }

  // Clear session
  sessionToken = null;
  localStorage.removeItem("session_token");

  // Reset forms
  loginUsernameInput.value = "";
  loginPasswordInput.value = "";
  registerUsernameInput.value = "";
  registerPasswordInput.value = "";
  registerPassword2Input.value = "";
  loginError.textContent = "";
  registerError.textContent = "";

  // Show auth
  authContainer.classList.add("active");
  chatApp.style.display = "none";
  chat.innerHTML = "";
  showLoginForm();
}

// ============= CHAT FUNCTIONS =============

function addBubble(text, type) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${type}`;
  bubble.textContent = text;
  chat.appendChild(bubble);
  chat.scrollTop = chat.scrollHeight;
}

function setStatus(text, isBusy) {
  statusBadge.textContent = text;
  statusBadge.style.background = isBusy
    ? "rgba(251, 146, 60, 0.18)"
    : "rgba(59, 130, 246, 0.15)";
  statusBadge.style.borderColor = isBusy
    ? "rgba(251, 146, 60, 0.4)"
    : "rgba(59, 130, 246, 0.4)";
}

function startTimer() {
  startTime = performance.now();
  timerId = window.setInterval(() => {
    const elapsed = (performance.now() - startTime) / 1000;
    timerEl.textContent = `${elapsed.toFixed(1)} s`;
    progressBar.style.width = `${Math.min(90, elapsed * 10)}%`;
  }, 100);
}

function stopTimer() {
  if (timerId) {
    window.clearInterval(timerId);
    timerId = null;
  }
  progressBar.style.width = "100%";
}

async function playTTS(text) {
  if (!text) return;
  try {
    const response = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || "TTS chyba.");
    }
    const audioBlob = await response.blob();
    const audioUrl = URL.createObjectURL(audioBlob);

    if (currentAudio) {
      currentAudio.pause();
      URL.revokeObjectURL(currentAudio.src);
    }

    currentAudio = new Audio(audioUrl);
    currentAudio.onended = () => URL.revokeObjectURL(audioUrl);
    await currentAudio.play();
  } catch (err) {
    console.warn("TTS failed", err);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = textarea.value.trim();
  if (!message) return;

  textarea.value = "";
  textarea.disabled = true;
  form.querySelector("button").disabled = true;

  addBubble(message, "user");
  setStatus("Generujem odpoveď…", true);
  progressText.textContent = "Generujem, prosím čakaj…";
  timerEl.textContent = "0.0 s";
  progressBar.style.width = "5%";
  startTimer();

  try {
    if (!sessionToken) {
      throw new Error("Nie si prihlásený. Prosím prihláš sa.");
    }
    
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        session_token: sessionToken,
        message 
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Chyba servera.");
    }
    addBubble(data.reply, "bot");
    if (data.blocked) {
      progressText.textContent = "Správa bola zablokovaná.";
      setStatus("Zablokované", true);
    } else {
      progressText.textContent = `Hotovo za ${data.elapsed.toFixed(1)} s | limit ${data.max_tokens} tok.`;
      setStatus("Pripravený", false);
      await playTTS(data.reply);
    }
  } catch (err) {
    addBubble(`Chyba: ${err.message}`, "bot");
    progressText.textContent = "Niečo sa pokazilo.";
    setStatus("Chyba", true);
  } finally {
    stopTimer();
    textarea.disabled = false;
    form.querySelector("button").disabled = false;
    textarea.focus();
  }
});

// ============= HISTORY FUNCTIONS =============

async function loadChatHistory() {
  if (!sessionToken) {
    console.warn("No session token available");
    return;
  }

  try {
    console.log("Loading chat history with token:", sessionToken);
    const response = await fetch(
      `/api/history?session_token=${encodeURIComponent(sessionToken)}`
    );
    const data = await response.json();

    console.log("History response:", data);

    if (!response.ok) {
      console.warn("Failed to load history:", data.error);
      return;
    }

    // Clear existing chat
    chat.innerHTML = "";

    // Load messages
    if (data.messages && data.messages.length > 0) {
      console.log("Loading", data.messages.length, "messages");
      data.messages.forEach((msg) => {
        addBubble(msg.user_message, "user");
        addBubble(msg.bot_reply, "bot");
      });
    } else {
      console.log("No messages in history");
    }
  } catch (err) {
    console.error("Error loading history:", err);
  }
}

// ============= EVENT LISTENERS =============

registerToggleBtn.addEventListener("click", showRegisterForm);
loginToggleBtn.addEventListener("click", showLoginForm);
loginBtn.addEventListener("click", handleLogin);
registerBtn.addEventListener("click", handleRegister);
logoutBtn.addEventListener("click", handleLogout);

// Login on Enter
loginPasswordInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") handleLogin();
});
registerPassword2Input.addEventListener("keypress", (e) => {
  if (e.key === "Enter") handleRegister();
});

// Check if already logged in
if (sessionToken) {
  authContainer.classList.remove("active");
  chatApp.style.display = "block";
  loadChatHistory();
}