(() => {
  const app = document.getElementById("app");
  if (!app) return;

  const csrfToken = document.querySelector(".hidden-csrf input[name=csrfmiddlewaretoken]")?.value;
  const pageId = app.dataset.page;
  const saveUrl = app.dataset.updateUrl;
  const titleInput = document.getElementById("page-title");
  const pageIcon = document.getElementById("page-icon");
  const blockHost = document.getElementById("blocks");
  const saveState = document.getElementById("save-state");
  const undoButton = document.getElementById("undo");
  const redoButton = document.getElementById("redo");
  const recoveryBanner = document.getElementById("recovery-banner");
  const editedLabel = document.getElementById("edited-label");
  const draftKey = "forma-page-draft:" + pageId;

  const blockLabels = {
    paragraph: "Type something…",
    heading_1: "Heading 1",
    heading_2: "Heading 2",
    heading_3: "Heading 3",
    bulleted_list: "List item",
    numbered_list: "List item",
    quote: "Quote",
    callout: "Write a callout…",
    code: "Write code…",
    toggle: "Toggle",
  };

  let content = JSON.parse(document.getElementById("initial-content").textContent || "[]");
  let saveTimer = null;
  let historyTimer = null;
  let draftTimer = null;
  let pending = false;
  let saving = false;
  let history = [];
  let historyIndex = 0;

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function readBlocks() {
    return Array.from(blockHost.children).map((node) => {
      const isTodo = node.matches(".todo-row");
      const element = isTodo ? node.querySelector(".block-text") : node;
      const type = element.dataset.type || "paragraph";

      if (["image", "file", "page_link", "link"].includes(type)) {
        return {
          type,
          text: element.dataset.text || element.innerText,
          url: element.dataset.url || "",
        };
      }

      if (type === "table") {
        return { type, text: "", rows: JSON.parse(element.dataset.rows || "[]") };
      }

      if (type === "divider") return { type, text: "" };

      const block = { type, text: element.innerText };
      if (type === "to_do") block.checked = node.querySelector("input").checked;
      return block;
    });
  }

  function currentSnapshot() {
    return {
      title: titleInput.value,
      icon: pageIcon.textContent.trim(),
      content: readBlocks(),
    };
  }

  function sameSnapshot(first, second) {
    return JSON.stringify(first) === JSON.stringify(second);
  }

  function setSaveState(message, className) {
    saveState.textContent = message;
    saveState.className = "save-state" + (className ? " " + className : "");
  }

  function updateHistoryButtons() {
    undoButton.disabled = historyIndex <= 0;
    redoButton.disabled = historyIndex >= history.length - 1;
  }

  function recordHistoryNow() {
    const snapshot = currentSnapshot();
    if (history.length && sameSnapshot(snapshot, history[historyIndex])) return;

    history = history.slice(0, historyIndex + 1);
    history.push(clone(snapshot));
    historyIndex = history.length - 1;

    if (history.length > 80) {
      history.shift();
      historyIndex -= 1;
    }

    updateHistoryButtons();
  }

  function scheduleHistoryEntry() {
    window.clearTimeout(historyTimer);
    historyTimer = window.setTimeout(recordHistoryNow, 300);
  }

  function writeLocalDraft() {
    try {
      const draft = {
        version: 1,
        data: currentSnapshot(),
        savedAt: Date.now(),
        serverUpdatedAt: app.dataset.pageUpdated || "",
      };
      window.localStorage.setItem(draftKey, JSON.stringify(draft));
      return true;
    } catch (error) {
      return false;
    }
  }

  function removeDraftIfSaved(snapshot) {
    try {
      const stored = window.localStorage.getItem(draftKey);
      if (!stored) return;
      const draft = JSON.parse(stored);
      if (sameSnapshot(draft.data, snapshot)) window.localStorage.removeItem(draftKey);
    } catch (error) {
      // An unreadable draft should not prevent the page from saving.
      try {
        window.localStorage.removeItem(draftKey);
      } catch (storageError) {
        // Local storage may be disabled by the browser.
      }
    }
  }

  function queueSave(options = {}) {
    pending = true;
    setSaveState("Unsaved changes", "is-dirty");

    if (options.captureHistory !== false) {
      scheduleHistoryEntry();

      // Keep Undo clickable while the debounced history entry is being recorded.
      const snapshot = currentSnapshot();
      if (history[historyIndex] && !sameSnapshot(snapshot, history[historyIndex])) {
        undoButton.disabled = false;
        redoButton.disabled = true;
      }
    }
    window.clearTimeout(draftTimer);
    draftTimer = window.setTimeout(() => {
      if (!writeLocalDraft()) setSaveState("Unsaved · local recovery unavailable", "is-error");
    }, 100);

    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(savePage, 700);
  }

  async function savePage() {
    window.clearTimeout(saveTimer);
    if (saving || !pending) return;

    window.clearTimeout(historyTimer);
    recordHistoryNow();
    saving = true;
    pending = false;
    const snapshot = currentSnapshot();
    writeLocalDraft();
    setSaveState("Saving…", "is-saving");

    try {
      const response = await fetch(saveUrl, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(snapshot),
      });
      if (!response.ok) throw new Error("The server could not save this page.");

      const result = await response.json();
      app.dataset.pageUpdated = result.updated_at || app.dataset.pageUpdated;
      saving = false;
      removeDraftIfSaved(snapshot);
      document.getElementById("crumb-title").textContent = snapshot.title || "Untitled";
      document.title = (snapshot.title || "Untitled") + " · Forma";
      editedLabel.textContent = "Edited just now";

      if (pending) {
        writeLocalDraft();
        setSaveState("Saving latest changes…", "is-saving");
        saveTimer = window.setTimeout(savePage, 0);
      } else {
        setSaveState("Saved just now", "is-saved");
      }
    } catch (error) {
      saving = false;
      pending = true;
      writeLocalDraft();
      setSaveState("Save failed · draft kept on this device", "is-error");
      saveTimer = window.setTimeout(savePage, 1800);
    }
  }

  async function flushSave() {
    window.clearTimeout(historyTimer);
    recordHistoryNow();

    for (let attempt = 0; attempt < 5; attempt += 1) {
      if (!pending && !saving) return true;
      if (saving) {
        await new Promise((resolve) => window.setTimeout(resolve, 40));
      } else {
        window.clearTimeout(saveTimer);
        await savePage();
      }
    }

    return !pending && !saving;
  }

  function makeBlock(item = { type: "paragraph", text: "" }, focus = false) {
    const type = item.type || "paragraph";

    if (["image", "file", "page_link", "link"].includes(type)) {
      const element = document.createElement("div");
      element.className = "block imported-" + type;
      element.dataset.type = type;
      element.dataset.url = item.url || "";
      element.dataset.text = item.text || "";
      element.contentEditable = "false";

      if (type === "image") {
        const image = document.createElement("img");
        image.src = item.url || "";
        image.alt = item.text || "Imported image";
        image.loading = "lazy";
        element.append(image);
      } else {
        const link = document.createElement("a");
        link.href = item.url || "#";
        link.textContent = item.text || "Open attachment";
        if (type === "page_link") {
          const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
          icon.className = "page-link-icon";
          icon.setAttribute("aria-hidden", "true");
          icon.setAttribute("viewBox", "0 0 20 20");
          icon.setAttribute("fill", "none");
          icon.setAttribute("stroke", "currentColor");
          icon.setAttribute("stroke-width", "1.5");
          icon.setAttribute("stroke-linecap", "round");
          icon.setAttribute("stroke-linejoin", "round");
          [
            "M5.5 2.5h6L16 7v10.5a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-14a1 1 0 0 1 1-1Z",
            "M11.5 2.5V7H16",
            "M7.25 11h6",
            "M7.25 14.25h6",
          ].forEach((pathData) => {
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute("d", pathData);
            icon.append(path);
          });
          link.prepend(icon);
          link.className = "page-link-anchor";
        }
        if (type === "link") {
          link.target = "_blank";
          link.rel = "noopener noreferrer";
        }
        element.append(link);
      }

      blockHost.append(element);
      return element;
    }

    if (type === "table") {
      const element = document.createElement("div");
      element.className = "block table-block";
      element.dataset.type = type;
      element.dataset.rows = JSON.stringify(item.rows || []);
      element.contentEditable = "false";

      const table = document.createElement("table");
      (item.rows || []).slice(0, 2000).forEach((row, rowIndex) => {
        const tableRow = document.createElement("tr");
        row.slice(0, 100).forEach((cell) => {
          const cellElement = document.createElement(rowIndex === 0 ? "th" : "td");
          cellElement.textContent = cell;
          tableRow.append(cellElement);
        });
        table.append(tableRow);
      });

      element.append(table);
      blockHost.append(element);
      return element;
    }

    if (type === "divider") {
      const element = document.createElement("div");
      element.className = "block divider";
      element.dataset.type = type;
      element.contentEditable = "false";
      element.innerHTML = "<hr>";
      blockHost.append(element);
      return element;
    }

    if (type === "to_do") {
      const row = document.createElement("div");
      row.className = "todo-row" + (item.checked ? " done" : "");

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(item.checked);

      const element = document.createElement("div");
      element.className = "block-text block";
      element.contentEditable = "true";
      element.dataset.type = type;
      element.dataset.placeholder = "To-do";
      element.textContent = item.text || "";

      checkbox.addEventListener("change", () => {
        row.classList.toggle("done", checkbox.checked);
        queueSave();
      });

      row.append(checkbox, element);
      blockHost.append(row);
      bindEditableBlock(element);
      if (focus) element.focus();
      return element;
    }

    const element = document.createElement("div");
    element.className = "block " + type;
    element.contentEditable = "true";
    element.dataset.type = type;
    element.dataset.placeholder = blockLabels[type] || "Type something…";
    element.textContent = item.text || "";
    blockHost.append(element);
    bindEditableBlock(element);
    if (focus) element.focus();
    return element;
  }

  function renderBlocks(blocks) {
    blockHost.replaceChildren();
    blocks.forEach((block) => makeBlock(block));
    if (!blocks.length) makeBlock({}, true);
  }

  function applySnapshot(snapshot) {
    titleInput.value = snapshot.title;
    pageIcon.textContent = snapshot.icon;
    content = clone(snapshot.content);
    renderBlocks(content);
    document.getElementById("crumb-title").textContent = snapshot.title || "Untitled";
    queueSave({ captureHistory: false });
    blockHost.querySelector("[contenteditable=true]")?.focus();
    updateHistoryButtons();
  }

  function undo() {
    window.clearTimeout(historyTimer);
    recordHistoryNow();
    if (historyIndex <= 0) return;
    historyIndex -= 1;
    applySnapshot(clone(history[historyIndex]));
  }

  function redo() {
    window.clearTimeout(historyTimer);
    recordHistoryNow();
    if (historyIndex >= history.length - 1) return;
    historyIndex += 1;
    applySnapshot(clone(history[historyIndex]));
  }

  function showSlashMenu(element) {
    const choices = [
      ["Text", "paragraph"],
      ["Heading 1", "heading_1"],
      ["Heading 2", "heading_2"],
      ["To-do", "to_do"],
      ["Bulleted list", "bulleted_list"],
      ["Quote", "quote"],
      ["Callout", "callout"],
      ["Code", "code"],
      ["Nested page", "child_page"],
    ];

    document.querySelector(".slash-menu")?.remove();
    const menu = document.createElement("div");
    menu.className = "slash-menu";
    Object.assign(menu.style, {
      position: "fixed",
      zIndex: 8,
      background: "white",
      border: "1px solid #e5e6e0",
      borderRadius: "8px",
      padding: "6px",
      boxShadow: "0 8px 25px #0002",
    });

    choices.forEach(([label, type]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      Object.assign(button.style, {
        display: "block",
        background: "white",
        border: 0,
        padding: "7px 30px 7px 10px",
        textAlign: "left",
        width: "100%",
        fontSize: "12px",
        borderRadius: "4px",
      });
      button.addEventListener("mouseenter", () => { button.style.background = "#f3f4f0"; });
      button.addEventListener("mouseleave", () => { button.style.background = "white"; });
      button.addEventListener("click", async () => {
        menu.remove();
        if (type === "child_page") {
          const row = element.closest(".todo-row") || element;
          const insertAt = Array.from(blockHost.children).indexOf(row);
          element.textContent = "";
          queueSave();
          const saved = await flushSave();
          if (!saved) {
            flash("Save the current edits before creating a nested page");
            return;
          }
          const result = await createPage(pageId, insertAt, false);
          if (result) {
            row.remove();
            const pageBlock = makeBlock({
              type: "page_link",
              text: "Untitled",
              url: result.url,
            });
            blockHost.insertBefore(pageBlock, blockHost.children[insertAt] || null);
            queueSave();
          }
          return;
        }

        element.dataset.type = type;
        element.className = "block " + type;
        element.textContent = "";
        element.dataset.placeholder = blockLabels[type] || "Type something…";
        element.focus();
        queueSave();
      });
      menu.append(button);
    });

    document.body.append(menu);
    const bounds = element.getBoundingClientRect();
    menu.style.left = bounds.left + "px";
    menu.style.top = bounds.bottom + 3 + "px";

    const closeMenu = (event) => {
      if (!menu.contains(event.target)) {
        menu.remove();
        document.removeEventListener("mousedown", closeMenu);
      }
    };
    window.setTimeout(() => document.addEventListener("mousedown", closeMenu), 0);
  }

  function bindEditableBlock(element) {
    element.addEventListener("input", () => queueSave());
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (element.dataset.type.startsWith("heading_")) {
          element.dataset.type = "paragraph";
          element.className = "block paragraph";
        }
        makeBlock({}, true).scrollIntoView({ block: "nearest" });
        queueSave();
      }

      if (event.key === "Backspace" && !element.textContent && blockHost.children.length > 1) {
        event.preventDefault();
        const row = element.closest(".todo-row") || element;
        const previousRow = row.previousElementSibling;
        row.remove();
        const focusTarget = previousRow?.matches(".todo-row")
          ? previousRow.querySelector(".block-text")
          : previousRow;
        focusTarget?.focus();
        queueSave();
      }

      if (event.key === "/" && !element.textContent) {
        window.setTimeout(() => showSlashMenu(element), 0);
      }
    });
  }

  async function createPage(parentId = null, insertAt = null, navigate = true) {
    const body = parentId ? { parent: parentId } : {};
    if (parentId && Number.isInteger(insertAt)) body.insert_at = insertAt;
    const response = await fetch(app.dataset.createUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(body),
    });

    if (response.ok) {
      const result = await response.json();
      if (navigate) window.location.href = result.url;
      return result;
    }

    flash("Could not create the page");
    return null;
  }

  function recoverLocalDraft() {
    let draft;
    try {
      draft = JSON.parse(window.localStorage.getItem(draftKey) || "null");
    } catch (error) {
      try {
        window.localStorage.removeItem(draftKey);
      } catch (storageError) {
        // Local storage may be unavailable in a restricted browser context.
      }
      return;
    }

    const serverSnapshot = currentSnapshot();
    const validDraft = draft
      && draft.version === 1
      && draft.data
      && typeof draft.data.title === "string"
      && typeof draft.data.icon === "string"
      && Array.isArray(draft.data.content);
    if (!validDraft || sameSnapshot(draft.data, serverSnapshot)) {
      window.localStorage.removeItem(draftKey);
      return;
    }

    recoveryBanner.hidden = false;
    document.getElementById("restore-draft").addEventListener("click", () => {
      recoveryBanner.hidden = true;
      applySnapshot(draft.data);
    });
    document.getElementById("discard-draft").addEventListener("click", () => {
      try {
        window.localStorage.removeItem(draftKey);
      } catch (error) {
        // Dismissing the banner should still work if storage is unavailable.
      }
      recoveryBanner.hidden = true;
      setSaveState("Saved", "is-saved");
    });
  }

  function flash(message) {
    let element = document.querySelector(".flash");
    if (!element) {
      element = document.createElement("div");
      element.className = "flash";
      document.body.append(element);
    }
    element.textContent = message;
    window.clearTimeout(element.timer);
    element.timer = window.setTimeout(() => element.remove(), 2600);
  }

  function showShareDialog(enabled, url = "") {
    const enableButton = document.getElementById("enable-share");
    const disableButton = document.getElementById("disable-share");
    const linkWrap = document.getElementById("share-link-wrap");
    const shareLink = document.getElementById("share-link");
    const status = document.getElementById("share-status");

    app.dataset.shareEnabled = enabled ? "true" : "false";
    enableButton.hidden = enabled;
    disableButton.hidden = !enabled;
    linkWrap.hidden = !enabled;
    if (url) shareLink.value = url;
    status.textContent = enabled
      ? "Anyone with this link can view this page."
      : "Create a public link to let anyone view this page.";
  }

  function handleShortcuts(event) {
    const key = event.key.toLowerCase();
    const modKey = event.ctrlKey || event.metaKey;

    if (modKey && key === "k") {
      event.preventDefault();
      searchDialog.showModal();
      searchInput.focus();
      return;
    }

    const editorHasFocus = event.target === titleInput || blockHost.contains(event.target);
    if (!modKey || !editorHasFocus) return;

    if (key === "z") {
      event.preventDefault();
      if (event.shiftKey) redo();
      else undo();
    } else if (key === "y") {
      event.preventDefault();
      redo();
    }
  }

  // Render the server copy before checking whether a recoverable local draft exists.
  renderBlocks(content);
  history = [clone(currentSnapshot())];
  historyIndex = 0;
  updateHistoryButtons();
  recoverLocalDraft();

  titleInput.addEventListener("input", () => queueSave());
  document.getElementById("add-block").addEventListener("click", () => makeBlock({}, true));
  undoButton.addEventListener("click", undo);
  redoButton.addEventListener("click", redo);
  document.addEventListener("keydown", handleShortcuts);

  const iconChoices = ["📄", "📝", "💡", "📚", "🎯", "🌱", "🚀", "✨", "📌", "🧠"];
  function cyclePageIcon() {
    const currentIndex = iconChoices.indexOf(pageIcon.textContent.trim());
    pageIcon.textContent = iconChoices[(currentIndex + 1) % iconChoices.length];
    queueSave();
  }
  pageIcon.addEventListener("click", cyclePageIcon);
  pageIcon.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      cyclePageIcon();
    }
  });

  const favoriteButton = document.getElementById("favorite");
  if (app.dataset.favorite === "true") {
    favoriteButton.textContent = "★";
    favoriteButton.style.color = "#bd9352";
  }
  favoriteButton.addEventListener("click", async (event) => {
    const response = await fetch(app.dataset.favoriteUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken },
    });
    if (!response.ok) return;

    const result = await response.json();
    event.currentTarget.textContent = result.favorite ? "★" : "☆";
    event.currentTarget.style.color = result.favorite ? "#bd9352" : "";
  });

  const shareDialog = document.getElementById("share-dialog");
  const shareLink = document.getElementById("share-link");
  const shareStatus = document.getElementById("share-status");
  document.querySelector(".share-btn").addEventListener("click", () => {
    showShareDialog(app.dataset.shareEnabled === "true");
    shareDialog.showModal();
  });

  document.getElementById("enable-share").addEventListener("click", async () => {
    try {
      const response = await fetch(app.dataset.shareUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
      });
      if (!response.ok) throw new Error("Could not create a share link.");
      const result = await response.json();
      showShareDialog(true, result.url);
    } catch (error) {
      shareStatus.textContent = "Could not create the link. Please try again.";
    }
  });

  document.getElementById("copy-share").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(shareLink.value);
      flash("Share link copied to clipboard");
    } catch (error) {
      shareLink.select();
      document.execCommand("copy");
      flash("Share link copied to clipboard");
    }
  });

  document.getElementById("disable-share").addEventListener("click", async () => {
    if (!window.confirm("Turn off the public link? Anyone using it will lose access.")) return;
    try {
      const response = await fetch(app.dataset.shareUrl, {
        method: "DELETE",
        headers: { "X-CSRFToken": csrfToken },
      });
      if (!response.ok) throw new Error("Could not disable the share link.");
      showShareDialog(false);
      shareLink.value = "";
    } catch (error) {
      shareStatus.textContent = "Could not turn off the link. Please try again.";
    }
  });

  const newPageButton = document.getElementById("new-page");
  const newPageMenu = document.getElementById("new-page-menu");
  newPageButton.addEventListener("click", () => {
    newPageMenu.hidden = !newPageMenu.hidden;
    newPageButton.setAttribute("aria-expanded", String(!newPageMenu.hidden));
  });
  newPageMenu.querySelectorAll("[data-new-page]").forEach((button) => {
    button.addEventListener("click", () => {
      newPageMenu.hidden = true;
      newPageButton.setAttribute("aria-expanded", "false");
      createPage(button.dataset.newPage === "child" ? pageId : null);
    });
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".new-page-container")) {
      newPageMenu.hidden = true;
      newPageButton.setAttribute("aria-expanded", "false");
    }
  });

  const searchDialog = document.getElementById("search-dialog");
  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");
  document.getElementById("search-open").addEventListener("click", () => {
    searchDialog.showModal();
    searchInput.focus();
  });

  let searchTimer = null;
  searchInput.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(async () => {
      const response = await fetch(app.dataset.searchUrl + "?q=" + encodeURIComponent(searchInput.value));
      if (!response.ok) return;
      const result = await response.json();
      searchResults.replaceChildren();
      result.results.forEach((page) => {
        const link = document.createElement("a");
        link.className = "search-result";
        link.href = page.url;
        link.textContent = page.icon + " " + page.title;
        searchResults.append(link);
      });
    }, 180);
  });

  window.addEventListener("beforeunload", (event) => {
    if (!pending && !saving) return;
    writeLocalDraft();
    event.preventDefault();
    event.returnValue = "";
  });
})();
