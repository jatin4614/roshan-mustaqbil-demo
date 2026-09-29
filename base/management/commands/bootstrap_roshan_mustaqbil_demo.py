"""Provision the administrator and centre record needed by a fresh demo.

The centre has one sign-in, the administrator, who does everything.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from base.models import Company
from employee.models import Employee, EmployeeWorkInformation
from horilla_auth.models import HorillaUser

# Demo staff accounts made by earlier versions of this command.
OLD_DEMO_STAFF = ("desk", "coordinator")
OLD_DEMO_STAFF_DOMAIN = "@staff.rm.local"
from horilla_theme.models import CompanyTheme, HorillaColorTheme


class Command(BaseCommand):
    help = "Create the initial Roshan Mustaqbil administrator and company safely."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=os.environ.get("DEMO_ADMIN_PASSWORD"),
            help="Initial admin password (defaults to DEMO_ADMIN_PASSWORD).",
        )
        parser.add_argument(
            "--username",
            default=os.environ.get("DEMO_ADMIN_USERNAME", "admin"),
            help="Initial admin username (defaults to DEMO_ADMIN_USERNAME or admin).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        username = options["username"]
        if not password:
            raise CommandError("Set DEMO_ADMIN_PASSWORD before bootstrapping the demo.")

        company = Company.objects.filter(company="Roshan Mustaqbil").first()
        if company is None:
            company = Company.objects.create(
                company="Roshan Mustaqbil",
                address="Kupwara, Jammu and Kashmir",
                hq=True,
                country="India",
                state="Jammu and Kashmir",
                city="Kupwara",
                zip="193222",
            )
        if not company.hq:
            company.hq = True
            company.save(update_fields=["hq"])

        # A calm teal scale avoids the inherited coral HR theme and gives RM
        # dashboards, navigation and actions a consistent visual language.
        theme_defaults = {
            "description": "Roshan Mustaqbil calm teal and navy theme.",
            "primary_50": "#F0FDFA", "primary_100": "#CCFBF1",
            "primary_200": "#99F6E4", "primary_300": "#5EEAD4",
            "primary_400": "#2DD4BF", "primary_500": "#14B8A6",
            "primary_600": "#0F766E", "primary_700": "#115E59",
            "primary_800": "#134E4A", "primary_900": "#042F2E",
            "dark_50": "#F8FAFC", "dark_100": "#E2E8F0",
            "dark_200": "#CBD5E1", "dark_300": "#64748B",
            "dark_400": "#475569", "dark_500": "#334155", "dark_600": "#172033",
            "secondary_50": "#EFF6FF", "secondary_100": "#DBEAFE",
            "secondary_200": "#BFDBFE", "secondary_300": "#93C5FD",
            "secondary_400": "#60A5FA", "secondary_500": "#335C8A",
            "secondary_600": "#274C77", "secondary_700": "#1E3A5F",
        }
        theme, _ = HorillaColorTheme.objects.update_or_create(
            name="Roshan Mustaqbil Teal", defaults=theme_defaults
        )
        CompanyTheme.objects.update_or_create(company=company, defaults={"theme": theme})

        email = "admin@roshanmustaqbil.demo"
        user, created_user = HorillaUser.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        if created_user:
            user.set_password(password)
            user.save(update_fields=["password"])
        elif not user.is_staff or not user.is_superuser or not user.is_active:
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save(update_fields=["is_staff", "is_superuser", "is_active"])

        employee, _ = Employee.objects.get_or_create(
            employee_user_id=user,
            defaults={
                "badge_id": "RM-ADMIN-001",
                "employee_first_name": "Roshan",
                "employee_last_name": "Mustaqbil Admin",
                "email": email,
                "phone": "7000000000",
            },
        )
        work_info, _ = EmployeeWorkInformation.objects.get_or_create(
            employee_id=employee
        )
        work_info.company_id = company
        work_info.date_joining = work_info.date_joining or timezone.localdate()
        work_info.email = work_info.email or employee.email
        work_info.mobile = work_info.mobile or employee.phone
        work_info.save()

        removed = self._remove_old_demo_staff(username)
        self.stdout.write(
            self.style.SUCCESS(
                f"Roshan Mustaqbil is ready. Sign in as {username}; it is the only account."
                + (f" Removed the old demo accounts: {', '.join(removed)}." if removed else "")
            )
        )

    def _remove_old_demo_staff(self, admin_username):
        removed = []
        old = HorillaUser.objects.filter(username__in=OLD_DEMO_STAFF, email__endswith=OLD_DEMO_STAFF_DOMAIN).exclude(username=admin_username)
        for user in old:
            try:
                Employee.objects.filter(employee_user_id=user).delete()
                user.delete()
            except ProtectedError:
                user.is_active = False
                user.save(update_fields=["is_active"])
            removed.append(user.username)
        return removed
