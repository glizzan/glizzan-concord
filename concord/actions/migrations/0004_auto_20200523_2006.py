# Generated by Django 2.2.4 on 2020-05-23 20:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0003_auto_20200522_2015'),
    ]

    operations = [
        migrations.AlterField(
            model_name='actioncontainer',
            name='action_info',
            field=models.CharField(blank=True, max_length=2000, null=True),
        ),
    ]
