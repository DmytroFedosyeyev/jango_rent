import logging
from django.shortcuts import render, redirect, get_object_or_404
from .forms import ExpenseForm, MeterReadingForm, RegisterForm
from .models import Expense, MeterReading
from django.contrib.auth.decorators import login_required
from datetime import date
from django.db.models import Sum
from django.http import HttpResponseBadRequest
from django.urls import reverse
from .forms import EditSingleReadingForm
from django.contrib import messages
from datetime import date, datetime, timedelta
from calendar import monthrange
from decimal import Decimal
from django.db.models import Sum
from django.db import transaction
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import MeterReading, Expense
from .models import RentRate



logger = logging.getLogger(__name__)

@login_required
def add_expense(request):
    if request.method == 'POST':
        expense_form = ExpenseForm(request.POST, prefix='expense')
        meter_form = MeterReadingForm(request.POST, prefix='meter')

        expense_valid = expense_form.is_valid()
        meter_valid = meter_form.is_valid()

        if expense_valid or meter_valid:
            if expense_valid:
                expense = expense_form.save(commit=False)
                expense.user = request.user

                if expense.category == 'rent':
                    # Берём актуальную ставку аренды на дату расхода
                    rent_rate = RentRate.objects.filter(
                        user=request.user,
                        start_date__lte=expense.date
                    ).order_by('-start_date').first()

                    if rent_rate:
                        expense.amount = rent_rate.amount
                    else:
                        messages.warning(request, 'Не найдена ставка аренды. Добавьте её в RentRate.')
                        return redirect('expenses:add_expense')

                expense.debt = expense.amount
                expense.save()
                logger.debug(f"Saved expense: {expense}")

            if meter_valid:
                date_ = meter_form.cleaned_data['date']
                electricity_usage = meter_form.cleaned_data['electricity_usage']
                cold_water_usage = meter_form.cleaned_data['cold_water_usage']
                hot_water_usage = meter_form.cleaned_data['hot_water_usage']

                if electricity_usage is not None:
                    MeterReading.objects.create(
                        user=request.user,
                        category='electricity',
                        value=electricity_usage,
                        date=date_
                    )
                    logger.debug(f"Saved electricity reading: {electricity_usage} kWh")
                if cold_water_usage is not None:
                    MeterReading.objects.create(
                        user=request.user,
                        category='cold_water',
                        value=cold_water_usage,
                        date=date_
                    )
                    logger.debug(f"Saved cold water reading: {cold_water_usage} m³")
                if hot_water_usage is not None:
                    MeterReading.objects.create(
                        user=request.user,
                        category='hot_water',
                        value=hot_water_usage,
                        date=date_
                    )
                    logger.debug(f"Saved hot water reading: {hot_water_usage} m³")

            return redirect('expenses:home')
    else:
        expense_form = ExpenseForm(prefix='expense')
        meter_form = MeterReadingForm(prefix='meter')

    return render(request, 'add_expense.html', {
        'expense_form': expense_form,
        'meter_form': meter_form
    })

@login_required
def home(request):
    today = date.today()
    current_month = today.month
    current_year = today.year
    start_of_month = today.replace(day=1)

    expenses = Expense.objects.filter(
        user=request.user,
        date__month=current_month,
        date__year=current_year
    )

    rent_expense = expenses.filter(category='rent').first()
    utilities_expense = expenses.filter(category='utilities').first()
    electricity_expense = expenses.filter(category='electricity').first()

    rent = rent_expense.amount if rent_expense else 0
    utilities = utilities_expense.amount if utilities_expense else 0
    electricity = electricity_expense.amount if electricity_expense else 0

    total = Decimal(rent) + Decimal(utilities) + Decimal(electricity)

    # Долги
    past_expenses = Expense.objects.filter(
        user=request.user,
        date__lt=start_of_month
    )
    rent_debt = past_expenses.filter(category='rent').aggregate(total_debt=Sum('debt'))['total_debt'] or Decimal('0.00')
    utilities_debt = past_expenses.filter(category='utilities').aggregate(total_debt=Sum('debt'))['total_debt'] or Decimal('0.00')
    electricity_debt = past_expenses.filter(category='electricity').aggregate(total_debt=Sum('debt'))['total_debt'] or Decimal('0.00')
    total_debt = Decimal(rent_debt) + Decimal(utilities_debt) + Decimal(electricity_debt)

    # Календарь месяцев
    months = []
    for month in range(1, 13):
        start_date = date(2025, month, 1)
        _, last_day = monthrange(2025, month)
        end_date = date(2025, month, last_day)
        month_expenses = Expense.objects.filter(
            user=request.user,
            date__range=[start_date, end_date]
        )
        total_month_debt = month_expenses.aggregate(total_debt=Sum('debt'))['total_debt'] or Decimal('0.00')
        status = 'future' if month > current_month else ('paid' if total_month_debt == 0 else 'debt')
        months.append({
            'name': ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'][month-1],
            'status': status,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
        })

    context = {
        'current_month': today.strftime('%B'),
        'current_year': current_year,
        'rent': {
            'amount': rent,
            'date': rent_expense.date if rent_expense else None,
            'paid': rent_expense.paid if rent_expense else False,
            'payment_date': rent_expense.payment_date if rent_expense else None,
            'payment_amount': rent_expense.amount - rent_expense.debt if rent_expense else 0,
        },
        'utilities': {
            'amount': utilities,
            'date': utilities_expense.date if utilities_expense else None,
            'paid': utilities_expense.paid if utilities_expense else False,
            'payment_date': utilities_expense.payment_date if utilities_expense else None,
            'payment_amount': utilities_expense.amount - utilities_expense.debt if utilities_expense else 0,
        },
        'electricity': {
            'amount': electricity,
            'date': electricity_expense.date if electricity_expense else None,
            'paid': electricity_expense.paid if electricity_expense else False,
            'payment_date': electricity_expense.payment_date if electricity_expense else None,
            'payment_amount': electricity_expense.amount - electricity_expense.debt if electricity_expense else 0,
        },
        'total': total,
        'debt': {
            'rent': rent_debt,
            'utilities': utilities_debt,
            'electricity': electricity_debt,
            'total': total_debt,
        },
        'months': months,
    }
    return render(request, 'home.html', context)

