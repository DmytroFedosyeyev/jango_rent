from django.contrib import admin
from .models import Expense, MeterReading, RentRate

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'amount', 'debt', 'date', 'paid')
    list_filter = ('category', 'paid', 'date')
    search_fields = ('user__username',)

@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'value', 'date')
    list_filter = ('category', 'date')
    search_fields = ('user__username',)

@admin.register(RentRate)
class RentRateAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'start_date')
    list_filter = ('start_date',)
    search_fields = ('user__username',)
