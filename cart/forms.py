from django import forms


class CartAddForm(forms.Form):
    """Quantity for "Add to cart" (catalog, book page) and "Update" (cart page).

    The upper limit (the stock of a paper book) is not checked here:
    Cart.add() limits the quantity itself and the view tells the user about it.
    """

    quantity = forms.IntegerField(min_value=1, initial=1)
    # Hidden field: "1" on the cart page (set the quantity), absent on the
    # "Add to cart" buttons (add to what is already in the cart)
    override = forms.BooleanField(required=False, widget=forms.HiddenInput)
    # The chosen format (the tiles of the book page, a hidden field of the
    # card and of the cart line). Empty: the main format of the book
    # (an old form without the field). Checked against the book by the view.
    format = forms.IntegerField(required=False, widget=forms.HiddenInput)


class CartFormatForm(forms.Form):
    """The "Format" select of a cart line: the id of the new format."""

    format = forms.IntegerField()
