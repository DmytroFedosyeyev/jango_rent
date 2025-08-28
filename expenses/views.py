import os
import logging
import datetime
import calendar
import json
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta, datetime
from calendar import monthrange
from django.utils import timezone
from decimal import Decimal
from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponse
from django.urls import reverse
from django.contrib import messages
from django.db.models import Sum, Q
from django.db import transaction
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import get_template
from django.conf import settings
from django.db import IntegrityError
from django.utils.safestring import mark_safe

from xhtml2pdf import pisa

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import cm
from reportlab.rl_config import TTFSearchPath

from calendar import monthrange

from .forms import ExpenseForm, MeterReadingForm, RegisterForm, EditSingleReadingForm
from .models import MeterReading, Expense, RentRate
from expenses.utils import process_category
from expenses.models import MonthlyUsage

from django.utils.translation import gettext_lazy as _
from dateutil.relativedelta import relativedelta
from django.utils.translation import gettext_lazy as _



logger = logging.getLogger(__name__)

CATEGORY_DISPLAY = {
    'rent': _('Аренда'),
    'utilities': _('Коммунальные'),
    'electricity': _('Электричество'),
}

# Список месяцев с переводом
MONTHS = [
    _('Янв'), _('Фев'), _('Мар'), _('Апр'), _('Май'), _('Июн'),
    _('Июл'), _('Авг'), _('Сен'), _('Окт'), _('Ноя'), _('Дек')
]

# Статусы с переводом
STATUS_DISPLAY = {
    'paid': _('Оплачено'),
    'debt': _('Долг'),
    'future': _('Будущие')
}

