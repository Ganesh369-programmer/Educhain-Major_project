# Generated manually during StudentProfile relocation from apps.credentials → apps.students.
# The physical DB table name (student_profiles) is UNCHANGED — this migration simply
# re-declares ownership of the table under the students app label.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('full_name', models.CharField(max_length=255)),
                ('roll_number', models.CharField(blank=True, max_length=100, null=True)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('wallet_address', models.CharField(blank=True, max_length=42, null=True)),
                ('public_profile_enabled', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    limit_choices_to={'role': 'STUDENT'},
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='student_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'student profile',
                'verbose_name_plural': 'student profiles',
                'db_table': 'student_profiles',
                'ordering': ['-created_at'],
            },
        ),
    ]
