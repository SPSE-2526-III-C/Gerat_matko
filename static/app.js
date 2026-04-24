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
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
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