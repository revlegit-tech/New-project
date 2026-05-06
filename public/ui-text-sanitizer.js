(() => {
  function cleanText(value) {
    return String(value || "")
      // Replace broken special-character rendering.
      .replaceAll(" ? ", " - ")
      .replaceAll(" ?\u00a0", " - ")
      .replaceAll("\u00a0?\u00a0", " - ")
      .replaceAll("?F", " deg F")
      .replaceAll("°F", " deg F")
      .replaceAll("°", " deg")
      .replaceAll(" · ", " - ")
      .replaceAll(" — ", " - ")
      .replaceAll(" – ", " - ");
  }

  function cleanNodeText(root) {
    if (!root) return;

    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          const text = node.nodeValue || "";

          if (
            text.includes(" ? ") ||
            text.includes("?F") ||
            text.includes("°") ||
            text.includes(" · ") ||
            text.includes(" — ") ||
            text.includes(" – ")
          ) {
            return NodeFilter.FILTER_ACCEPT;
          }

          return NodeFilter.FILTER_REJECT;
        },
      }
    );

    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach((node) => {
      node.nodeValue = cleanText(node.nodeValue);
    });
  }

  function run() {
    cleanNodeText(document.getElementById("simplePropApp"));
    cleanNodeText(document.getElementById("simpleResult"));
    cleanNodeText(document.getElementById("simpleAutofillSummary"));
  }

  function observe() {
    const targets = [
      document.getElementById("simplePropApp"),
      document.getElementById("simpleResult"),
      document.getElementById("simpleAutofillSummary"),
    ].filter(Boolean);

    targets.forEach((target) => {
      const observer = new MutationObserver(() => run());
      observer.observe(target, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      run();
      observe();
    });
  } else {
    run();
    observe();
  }
})();
