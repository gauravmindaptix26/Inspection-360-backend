from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inspection', '0011_user_is_staff_alter_user_is_active'),
    ]

    operations = [
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('image', models.TextField(blank=True, null=True)),
                ('department', models.CharField(blank=True, max_length=255, null=True)),
                ('dob', models.DateField(blank=True, null=True)),
                ('projects', models.TextField(blank=True, null=True)),
                ('designation', models.CharField(blank=True, max_length=255, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('mobile_no', models.CharField(blank=True, max_length=20, null=True)),
                ('address', models.TextField(blank=True, null=True)),
                ('salary', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('leave_balance', models.PositiveIntegerField(default=0)),
                ('joining_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('createdAt', models.DateTimeField(auto_now_add=True)),
                ('updatedAt', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'employee',
                'ordering': ['-createdAt'],
            },
        ),
    ]
