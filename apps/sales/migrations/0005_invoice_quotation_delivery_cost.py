from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0004_sales_distribution_workflow"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="delivery_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                max_digits=18,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="salesquotation",
            name="delivery_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                max_digits=18,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
    ]
