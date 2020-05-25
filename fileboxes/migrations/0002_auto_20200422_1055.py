# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2020-04-22 08:55
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("fileboxes", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fileboxaccountgrant",
            name="file_box",
            field=models.ForeignKey(
                help_text="The file box that this audit entry belongs to",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="account_grants",
                to="fileboxes.FileBox",
            ),
        ),
        migrations.AlterField(
            model_name="fileboxauditentry",
            name="file_box",
            field=models.ForeignKey(
                help_text="The file box that this audit entry belongs to",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="audit_entries",
                to="fileboxes.FileBox",
            ),
        ),
    ]
