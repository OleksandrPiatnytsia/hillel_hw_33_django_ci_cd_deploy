// The filter panel of the catalog (books/book_list.html, filter_section.html).
//
// - a checkbox or a radio button sends the form at once (no "Apply");
//   the search and the price wait for Enter or their own button;
// - empty fields are not sent: "?q=&price_min=" would only make the URL
//   and the links of the chips longer;
// - a long list shows its first 5 options (and every chosen one) and a
//   "Show all" button; the search box above it hides the options that
//   don't match;
// - the folded blocks are remembered in localStorage, so after the page
//   reloads (every click on a checkbox) the panel looks the same.
// Without JavaScript all options are shown, the blocks are open and the
// "Apply" button in <noscript> sends the form.
(() => {
  const form = document.querySelector("form[data-filter-form]");
  if (!form) return;

  const VISIBLE = 5;
  const STORAGE_KEY = "catalog-filters-folded";

  // ---------- Sending ----------

  form.addEventListener("change", (event) => {
    if (event.target.matches("input[type=checkbox], input[type=radio]")) {
      form.requestSubmit();
    }
  });

  // "formdata": the data the browser is about to send; the empty values
  // are taken out (a checkbox list sends nothing when nothing is chosen)
  form.addEventListener("formdata", (event) => {
    for (const [name, value] of [...event.formData.entries()]) {
      if (value === "") event.formData.delete(name);
    }
  });

  // ---------- Folded blocks ----------

  const folded = new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"));
  const save = () => localStorage.setItem(STORAGE_KEY, JSON.stringify([...folded]));

  for (const block of form.querySelectorAll("[data-filter-section]")) {
    const name = block.dataset.filterSection;
    const toggle = form.querySelector(`[data-bs-target="#${block.id}"]`);
    if (folded.has(name)) {
      // Folded at once, without the animation of Bootstrap
      block.classList.remove("show");
      toggle.setAttribute("aria-expanded", "false");
      toggle.classList.add("collapsed");
    }
    block.addEventListener("hidden.bs.collapse", () => { folded.add(name); save(); });
    block.addEventListener("shown.bs.collapse", () => { folded.delete(name); save(); });
  }

  // ---------- Long lists: "Show all" and the search ----------

  for (const body of form.querySelectorAll(".filter-section-body")) {
    const options = [...body.querySelectorAll("[data-option]")];
    const search = body.querySelector("[data-option-search]");
    const more = body.querySelector("[data-show-all]");
    const nothing = body.querySelector("[data-nothing-found]");
    if (!more) continue; // a short list: everything is visible
    let expanded = false;

    const paint = () => {
      const text = search.value.trim().toLocaleLowerCase();
      let shown = 0;
      options.forEach((option, index) => {
        const label = option.textContent.trim().toLocaleLowerCase();
        const checked = option.querySelector("input").checked;
        const visible = text
          ? label.includes(text) // searching: every match
          : expanded || index < VISIBLE || checked;
        option.hidden = !visible;
        if (visible) shown += 1;
      });
      nothing.hidden = shown > 0;
      // While searching the button is not needed: all matches are shown
      more.hidden = Boolean(text);
      more.textContent = expanded ? more.dataset.labelLess : more.dataset.labelMore;
    };

    more.addEventListener("click", () => { expanded = !expanded; paint(); });
    search.addEventListener("input", paint);
    // Enter in the search box of a list must not send the form
    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") event.preventDefault();
    });
    paint();
  }
})();
