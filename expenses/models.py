from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

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
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Новое поле

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


class RentRate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rent_rates')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField()

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.amount} € с {self.start_date}"


class MonthlyUsage(models.Model):
    CATEGORY_CHOICES = [
        ('cold_water', 'Холодная вода'),
        ('hot_water', 'Горячая вода'),
        ('electricity', 'Электричество'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    year = models.IntegerField()
    month = models.IntegerField()
    usage = models.FloatField()

    class Meta:
        unique_together = ('user', 'category', 'year', 'month')
        ordering = ['year', 'month']

    def __str__(self):
        return f'{self.user.username} — {self.category} {self.month}/{self.year}: {self.usage}'
