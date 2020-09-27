# Generated by Django 2.2.4 on 2020-09-23 19:46

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('conditionals', '0004_auto_20200920_1424'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConsensusCondition',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('foundational_permission_enabled', models.BooleanField(default=False)),
                ('governing_permission_enabled', models.BooleanField(default=True)),
                ('action', models.IntegerField()),
                ('source_id', models.CharField(max_length=20)),
                ('resolved', models.BooleanField(default=False)),
                ('is_strict', models.BooleanField(default=False)),
                ('responses', models.CharField(default='{}', max_length=500)),
                ('minimum_duration', models.IntegerField(default=48)),
                ('discussion_starts', models.DateTimeField(default=django.utils.timezone.now)),
                ('creator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='consensuscondition_models', to=settings.AUTH_USER_MODEL)),
                ('owner_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='conditionals_consensuscondition_owned_objects', to='contenttypes.ContentType')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
