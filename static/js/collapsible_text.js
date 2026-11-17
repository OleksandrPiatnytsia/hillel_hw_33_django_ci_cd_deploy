// A long text cut to a few lines with a button "Read more" / "Show less"
// (the description on the book page, books/book_detail.html).
//
// Markup:
//   <div id="text" data-collapsible-text>...</div>
//   <button class="collapsible-toggle" hidden aria-controls="text"
//           aria-expanded="false" data-label-more="..." data-label-less="...">
//     <span class="collapsible-toggle__label">...</span> <svg arrow>
//   </button>
// The labels come from the template, so they are translated by Django.
//
// Without JavaScript the whole text is shown and the button stays hidden.
// Here: cut the text (.is-collapsible, max-height in styles.css) and show
// the button only when the text is really longer than the cut; a short
// description gets neither the fade nor the button.
document.querySelectorAll("[data-collapsible-text]").forEach((text) => {
  const button = document.querySelector(`.collapsible-toggle[aria-controls="${text.id}"]`);
  if (!button) {
    return;
  }
  text.classList.add("is-collapsible");
  // scrollHeight: the height of the whole text; clientHeight: of the cut box
  if (text.scrollHeight <= text.clientHeight + 1) {
    text.classList.remove("is-collapsible");
    return;
  }
  const label = button.querySelector(".collapsible-toggle__label");
  button.hidden = false;
  button.addEventListener("click", () => {
    const expanded = text.classList.toggle("is-expanded");
    button.setAttribute("aria-expanded", String(expanded));
    label.textContent = expanded ? button.dataset.labelLess : button.dataset.labelMore;
  });
});
