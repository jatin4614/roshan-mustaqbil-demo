"""Who may open which Roshan Mustaqbil screen.

Three roles, each including the one before it:
front desk -> coordinator -> manager (see base.rm.ROLE_GROUPS).
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from base.rm import ROLE_LABELS, has_role, role_of


def rm_required(minimum="frontdesk"):
    """Allow the view for users with at least the ``minimum`` role."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if has_role(request.user, minimum):
                return view(request, *args, **kwargs)
            if role_of(request.user):
                messages.info(request, f"That page is for the {ROLE_LABELS[minimum].lower()} or a manager.")
                return redirect("rm-home")
            return no_access(request)

        wrapped.rm_minimum_role = minimum
        return wrapped

    return decorator


def no_access(request):
    return render(request, "rm/no_access.html", status=403)


@login_required
def rm_home(request):
    """Send each role to the screen they use most."""
    role = role_of(request.user)
    if role == "frontdesk":
        return redirect("youth-daily-attendance")
    if role:
        return redirect("dashboard")
    return no_access(request)


# Sidebar accessibility hooks (see horilla.config.sidebar).
def sidebar_frontdesk(request, *args, **kwargs):
    return has_role(request.user, "frontdesk")


def sidebar_coordinator(request, *args, **kwargs):
    return has_role(request.user, "coordinator")
