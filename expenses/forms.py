from django import forms
from .models import Expense, MeterReading
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

class ExpenseForm(forms.ModelForm):
 class Meta:
     model = Expense
     fields = ['category', 'amount', 'date', 'paid']
     widgets = {
         'date': forms.DateInput(attrs={'type': 'date'}),
         'category': forms.Select(),
         'amount': forms.NumberInput(attrs={'step': '0.01'}),
     }


class MeterReadingForm(forms.Form):
    electricity_usage = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        label=_("Electricity (kWh)")
    )
    cold_water_usage = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        label=_("Cold water (m³)")
    )
    hot_water_usage = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        label=_("Hot water (m³)")
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label=_("Date")
    )


class EditSingleReadingForm(forms.ModelForm):
    class Meta:
        model = MeterReading
        fields = ['category', 'value', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'value': forms.NumberInput(attrs={'step': '0.01'}),
        }
        labels = {
            'category': 'Категория',
            'value': 'Значение',
            'date': 'Дата',
        }


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, label='Email')

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
