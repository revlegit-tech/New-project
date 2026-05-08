(function () {
  const params = new URLSearchParams(window.location.search);
  const enabled = params.get("view") === "outlier" || params.has("outlier");
  if (!enabled) return;

  async function boot() {
    try {
      const core = await import("/outlier-core.js");
      await core.bootOutlierApp({ params });
    } catch (error) {
      const target = document.querySelector("main") || document.body;
      const panel = document.createElement("section");
      panel.className = "ob-shell ob-shell-error";
      const title = document.createElement("h1");
      title.textContent = "Outlier UI could not start";
      const copy = document.createElement("p");
      copy.textContent = String(error && error.message ? error.message : error);
      panel.append(title, copy);
      target.replaceChildren(panel);
      console.warn("Outlier module boot failed", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