@login_required
def add_expense(request):
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        logger.debug(f"POST request received with form_type: {form_type}")
        logger.debug(f"POST data: {request.POST}")

        # Инициализируем обе формы
        expense_form = ExpenseForm(request.POST, prefix='expense')
        meter_form = MeterReadingForm(request.POST, prefix='meter')

        if form_type == 'expense':
            logger.debug("Handling expense form submission.")
            if expense_form.is_valid():
                expense = expense_form.save(commit=False)
                expense.user = request.user
                logger.debug(f"Expense form valid. Category: {expense.category}, Date: {expense.date}")

                # Проверка на дублирующий расход
                existing = Expense.objects.filter(
                    user=expense.user,
                    category=expense.category,
                    date__year=expense.date.year,
                    date__month=expense.date.month
                ).first()

                if existing and 'confirm_update' not in request.POST:
                    logger.info(f"Duplicate expense found: {existing}. Asking for confirmation.")
                    return render(request, 'expenses/confirm_update.html', {
                        'existing': existing,
                        'new_expense': expense,
                        'expense_form': expense_form,
                        'meter_form': MeterReadingForm(prefix='meter'),
                    })

                if existing and 'confirm_update' in request.POST:
                    logger.info(f"User confirmed update. Updating existing expense: {existing}")
                    existing.amount = expense.amount
                    existing.debt = expense.amount if not expense.paid else Decimal('0.00')
                    existing.paid = expense.paid
                    existing.payment_amount = Decimal('0.00')
                    existing.date = expense.date
                    existing.save()
                    messages.success(request, "Расход обновлён.")
                    return redirect('expenses:home')

                # Сохраняем расход без проверки RentRate
                expense.debt = expense.amount if not expense.paid else Decimal('0.00')
                expense.payment_amount = Decimal('0.00')
                expense.save()
                logger.debug(f"Expense saved: {expense}")
                messages.success(request, "✅ Расход успешно добавлен.")
                expense_form = ExpenseForm(prefix='expense')  # Очистим форму
                meter_form = MeterReadingForm(prefix='meter')  # Очистим форму
                return render(request, 'add_expense.html', {
                    'expense_form': expense_form,
                    'meter_form': meter_form,
                })
            else:
                logger.warning(f"Expense form invalid: {expense_form.errors}")
                messages.error(request, "Ошибка в форме расхода.")
                meter_form = MeterReadingForm(prefix='meter')

        elif form_type == 'meter':
            logger.debug("Handling meter reading form submission.")
            if meter_form.is_valid():
                date_ = meter_form.cleaned_data['date']
                electricity_usage = meter_form.cleaned_data['electricity_usage']
                cold_water_usage = meter_form.cleaned_data['cold_water_usage']
                hot_water_usage = meter_form.cleaned_data['hot_water_usage']

                logger.debug(
                    f"Meter form valid for date {date_}. Electricity: {electricity_usage}, Cold water: {cold_water_usage}, Hot water: {hot_water_usage}")

                if electricity_usage is not None:
                    obj, created = MeterReading.objects.update_or_create(
                        user=request.user,
                        category='electricity',
                        date=date_,
                        defaults={'value': electricity_usage}
                    )
                    if created:
                        logger.debug(f"Created electricity reading for {date_}")
                    else:
                        logger.debug(f"Updated electricity reading for {date_}")
                    save_monthly_usage(request.user, 'electricity', date_)

                if cold_water_usage is not None:
                    obj, created = MeterReading.objects.update_or_create(
                        user=request.user,
                        category='cold_water',
                        date=date_,
                        defaults={'value': cold_water_usage}
                    )
                    if created:
                        logger.debug(f"Created cold water reading for {date_}")
                    else:
                        logger.debug(f"Updated cold water reading for {date_}")
                    save_monthly_usage(request.user, 'cold_water', date_)

                if hot_water_usage is not None:
                    obj, created = MeterReading.objects.update_or_create(
                        user=request.user,
                        category='hot_water',
                        date=date_,
                        defaults={'value': hot_water_usage}
                    )
                    if created:
                        logger.debug(f"Created hot water reading for {date_}")
                    else:
                        logger.debug(f"Updated hot water reading for {date_}")
                    save_monthly_usage(request.user, 'hot_water', date_)

                messages.success(request, "✅ Показания счётчиков успешно добавлены.")
                return redirect('expenses:home')
            else:
                logger.warning(f"Meter form invalid: {meter_form.errors}")
                messages.error(request, "Ошибка в форме показаний.")
                expense_form = ExpenseForm(prefix='expense')

        else:
            logger.warning("form_type not specified or invalid.")
            messages.error(request, "Неверный тип формы.")
            expense_form = ExpenseForm(prefix='expense')
            meter_form = MeterReadingForm(prefix='meter')

    else:
        logger.debug("GET request. Rendering empty forms.")
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

    rent = {
        'amount': rent_expense.amount if rent_expense else 0,
        'date': rent_expense.date if rent_expense else None,
        'paid': rent_expense.paid if rent_expense else False,
        'payment_date': rent_expense.payment_date if rent_expense else None,
        'payment_amount': rent_expense.payment_amount if rent_expense else 0,
    }
    utilities = {
        'amount': utilities_expense.amount if utilities_expense else 0,
        'date': utilities_expense.date if utilities_expense else None,
        'paid': utilities_expense.paid if utilities_expense else False,
        'payment_date': utilities_expense.payment_date if utilities_expense else None,
        'payment_amount': utilities_expense.payment_amount if utilities_expense else 0,
    }
    electricity = {
        'amount': electricity_expense.amount if electricity_expense else 0,
        'date': electricity_expense.date if electricity_expense else None,
        'paid': electricity_expense.paid if electricity_expense else False,
        'payment_date': electricity_expense.payment_date if electricity_expense else None,
        'payment_amount': electricity_expense.payment_amount if electricity_expense else 0,
    }

    total = Decimal(rent['amount']) + Decimal(utilities['amount']) + Decimal(electricity['amount'])

    past_expenses = Expense.objects.filter(
        user=request.user,
        date__lt=start_of_month
    )
    rent_debt = past_expenses.filter(category='rent').aggregate(total_debt=Sum('debt'))['total_debt'] or Decimal('0.00')
    utilities_debt = past_expenses.filter(category='utilities').aggregate(total_debt=Sum('debt'))['total_debt'] or Decimal('0.00')
    electricity_debt = past_expenses.filter(category='electricity').aggregate(total_debt=Sum('debt'))['total_debt'] or Decimal('0.00')
    total_debt = Decimal(rent_debt) + Decimal(utilities_debt) + Decimal(electricity_debt)

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
            'name': MONTHS[month-1],  # Используем переведённые названия месяцев
            'status': status,  # Используем переведённые статусы
            'start_date': start_date,
            'end_date': end_date,
        })

    context = {
        'current_month': today.strftime('%B'),
        'current_year': current_year,
        'rent': rent,
        'utilities': utilities,
        'electricity': electricity,
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

    # Выбор месяца
    month = request.GET.get('month')
    if month:
        try:
            month_date = datetime.strptime(month, '%Y-%m-%d').date()
            current_month = month_date.replace(day=1)
            request.session['selected_month'] = current_month.strftime('%Y-%m-%d')
            request.session.modified = True
        except ValueError:
            current_month = date.today().replace(day=1)
    else:
        current_month = datetime.strptime(request.session.get('selected_month', date.today().strftime('%Y-%m-%d')), '%Y-%m-%d').date()
    logger.debug(f"Selected month: {current_month}")

    # Фильтр по периоду
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date and end_date:
        try:
            start_month = datetime.strptime(start_date, '%Y-%m').replace(day=1)
            end_month = datetime.strptime(end_date, '%Y-%m').replace(day=1)
            last_day = calendar.monthrange(end_month.year, end_month.month)[1]
            end_month = end_month.replace(day=last_day)

            process_category('cold_water', request.user)
            process_category('hot_water', request.user)
            process_category('electricity', request.user)

            request.session['filter_start_date'] = start_month.strftime('%Y-%m-%d')
            request.session['filter_end_date'] = end_month.strftime('%Y-%m-%d')
            request.session.modified = True
            logger.debug(f"Saved to session: start_date={start_month}, end_date={end_month}")
        except ValueError:
            start_month = None
            end_month = None
    else:
        try:
            start_month = datetime.strptime(request.session.get('filter_start_date', '2025-07-01'), '%Y-%m-%d').date()
            end_month = datetime.strptime(request.session.get('filter_end_date', '2025-07-31'), '%Y-%m-%d').date()
        except Exception:
            start_month = None
            end_month = None
        logger.debug(f"Loaded from session: start_date={start_month}, end_date={end_month}")

    # Защита от None: если даты не установлены — задаём текущий месяц
    if not start_month:
        start_month = date.today().replace(day=1)
    if not end_month:
        _, last_day = calendar.monthrange(start_month.year, start_month.month)
        end_month = date(start_month.year, start_month.month, last_day)

    # Список месяцев для кнопок
    year = current_month.year  # или просто: year = date.today().year
    months = [date(year, m, 1) for m in range(1, 13)]
    month_data = [(month_date, MONTHS[month_date.month - 1]) for month_date in months]

    # Данные для текущего месяца
    expenses = Expense.objects.filter(user=request.user, date__year=current_month.year, date__month=current_month.month)
    meter_readings = MeterReading.objects.filter(user=request.user, date__year=current_month.year, date__month=current_month.month)

    rent_expenses = expenses.filter(category='rent')
    utilities_expenses = expenses.filter(category='utilities')
    electricity_expenses = expenses.filter(category='electricity')

    rent = {
        'amount': rent_expenses.aggregate(total=Sum('amount'))['total'] or 0,
        'debt': rent_expenses.aggregate(total=Sum('debt'))['total'] or 0,
        'payment_amount': rent_expenses.aggregate(total=Sum('payment_amount'))['total'] or 0,
        'paid': all(e.paid for e in rent_expenses) if rent_expenses.exists() else False,
        'payment_date': max((e.payment_date for e in rent_expenses if e.payment_date), default=None),
    }
    utilities = {
        'amount': utilities_expenses.aggregate(total=Sum('amount'))['total'] or 0,
        'debt': utilities_expenses.aggregate(total=Sum('debt'))['total'] or 0,
        'payment_amount': utilities_expenses.aggregate(total=Sum('payment_amount'))['total'] or 0,
        'paid': all(e.paid for e in utilities_expenses) if utilities_expenses.exists() else False,
        'payment_date': max((e.payment_date for e in utilities_expenses if e.payment_date), default=None),
    }
    electricity = {
        'amount': electricity_expenses.aggregate(total=Sum('amount'))['total'] or 0,
        'debt': electricity_expenses.aggregate(total=Sum('debt'))['total'] or 0,
        'payment_amount': electricity_expenses.aggregate(total=Sum('payment_amount'))['total'] or 0,
        'paid': all(e.paid for e in electricity_expenses) if electricity_expenses.exists() else False,
        'payment_date': max((e.payment_date for e in electricity_expenses if e.payment_date), default=None),
    }

    total = Decimal(rent['amount']) + Decimal(utilities['amount']) + Decimal(electricity['amount'])
    total_debt = Decimal(rent['debt']) + Decimal(utilities['debt']) + Decimal(electricity['debt'])
    total_payment = Decimal(rent['payment_amount']) + Decimal(utilities['payment_amount']) + Decimal(electricity['payment_amount'])

    # Данные по расходам за период
    period_expenses = Expense.objects.filter(user=request.user)
    if start_month and end_month:
        period_expenses = period_expenses.filter(date__range=[start_month, end_month])

    period_rent = period_expenses.filter(category='rent').aggregate(total_amount=Sum('amount'), total_debt=Sum('debt'), total_payment=Sum('payment_amount'))
    period_utilities = period_expenses.filter(category='utilities').aggregate(total_amount=Sum('amount'), total_debt=Sum('debt'), total_payment=Sum('payment_amount'))
    period_electricity = period_expenses.filter(category='electricity').aggregate(total_amount=Sum('amount'), total_debt=Sum('debt'), total_payment=Sum('payment_amount'))

    period_total = {
        'rent': {
            'amount': period_rent['total_amount'] or 0,
            'debt': period_rent['total_debt'] or 0,
            'payment_amount': period_rent['total_payment'] or 0,
        },
        'utilities': {
            'amount': period_utilities['total_amount'] or 0,
            'debt': period_utilities['total_debt'] or 0,
            'payment_amount': period_utilities['total_payment'] or 0,
        },
        'electricity': {
            'amount': period_electricity['total_amount'] or 0,
            'debt': period_electricity['total_debt'] or 0,
            'payment_amount': period_electricity['total_payment'] or 0,
        },
        'total': sum([period_rent['total_amount'] or 0, period_utilities['total_amount'] or 0, period_electricity['total_amount'] or 0]),
        'total_debt': sum([period_rent['total_debt'] or 0, period_utilities['total_debt'] or 0, period_electricity['total_debt'] or 0]),
        'total_payment': sum([period_rent['total_payment'] or 0, period_utilities['total_payment'] or 0, period_electricity['total_payment'] or 0]),
    }

    # Расчёт расхода по счётчикам из MonthlyUsage
    def compute_usage_stats(category, user, start_date, end_date):
        usages = MonthlyUsage.objects.filter(
            user=user,
            category=category,
            year__gte=start_date.year,
            month__gte=start_date.month,
            year__lte=end_date.year,
            month__lte=end_date.month
        )
        usage_values = [u.usage for u in usages]
        if not usage_values:
            return {'total': 0, 'min': 0, 'max': 0, 'avg': 0}
        total = round(sum(usage_values), 2)
        return {
            'total': total,
            'min': round(min(usage_values), 2),
            'max': round(max(usage_values), 2),
            'avg': round(total / len(usage_values), 2)
        }

    meter_usage = {
        'electricity': compute_usage_stats('electricity', request.user, start_month, end_month),
        'cold_water': compute_usage_stats('cold_water', request.user, start_month, end_month),
        'hot_water': compute_usage_stats('hot_water', request.user, start_month, end_month),
    }

    context = {
        'current_month': current_month,
        'month_name': current_month.strftime('%B'),
        'month_year': current_month.strftime('%Y'),
        'rent': rent,
        'utilities': utilities,
        'electricity': electricity,
        'total': total,
        'total_debt': total_debt,
        'total_payment': total_payment,
        'meter_readings': meter_readings,
        'start_month': start_month,
        'end_month': end_month,
        'period_total': period_total,
        'meter_usage': meter_usage,
        'month_data': month_data,
        'start_formatted': start_month.strftime('%B %Y') if start_month else '',
        'end_formatted': end_month.strftime('%B %Y') if end_month else '',
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
    current_month = today.month

    # Финансовые расходы
    category_expenses = Expense.objects.filter(
        user=user,
        date__year=current_year,
        category__in=['rent', 'utilities', 'electricity']
    ).values('category').annotate(total_amount=Sum('amount'))

    desired_order = ['rent', 'utilities', 'electricity']
    expenses_dict = {exp['category']: exp['total_amount'] or 0 for exp in category_expenses}

    expenses_by_category = [
        {
            'category': category,
            'category_display': CATEGORY_DISPLAY.get(category, category),
            'total_amount': expenses_dict.get(category, 0)
        } for category in desired_order
    ]

    total_year = sum(exp['total_amount'] for exp in expenses_by_category)
    total_all_time = Expense.objects.filter(
        user=user,
        category__in=desired_order
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Список месяцев (преобразуем gettext_lazy в строки)
    MONTHS = [
        str(_('Янв')), str(_('Фев')), str(_('Мар')), str(_('Апр')),
        str(_('Май')), str(_('Июн')), str(_('Июл')), str(_('Авг')),
        str(_('Сен')), str(_('Окт')), str(_('Ноя')), str(_('Дек'))
    ]

    # Данные для графиков (только ненулевые usage)
    categories = ['electricity', 'cold_water', 'hot_water']
    usage_data = {cat: {'months': [], 'values': []} for cat in categories}

    for usage in MonthlyUsage.objects.filter(
        user=user,
        year=current_year,
        category__in=categories,
        usage__gt=0  # Только ненулевые значения
    ):
        category = usage.category
        month = usage.month - 1  # 0-based index
        usage_data[category]['months'].append(MONTHS[month])
        usage_data[category]['values'].append(float(usage.usage))

    def compute_stats(values):
        clean = [v for v in values if v > 0]
        return {
            'min': round(min(clean), 2) if clean else 0,
            'max': round(max(clean), 2) if clean else 0,
            'avg': round(sum(clean) / len(clean), 2) if clean else 0
        }

    context = {
        'current_month': today.strftime('%B'),
        'current_year': current_year,
        'expenses_by_category': expenses_by_category,
        'total_year': total_year,
        'total_all_time': total_all_time,
        'chart_months': MONTHS,
        'electricity_months': usage_data['electricity']['months'],
        'electricity_values': usage_data['electricity']['values'],
        'cold_water_months': usage_data['cold_water']['months'],
        'cold_water_values': usage_data['cold_water']['values'],
        'hot_water_months': usage_data['hot_water']['months'],
        'hot_water_values': usage_data['hot_water']['values'],
        'electricity_stats': compute_stats(usage_data['electricity']['values']),
        'cold_water_stats': compute_stats(usage_data['cold_water']['values']),
        'hot_water_stats': compute_stats(usage_data['hot_water']['values']),
    }

    return render(request, 'overview.html', context)


@login_required
@require_POST
def pay_all_expenses(request):
    logger.debug(f"POST data: {request.POST}")
    logger.debug(f"Session data: {request.session.items()}")

    try:
        amount = Decimal(request.POST.get('amount', '0.00'))
        payment_date = request.POST.get('payment_date')
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if not payment_date:
            raise ValueError("Payment date is required")
        payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
    except (ValueError, TypeError, InvalidOperation) as e:
        logger.error(f"Invalid input: {str(e)}")
        messages.error(request, "Неверный формат суммы или даты")
        return redirect('expenses:home')

    user = request.user
    remaining = amount
    distributed = Decimal('0.00')

    # Получаем текущий месяц из сессии или POST
    selected_month = request.POST.get('month') or request.session.get('selected_month')
    if selected_month:
        try:
            selected_date = datetime.strptime(selected_month, '%Y-%m-%d').date()
            year, month = selected_date.year, selected_date.month
            logger.debug(f"Using selected_month: {year}-{month}")
        except ValueError:
            logger.error("Invalid selected_month format")
            year, month = timezone.now().date().year, timezone.now().date().month
    else:
        year, month = timezone.now().date().year, timezone.now().date().month
        logger.debug(f"No selected_month, using current month: {year}-{month}")

    start_date = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end_date = date(year, month, last_day)
    logger.debug(f"Starting period: {start_date} to {end_date}")

    with transaction.atomic():
        # Категории в порядке приоритета
        categories = ['rent', 'utilities', 'electricity']
        # Обрабатываем все долги, начиная с самого раннего
        expenses = Expense.objects.filter(
            user=user,
            debt__gt=0
        ).order_by('date')

        for expense in expenses:
            if remaining <= 0:
                break
            # Проверяем приоритет категории
            if expense.category not in categories:
                continue
            to_pay = min(remaining, expense.debt)
            logger.debug(f"Paying {to_pay} for expense {expense.id} ({expense.category}, {expense.date})")
            expense.debt -= to_pay
            expense.payment_amount += to_pay
            if expense.debt <= 0:
                expense.debt = Decimal('0.00')
                expense.paid = True
            expense.payment_date = payment_date
            expense.save()
            remaining -= to_pay
            distributed += to_pay
            logger.debug(f"Updated expense {expense.id}: debt={expense.debt}, paid={expense.paid}")

        # Сохраняем переплату в сессии
        if remaining > 0:
            logger.debug(f"Overpayment remaining: {remaining}")
            request.session['overpayment'] = float(remaining)
            messages.success(request, f"Оплата прошла. Распределено: {distributed:.2f} €. У вас {remaining:.2f} € в плюсе.")
        else:
            request.session['overpayment'] = 0.0
            messages.success(request, f"Оплата прошла. Распределено: {distributed:.2f} €.")

        # Обновляем сессию
        request.session['filter_start_date'] = start_date.strftime('%Y-%m-%d')
        request.session['filter_end_date'] = end_date.strftime('%Y-%m-%d')
        request.session['selected_month'] = start_date.strftime('%Y-%m-01')
        request.session.modified = True

    if distributed == 0:
        messages.error(request, "Не найдено расходов для оплаты.")
        logger.warning("No expenses found to pay")

    return redirect(f"{reverse('expenses:filter_expenses')}?month={year}-{month:02d}")

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
@require_POST
def pay_expense(request, category):
    if request.method != 'POST':
        return HttpResponseBadRequest("Некорректный метод запроса")

    amount = request.POST.get('amount')
    payment_date = request.POST.get('payment_date')

    if not amount or not payment_date:
        messages.error(request, "Сумма и дата оплаты обязательны.")
        return redirect('expenses:home')

    try:
        amount = Decimal(amount)
        if amount <= 0:
            raise ValueError("Сумма оплаты должна быть положительной.")
        payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, "Неверный формат суммы или даты оплаты.")
        return redirect('expenses:home')

    # Период фильтра
    selected_month = request.session.get('selected_month')
    if selected_month:
        try:
            selected_date = datetime.strptime(selected_month, '%Y-%m-%d').date()
            year, month = selected_date.year, selected_date.month
            start_date = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            end_date = date(year, month, last_day)
        except ValueError:
            logger.error("Invalid selected_month format, using current month")
            year, month = timezone.now().date().year, timezone.now().date().month
            start_date = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            end_date = date(year, month, last_day)
    else:
        year, month = timezone.now().date().year, timezone.now().date().month
        start_date = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)
    logger.debug(f"Filter dates: start_date={start_date}, end_date={end_date}")

    # Ищем существующую запись
    expenses = Expense.objects.filter(user=request.user, category=category)
    expenses = expenses.filter(date__range=[start_date, end_date])
    expense = expenses.first()
    logger.debug(f"Found expense: {expense}")

    if not expense or expense.amount <= 0:
        messages.error(request, "Сначала введите сумму расхода через 'Ввести данные'.")
        return redirect('expenses:home')

    # Обновляем запись
    paid_part = min(expense.debt, amount)
    logger.debug(f"Before update: debt={expense.debt}, payment_amount={expense.payment_amount}, paid={expense.paid}")
    expense.debt -= paid_part
    expense.payment_amount += paid_part
    if expense.debt <= 0:
        expense.debt = Decimal('0.00')
        expense.paid = True
    expense.payment_date = payment_date
    expense.save()
    logger.debug(f"After update: debt={expense.debt}, payment_amount={expense.payment_amount}, paid={expense.paid}, payment_date={expense.payment_date}")

    messages.success(request, f"Оплата для {category} на сумму {paid_part} € обработана.")
    return redirect(f"{reverse('expenses:filter_expenses')}?month={year}-{month:02d}-01")  # Остаёмся на странице фильтра

@login_required
@require_POST
def add_expense_modal(request):
    category = request.POST.get('category')
    amount = request.POST.get('amount')
    date_str = request.POST.get('date')

    if not category or not amount or not date_str:
        messages.error(request, "Все поля обязательны для заполнения.")
        return redirect('expenses:home')

    try:
        amount = Decimal(amount)
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной.")
        date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, "Неверный формат суммы или даты.")
        return redirect('expenses:home')

    Expense.objects.create(
        user=request.user,
        category=category,
        amount=amount,
        debt=amount,
        date=date_obj,
        paid=False
    )

    messages.success(request, f"Расход ({category}) на сумму {amount} € добавлен.")
    return redirect('expenses:home')


