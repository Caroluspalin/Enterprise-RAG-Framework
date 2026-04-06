/**
 * widget.js
 *
 * Embeddable chat widget for the B2B RAG Chatbot.
 * Zero dependencies, vanilla JS, Shadow DOM for CSS isolation.
 *
 * Usage — drop a single script tag on any page:
 *
 *   <script
 *     src="https://your-app.vercel.app/widget.js"
 *     data-api="https://your-backend.onrender.com"
 *     data-key="your-widget-api-key"
 *     data-title="Asiakaspalvelu"
 *     data-accent="#2563eb"
 *     data-bg="#0f172a"
 *     data-position="right"
 *   ></script>
 *
 * Config (data-* attributes):
 *   data-api       — FastAPI backend URL (required)
 *   data-key       — Widget API key for X-Widget-Key header (required)
 *   data-title     — Chat window title (default: "Chat")
 *   data-accent    — Accent color hex (default: "#2563eb")
 *   data-bg        — Chat background color hex (default: "#0f172a")
 *   data-position  — FAB position: "right" or "left" (default: "right")
 */
(function () {
  "use strict";

  // Prevent double-initialisation if the script is included twice.
  if (window.__ragWidgetLoaded) return;
  window.__ragWidgetLoaded = true;

  // ---------------------------------------------------------------------------
  // Config — read from the <script> tag's data-* attributes.
  // ---------------------------------------------------------------------------

  var scriptTag = document.currentScript;
  var API_URL = (scriptTag.getAttribute("data-api") || "").replace(/\/+$/, "");
  var API_KEY = scriptTag.getAttribute("data-key") || "";
  var TITLE = scriptTag.getAttribute("data-title") || "Chat";
  var ACCENT = scriptTag.getAttribute("data-accent") || "#2563eb";
  var BG_COLOR = scriptTag.getAttribute("data-bg") || "#0f172a";
  var POSITION = scriptTag.getAttribute("data-position") || "right";

  if (!API_URL) {
    console.error("[RAG Widget] data-api is required.");
    return;
  }

  // ---------------------------------------------------------------------------
  // Session — persisted across page navigations within the same tab.
  // ---------------------------------------------------------------------------

  var SESSION_KEY = "__rag_widget_session";

  function getSessionId() {
    var id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = _uuid();
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  // Simple UUID v4 generator (no crypto dependency needed for session IDs).
  function _uuid() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  var messages = [];   // { role: "user"|"assistant", content: string }
  var isStreaming = false;
  var isOpen = false;

  // ---------------------------------------------------------------------------
  // Safe text rendering — no innerHTML, no XSS risk.
  //
  // Supports a minimal subset of Markdown-like formatting:
  //   **bold**   →  <strong>
  //   *italic*   →  <em>
  //   `code`     →  <code>
  //   [text](url)→  <a> (only http/https URLs)
  //   newlines   →  <br>
  //   - list     →  bullet list
  // ---------------------------------------------------------------------------

  function renderSafeContent(text, container) {
    // Clear previous content safely.
    while (container.firstChild) container.removeChild(container.firstChild);

    var lines = text.split("\n");
    var listBuffer = [];

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];

      // Bullet list items: lines starting with "- " or "* "
      var bulletMatch = line.match(/^\s*[-*]\s+(.*)/);
      if (bulletMatch) {
        listBuffer.push(bulletMatch[1]);
        // If next line is not a bullet, flush the list.
        var nextLine = lines[i + 1];
        var nextIsBullet = nextLine && /^\s*[-*]\s+/.test(nextLine);
        if (!nextIsBullet) {
          var ul = document.createElement("ul");
          ul.style.cssText = "margin:4px 0;padding-left:20px;";
          for (var j = 0; j < listBuffer.length; j++) {
            var li = document.createElement("li");
            _appendInlineFormatted(listBuffer[j], li);
            ul.appendChild(li);
          }
          container.appendChild(ul);
          listBuffer = [];
        }
        continue;
      }

      // Empty line = paragraph break
      if (line.trim() === "") {
        container.appendChild(document.createElement("br"));
        continue;
      }

      var p = document.createElement("span");
      p.style.display = "block";
      _appendInlineFormatted(line, p);
      container.appendChild(p);
    }
  }

  // Parse inline formatting tokens and append safe DOM nodes.
  function _appendInlineFormatted(text, parent) {
    // Regex matches: **bold**, *italic*, `code`, [text](url)
    var pattern = /(\*\*(.+?)\*\*)|(\*(.+?)\*)|(`(.+?)`)|(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))/g;
    var lastIndex = 0;
    var match;

    while ((match = pattern.exec(text)) !== null) {
      // Append plain text before this match.
      if (match.index > lastIndex) {
        parent.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
      }

      if (match[2]) {
        // **bold**
        var strong = document.createElement("strong");
        strong.textContent = match[2];
        parent.appendChild(strong);
      } else if (match[4]) {
        // *italic*
        var em = document.createElement("em");
        em.textContent = match[4];
        parent.appendChild(em);
      } else if (match[6]) {
        // `code`
        var code = document.createElement("code");
        code.textContent = match[6];
        code.style.cssText =
          "background:rgba(255,255,255,0.1);padding:1px 4px;border-radius:3px;font-size:0.9em;";
        parent.appendChild(code);
      } else if (match[8] && match[9]) {
        // [text](url) — only http/https links allowed.
        var a = document.createElement("a");
        a.textContent = match[8];
        a.href = match[9];
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.style.cssText = "color:" + ACCENT + ";text-decoration:underline;";
        parent.appendChild(a);
      }

      lastIndex = pattern.lastIndex;
    }

    // Remaining plain text after last match.
    if (lastIndex < text.length) {
      parent.appendChild(document.createTextNode(text.slice(lastIndex)));
    }
  }

  // ---------------------------------------------------------------------------
  // Shadow DOM — host element + isolated styles
  // ---------------------------------------------------------------------------

  var host = document.createElement("div");
  host.id = "rag-chat-widget";
  document.body.appendChild(host);

  var shadow = host.attachShadow({ mode: "closed" });

  var style = document.createElement("style");
  style.textContent = `
    /* Reset inside shadow DOM */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :host {
      all: initial;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #e2e8f0;
    }

    /* -- FAB (floating action button) -- */
    .fab {
      position: fixed;
      bottom: 24px;
      ${POSITION === "left" ? "left: 24px;" : "right: 24px;"}
      width: 56px;
      height: 56px;
      border-radius: 50%;
      border: none;
      background: ${ACCENT};
      color: #fff;
      cursor: pointer;
      box-shadow: 0 4px 14px rgba(0,0,0,0.35);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
      z-index: 2147483646;
    }
    .fab:hover { transform: scale(1.08); box-shadow: 0 6px 20px rgba(0,0,0,0.4); }
    .fab:focus-visible { outline: 2px solid ${ACCENT}; outline-offset: 3px; }
    .fab svg { width: 24px; height: 24px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

    /* -- Chat window -- */
    .chat-window {
      position: fixed;
      bottom: 96px;
      ${POSITION === "left" ? "left: 24px;" : "right: 24px;"}
      width: 380px;
      height: 520px;
      background: ${BG_COLOR};
      border-radius: 16px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.4);
      display: none;
      flex-direction: column;
      overflow: hidden;
      z-index: 2147483646;
    }
    .chat-window.open { display: flex; }

    /* Responsive — full-screen on small viewports */
    @media (max-width: 480px) {
      .chat-window {
        top: 0; left: 0; right: 0; bottom: 0;
        width: 100%; height: 100%;
        border-radius: 0;
      }
    }

    /* -- Header -- */
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: ${ACCENT};
      color: #fff;
      flex-shrink: 0;
    }
    .header-title { font-size: 15px; font-weight: 600; }
    .header-close {
      background: none; border: none; color: #fff; cursor: pointer;
      width: 28px; height: 28px; border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      transition: background 0.15s;
    }
    .header-close:hover { background: rgba(255,255,255,0.2); }
    .header-close svg { width: 16px; height: 16px; stroke: currentColor; fill: none; stroke-width: 2; }

    /* -- Messages area -- */
    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .messages::-webkit-scrollbar { width: 4px; }
    .messages::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 4px; }

    /* -- Welcome message -- */
    .welcome {
      text-align: center;
      color: #94a3b8;
      padding: 40px 20px;
      font-size: 13px;
      line-height: 1.6;
    }
    .welcome-icon {
      width: 48px; height: 48px; margin: 0 auto 12px;
      background: ${ACCENT}22;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
    }
    .welcome-icon svg { width: 24px; height: 24px; stroke: ${ACCENT}; fill: none; stroke-width: 1.5; }

    /* -- Message bubbles -- */
    .msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 12px;
      word-wrap: break-word;
      overflow-wrap: break-word;
      font-size: 14px;
      line-height: 1.5;
    }
    .msg-user {
      align-self: flex-end;
      background: ${ACCENT};
      color: #fff;
      border-bottom-right-radius: 4px;
    }
    .msg-assistant {
      align-self: flex-start;
      background: #1e293b;
      color: #e2e8f0;
      border-bottom-left-radius: 4px;
    }

    /* -- Sources -- */
    .sources {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 6px;
    }
    .source-chip {
      font-size: 11px;
      background: rgba(255,255,255,0.08);
      color: #94a3b8;
      padding: 2px 8px;
      border-radius: 10px;
      white-space: nowrap;
    }

    /* -- Typing indicator (three dots) -- */
    .typing {
      align-self: flex-start;
      display: flex;
      gap: 4px;
      padding: 12px 16px;
      background: #1e293b;
      border-radius: 12px;
      border-bottom-left-radius: 4px;
    }
    .typing-dot {
      width: 6px; height: 6px;
      background: #64748b;
      border-radius: 50%;
      animation: typingBounce 1.2s ease-in-out infinite;
    }
    .typing-dot:nth-child(2) { animation-delay: 0.15s; }
    .typing-dot:nth-child(3) { animation-delay: 0.3s; }
    @keyframes typingBounce {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-4px); }
    }

    /* -- Input area -- */
    .input-area {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px;
      border-top: 1px solid rgba(255,255,255,0.08);
      background: ${BG_COLOR};
      flex-shrink: 0;
    }
    .input-field {
      flex: 1;
      padding: 10px 14px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.06);
      color: #e2e8f0;
      font-size: 14px;
      font-family: inherit;
      outline: none;
      resize: none;
      min-height: 40px;
      max-height: 100px;
    }
    .input-field::placeholder { color: #64748b; }
    .input-field:focus { border-color: ${ACCENT}; }
    .send-btn {
      width: 40px; height: 40px;
      border-radius: 10px;
      border: none;
      background: ${ACCENT};
      color: #fff;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
      transition: opacity 0.15s;
    }
    .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .send-btn svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

    /* -- Error banner -- */
    .error-banner {
      padding: 8px 14px;
      background: #7f1d1d;
      color: #fca5a5;
      font-size: 13px;
      text-align: center;
      flex-shrink: 0;
    }
  `;
  shadow.appendChild(style);

  // ---------------------------------------------------------------------------
  // Build DOM structure
  // ---------------------------------------------------------------------------

  // FAB button
  var fab = document.createElement("button");
  fab.className = "fab";
  fab.setAttribute("aria-label", "Avaa chat");
  fab.setAttribute("aria-haspopup", "dialog");
  fab.setAttribute("aria-expanded", "false");
  fab.innerHTML =
    '<svg viewBox="0 0 24 24"><path d="M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>';
  shadow.appendChild(fab);

  // Chat window
  var chatWindow = document.createElement("div");
  chatWindow.className = "chat-window";
  chatWindow.setAttribute("role", "dialog");
  chatWindow.setAttribute("aria-label", TITLE);
  shadow.appendChild(chatWindow);

  // Header
  var header = document.createElement("div");
  header.className = "header";

  var titleSpan = document.createElement("span");
  titleSpan.className = "header-title";
  titleSpan.textContent = TITLE;
  header.appendChild(titleSpan);

  var closeBtn = document.createElement("button");
  closeBtn.className = "header-close";
  closeBtn.setAttribute("aria-label", "Sulje chat");
  closeBtn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" stroke-linecap="round"/></svg>';
  header.appendChild(closeBtn);
  chatWindow.appendChild(header);

  // Messages container
  var messagesDiv = document.createElement("div");
  messagesDiv.className = "messages";
  messagesDiv.setAttribute("role", "log");
  messagesDiv.setAttribute("aria-live", "polite");
  messagesDiv.setAttribute("aria-label", "Keskusteluhistoria");
  chatWindow.appendChild(messagesDiv);

  // Welcome message (shown when no messages)
  function renderWelcome() {
    messagesDiv.innerHTML = "";
    var welcome = document.createElement("div");
    welcome.className = "welcome";
    welcome.innerHTML =
      '<div class="welcome-icon"><svg viewBox="0 0 24 24"><path d="M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg></div>' +
      "<div><strong>" + _escapeHtml(TITLE) + "</strong></div>" +
      "<div>Kysy mitä vain, autan mielelläni!</div>";
    messagesDiv.appendChild(welcome);
  }

  // Error banner (inserted above input when needed, removed on next send)
  var errorBanner = null;

  function showError(msg) {
    clearError();
    errorBanner = document.createElement("div");
    errorBanner.className = "error-banner";
    errorBanner.setAttribute("role", "alert");
    errorBanner.textContent = msg;
    chatWindow.insertBefore(errorBanner, inputArea);
  }

  function clearError() {
    if (errorBanner && errorBanner.parentNode) {
      errorBanner.parentNode.removeChild(errorBanner);
      errorBanner = null;
    }
  }

  // Input area
  var inputArea = document.createElement("div");
  inputArea.className = "input-area";

  var inputField = document.createElement("textarea");
  inputField.className = "input-field";
  inputField.setAttribute("placeholder", "Kirjoita viesti...");
  inputField.setAttribute("aria-label", "Viesti");
  inputField.setAttribute("rows", "1");
  inputArea.appendChild(inputField);

  var sendBtn = document.createElement("button");
  sendBtn.className = "send-btn";
  sendBtn.setAttribute("aria-label", "Lähetä");
  sendBtn.innerHTML =
    '<svg viewBox="0 0 24 24"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>';
  inputArea.appendChild(sendBtn);
  chatWindow.appendChild(inputArea);

  // Show welcome on init.
  renderWelcome();

  // ---------------------------------------------------------------------------
  // UI helpers
  // ---------------------------------------------------------------------------

  function _escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  function scrollToBottom() {
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  // Auto-resize textarea as user types.
  inputField.addEventListener("input", function () {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 100) + "px";
  });

  // ---------------------------------------------------------------------------
  // Render messages
  // ---------------------------------------------------------------------------

  function renderMessages() {
    // Clear the container.
    while (messagesDiv.firstChild) messagesDiv.removeChild(messagesDiv.firstChild);

    if (messages.length === 0) {
      renderWelcome();
      return;
    }

    for (var i = 0; i < messages.length; i++) {
      var msg = messages[i];
      var bubble = document.createElement("div");
      bubble.className = "msg msg-" + msg.role;
      bubble.setAttribute("aria-label", msg.role === "user" ? "Sinä" : "Assistentti");

      if (msg.role === "assistant") {
        renderSafeContent(msg.content || "", bubble);

        // Source citation chips
        if (msg.sources && msg.sources.length > 0) {
          var sourcesDiv = document.createElement("div");
          sourcesDiv.className = "sources";
          for (var s = 0; s < msg.sources.length; s++) {
            var chip = document.createElement("span");
            chip.className = "source-chip";
            chip.textContent = msg.sources[s].filename + " s." + msg.sources[s].page;
            sourcesDiv.appendChild(chip);
          }
          bubble.appendChild(sourcesDiv);
        }
      } else {
        // User messages are plain text — safe to use textContent.
        bubble.textContent = msg.content;
      }

      messagesDiv.appendChild(bubble);
    }

    // Typing indicator while streaming.
    if (isStreaming) {
      var lastMsg = messages[messages.length - 1];
      // Show dots only if the assistant hasn't started producing tokens yet.
      if (lastMsg && lastMsg.role === "assistant" && lastMsg.content === "") {
        var typing = document.createElement("div");
        typing.className = "typing";
        typing.setAttribute("aria-label", "Kirjoittaa...");
        for (var d = 0; d < 3; d++) {
          var dot = document.createElement("div");
          dot.className = "typing-dot";
          typing.appendChild(dot);
        }
        messagesDiv.appendChild(typing);
      }
    }

    scrollToBottom();
  }

  // ---------------------------------------------------------------------------
  // SSE streaming — fetch + ReadableStream
  // ---------------------------------------------------------------------------

  function sendMessage(question) {
    if (isStreaming || !question.trim()) return;
    clearError();

    // Build history from current messages (exclude the question being sent).
    var history = [];
    for (var i = 0; i < messages.length; i++) {
      history.push({ role: messages[i].role, content: messages[i].content });
    }

    // Add user message.
    messages.push({ role: "user", content: question.trim() });

    // Add empty assistant placeholder for streaming.
    var assistantIndex = messages.length;
    messages.push({ role: "assistant", content: "", sources: [] });

    isStreaming = true;
    renderMessages();

    // Reset input.
    inputField.value = "";
    inputField.style.height = "auto";
    sendBtn.disabled = true;

    var sessionId = getSessionId();

    fetch(API_URL + "/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Widget-Key": API_KEY,
      },
      body: JSON.stringify({
        question: question.trim(),
        history: history,
        session_id: sessionId,
        user_id: "widget-" + sessionId.slice(0, 8),
      }),
    })
      .then(function (res) {
        if (!res.ok) {
          if (res.status === 429) throw new Error("Liian monta pyyntöä. Yritä hetken kuluttua.");
          if (res.status === 403) throw new Error("Virheellinen API-avain.");
          throw new Error("Palvelinvirhe (" + res.status + ")");
        }
        return _readSSE(res, assistantIndex);
      })
      .catch(function (err) {
        // Network error or backend down.
        isStreaming = false;
        sendBtn.disabled = false;
        // Remove the empty assistant placeholder on error.
        if (messages[assistantIndex] && messages[assistantIndex].content === "") {
          messages.splice(assistantIndex, 1);
        }
        showError(err.message || "Yhteys palvelimeen epäonnistui.");
        renderMessages();
      });
  }

  function _readSSE(response, assistantIndex) {
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";

    function pump() {
      return reader.read().then(function (result) {
        if (result.done) {
          isStreaming = false;
          sendBtn.disabled = false;
          renderMessages();
          return;
        }

        buffer += decoder.decode(result.value, { stream: true });
        var parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (var i = 0; i < parts.length; i++) {
          var line = parts[i].trim();
          if (!line.startsWith("data: ")) continue;

          try {
            var event = JSON.parse(line.slice(6));
          } catch (e) {
            continue;
          }

          if (event.type === "token" && event.content) {
            messages[assistantIndex].content += event.content;
            renderMessages();
          } else if (event.type === "sources" && event.sources) {
            messages[assistantIndex].sources = event.sources;
          } else if (event.type === "done") {
            isStreaming = false;
            sendBtn.disabled = false;
            renderMessages();
          }
        }

        return pump();
      });
    }

    return pump().catch(function (err) {
      isStreaming = false;
      sendBtn.disabled = false;
      showError("Stream katkennut. Yritä uudelleen.");
      renderMessages();
    });
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  // Toggle chat open/closed.
  fab.addEventListener("click", function () {
    isOpen = !isOpen;
    chatWindow.classList.toggle("open", isOpen);
    fab.setAttribute("aria-expanded", isOpen ? "true" : "false");
    if (isOpen) {
      inputField.focus();
      scrollToBottom();
    }
  });

  closeBtn.addEventListener("click", function () {
    isOpen = false;
    chatWindow.classList.remove("open");
    fab.setAttribute("aria-expanded", "false");
  });

  // Send on button click.
  sendBtn.addEventListener("click", function () {
    sendMessage(inputField.value);
  });

  // Send on Enter (Shift+Enter for newline).
  inputField.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(inputField.value);
    }
  });

  // Close on Escape.
  shadow.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && isOpen) {
      isOpen = false;
      chatWindow.classList.remove("open");
      fab.setAttribute("aria-expanded", "false");
      fab.focus();
    }
  });
})();
