import getpass
from django.core.management.base import BaseCommand, CommandError
from apps.accounts.models import User, UserRole


class Command(BaseCommand):
    help = 'Creates a platform ADMIN user with superuser rights. Admin accounts cannot self-register via API.'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Admin email address')
        parser.add_argument('--password', type=str, help='Admin password')
        parser.add_argument('--phone', type=str, default='', help='Admin phone number (optional)')

    def handle(self, *args, **options):
        email = options.get('email')
        password = options.get('password')
        phone = options.get('phone')

        if not email:
            email = input('Admin Email: ').strip()
        if not email:
            raise CommandError('Email is required.')

        if not password:
            password = getpass.getpass('Admin Password: ')
            confirm_password = getpass.getpass('Confirm Password: ')
            if password != confirm_password:
                raise CommandError('Passwords do not match.')

        if not password or len(password) < 8:
            raise CommandError('Password must be at least 8 characters long.')

        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f'User with email {email} already exists.')

        user = User.objects.create_superuser(
            email=email,
            password=password,
            role=UserRole.ADMIN,
            phone_number=phone or None,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created ADMIN user: {user.email} (ID: {user.id})'
            )
        )
