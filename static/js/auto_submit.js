// Sends a form as soon as one of its <select> fields changes, so the user
// needs no extra button (e.g. "Per page" in the catalog).
// Usage: <form data-auto-submit> ... <select> ... </form>
// Without JavaScript the form keeps working through its own submit button.
(() => {
  for (const form of document.querySelectorAll("form[data-auto-submit]")) {
    form.addEventListener("change", (event) => {
      if (event.target.matches("select")) {
        // requestSubmit(), not submit(): it runs the browser's validation
        // and the "submit" event like a click on the button would
        form.requestSubmit();
      }
    });
  }
})();
