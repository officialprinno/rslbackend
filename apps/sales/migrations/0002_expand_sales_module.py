# Generated manually for Rock Solutions FMS sales module expansion

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


def populate_customer_defaults(apps, schema_editor):
    Customer = apps.get_model("sales", "Customer")
    Currency = apps.get_model("core", "Currency")

    default_currency = Currency.objects.filter(is_default=True).order_by("id").first()
    if default_currency is None:
        default_currency = Currency.objects.order_by("id").first()
    if default_currency is None:
        return

    for customer in Customer.objects.all().iterator():
        customer.mine_name = customer.name
        customer.currency_id = default_currency.id
        customer.save(update_fields=["mine_name", "currency_id"])


def reverse_populate_customer_defaults(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0001_initial"),
        ("core", "0002_initial"),
        ("users", "0001_initial"),
        ("inventory", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="registration_number",
            field=models.CharField(blank=True, default="", max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="tin_number",
            field=models.CharField(default="", max_length=50),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="vat_number",
            field=models.CharField(blank=True, default="", max_length=50),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="email",
            field=models.EmailField(default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="phone",
            field=models.CharField(default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="address",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="city",
            field=models.CharField(blank=True, default="", max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="country",
            field=models.CharField(default="Tanzania", max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="mine_name",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="mine_location",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="mine_type",
            field=models.CharField(
                choices=[
                    ("UNDERGROUND", "Underground"),
                    ("OPEN_PIT", "Open Pit"),
                    ("BOTH", "Both"),
                ],
                default="UNDERGROUND",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="contact_person",
            field=models.CharField(blank=True, default="", max_length=150),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="contact_phone",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="currency",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="customers",
                to="core.currency",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="credit_limit",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="customer",
            name="payment_terms",
            field=models.CharField(
                choices=[
                    ("IMMEDIATE", "Immediate"),
                    ("NET_15", "Net 15"),
                    ("NET_30", "Net 30"),
                    ("NET_60", "Net 60"),
                ],
                default="NET_30",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(
            populate_customer_defaults,
            reverse_populate_customer_defaults,
        ),
        migrations.AlterField(
            model_name="customer",
            name="currency",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="customers",
                to="core.currency",
            ),
        ),
        migrations.CreateModel(
            name="SalesQuotation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "quotation_number",
                    models.CharField(editable=False, max_length=30, unique=True),
                ),
                (
                    "exchange_rate",
                    models.DecimalField(
                        decimal_places=6, default=Decimal("1"), max_digits=18
                    ),
                ),
                ("valid_until", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("SENT", "Sent"),
                            ("ACCEPTED", "Accepted"),
                            ("REJECTED", "Rejected"),
                            ("EXPIRED", "Expired"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("apply_vat", models.BooleanField(default=True)),
                (
                    "subtotal",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "discount_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "tax_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "total_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("terms_conditions", models.TextField(blank=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sales_quotations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "currency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sales_quotations",
                        to="core.currency",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="quotations",
                        to="sales.customer",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SalesOrder",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "so_number",
                    models.CharField(editable=False, max_length=30, unique=True),
                ),
                ("lpo_number", models.CharField(blank=True, max_length=100)),
                ("lpo_date", models.DateField(blank=True, null=True)),
                (
                    "exchange_rate",
                    models.DecimalField(
                        decimal_places=6, default=Decimal("1"), max_digits=18
                    ),
                ),
                ("delivery_date", models.DateField()),
                ("delivery_address", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("CONFIRMED", "Confirmed"),
                            ("PROCESSING", "Processing"),
                            ("PARTIAL", "Partial"),
                            ("DELIVERED", "Delivered"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                (
                    "delivery_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("PROCESSING", "Processing"),
                            ("PARTIAL", "Partial"),
                            ("DELIVERED", "Delivered"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                (
                    "payment_status",
                    models.CharField(
                        choices=[
                            ("UNPAID", "Unpaid"),
                            ("PARTIAL", "Partial"),
                            ("PAID", "Paid"),
                        ],
                        default="UNPAID",
                        max_length=20,
                    ),
                ),
                ("apply_vat", models.BooleanField(default=True)),
                (
                    "subtotal",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "discount_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "tax_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "total_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("cancel_reason", models.TextField(blank=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_orders_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sales_orders_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "currency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sales_orders",
                        to="core.currency",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sales_orders",
                        to="sales.customer",
                    ),
                ),
                (
                    "quotation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_orders",
                        to="sales.salesquotation",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SalesInvoice",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "invoice_number",
                    models.CharField(editable=False, max_length=30, unique=True),
                ),
                (
                    "exchange_rate",
                    models.DecimalField(
                        decimal_places=6, default=Decimal("1"), max_digits=18
                    ),
                ),
                (
                    "invoice_date",
                    models.DateField(default=django.utils.timezone.now),
                ),
                ("due_date", models.DateField()),
                (
                    "subtotal",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "discount_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "tax_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "total_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "paid_amount",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("SENT", "Sent"),
                            ("PARTIAL", "Partial"),
                            ("PAID", "Paid"),
                            ("OVERDUE", "Overdue"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("tra_receipt_number", models.CharField(blank=True, max_length=100)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sales_invoices",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "currency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sales_invoices",
                        to="core.currency",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invoices",
                        to="sales.customer",
                    ),
                ),
                (
                    "sales_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoices",
                        to="sales.salesorder",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SalesQuotationItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=18,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.0001"))
                        ],
                    ),
                ),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=18)),
                (
                    "discount_percent",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        max_digits=5,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0")),
                            django.core.validators.MaxValueValidator(Decimal("100")),
                        ],
                    ),
                ),
                (
                    "total_price",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sales_quotation_lines",
                        to="inventory.item",
                    ),
                ),
                (
                    "quotation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="sales.salesquotation",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="SalesOrderItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity_ordered",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=18,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.0001"))
                        ],
                    ),
                ),
                (
                    "quantity_delivered",
                    models.DecimalField(
                        decimal_places=4, default=Decimal("0"), max_digits=18
                    ),
                ),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=18)),
                (
                    "discount_percent",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=5
                    ),
                ),
                (
                    "total_price",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sales_order_lines",
                        to="inventory.item",
                    ),
                ),
                (
                    "sales_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="sales.salesorder",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="SalesOrderActivity",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("action", models.CharField(max_length=100)),
                ("details", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "sales_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activities",
                        to="sales.salesorder",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sales_activities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SalesInvoiceItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=18,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.0001"))
                        ],
                    ),
                ),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=18)),
                (
                    "discount_percent",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=5
                    ),
                ),
                (
                    "tax_rate",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("18"), max_digits=5
                    ),
                ),
                (
                    "total_price",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0"), max_digits=18
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="sales.salesinvoice",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invoice_lines",
                        to="inventory.item",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="CustomerPayment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "payment_number",
                    models.CharField(editable=False, max_length=30, unique=True),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=18,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01"))
                        ],
                    ),
                ),
                (
                    "payment_date",
                    models.DateField(default=django.utils.timezone.now),
                ),
                (
                    "payment_method",
                    models.CharField(
                        choices=[
                            ("CASH", "Cash"),
                            ("BANK_TRANSFER", "Bank Transfer"),
                            ("CHEQUE", "Cheque"),
                            ("MOBILE", "Mobile Money"),
                        ],
                        max_length=20,
                    ),
                ),
                ("reference_number", models.CharField(blank=True, max_length=100)),
                ("bank_name", models.CharField(blank=True, max_length=150)),
                ("notes", models.TextField(blank=True)),
                (
                    "currency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="customer_payments",
                        to="core.currency",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to="sales.customer",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to="sales.salesinvoice",
                    ),
                ),
                (
                    "received_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments_received",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-payment_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CreditNote",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "cn_number",
                    models.CharField(editable=False, max_length=30, unique=True),
                ),
                ("reason", models.TextField()),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=18,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01"))
                        ],
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("APPROVED", "Approved"),
                            ("APPLIED", "Applied"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="credit_notes_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="credit_notes_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="credit_notes",
                        to="sales.customer",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="credit_notes",
                        to="sales.salesinvoice",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
