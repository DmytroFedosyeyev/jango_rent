from django import forms
from .models import Expense, MeterReading

class ExpenseForm(forms.ModelForm):
 class Meta:
     model = Expense
     fields = ['category', 'amount', 'date', 'paid']
     widgets = {
         'date': forms.DateInput(attrs={'type': 'date'}),
         'category': forms.Select(),
         'amount': forms.NumberInput(attrs={'step': '0.01'}),
     }


class MeterReadingForm(forms.Form):  # Изменили на Form, так как не привязываем к модели напрямую
    electricity_usage = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, label='Электричество (кВт·ч)'
    )
    cold_water_usage = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, label='Холодная вода (м³)'
    )
    hot_water_usage = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, label='Горячая вода (м³)'
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Дата'
    )