# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-02-19 05:56
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("flowcells", "0009_auto_20190206_0941")]

    operations = [
        migrations.AddField(
            model_name="flowcell",
            name="cache_index_errors",
            field=django.contrib.postgres.fields.jsonb.JSONField(
                blank=True, default=None, null=True
            ),
        ),
        migrations.AddField(
            model_name="flowcell",
            name="cache_reverse_index_errors",
            field=django.contrib.postgres.fields.jsonb.JSONField(
                blank=True, default=None, null=True
            ),
        ),
        migrations.AddField(
            model_name="flowcell",
            name="cache_sample_sheet_errors",
            field=django.contrib.postgres.fields.jsonb.JSONField(
                blank=True, default=None, null=True
            ),
        ),
        migrations.AddField(
            model_name="flowcell",
            name="error_caches_version",
            field=models.IntegerField(blank=True, default=None, null=True),
        ),
    ]
