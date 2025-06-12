from django.db import models
from django.contrib.auth.models import User


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ('rent', 'Аренда'),
        ('utilities', 'Коммунальные'),
        ('electricity', 'Электричество'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expenses')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    debt = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Новое поле
    payment_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_category_display()} - {self.amount}€ ({self.date})"


class MeterReading(models.Model):
    CATEGORY_CHOICES = [
        ('electricity', 'Электричество (кВт·ч)'),
        ('cold_water', 'Холодная вода (м³)'),
        ('hot_water', 'Горячая вода (м³)'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meter_readings')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    value = models.DecimalField(max_digits=10, decimal_places=2)  # Показания
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_category_display()} - {self.value} ({self.date})"