"""Staff accounts for the centre: who can sign in, and with which role."""

from django import forms
from django.contrib import messages
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from base.models import Company
from base.rm import ROLE_GROUPS, ROLE_HELP, ROLE_LABELS, normalize_phone, role_of, valid_mobile
from base.rm_access import rm_required
from employee.models import Employee, EmployeeWorkInformation
from horilla_auth.models import HorillaUser

ROLE_CHOICES = [(key, ROLE_LABELS[key]) for key in ("frontdesk", "coordinator", "manager")]


def ensure_role_groups():
    return {key: Group.objects.get_or_create(name=name)[0] for key, name in ROLE_GROUPS.items()}


class NewStaffForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Full name")
    username = forms.CharField(max_length=150, label="Username", help_text="What they type to sign in, for example 'asma'.")
    phone = forms.CharField(max_length=25, label="Phone number", widget=forms.TextInput(attrs={"type": "tel", "inputmode": "numeric"}))
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="Role", widget=forms.RadioSelect)
    password = forms.CharField(label="Temporary password", widget=forms.PasswordInput(render_value=False), help_text="They'll be asked to choose their own password when they first sign in.")

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if HorillaUser.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not valid_mobile(phone):
            raise forms.ValidationError("Enter a 10-digit mobile number.")
        return phone

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


class ResetPasswordForm(forms.Form):
    password = forms.CharField(label="New temporary password", widget=forms.PasswordInput)

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


def _centre_company():
    return Company.objects.filter(hq=True).first() or Company.objects.first()


def _set_role(user, role):
    groups = ensure_role_groups()
    user.groups.remove(*groups.values())
    if role:
        user.groups.add(groups[role])
    user._rm_role = "unset"


def _staff_users():
    names = list(ROLE_GROUPS.values())
    return HorillaUser.objects.filter(Q(is_superuser=True) | Q(groups__name__in=names)).distinct().order_by("-is_active", "username")


def _managers_left(excluding=None):
    managers = [user for user in _staff_users().filter(is_active=True) if role_of(user) == "manager"]
    return [user for user in managers if user != excluding]


@rm_required("manager")
def staff(request):
    ensure_role_groups()
    form = NewStaffForm(request.POST or None, initial={"role": "frontdesk"})
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        with transaction.atomic():
            username = values["username"]
            user = HorillaUser.objects.create_user(username=username, email=f"{username}@staff.rm.local", password=values["password"])
            if hasattr(user, "is_new_employee"):
                user.is_new_employee = True
                user.save(update_fields=["is_new_employee"])
            _set_role(user, values["role"])
            names = values["full_name"].strip().split(maxsplit=1)
            employee = Employee(
                employee_user_id=user, employee_first_name=names[0], employee_last_name=names[1] if len(names) > 1 else "",
                email=user.email, phone=values["phone"],
            )
            employee.save()
            company = _centre_company()
            if company:
                EmployeeWorkInformation.objects.update_or_create(employee_id=employee, defaults={"company_id": company, "email": user.email, "mobile": values["phone"]})
        messages.success(request, f"{values['full_name']} can now sign in as “{username}” with the temporary password.")
        return redirect("rm-staff")
    rows = []
    for user in _staff_users():
        employee = getattr(user, "employee_get", None)
        role = "manager" if user.is_superuser else role_of(user) if user.is_active else next((key for key, name in ROLE_GROUPS.items() if user.groups.filter(name=name).exists()), None)
        rows.append({
            "user": user, "name": employee.get_full_name() if employee else user.username, "role": role,
            "role_label": ROLE_LABELS.get(role, "No access"), "is_self": user == request.user, "locked": user.is_superuser,
        })
    context = {"form": form, "rows": rows, "roles": ROLE_CHOICES, "role_help": [(ROLE_LABELS[key], ROLE_HELP[key]) for key, _ in ROLE_CHOICES], "reset_form": ResetPasswordForm()}
    return render(request, "rm/staff.html", context)


@rm_required("manager")
@require_POST
def staff_update(request, user_id):
    user = get_object_or_404(HorillaUser, id=user_id)
    action = request.POST.get("action")
    if user.is_superuser:
        messages.info(request, "The main administrator account can't be changed here.")
        return redirect("rm-staff")
    if action == "role" and request.POST.get("role") in ROLE_GROUPS:
        if user == request.user and request.POST["role"] != "manager" and not _managers_left(excluding=user):
            messages.error(request, "You're the only manager. Make someone else a manager first.")
        else:
            _set_role(user, request.POST["role"])
            messages.success(request, f"{user.username} is now {ROLE_LABELS[request.POST['role']].lower()}.")
    elif action == "deactivate":
        if user == request.user:
            messages.error(request, "You can't switch off your own account.")
        else:
            user.is_active = False
            user.save(update_fields=["is_active"])
            messages.success(request, f"{user.username} can no longer sign in.")
    elif action == "activate":
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, f"{user.username} can sign in again.")
    elif action == "reset":
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data["password"])
            if hasattr(user, "is_new_employee"):
                user.is_new_employee = True
            user.save()
            messages.success(request, f"Password reset. {user.username} will choose a new one at their next sign-in.")
        else:
            messages.error(request, " ".join(form.errors.get("password", ["Choose a stronger password."])))
    return redirect("rm-staff")
