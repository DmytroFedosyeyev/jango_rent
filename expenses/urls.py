from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('add/', views.add_expense, name='add_expense'),
    path('', views.home, name='home'),
    path('filter/', views.filter_expenses, name='filter_expenses'),
    path('overview/', views.overview, name='overview'),
    path('pay/<str:category>/', views.pay_expense, name='pay_expense'),
    path('meter/edit/<int:pk>/', views.edit_meter_reading, name='edit_meter_reading'),
]