@login_required
def monthly_expenses(request, year, month):
    user = request.user
    month_start = date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    month_end = date(year, month, last_day)

    # Расходы
    expenses = Expense.objects.filter(user=user, date__range=[month_start, month_end])
    rent = expenses.filter(category='rent').first()
    utilities = expenses.filter(category='utilities').first()
    electricity = expenses.filter(category='electricity').first()

    # Показания счётчиков
    readings = MeterReading.objects.filter(user=user, date__year=year, date__month=month)
    usage = {}
    for cat in ['electricity', 'cold_water', 'hot_water']:
        try:
            curr = readings.filter(category=cat).latest('date')
            prev = MeterReading.objects.filter(user=user, category=cat, date__lt=curr.date).latest('date')
            usage[cat] = round(curr.value - prev.value, 2)
        except MeterReading.DoesNotExist:
            usage[cat] = 0

    context = {
        'year': year,
        'month': month,
        'rent': rent,
        'utilities': utilities,
        'electricity': electricity,
        'readings': readings,
        'usage': usage,
        'month_name': ['Январь','Февраль','Март','Апрель','Май','Июнь',
                       'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'][month-1],
    }
    return render(request, 'monthly_expenses.html', context)


@login_required
def export_to_pdf(request):
    user = request.user
    year = request.GET.get('year')
    month = request.GET.get('month')

    if not (year and month):
        return HttpResponse("Нужно передать year и month", status=400)

    try:
        year = int(year)
        month = int(month)
        month_start = datetime.date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        month_end = datetime.date(year, month, last_day)
    except Exception:
        return HttpResponse("Некорректные year или month", status=400)

    expenses = Expense.objects.filter(user=user, date__range=[month_start, month_end])

    # Получаем usage по категориям за месяц
    usage_records = MonthlyUsage.objects.filter(user=user, year=year, month=month)
    usage_dict = {rec.category: rec.usage for rec in usage_records}

    font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf')
    pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="report_{year}_{month}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4

    p.setFont("DejaVuSans", 14)
    p.drawCentredString(width / 2, height - 2 * cm, f"Отчёт за {month_start.strftime('%B %Y')}")

    y = height - 3 * cm
    p.setFont("DejaVuSans", 12)
    p.drawString(2 * cm, y, "Расходы:")
    y -= 1 * cm

    p.setFont("DejaVuSans", 10)
    p.drawString(2 * cm, y, "Категория")
    p.drawString(7 * cm, y, "Сумма")
    p.drawString(10 * cm, y, "Оплачено")
    p.drawString(14 * cm, y, "Дата оплаты")
    y -= 0.7 * cm

    for expense in expenses:
        p.drawString(2 * cm, y, str(expense.get_category_display()))
        p.drawString(7 * cm, y, str(expense.amount))
        p.drawString(10 * cm, y, str(expense.payment_amount))
        p.drawString(14 * cm, y, expense.payment_date.strftime('%d.%m.%Y') if expense.payment_date else '-')
        y -= 0.6 * cm
        if y < 3 * cm:
            p.showPage()
            y = height - 2 * cm
            p.setFont("DejaVuSans", 10)

    y -= 1 * cm
    p.setFont("DejaVuSans", 12)
    p.drawString(2 * cm, y, "Потребление ресурсов:")
    y -= 1 * cm

    p.setFont("DejaVuSans", 10)
    # Теперь подставляем из словаря, если нет данных — ставим "-"
    p.drawString(2 * cm, y, f"{month:02d}/{year}")
    p.drawString(6 * cm, y, f"Электричество: {usage_dict.get('electricity', '-')}")
    p.drawString(11 * cm, y, f"Хол. вода: {usage_dict.get('cold_water', '-')}")
    p.drawString(16 * cm, y, f"Гор. вода: {usage_dict.get('hot_water', '-')}")

    p.showPage()
    p.save()
    return response

