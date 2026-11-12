from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import FileExtensionValidator
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from inventory.services import set_stock

from .models import Author, Book, BookQuerySet, Category

COVER_MAX_SIZE_MB = 2
COVER_ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]


class CoverInput(forms.ClearableFileInput):
    """File input with a preview of the current cover and a "Remove" checkbox.

    Same logic as Django's ClearableFileInput, only the HTML is replaced
    with Bootstrap markup (see the template).
    """

    template_name = "books/widgets/cover_input.html"


class BookForm(forms.ModelForm):
    """Create / update a book, styled with Bootstrap classes.

    "stock" is not a field of Book any more (inventory.Stock), so it is
    declared here by hand and saved in save() to the default warehouse.
    For the user the form is the same as before.
    """

    # max_value: the largest value of PositiveIntegerField in PostgreSQL,
    # a bigger number would be a database error instead of a form error
    stock = forms.IntegerField(
        label=_("stock"),
        min_value=0,
        max_value=2147483647,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
        # A hidden copy of the value the page was opened with:
        #   <input type="hidden" name="initial-stock" value="5">
        # changed_data then compares the sent value with THAT one, not with
        # the stock at the moment of saving. 5 when opened, 1 sold
        # meanwhile (now 4), the manager edits only the title and sends 5:
        # 5 == 5 -> "not changed" -> the 4 stays. Without it 5 != 4 would
        # count as a change and the sold copy would come back.
        show_hidden_initial=True,
    )

    class Meta:
        model = Book
        fields = [
            "title",
            "author",
            "price",
            # Not a model field: the declared field above; listed to keep
            # its place in the form
            "stock",
            "categories",
            "description",
            "cover",
        ]
        help_texts = {
            "author": _("New authors are added in the admin."),
            # format_lazy: translated first, the number is put in after
            "cover": format_lazy(
                _("JPG, PNG or WebP, up to {size} MB. Without a cover a placeholder is shown."),
                size=COVER_MAX_SIZE_MB,
            ),
        }
        widgets = {
            # accept: the browser's file dialog shows only these types
            # (just a convenience — the real check is in clean_cover)
            "cover": CoverInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/jpeg,image/png,image/webp",
                }
            ),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            # ForeignKey -> <select> with all authors (ModelChoiceField)
            "author": forms.Select(attrs={"class": "form-select"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            # Through model (BookCategory) has no extra required fields,
            # so ModelForm.save() can write the M2M as usual
            "categories": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        }

    def __init__(self, *args, user=None, **kwargs):
        # user comes from BookFormUserMixin.get_form_kwargs() in the views
        super().__init__(*args, **kwargs)
        # Django's default empty choice "- Select an option -" (new in
        # Django 6.1) has no Ukrainian translation in Django yet
        self.fields["author"].empty_label = _("— Choose an author —")
        if self.instance.pk:
            # Editing: the current stock (a ModelForm fills only model fields)
            self.initial.setdefault("stock", self.instance.stock)
        if user is not None and not user.has_perm("inventory.change_stock"):
            stock = self.fields["stock"]
            # disabled: the browser shows the field greyed out AND Django
            # ignores whatever is POSTed for it, using the initial value
            # (current stock, or 0 for a new book) — so
            # editing the HTML in DevTools doesn't help
            stock.disabled = True
            stock.help_text = _("Only users with the “manage stock” permission can change it.")

    def save(self, commit=True):
        book = super().save(commit=commit)
        if commit:
            self.save_stock()
        return book

    def save_stock(self):
        """Write the stock to the default warehouse, only if the user changed it.

        Disabled field (no permission) or not changed by the user: nothing
        is written. Writing the old value back could undo an order made
        while the form was open (see show_hidden_initial above).
        A new book with 0: nothing to write either, inventory.signals has
        already made its row with 0.
        With commit=False the caller saves the book and then calls this.
        """
        if self.fields["stock"].disabled or "stock" not in self.changed_data:
            return
        set_stock(self.instance, self.cleaned_data["stock"])

    def clean_cover(self):
        """Extra checks on top of ImageField (which already verifies via Pillow
        that the file is a real image)."""
        cover = self.cleaned_data.get("cover")
        # Only a newly uploaded file needs checking. Otherwise the value is
        # the current cover (nothing uploaded) or False ("Remove" checked).
        if isinstance(cover, UploadedFile):
            FileExtensionValidator(COVER_ALLOWED_EXTENSIONS)(cover)
            if cover.size > COVER_MAX_SIZE_MB * 1024 * 1024:
                size_mb = cover.size / (1024 * 1024)
                raise forms.ValidationError(
                    _("The file is %(size).1f MB, the limit is %(limit)s MB."),
                    params={"size": size_mb, "limit": COVER_MAX_SIZE_MB},
                )
        return cover


class BookFilterForm(forms.Form):
    """GET filters for the book catalog. All fields are optional."""

    SORT_CHOICES = [
        ("title", _("Title A→Z")),
        ("-title", _("Title Z→A")),
        ("author__name", _("Author A→Z")),
        ("price", _("Price: low to high")),
        ("-price", _("Price: high to low")),
        ("-created_at", _("Newest first")),
    ]

    q = forms.CharField(
        required=False,
        label=_("Search"),
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": _("Title or author")}
        ),
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        to_field_name="slug",  # ?category=fantasy instead of ?category=3
        label=_("Category"),
        empty_label=_("All categories"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    author = forms.ModelChoiceField(
        queryset=Author.objects.all(),
        required=False,  # ?author=<pk>
        label=_("Author"),
        empty_label=_("All authors"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    stock = forms.ChoiceField(
        choices=[("", _("Any"))] + BookQuerySet.STOCK_STATUS_CHOICES,
        required=False,
        label=_("Availability"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    price_min = forms.DecimalField(
        required=False,
        min_value=0,
        label=_("Price from"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    price_max = forms.DecimalField(
        required=False,
        min_value=0,
        label=_("Price to"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    sort = forms.ChoiceField(
        choices=SORT_CHOICES,
        required=False,
        label=_("Sort by"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        price_min = cleaned_data.get("price_min")
        price_max = cleaned_data.get("price_max")
        if price_min is not None and price_max is not None and price_min > price_max:
            # Out of cleaned_data: the catalog ignores both prices (instead of
            # "from 500 to 100" = always empty) and applies the other filters
            del cleaned_data["price_min"], cleaned_data["price_max"]
            raise forms.ValidationError(_("“Price from” can't be greater than “Price to”."))
        return cleaned_data
