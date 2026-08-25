from config import DEBUG


def debug_print(*args, **kwargs):
    """
    Замена print() для всего, что печатается на КАЖДУЮ карточку/строку
    (RAW/CLEANED, TIMING, кандидаты, [CARD SAVE] и т.п.).
    Включается через config.DEBUG = True.

    Однократные служебные print() при старте (например,
    "Индексы построены") можно не трогать - они не влияют
    на скорость обработки тысяч строк.
    """
    if DEBUG:
        print(*args, **kwargs)