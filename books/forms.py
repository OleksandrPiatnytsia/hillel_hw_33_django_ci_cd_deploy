from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.db.models import Q
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from currencies.models import Currency

from .models import FIRST_PUBLICATION_YEAR, Book, BookFormat

COVER_MAX_SIZE_MB = 2
COVER_ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]

# The details of the edition: a block of their own in the book form.
# Module level: class Meta of the form below can't see the attributes of
# the form class itself
DETAIL_FIELDS = [
    "publisher",
    "language",
    "publication_year",
]


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

    The details of the edition (DETAIL_FIELDS) are shown as a separate
    block of the form, several fields in a row (books/book_form.html).

    No price here either: the price, the currency, the cover and the pages
    belong to a format (BookFormatFormSet below, a block of the same page).
    """

    DETAIL_FIELDS = DETAIL_FIELDS

    class Meta:
        model = Book
        fields = [
            "title",
            "author",
            "categories",
            "description",
            *DETAIL_FIELDS,
            "cover",
        ]
        help_texts = {
            "author": _("New authors are added in the admin."),
            "publisher": _("New publishers are added in the admin."),
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
            # Through model (BookCategory) has no extra required fields,
            # so ModelForm.save() can write the M2M as usual
            "categories": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "publisher": forms.Select(attrs={"class": "form-select"}),
            "language": forms.Select(attrs={"class": "form-select"}),
            # min / max: hints for the browser's arrows; the model checks
            # the year itself (Book.publication_year validators). The max
            # (this year) is set in __init__: here it would be fixed at the
            # start of the server
            "publication_year": forms.NumberInput(
                attrs={"class": "form-control", "min": FIRST_PUBLICATION_YEAR, "step": "1"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Django's default empty choice "- Select an option -" (new in
        # Django 6.1) has no Ukrainian translation in Django yet
        self.fields["author"].empty_label = _("— Choose an author —")
        # Not required: "not known" instead of Django's "---------"
        self.fields["publisher"].empty_label = _("— Not known —")
        _not_known_choice(self.fields["language"])
        self.fields["publication_year"].widget.attrs["max"] = timezone.now().year

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

    def main_fields(self):
        """The fields above the details block, in the Meta order (the cover
        comes after the block, the template shows it by itself)."""
        skip = {*self.DETAIL_FIELDS, "cover"}
        return [field for field in self if field.name not in skip]

    def detail_fields(self):
        """The details of the edition: one block, several fields in a row."""
        return [self[name] for name in self.DETAIL_FIELDS]


def _not_known_choice(field):
    """ "— Not known —" instead of Django's "---------" in an optional choices field."""
    # The first choice of an optional choices field is the empty one
    field.choices = [("", _("— Not known —")), *field.choices[1:]]


class BookFormatForm(forms.ModelForm):
    """One format of the book in the book form: one row of BookFormatFormSet.

    "A cover only for paper" and "no pages for an audiobook" are checked
    by BookFormat.clean(): a ModelForm calls it, the error goes under the
    field.
    """

    class Meta:
        model = BookFormat
        fields = ["format_type", "price", "currency", "cover_type", "pages", "is_active"]
        widgets = {
            "format_type": forms.Select(attrs={"class": "form-select"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "0.01"}),
            "currency": forms.Select(attrs={"class": "form-select"}),
            "cover_type": forms.Select(attrs={"class": "form-select"}),
            "pages": forms.NumberInput(attrs={"class": "form-control", "min": "1", "step": "1"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        help_texts = {
            "cover_type": _("Only for paper."),
            # The model's help text is for the admin; the row has no room
            "is_active": "",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        format_type = self.fields["format_type"]
        format_type.choices = [("", _("— Choose a format —")), *format_type.choices[1:]]
        _not_known_choice(self.fields["cover_type"])
        # Only the active currencies, and the current one of the format even
        # if it was turned off since: editing the price must not force a
        # new currency. No empty choice: the price always has a currency
        # (UAH is preselected for a new format, the model default).
        currency = self.fields["currency"]
        currency.queryset = Currency.objects.filter(
            Q(is_active=True) | Q(pk=self.instance.currency_id)
        )
        currency.empty_label = None
        currency.label_from_instance = lambda item: f"{item.code} ({item.symbol})"


class BaseBookFormatFormSet(BaseInlineFormSet):
    """The formats of a book: at least one, each type once (unique book + format_type)."""

    def add_fields(self, form, index):
        super().add_fields(form, index)
        # The "Delete" checkbox Django adds to every row: Bootstrap's class
        if "DELETE" in form.fields:
            form.fields["DELETE"].widget.attrs["class"] = "form-check-input"

    def main_format(self):
        """The cleaned data of the main format: on sale first, then paper, e-book, audiobook.

        The old fields of the book (price, currency, book type, cover,
        pages) copy it until they are removed: the cart and the API still
        read them. Call after is_valid().
        """
        rows = [
            form.cleaned_data
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        order = list(BookFormat.FormatType.values)
        return min(rows, key=lambda row: (not row["is_active"], order.index(row["format_type"])))


# Three rows at most (paper, e-book, audiobook). A new book gets three
# empty rows (min_num 1 + extra 2), a book with one format its row + two
# empty ones; an empty row is skipped. validate_min: a book without any
# format can't be saved ("Please submit at least 1 form").
BookFormatFormSet = inlineformset_factory(
    Book,
    BookFormat,
    form=BookFormatForm,
    formset=BaseBookFormatFormSet,
    extra=2,
    min_num=1,
    validate_min=True,
    max_num=len(BookFormat.FormatType),
    validate_max=True,
    can_delete=True,
)
