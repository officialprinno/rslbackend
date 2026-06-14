"""Django admin for sales module."""

from django.contrib import admin

from apps.sales.models import (
    CreditNote,
    Customer,
    CustomerPayment,
    SalesInvoice,
    SalesOrder,
    SalesQuotation,
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "mine_name", "tin_number", "country", "is_active", "created_at"]
    search_fields = ["name", "tin_number", "email", "mine_name"]
    list_filter = ["country", "is_active", "payment_terms"]


@admin.register(SalesQuotation)
class SalesQuotationAdmin(admin.ModelAdmin):
    list_display = ["quotation_number", "customer", "status", "total_amount", "valid_until"]
    search_fields = ["quotation_number", "customer__name"]
    list_filter = ["status"]


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ["so_number", "customer", "status", "delivery_status", "total_amount"]
    search_fields = ["so_number", "lpo_number"]
    list_filter = ["status", "delivery_status", "payment_status"]


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = ["invoice_number", "customer", "status", "total_amount", "due_date"]
    search_fields = ["invoice_number"]
    list_filter = ["status"]


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(admin.ModelAdmin):
    list_display = ["payment_number", "customer", "amount", "payment_date", "payment_method"]
    search_fields = ["payment_number", "reference_number"]


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ["cn_number", "customer", "amount", "status"]
    search_fields = ["cn_number"]