@login_required
def filter_expenses(request):
    logger.debug(f"Session before: {request.session.items()}")

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date and end_date:
        request.session['filter_start_date'] = start_date
        request.session['filter_end_date'] = end_date
        request.session.modified = True
        logger.debug(f"Saved to session: start_date={start_date}, end_date={end_date}")
    else:
        start_date = request.session.get('filter_start_date')
        end_date = request.session.get('filter_end_date')
        logger.debug(f"Loaded from session: start_date={start_date}, end_date={end_date}")

    expenses = Expense.objects.filter(user=request.user)

    if start_date and end_date:
        expenses = expenses.filter(date__range=[start_date, end_date])

    rent_expense = expenses.filter(category='rent').first()
    utilities_expense = expenses.filter(category='utilities').first()
    electricity_expense = expenses.filter(category='electricity').first()

    rent = {
        'amount': rent_expense.amount if rent_expense else 0,
        'debt': rent_expense.debt if rent_expense else 0,
        'date': rent_expense.date if rent_expense else None,
        'paid': rent_expense.paid if rent_expense else False,
        'payment_date': rent_expense.payment_date if rent_expense else None,
        'payment_amount': rent_expense.payment_amount if rent_expense else 0,
    }
    utilities = {
        'amount': utilities_expense.amount if utilities_expense else 0,
        'debt': utilities_expense.debt if utilities_expense else 0,
        'date': utilities_expense.date if utilities_expense else None,
        'paid': utilities_expense.paid if utilities_expense else False,
        'payment_date': utilities_expense.payment_date if utilities_expense else None,
        'payment_amount': utilities_expense.payment_amount if utilities_expense else 0,
    }
    electricity = {
        'amount': electricity_expense.amount if electricity_expense else 0,
        'debt': electricity_expense.debt if electricity_expense else 0,
        'date': electricity_expense.date if electricity_expense else None,
        'paid': electricity_expense.paid if electricity_expense else False,
        'payment_date': electricity_expense.payment_date if electricity_expense else None,
        'payment_amount': electricity_expense.payment_amount if electricity_expense else 0,
    }

    total = Decimal(rent['amount']) + Decimal(utilities['amount']) + Decimal(electricity['amount'])
    total_debt = Decimal(rent['debt']) + Decimal(utilities['debt']) + Decimal(electricity['debt'])

    # Получаем показания счетчиков за выбранный период
    meter_readings = MeterReading.objects.filter(
        user=request.user,
        date__range=[start_date, end_date]
    ).order_by('date', 'category')

    context = {
        'start_date': start_date,
        'end_date': end_date,
        'rent': rent,
        'utilities': utilities,
        'electricity': electricity,
        'total': total,
        'total_debt': total_debt,
        'meter_readings': meter_readings,
    }

    logger.debug(f"Session after: {request.session.items()}")
    return render(request, 'filter_expenses.html', context)

@login_required
def edit_meter_reading(request, pk):
    reading = get_object_or_404(MeterReading, pk=pk, user=request.user)

    if request.method == 'POST':
        form = EditSingleReadingForm(request.POST, instance=reading)
        if form.is_valid():
            form.save()
            return redirect('expenses:filter_expenses')
    else:
        form = EditSingleReadingForm(instance=reading)

    return render(request, 'edit_meter_reading.html', {'form': form})

