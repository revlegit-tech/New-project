(() => {
  const STORAGE_KEY = "bppControlsWidth";

  function $(selector, root = document) {
    return root.querySelector(selector);
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function applyWidth(width) {
    const shell = $(".workspace");
    if (!shell) return;

    const safeWidth = clamp(Number(width) || 520, 420, 820);
    shell.style.setProperty("--controls-width", `${safeWidth}px`);
    localStorage.setItem(STORAGE_KEY, String(safeWidth));
  }

  function addResizeHandle() {
    const workspace = $(".workspace");
    const controls = $(".panel.controls");
    const results = $(".results");

    if (!workspace || !controls || !results || $("#layoutResizeHandle")) return;

    const handle = document.createElement("div");
    handle.id = "layoutResizeHandle";
    handle.className = "layout-resize-handle";
    handle.title = "Drag to resize the left panel";

    controls.insertAdjacentElement("afterend", handle);

    const saved = localStorage.getItem(STORAGE_KEY);
    applyWidth(saved || 560);

    let dragging = false;

    function onMove(event) {
      if (!dragging) return;

      const rect = workspace.getBoundingClientRect();
      const x = event.clientX - rect.left;
      applyWidth(x);
    }

    function onUp() {
      dragging = false;
      document.body.classList.remove("is-resizing-layout");
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    }

    handle.addEventListener("mousedown", (event) => {
      event.preventDefault();
      dragging = true;
      document.body.classList.add("is-resizing-layout");
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });

    handle.addEventListener("dblclick", () => {
      applyWidth(560);
    });
  }

  function addWidthControls() {
    const command = $("#seamlessCommandCenter");
    if (!command || $("#layoutWidthControls")) return;

    const wrap = document.createElement("div");
    wrap.id = "layoutWidthControls";
    wrap.className = "layout-width-controls";

    const wider = document.createElement("button");
    wider.type = "button";
    wider.textContent = "Wider left panel";

    const narrower = document.createElement("button");
    narrower.type = "button";
    narrower.textContent = "Narrower left panel";

    wider.addEventListener("click", () => {
      const current = Number(localStorage.getItem(STORAGE_KEY) || 560);
      applyWidth(current + 60);
    });

    narrower.addEventListener("click", () => {
      const current = Number(localStorage.getItem(STORAGE_KEY) || 560);
      applyWidth(current - 60);
    });

    wrap.append(wider, narrower);
    command.appendChild(wrap);
  }

  function init() {
    addResizeHandle();
    addWidthControls();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