def save_monthly_usage(user, category, reading_date):
    year = reading_date.year
    month = reading_date.month

    try:
        current = MeterReading.objects.get(user=user, category=category, date=reading_date)
    except MeterReading.DoesNotExist:
        return

    # Предыдущее показание
    previous = (
        MeterReading.objects.filter(user=user, category=category, date__lt=reading_date)
        .order_by('-date')
        .first()
    )

    if not previous:
        # Нельзя вычислить расход — нет предыдущего значения
        return

    usage = float(current.value) - float(previous.value)
    if usage < 0:
        return  # Невозможно: счётчик не может уменьшиться

    try:
        MonthlyUsage.objects.update_or_create(
            user=user,
            category=category,
            year=year,
            month=month,
            defaults={'usage': usage}
        )
    except IntegrityError:
        pass  # на случай гонки данных


@login_required
def edit_data_selector(request):
    current_year = timezone.now().year
    years = range(current_year - 5, current_year + 2)
    months = [(i, _(calendar.month_name[i])) for i in range(1, 13)]
    return render(request, 'expenses/edit_data_selector.html', {
        'years': years,
        'months': months,
        'current_year': current_year,
    })

@login_required
def edit_data_view(request):
    user = request.user
    year = int(request.GET.get('year'))
    month = request.GET.get('month')

    expenses = Expense.objects.filter(user=user, date__year=year)
    meter_readings = MeterReading.objects.filter(user=user, date__year=year)

    if month:
        expenses = expenses.filter(date__month=int(month))
        meter_readings = meter_readings.filter(date__month=int(month))

    grouped_data = defaultdict(lambda: {'expenses': [], 'readings': []})
    for e in expenses:
        grouped_data[e.date.month]['expenses'].append(e)
    for r in meter_readings:
        grouped_data[r.date.month]['readings'].append(r)

    return render(request, 'expenses/edit_data_view.html', {
        'grouped_data': dict(sorted(grouped_data.items())),
        'year': year,
        'month': int(month) if month else None,
    })

@login_required
def edit_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    form = ExpenseForm(request.POST or None, instance=expense)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Данные по расходу обновлены.')
        return redirect('expenses:edit_data_selector')
    return render(request, 'expenses/edit_single_entry.html', {'form': form})

@login_required
def edit_meter_reading(request, pk):
    reading = get_object_or_404(MeterReading, pk=pk, user=request.user)
    form = MeterReadingForm(request.POST or None, instance=reading)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Показание счётчика обновлено.')
        return redirect('expenses:edit_data_selector')
    return render(request, 'expenses/edit_single_entry.html', {'form': form})

