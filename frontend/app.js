const API_BASE_URL = "http://localhost:8000"; // change for production deploys

let documentId = null;

const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const uploadButton = document.getElementById("upload-button");

const documentInfo = document.getElementById("document-info");
const docFilename = document.getElementById("doc-filename");
const docChunkCount = document.getElementById("doc-chunk-count");
const docCachedBadge = document.getElementById("doc-cached-badge");

const errorMessage = document.getElementById("error-message");

const chatSection = document.getElementById("chat-section");
const conversation = document.getElementById("conversation");
const chatForm = document.getElementById("chat-form");
const questionInput = document.getElementById("question-input");
const sendButton = document.getElementById("send-button");

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function hideError() {
  errorMessage.hidden = true;
}

function setButtonLoading(button, loading) {
  button.disabled = loading;
  button.querySelector(".btn-label").hidden = loading;
  button.querySelector(".spinner").hidden = !loading;
}

// --- Upload ---

uploadButton.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    handleFile(fileInput.files[0]);
  }
});

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
  });
});

dropZone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    handleFile(file);
  }
});

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showError("Could not process PDF");
    return;
  }

  hideError();
  setButtonLoading(uploadButton, true);

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(`${API_BASE_URL}/upload`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error("upload failed");
    }

    const data = await response.json();
    documentId = data.document_id;

    docFilename.textContent = data.filename;
    docChunkCount.textContent = `${data.chunk_count} chunks`;
    docCachedBadge.hidden = !data.cached;
    documentInfo.hidden = false;

    conversation.innerHTML = "";
    chatSection.hidden = false;
  } catch (err) {
    showError("Could not process PDF");
  } finally {
    setButtonLoading(uploadButton, false);
  }
}

// --- Chat ---

questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionInput.value.trim();
  if (!question || !documentId) {
    return;
  }

  hideError();
  appendMessage("user", question);
  questionInput.value = "";
  setButtonLoading(sendButton, true);

  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id: documentId, question }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "No answer found in document");
    }

    appendMessage("assistant", data.answer, {
      sources: data.sources,
      latencyMs: data.latency_ms,
      costUsd: data.cost_usd,
    });
  } catch (err) {
    showError(err.message || "No answer found in document");
  } finally {
    setButtonLoading(sendButton, false);
  }
});

function appendMessage(role, content, extra = {}) {
  const messageEl = document.createElement("div");
  messageEl.className = `message ${role}`;

  const textEl = document.createElement("div");
  textEl.textContent = content;
  messageEl.appendChild(textEl);

  if (role === "assistant") {
    const metaEl = document.createElement("div");
    metaEl.className = "message-meta";
    metaEl.textContent = `${extra.latencyMs}ms · $${extra.costUsd.toFixed(6)}`;
    messageEl.appendChild(metaEl);

    if (extra.sources && extra.sources.length > 0) {
      const details = document.createElement("details");
      details.className = "sources";
      const summary = document.createElement("summary");
      summary.textContent = "Sources";
      details.appendChild(summary);

      extra.sources.forEach((source) => {
        const pre = document.createElement("pre");
        pre.textContent = source;
        details.appendChild(pre);
      });

      messageEl.appendChild(details);
    }
  }

  conversation.appendChild(messageEl);
  conversation.scrollTop = conversation.scrollHeight;
}