@login_required
def overview(request):
    user = request.user
    today = date.today()
    current_year = today.year

    categories = ['electricity', 'cold_water', 'hot_water']
    months = [date(current_year, m, 1) for m in range(1, 13)]

    # Получаем все показания до и включая декабрь предыдущего года и текущий год
    readings = MeterReading.objects.filter(
        user=user,
        date__lte=date(current_year, 12, 31),
        category__in=categories
    ).order_by('category', 'date')

    readings_by_cat = {cat: [] for cat in categories}
    for r in readings:
        readings_by_cat[r.category].append(r)

    # Обработка и заполнение пропусков
    @transaction.atomic
    def process_category(category):
        data = readings_by_cat[category]
        filled = {}

        # Словарь: (год, месяц) -> показание
        raw = {(r.date.year, r.date.month): r for r in data}

        # Найдём крайние даты
        all_keys = sorted(raw.keys())
        if not all_keys:
            return []  # нет данных вообще

        # Добавим показания на каждое начало месяца, если не хватает — интерполируем
        for i in range(len(all_keys) - 1):
            (y1, m1), (y2, m2) = all_keys[i], all_keys[i + 1]
            d1 = raw[(y1, m1)].date
            d2 = raw[(y2, m2)].date
            v1 = raw[(y1, m1)].value
            v2 = raw[(y2, m2)].value

            delta_months = (y2 - y1) * 12 + (m2 - m1)
            if delta_months <= 1:
                continue  # нет пропусков

            avg_increase = (v2 - v1) / delta_months

            for j in range(1, delta_months):
                new_month = (m1 + j - 1) % 12 + 1
                new_year = y1 + (m1 + j - 1) // 12
                _, last_day = monthrange(new_year, new_month)
                new_date = date(new_year, new_month, last_day)
                new_value = v1 + avg_increase * j

                # Добавим в базу
                new_reading = MeterReading.objects.create(
                    user=user,
                    category=category,
                    value=round(new_value, 2),
                    date=new_date
                )
                raw[(new_year, new_month)] = new_reading

        # Снова отсортируем
        sorted_keys = sorted([k for k in raw if k[0] == current_year])
        usage = []
        for i in range(len(sorted_keys)):
            y, m = sorted_keys[i]
            curr = raw[(y, m)]
            prev_key = (y, m - 1) if m > 1 else (y - 1, 12)
            if prev_key not in raw:
                usage.append(0)
                continue
            prev = raw[prev_key]
            diff = round(float(curr.value - prev.value), 2)
            usage.append(diff if diff >= 0 else 0)

        return usage

    electricity_data = process_category('electricity')
    cold_water_data = process_category('cold_water')
    hot_water_data = process_category('hot_water')

    def compute_stats(data):
        filtered = [d for d in data if d > 0]
        if not filtered:
            return {'min': 0, 'max': 0, 'avg': 0}
        return {
            'min': min(filtered),
            'max': max(filtered),
            'avg': round(sum(filtered) / len(filtered), 2),
        }

    month_labels = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                    'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']

    # последние расходы для таблицы
    recent_expenses = Expense.objects.filter(user=user).order_by('-date')[:5]
    total_all_time = Expense.objects.filter(user=user).aggregate(total=Sum('amount'))['total'] or 0
    total_year = Expense.objects.filter(user=user, date__year=current_year).aggregate(total=Sum('amount'))['total'] or 0

    context = {
        'current_month': today.strftime('%B'),
        'current_year': current_year,
        'recent_expenses': recent_expenses,
        'total_all_time': total_all_time,
        'total_year': total_year,
        'chart_months': month_labels,
        'electricity_data': electricity_data,
        'cold_water_data': cold_water_data,
        'hot_water_data': hot_water_data,
        'electricity_stats': compute_stats(electricity_data),
        'cold_water_stats': compute_stats(cold_water_data),
        'hot_water_stats': compute_stats(hot_water_data),
    }
    return render(request, 'overview.html', context)


