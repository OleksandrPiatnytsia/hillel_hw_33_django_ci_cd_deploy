// The price slider of the catalog filter (books/includes/price_filter.html).
//
// Two <input type="range"> without a "name" fill the number fields
// "Price from" / "Price to", which are sent with the form:
// - a handle moved -> its field gets the number; a handle at its end
//   (the cheapest / the dearest book) -> the field is emptied, so the URL
//   has no ?price_min= and the filter means "any";
// - a number typed into a field -> its handle moves there;
// - the handles can't pass each other.
// Without JavaScript the slider stays hidden and the fields work alone.
(() => {
  for (const block of document.querySelectorAll("[data-price-range]")) {
    const slider = block.querySelector(".price-slider");
    if (!slider) continue; // no books or one price: nothing to slide

    const low = Number(slider.dataset.min);
    const high = Number(slider.dataset.max);
    const [fromRange, toRange] = slider.querySelectorAll("input[type=range]");
    const fill = slider.querySelector(".price-slider-fill");
    const fieldOf = (range) => document.getElementById(range.dataset.field);
    const fromField = fieldOf(fromRange);
    const toField = fieldOf(toRange);

    // The ends as hints in the empty fields: "12" and "1511"
    fromField.placeholder = low;
    toField.placeholder = high;

    const clamp = (value) => Math.min(Math.max(value, low), high);

    function paint() {
      const span = high - low;
      fill.style.left = `${((fromRange.value - low) / span) * 100}%`;
      fill.style.right = `${((high - toRange.value) / span) * 100}%`;
      // The "to" input is on top (later in the HTML). When the handles meet
      // in the right half, "from" goes on top: the only way left is to
      // pull "from" back; in the left half "to" stays on top for the same
      // reason the other way
      fromRange.style.zIndex = Number(fromRange.value) > (low + high) / 2 ? 2 : "";
    }

    // A field -> its handle (an empty or wrong field: the handle at its end)
    function fromFields() {
      const from = parseFloat(fromField.value.replace(",", "."));
      const to = parseFloat(toField.value.replace(",", "."));
      // floor / ceil: "to 14.31" puts the handle at 15, not before the price
      fromRange.value = Number.isFinite(from) ? Math.floor(clamp(from)) : low;
      toRange.value = Number.isFinite(to) ? Math.ceil(clamp(to)) : high;
      paint();
    }

    // A handle -> its field
    function fromRanges(event) {
      // The handles don't cross: the moved one stops at the other one
      if (Number(fromRange.value) > Number(toRange.value)) {
        event.target.value = event.target === fromRange ? toRange.value : fromRange.value;
      }
      fromField.value = Number(fromRange.value) === low ? "" : fromRange.value;
      toField.value = Number(toRange.value) === high ? "" : toRange.value;
      paint();
    }

    fromRange.addEventListener("input", fromRanges);
    toRange.addEventListener("input", fromRanges);
    fromField.addEventListener("input", fromFields);
    toField.addEventListener("input", fromFields);

    fromFields();
    slider.hidden = false;
  }
})();
