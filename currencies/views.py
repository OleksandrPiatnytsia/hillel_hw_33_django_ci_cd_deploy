from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .display import SESSION_KEY
from .services import available_currencies


@require_POST
def set_currency(request):
    """The currency switcher in the navbar: POST currency=USD, next=<page>.

    POST, like the language switcher: it changes the visitor's state (the
    session), a plain link could be followed by a bot or another site.
    Only a currency offered on the site is saved; anything else (an old
    page with a currency turned off since, a crafted form) changes nothing.
    Then back to `next` (only an address of this site: no open redirect).
    """
    code = request.POST.get("currency", "")
    if code in {currency.code for currency in available_currencies()}:
        request.session[SESSION_KEY] = code

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("books:list")
