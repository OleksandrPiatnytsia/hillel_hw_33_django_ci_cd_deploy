// The catalog without page reloads (books/book_list.html).
//
// What goes through here instead of a normal page load:
// - the filter form (a checkbox, a radio button, "Apply" of the price);
// - the links of the results that lead to the catalog itself: the chips
//   and "Clear all", the sort menu, "Out of stock last", the pages;
// - the "Per page" form.
// The script asks the server for the same URL (the same view, the same
// HTML: no separate API), takes the results part of the answer and puts it
// in place of the current one. The filter panel is NOT replaced, only its
// fields get the new values: so the panel keeps its scroll, the text in
// the search boxes of the lists, the opened "Show all" and the folded
// blocks.
// The address bar gets the new URL (history.pushState): the page can be
// bookmarked, and "Back" / "Forward" show the previous lists.
// If anything goes wrong (no network, a server error), the browser simply
// opens the URL the normal way. Without JavaScript nothing of this runs:
// the forms and the links work as before.
(() => {
  const panel = document.querySelector("form[data-filter-form]");
  const results = document.querySelector("[data-catalog-results]");
  if (!panel || !results || !window.fetch || !window.history.pushState) return;

  // The path of the catalog, e.g. "/" or "/en/": only its URLs are loaded here
  const catalogPath = new URL(panel.action, location.href).pathname;
  let controller = null; // the request in progress, to cancel it

  const isCatalog = (url) => url.origin === location.origin && url.pathname === catalogPath;

  // ---------- Loading and swapping ----------

  async function load(url, { push = true, scroll = false } = {}) {
    // A click while the previous list is still loading: that one is
    // cancelled, only the last choice is shown
    controller?.abort();
    controller = new AbortController();
    results.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const html = await response.text();
      const page = new DOMParser().parseFromString(html, "text/html");
      const newResults = page.querySelector("[data-catalog-results]");
      const newPanel = page.querySelector("form[data-filter-form]");
      if (!newResults || !newPanel) throw new Error("not a catalog page");

      results.replaceChildren(...newResults.childNodes);
      syncPanel(newPanel);
      syncNavbarSearch(page);
      if (push) history.pushState({ catalog: true }, "", url);
      // Another page of the list: back to its top (if it is above the screen)
      if (scroll && results.getBoundingClientRect().top < 0) {
        results.scrollIntoView({ behavior: "smooth" });
      }
    } catch (error) {
      if (error.name === "AbortError") return; // a newer request took over
      location.href = url; // the normal way
    } finally {
      results.removeAttribute("aria-busy");
    }
  }

  // The fields of the panel get the values of the new page. Needed when the
  // change came from outside the panel (a chip removed an author: its box
  // must be unticked) and for the hidden fields (the sort, "Per page").
  function syncPanel(newPanel) {
    for (const field of newPanel.querySelectorAll("input[id]")) {
      const current = document.getElementById(field.id);
      if (!current || !panel.contains(current)) continue;
      if (current.type === "checkbox" || current.type === "radio") {
        current.checked = field.checked;
      } else if (current.value !== field.value) {
        current.value = field.value;
        // The price slider follows its fields (static/js/price_range.js)
        current.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
    // Hidden fields: replaced as a whole, their set changes (no "sort" for
    // the default sort)
    for (const hidden of panel.querySelectorAll("input[type=hidden]")) hidden.remove();
    const errors = panel.querySelector("[data-form-errors]");
    for (const hidden of newPanel.querySelectorAll("input[type=hidden]")) {
      errors.before(document.importNode(hidden, true));
    }
    errors.replaceChildren(
      ...[...newPanel.querySelector("[data-form-errors]").childNodes].map((node) =>
        document.importNode(node, true)
      )
    );
    // "Show all" lists: the newly ticked options must be visible
    panel.dispatchEvent(new Event("catalog:updated"));
  }

  // A chip of the search removed "?q=": the navbar field must be empty too
  function syncNavbarSearch(page) {
    const current = document.querySelector("form[data-book-search] input[name=q]");
    const fresh = page.querySelector("form[data-book-search] input[name=q]");
    if (current && fresh) current.value = fresh.value;
  }

  // The URL a GET form would open: its action + its fields. new FormData()
  // runs the "formdata" listeners too, which drop the empty fields
  // (static/js/filter_panel.js)
  function formUrl(form) {
    const url = new URL(form.action, location.href);
    url.search = new URLSearchParams(new FormData(form)).toString();
    return url;
  }

  // ---------- What is caught ----------

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (form.method.toLowerCase() !== "get") return; // "Add to cart" is a POST
    if (form !== panel && !results.contains(form)) return; // the navbar search
    const url = formUrl(form);
    if (!isCatalog(url)) return;
    event.preventDefault();
    load(url.href);
  });

  results.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    // A new tab (Ctrl / Cmd / middle button) stays the browser's
    if (!link || event.defaultPrevented || event.button !== 0) return;
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href, location.href);
    if (!isCatalog(url)) return; // a book page, the cart
    event.preventDefault();
    // The page links of the pagination: back to the top of the list
    load(url.href, { scroll: Boolean(link.closest(".pagination")) });
  });

  // "Back" / "Forward": the list of that address, without a new history entry
  history.replaceState({ catalog: true }, "");
  window.addEventListener("popstate", (event) => {
    if (event.state?.catalog) load(location.href, { push: false });
  });
})();