@login_required
def pay_all_expenses(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("Некорректный запрос")

    try:
        amount = Decimal(request.POST.get('amount', '0.00'))
        payment_date = request.POST.get('payment_date')
        start_date = request.session.get('filter_start_date')
        end_date = request.session.get('filter_end_date')

        if amount <= 0 or not payment_date:
            raise ValueError
    except (ValueError, TypeError):
        return HttpResponseBadRequest("Некорректная сумма или дата оплаты")

    user = request.user
    remaining = amount
    categories = ['rent', 'utilities', 'electricity']

    # 1. Погашаем текущие расходы
    for category in categories:
        expenses = Expense.objects.filter(
            user=user,
            category=category,
            date__range=[start_date, end_date]
        ).order_by('date')

        for expense in expenses:
            if remaining <= 0:
                break
            to_pay = min(remaining, expense.debt)
            expense.debt -= to_pay
            expense.payment_amount += to_pay
            if expense.debt <= 0:
                expense.debt = Decimal('0.00')
                expense.paid = True
            expense.payment_date = payment_date
            expense.save()
            remaining -= to_pay

    # 2. Закрываем долги за прошлые месяцы
    if remaining > 0:
        past_expenses = Expense.objects.filter(
            user=user,
            date__lt=start_date,
            debt__gt=0
        ).order_by('date')

        for expense in past_expenses:
            if remaining <= 0:
                break
            to_pay = min(expense.debt, remaining)
            expense.debt -= to_pay
            expense.payment_amount += to_pay
            if expense.debt <= 0:
                expense.debt = Decimal('0.00')
                expense.paid = True
            expense.payment_date = payment_date
            expense.save()
            remaining -= to_pay

    # 3. Перенос излишков на будущие месяцы (максимум на 24 месяца вперёд)
    month_offset = 1
    while remaining > 0 and month_offset <= 24:
        next_month = (date.today().replace(day=1) + timedelta(days=32 * month_offset)).replace(day=1)

        for category in categories:
            if remaining <= 0:
                break

            # Пытаемся найти расход
            expense = Expense.objects.filter(
                user=user,
                category=category,
                date__year=next_month.year,
                date__month=next_month.month
            ).first()

            if not expense and category == 'rent':
                # Получаем актуальную ставку аренды
                rent_rate = RentRate.objects.filter(
                    user=user,
                    start_date__lte=next_month
                ).order_by('-start_date').first()

                if rent_rate:
                    expense = Expense.objects.create(
                        user=user,
                        category='rent',
                        amount=rent_rate.amount,
                        debt=rent_rate.amount,
                        paid=False,
                        date=next_month
                    )

            if expense:
                to_pay = min(expense.debt, remaining)
                expense.debt -= to_pay
                expense.payment_amount += to_pay
                if expense.debt <= 0:
                    expense.debt = Decimal('0.00')
                    expense.paid = True
                expense.payment_date = payment_date
                expense.save()
                remaining -= to_pay
            else:
                # если расходы не найдены и не аренда — не создаём, переносим остаток дальше
                continue

        month_offset += 1

    # Сохраняем сессию фильтра и редиректим
    if start_date and end_date:
        request.session['filter_start_date'] = start_date
        request.session['filter_end_date'] = end_date
        request.session.modified = True

    messages.success(request, f"Оплата прошла. Распределено: {amount - remaining:.2f} €. Остаток: {remaining:.2f} € перенесён.")
    if start_date and end_date:
        return redirect(f"{reverse('expenses:filter_expenses')}?start_date={start_date}&end_date={end_date}")
    return redirect('expenses:home')


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Регистрация прошла успешно. Теперь войдите в систему.')
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'register.html', {'form': form})


from django.shortcuts import render

def welcome(request):
    if request.user.is_authenticated:
        return redirect('expenses:home')  # если вошел — на домашнюю
    return render(request, 'welcome.html')


@login_required
def pay_expense(request, category):
    if request.method == 'POST':
        amount = request.POST.get('amount')
        payment_date = request.POST.get('payment_date')

        if not amount or not payment_date:
            return HttpResponseBadRequest("Некорректная сумма или дата оплаты")

        try:
            amount = Decimal(amount)
            if amount <= 0:
                raise ValueError
        except:
            return HttpResponseBadRequest("Некорректная сумма")

        # Период фильтра
        start_date = request.session.get('filter_start_date')
        end_date = request.session.get('filter_end_date')

        expenses = Expense.objects.filter(user=request.user, category=category)
        if start_date and end_date:
            expenses = expenses.filter(date__range=[start_date, end_date])
        expense = expenses.first()

        if expense:
            paid_part = min(expense.debt, amount)
            expense.debt -= paid_part
            if expense.debt <= 0:
                expense.debt = Decimal('0.00')
                expense.paid = True
            expense.payment_date = payment_date
            expense.save()
        else:
            Expense.objects.create(
                user=request.user,
                category=category,
                amount=amount,
                debt=Decimal('0.00'),
                payment_date=payment_date,
                date=payment_date,
                paid=True
            )

        # Возврат на нужную страницу
        if start_date and end_date:
            return redirect(f"{reverse('expenses:filter_expenses')}?start_date={start_date}&end_date={end_date}")
        else:
            return redirect('expenses:home')

    return HttpResponseBadRequest("Некорректный метод запроса")