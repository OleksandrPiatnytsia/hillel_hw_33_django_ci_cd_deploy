from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import BASE_CURRENCY, Currency, ExchangeRate
from .services import current_rates


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "symbol", "is_active", "current_rate", "rate_date"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]

    def get_readonly_fields(self, request, obj=None):
        # The code is the primary key: changing it would create a second
        # currency instead of renaming this one. Set once, when adding.
        return ["code"] if obj else []

    @admin.display(description=_("current rate, UAH"))
    def current_rate(self, obj):
        rate = current_rates().get(obj.code)
        return rate.value if rate else "—"

    @admin.display(description=_("rate date"))
    def rate_date(self, obj):
        rate = current_rates().get(obj.code)
        return rate.date if rate and rate.date else "—"


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    """The history of rates; a rate added or changed here is "manual".

    A manual rate wins over the NBU: the next NBU update keeps it
    (services.update_rates). To go back to the NBU rate of that day, delete
    the manual row and run python manage.py update_exchange_rates --date ...
    """

    list_display = ["date", "currency", "rate", "source", "updated_at"]
    list_filter = ["currency", "source"]
    date_hierarchy = "date"
    fields = ["currency", "date", "rate", "source", "created_at", "updated_at"]
    readonly_fields = ["source", "created_at", "updated_at"]
    list_select_related = ["currency"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "currency":
            # UAH is the base and has no rates (CheckConstraint in models.py):
            # don't offer it at all instead of failing on save
            kwargs["queryset"] = Currency.objects.exclude(code=BASE_CURRENCY)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        obj.source = ExchangeRate.Source.MANUAL
        super().save_model(request, obj, form, change)
