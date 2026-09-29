"""Who may open the Roshan Mustaqbil screens.

The centre has one sign-in, the administrator, who does everything:
attendance, enrollment, calls, imports and analytics. Anyone else who signs
in (an account left over from the HR product, say) sees a "no access" page.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from base.rm import is_centre_admin


def rm_required(view):
    """Allow the view for the centre administrator only."""

    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if is_centre_admin(request.user):
            return view(request, *args, **kwargs)
        return no_access(request)

    return wrapped


def no_access(request):
    return render(request, "rm/no_access.html", status=403)


@login_required
def rm_home(request):
    """Where signing in lands."""
    if is_centre_admin(request.user):
        return redirect("dashboard")
    return no_access(request)


# Sidebar accessibility hook (see horilla.config.sidebar).
def sidebar_admin(request, *args, **kwargs):
    return is_centre_admin(request.user)
