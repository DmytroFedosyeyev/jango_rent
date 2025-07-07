from expenses.models import MeterReading, MonthlyUsage
from calendar import monthrange
from datetime import date
from django.db import transaction

@transaction.atomic
def process_category(category, user):
    readings = MeterReading.objects.filter(
        user=user,
        category=category,
    ).order_by('date')

    raw = {(r.date.year, r.date.month): r for r in readings}
    all_keys = sorted(raw.keys())
    if not all_keys:
        return []

    for i in range(len(all_keys) - 1):
        (y1, m1), (y2, m2) = all_keys[i], all_keys[i + 1]
        d1 = raw[(y1, m1)].date
        d2 = raw[(y2, m2)].date
        v1 = raw[(y1, m1)].value
        v2 = raw[(y2, m2)].value

        delta_months = (y2 - y1) * 12 + (m2 - m1)
        if delta_months <= 1:
            usage = round(v2 - v1, 2)
            MonthlyUsage.objects.update_or_create(
                user=user,
                category=category,
                year=y2,
                month=m2,
                defaults={'usage': usage}
            )
            continue

        avg_increase = (v2 - v1) / delta_months

        for j in range(1, delta_months):
            new_month = (m1 + j - 1) % 12 + 1
            new_year = y1 + (m1 + j - 1) // 12
            _, last_day = monthrange(new_year, new_month)
            new_date = date(new_year, new_month, last_day)
            new_value = round(v1 + avg_increase * j, 2)

            new_reading, created = MeterReading.objects.get_or_create(
                user=user,
                category=category,
                date=new_date,
                defaults={'value': new_value}
            )
            usage = round(avg_increase, 2)
            MonthlyUsage.objects.update_or_create(
                user=user,
                category=category,
                year=new_year,
                month=new_month,
                defaults={'usage': usage}
            )

    return list(raw.values())
