from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from accounts.models import User


class Command(BaseCommand):
    help = (
        "Create an admin account. This is the ONLY way to make an admin: "
        "there is no public admin sign-up."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", default="Administrator")
        parser.add_argument(
            "--password",
            help="Optional. If omitted you are asked for it (input is hidden).",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError("Enter a valid email address.")
        if User.objects.filter(email=email).exists():
            raise CommandError(f"An account with {email} already exists.")

        password = options["password"] or getpass("Password: ")
        candidate = User(email=email, name=options["name"])
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise CommandError("Weak password: " + " ".join(exc.messages))

        User.objects.create_admin(email=email, password=password, name=options["name"])
        self.stdout.write(self.style.SUCCESS(f"Admin created: {email}"))
