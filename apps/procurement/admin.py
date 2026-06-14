from django.contrib import admin

from apps.procurement.models import (
    GoodsReceivedNote,
    PurchaseOrder,
    PurchaseRequisition,
    RequestForQuotation,
    Supplier,
    SupplierInvoice,
    SupplierQuotation,
)

admin.site.register(Supplier)
admin.site.register(PurchaseRequisition)
admin.site.register(RequestForQuotation)
admin.site.register(SupplierQuotation)
admin.site.register(PurchaseOrder)
admin.site.register(GoodsReceivedNote)
admin.site.register(SupplierInvoice)
