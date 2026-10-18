'''
Справочники полей чека по документации АТОЛ Онлайн v4 (ФФД 1.05) и v5 (ФФД 1.2).
Храним код v4 (строка), для v5 переводим в числовые коды через словари *_V5.
'''

PROTOCOLS = {'v4', 'v5'}
RECEIPT_TYPES = {'regular', 'correction', 'agent'}
# Операция (тип документа в URL запроса): приход / возврат прихода.
OPERATIONS = {'sell', 'sell_refund'}

# Тег 1214 - признак способа расчёта (одинаково в v4 и v5).
PAYMENT_METHODS = {'full_prepayment', 'prepayment', 'advance', 'full_payment',
                   'partial_payment', 'credit', 'credit_payment'}

# Тег 1212 - признак предмета расчёта. v4 - строки, v5 - числа.
PAYMENT_OBJECTS_V5 = {
    'commodity': 1,
    'commodity_marked': 33,
    'service': 4,
    'job': 3,
    'payment': 10,
}

# Единицы измерения. v4 - measurement_unit (строка), v5 - measure (тег 2108, число).
MEASURES = {
    'piece': {'v4': 'шт', 'v5': 0},
    'gram': {'v4': 'г', 'v5': 10},
    'kilogram': {'v4': 'кг', 'v5': 11},
    'day': {'v4': 'сут', 'v5': 70},
}

# Ставка НДС позиции (vat.type) - для чека без корзины у источника; пусто - без НДС.
VATS = {'none', 'vat0', 'vat5', 'vat7', 'vat10', 'vat20', 'vat22', 'vat105', 'vat107', 'vat110', 'vat120', 'vat122'}

# Вид оплаты payments[].type: 0 - наличные, 1 - безналичный, 2 - предоплата (зачёт аванса).
PAYMENT_TYPES = {0, 1, 2}

# correction_info.type (тег 1173): в шаблонах только самостоятельная коррекция.
CORRECTION_TYPE = 'self'
# Откуда брать correction_info.base_date: дата платежа или фиксированная дата из шаблона.
DATE_SOURCES = {'payment', 'today', 'yesterday', 'fixed', 'client'}

# Агентский чек (теги 1057/1222 - признак агента, ФФД 1.05 и 1.2).
AGENT_TYPES = {'bank_paying_agent', 'bank_paying_subagent', 'paying_agent', 'paying_subagent',
               'attorney', 'commission_agent', 'another'}
# Для каких признаков агента нужны данные платёжного агента и оператора перевода.
PAYING_AGENT_TYPES = {'bank_paying_agent', 'bank_paying_subagent', 'paying_agent', 'paying_subagent'}
MONEY_TRANSFER_TYPES = {'bank_paying_agent', 'bank_paying_subagent'}
