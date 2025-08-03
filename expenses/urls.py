from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('add/', views.add_expense, name='add_expense'),
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('filter/', views.filter_expenses, name='filter_expenses'),
    path('overview/', views.overview, name='overview'),
    path('pay/<str:category>/', views.pay_expense, name='pay_expense'),
    path('meter/edit/<int:pk>/', views.edit_meter_reading, name='edit_meter_reading'),
    path('pay_all/', views.pay_all_expenses, name='pay_all_expenses'),
    path('add-expense-modal/', views.add_expense_modal, name='add_expense_modal'),
    path('month/<int:year>/<int:month>/', views.monthly_expenses, name='monthly_expenses'),
    path('export/pdf/', views.export_to_pdf, name='export_to_pdf'),
    path('readings/', views.meter_reading_list, name='meter_readings_list'),
    path('readings/edit/<int:pk>/', views.edit_all_list, name='edit_meter_reading'),
]
