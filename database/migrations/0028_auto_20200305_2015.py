# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-03-05 20:15
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0027_auto_20200304_2234'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='relativeschedule',
            name='participant',
        ),
        migrations.RemoveField(
            model_name='survey',
            name='schedule_type',
        ),
    ]
