from django import forms
from django.db.models import Q
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import FileExtensionValidator
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from currencies.models import Currency

from .models import Book

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

    No stock here: the copies live in inventory.Stock, per warehouse, and
    are changed in the admin (the book page there, or Stock). A new book
    gets its row with 0 from inventory.signals.
    """

    class Meta:
        model = Book
        fields = [
            "title",
            "author",
            "price",
            "currency",
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
            "currency": forms.Select(attrs={"class": "form-select"}),
            # Through model (BookCategory) has no extra required fields,
            # so ModelForm.save() can write the M2M as usual
            "categories": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Django's default empty choice "- Select an option -" (new in
        # Django 6.1) has no Ukrainian translation in Django yet
        self.fields["author"].empty_label = _("— Choose an author —")
        # Only the active currencies, and the current one of the book even
        # if it was turned off since: editing the title must not force
        # a new currency. No empty choice: the price always has a currency
        # (UAH is preselected for a new book, the model default).
        currency = self.fields["currency"]
        currency.queryset = Currency.objects.filter(
            Q(is_active=True) | Q(pk=self.instance.currency_id)
        )
        currency.empty_label = None
        currency.label_from_instance = lambda item: f"{item.code} ({item.symbol})"

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
