import logging
from django.shortcuts import render, redirect, get_object_or_404
from .forms import ExpenseForm, MeterReadingForm, RegisterForm
from .models import Expense, MeterReading
from django.contrib.auth.decorators import login_required
from datetime import date
from django.db.models import Sum
from django.http import HttpResponseBadRequest
from django.urls import reverse
from decimal import Decimal
from calendar import monthrange
from .forms import EditSingleReadingForm
from django.db.models import Avg, Max, Min
from django.contrib import messages


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
        },
        'utilities': {
            'amount': utilities,
            'date': utilities_expense.date if utilities_expense else None,
            'paid': utilities_expense.paid if utilities_expense else False,
        },
        'electricity': {
            'amount': electricity,
            'date': electricity_expense.date if electricity_expense else None,
            'paid': electricity_expense.paid if electricity_expense else False,
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

    rent = rent_expense.amount if rent_expense else 0
    rent_debt = rent_expense.debt if rent_expense else 0
    utilities = utilities_expense.amount if utilities_expense else 0
    utilities_debt = utilities_expense.debt if utilities_expense else 0
    electricity = electricity_expense.amount if electricity_expense else 0
    electricity_debt = electricity_expense.debt if electricity_expense else 0
    total = Decimal(rent) + Decimal(utilities) + Decimal(electricity)
    total_debt = Decimal(rent_debt) + Decimal(utilities_debt) + Decimal(electricity_debt)

    # Получаем показания счетчиков за выбранный период
    meter_readings = MeterReading.objects.filter(
        user=request.user,
        date__range=[start_date, end_date]
    ).order_by('date', 'category')

    context = {
        'start_date': start_date,
        'end_date': end_date,
        'rent': {
            'amount': rent,
            'debt': rent_debt,
            'date': rent_expense.date if rent_expense else None,
            'paid': rent_expense.paid if rent_expense else False,
            'expense': rent_expense,
        },
        'utilities': {
            'amount': utilities,
            'debt': utilities_debt,
            'date': utilities_expense.date if utilities_expense else None,
            'paid': utilities_expense.paid if utilities_expense else False,
            'expense': utilities_expense,
        },
        'electricity': {
            'amount': electricity,
            'debt': electricity_debt,
            'date': electricity_expense.date if electricity_expense else None,
            'paid': electricity_expense.paid if electricity_expense else False,
            'expense': electricity_expense,
        },
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
    today = date.today()
    year = today.year

    # Последние расходы
    expenses = Expense.objects.filter(user=request.user).order_by('-date')[:5]

    total_all_time = Expense.objects.filter(user=request.user).aggregate(total=Sum('amount'))['total'] or 0
    total_year = Expense.objects.filter(user=request.user, date__year=year).aggregate(total=Sum('amount'))['total'] or 0

    # Подсчёт месячного потребления (по разнице между показаниями)
    def get_monthly_usage(category, start_date, end_date):
        current = MeterReading.objects.filter(
            user=request.user,
            category=category,
            date__lte=end_date
        ).order_by('-date').first()

        previous = MeterReading.objects.filter(
            user=request.user,
            category=category,
            date__lt=start_date
        ).order_by('-date').first()

        if current and previous:
            return round(float(current.value - previous.value), 2)
        return 0.0

    months = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    electricity_usage = []
    cold_water_usage = []
    hot_water_usage = []

    for month in range(1, 13):
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)

        electricity = get_monthly_usage('electricity', start_date, end_date)
        cold = get_monthly_usage('cold_water', start_date, end_date)
        hot = get_monthly_usage('hot_water', start_date, end_date)

        electricity_usage.append(electricity)
        cold_water_usage.append(cold)
        hot_water_usage.append(hot)

    def compute_stats(data):
        filtered = [d for d in data if d > 0]
        if not filtered:
            return {'min': 0, 'max': 0, 'avg': 0}
        return {
            'min': min(filtered),
            'max': max(filtered),
            'avg': round(sum(filtered) / len(filtered), 2),
        }

    context = {
        'current_month': today.strftime('%B'),
        'current_year': year,
        'recent_expenses': expenses,
        'total_all_time': total_all_time,
        'total_year': total_year,
        'chart_months': months,
        'electricity_data': electricity_usage,
        'cold_water_data': cold_water_usage,
        'hot_water_data': hot_water_usage,
        'electricity_stats': compute_stats(electricity_usage),
        'cold_water_stats': compute_stats(cold_water_usage),
        'hot_water_stats': compute_stats(hot_water_usage),
    }
    return render(request, 'overview.html', context)


@login_required
def pay_expense(request, category):
    if request.method == 'POST':
        amount = request.POST.get('amount')
        payment_date = request.POST.get('payment_date')
        start_date = request.POST.get('start_date') or request.session.get('filter_start_date')
        end_date = request.POST.get('end_date') or request.session.get('filter_end_date')

        if not amount or not payment_date:
            return HttpResponseBadRequest("Некорректная сумма или дата оплаты")

        try:
            amount = Decimal(amount)
            if amount <= 0:
                raise ValueError("Сумма должна быть положительной")
        except ValueError:
            return HttpResponseBadRequest("Некорректная сумма")

        expenses = Expense.objects.filter(
            user=request.user,
            category=category,
        )
        if start_date and end_date:
            expenses = expenses.filter(date__range=[start_date, end_date])
        expense = expenses.first()

        if expense:
            expense.debt -= amount
            if expense.debt <= 0:
                expense.debt = Decimal('0.00')
                expense.paid = True
            expense.payment_date = payment_date
            expense.save()
        else:
            initial_amount = amount
            debt = initial_amount - amount
            paid = debt <= 0
            Expense.objects.create(
                user=request.user,
                category=category,
                amount=initial_amount,
                debt=debt if debt > 0 else Decimal('0.00'),
                date=payment_date,
                payment_date=payment_date,
                paid=paid
            )

        if start_date and end_date:
            request.session['filter_start_date'] = start_date
            request.session['filter_end_date'] = end_date
            request.session.modified = True

        return redirect(
            f"{reverse('expenses:filter_expenses')}?start_date={start_date or ''}&end_date={end_date or ''}")

    return HttpResponseBadRequest("Некорректный запрос")


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

