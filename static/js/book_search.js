// Search suggestions in the navbar while the user types.
// GET /search/?q=... -> JSON (async view books.views.book_search).
// Enter still submits the form: the full catalog search (?q=...).
// The texts come from data-* attributes of the form (translated in the
// template), so this file has no language of its own.
(() => {
  const form = document.querySelector("[data-book-search]");
  if (!form) return;
  const input = form.querySelector("input[name=q]");
  const menu = form.querySelector("[data-search-results]");
  const minLength = Number(form.dataset.minLength);
  let timer = null;
  let controller = null;

  function hide() {
    menu.classList.remove("show");
    menu.replaceChildren();
  }

  function show(results) {
    menu.replaceChildren();
    if (!results.length) {
      const empty = document.createElement("span");
      empty.className = "dropdown-item-text small text-body-secondary";
      empty.textContent = form.dataset.emptyText;
      menu.append(empty);
    }
    for (const book of results) {
      // textContent, never innerHTML: a title with "<script>" stays text
      const link = document.createElement("a");
      link.className = "dropdown-item";
      link.href = book.url;
      const title = document.createElement("div");
      title.textContent = book.title;
      const details = document.createElement("div");
      details.className = "small text-body-secondary";
      // book.price comes with its currency symbol: "250,00 ₴" / "$5.50"
      details.textContent = `${book.author} · ${book.price}`;
      link.append(title, details);
      menu.append(link);
    }
    menu.classList.add("show");
  }

  async function search(query) {
    // A slower answer to an older query must not replace a newer one
    controller?.abort();
    controller = new AbortController();
    try {
      const response = await fetch(`${form.dataset.searchUrl}?q=${encodeURIComponent(query)}`, {
        signal: controller.signal,
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return hide();
      const data = await response.json();
      show(data.results);
    } catch (error) {
      if (error.name !== "AbortError") hide();
    }
  }

  input.addEventListener("input", () => {
    // Debounce: one request 250 ms after the last key, not one per key
    clearTimeout(timer);
    const query = input.value.trim();
    if (query.length < minLength) return hide();
    timer = setTimeout(() => search(query), 250);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });
  document.addEventListener("click", (event) => {
    if (!form.contains(event.target)) hide();
  });
})();
