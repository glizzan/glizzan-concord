# Generated by Django 2.2.13 on 2021-04-19 18:55

import concord.utils.converters
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('resources', '0005_auto_20210405_2157'),
    ]

    operations = [
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('foundational_permission_enabled', models.BooleanField(default=False)),
                ('governing_permission_enabled', models.BooleanField(default=True)),
                ('name', models.CharField(max_length=200)),
                ('description', models.CharField(default='', max_length=200)),
                ('content', models.TextField(default='')),
                ('creator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='document_models', to=settings.AUTH_USER_MODEL)),
                ('owner_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='resources_document_owned_objects', to='contenttypes.ContentType')),
            ],
            options={
                'abstract': False,
            },
            bases=(concord.utils.converters.ConcordConverterMixin, models.Model),
        ),
    ]
