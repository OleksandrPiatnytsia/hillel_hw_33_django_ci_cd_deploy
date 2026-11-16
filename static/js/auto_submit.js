// Sends a form as soon as one of its <select> fields changes, so the user
// needs no extra button (e.g. "Per page" in the catalog).
// Usage: <form data-auto-submit> ... <select> ... </form>
// Without JavaScript the form keeps working through its own submit button.
// One listener on the whole document (event delegation), not one per form:
// a form that appears later (the catalog results replaced by
// static/js/catalog_live.js) works too.
document.addEventListener("change", (event) => {
  const form = event.target.closest("form[data-auto-submit]");
  if (form && event.target.matches("select")) {
    // requestSubmit(), not submit(): it runs the browser's validation
    // and the "submit" event like a click on the button would
    form.requestSubmit();
  }
});
