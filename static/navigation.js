(() => {
  const shell = document.querySelector(".app-shell");
  if (!shell) return;

  const workspaceId = shell.dataset.workspace || "default";
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const isMobile = () => window.matchMedia("(max-width: 760px)").matches;
  const collapsedTreeKey = "forma-collapsed-tree:" + workspaceId;
  let collapsedPages = new Set();

  function updateSidebarButton() {
    if (!sidebarToggle) return;

    const open = isMobile()
      ? shell.classList.contains("sidebar-open")
      : !shell.classList.contains("sidebar-collapsed");
    sidebarToggle.textContent = isMobile() ? (open ? "×" : "☰") : (open ? "‹" : "›");
    sidebarToggle.setAttribute("aria-label", open ? "Minimize sidebar" : "Expand sidebar");
    sidebarToggle.title = open ? "Minimize sidebar" : "Expand sidebar";
  }

  try {
    collapsedPages = new Set(JSON.parse(window.localStorage.getItem(collapsedTreeKey) || "[]"));
  } catch (error) {
    collapsedPages = new Set();
  }

  const pageRows = Array.from(shell.querySelectorAll(".nav-row"));
  pageRows.forEach((row) => {
    const toggle = row.querySelector("[data-tree-toggle]");
    const link = row.querySelector(".nav-item");
    if (toggle && link && collapsedPages.has(link.getAttribute("href"))) {
      toggle.setAttribute("aria-expanded", "false");
      toggle.textContent = "›";
    }
  });

  function updatePageTree() {
    const collapsedLevels = [];

    pageRows.forEach((row) => {
      const depth = Number(row.dataset.depth || 0);
      while (collapsedLevels.length && collapsedLevels[collapsedLevels.length - 1] >= depth) {
        collapsedLevels.pop();
      }

      row.hidden = collapsedLevels.length > 0;
      const toggle = row.querySelector("[data-tree-toggle]");
      if (toggle && toggle.getAttribute("aria-expanded") === "false") {
        collapsedLevels.push(depth);
      }
    });
  }

  pageRows.forEach((row) => {
    const toggle = row.querySelector("[data-tree-toggle]");
    if (!toggle) return;

    toggle.addEventListener("click", () => {
      const isOpen = toggle.getAttribute("aria-expanded") !== "false";
      toggle.setAttribute("aria-expanded", String(!isOpen));
      toggle.textContent = isOpen ? "›" : "⌄";

      const title = row.querySelector(".nav-title")?.textContent || "page";
      toggle.setAttribute("aria-label", (isOpen ? "Expand " : "Collapse ") + title);

      const pageLink = row.querySelector(".nav-item")?.getAttribute("href");
      if (pageLink) {
        if (isOpen) collapsedPages.add(pageLink);
        else collapsedPages.delete(pageLink);
        window.localStorage.setItem(collapsedTreeKey, JSON.stringify(Array.from(collapsedPages)));
      }

      updatePageTree();
    });
  });

  updatePageTree();
  updateSidebarButton();

  sidebarToggle?.addEventListener("click", () => {
    if (isMobile()) {
      shell.classList.toggle("sidebar-open");
    } else {
      shell.classList.toggle("sidebar-collapsed");
      const isCollapsed = shell.classList.contains("sidebar-collapsed");
      window.localStorage.setItem("forma-sidebar-collapsed", isCollapsed ? "1" : "0");
    }
    updateSidebarButton();
  });

  if (!isMobile() && window.localStorage.getItem("forma-sidebar-collapsed") === "1") {
    shell.classList.add("sidebar-collapsed");
  }
  updateSidebarButton();
  window.addEventListener("resize", updateSidebarButton);
})();