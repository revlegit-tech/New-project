export function h<K extends keyof HTMLElementTagNameMap>(tagName: K, options: Record<string, unknown> = {}, children: Array<Node | string | null | undefined> = []): HTMLElementTagNameMap[K] {
  const element = document.createElement(tagName);
  if (typeof options.className === "string") element.className = options.className;
  if (typeof options.id === "string") element.id = options.id;
  if (options.text !== undefined) element.textContent = String(options.text);
  if (typeof options.type === "string" && "type" in element) (element as HTMLButtonElement).type = options.type;
  if (options.value !== undefined && "value" in element) (element as HTMLInputElement).value = String(options.value);
  if (options.dataset && typeof options.dataset === "object") {
    Object.entries(options.dataset as Record<string, unknown>).forEach(([key, value]) => {
      element.dataset[key] = String(value);
    });
  }
  if (options.attrs && typeof options.attrs === "object") {
    Object.entries(options.attrs as Record<string, unknown>).forEach(([key, value]) => {
      if (value !== false && value !== null && value !== undefined) element.setAttribute(key, String(value));
    });
  }
  children.filter(Boolean).forEach((child) => element.append(child instanceof Node ? child : document.createTextNode(String(child))));
  return element;
}

export function clear(target: Element | null, children: Node[] = []): void {
  if (!target) return;
  target.replaceChildren(...children);
}
