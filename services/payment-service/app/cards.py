from datetime import date

# Dummy gateway test cards (like Stripe/Razorpay test mode).
SUCCESS_TEST_CARD = "4111111111111111"
DECLINED_TEST_CARD = "4000000000000002"


def luhn_valid(number: str) -> bool:
    """Standard checksum every real card number satisfies."""
    total = 0
    for i, digit in enumerate(reversed(number)):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def expiry_valid(expiry: str, today: date | None = None) -> bool:
    today = today or date.today()
    month, year = expiry.split("/")
    return (2000 + int(year), int(month)) >= (today.year, today.month)
