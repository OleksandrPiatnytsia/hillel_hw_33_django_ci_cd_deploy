// The hearts of the wishlist (wishlist/includes/heart.html) without a page
// reload.
//
// A heart is a POST form to /wishlist/add/<id>/ or /wishlist/remove/<id>/.
// Here it is sent with fetch() and "Accept: application/json"; the server
// (wishlist/views.py) answers with the new state:
//   {"saved": true, "url": "/wishlist/remove/7/", "message": "..."}
// and the script:
// - fills or empties the heart (.is-saved, aria-pressed, the labels);
// - points the form to the other URL (add <-> remove);
// - on the wishlist page removes the card of a book taken out.
// The session has ended (401): the login page from the answer.
// Anything else goes wrong (no network, a server error): the form is sent
// the normal way, the server answers with a message and a redirect.
// Without JavaScript the forms work as usual.
// One listener on the whole document (event delegation): the cards the
// catalog loads later (static/js/catalog_live.js) work too.
document.addEventListener("submit", async (event) => {
  const form = event.target.closest("form[data-wishlist-form]");
  if (!form || !window.fetch) return;
  event.preventDefault();
  const button = form.querySelector("button");
  if (button.disabled) return; // the previous click is still on its way
  button.disabled = true;

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form), // with csrfmiddlewaretoken and next
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    const data = await response.json();
    if (response.status === 401 && data.login_url) {
      location.href = data.login_url;
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    update(form, button, data);
  } catch {
    form.submit(); // the normal way: the server shows what happened
    return;
  } finally {
    button.disabled = false;
  }
});

function update(form, button, data) {
  form.action = data.url;
  button.classList.toggle("is-saved", data.saved);
  button.setAttribute("aria-pressed", String(data.saved));
  const label = data.saved ? button.dataset.labelRemove : button.dataset.labelAdd;
  button.title = label;
  button.setAttribute("aria-label", label);
  const text = button.querySelector(".wishlist-heart__text");
  if (text) text.textContent = data.saved ? button.dataset.textSaved : button.dataset.textAdd;

  // The wishlist page: a book taken out leaves the list
  const card = form.closest("[data-wishlist-card]");
  if (card && !data.saved) {
    card.remove();
    // The last card of the page: open the first page (a reload of
    // ?page=3 that has no books any more would be a 404); it shows the
    // other books or "Your wishlist is empty"
    if (!document.querySelector("[data-wishlist-card]")) location.href = location.pathname;
  }
}
