"""Money and number formatting for any country."""

# Menu label -> (symbol, name used when talking to the AI)
CURRENCIES = {
    "Not specified": None,
    "₹ Indian Rupee (INR)": ("₹", "Indian Rupees (INR)"),
    "$ US Dollar (USD)": ("$", "US Dollars (USD)"),
    "A$ Australian Dollar (AUD)": ("A$", "Australian Dollars (AUD)"),
    "£ British Pound (GBP)": ("£", "British Pounds (GBP)"),
    "€ Euro (EUR)": ("€", "Euros (EUR)"),
    "¥ Japanese Yen (JPY)": ("¥", "Japanese Yen (JPY)"),
    "CN¥ Chinese Yuan (CNY)": ("CN¥", "Chinese Yuan (CNY)"),
    "AED UAE Dirham": ("AED ", "UAE Dirhams (AED)"),
    "SAR Saudi Riyal": ("SAR ", "Saudi Riyals (SAR)"),
    "C$ Canadian Dollar (CAD)": ("C$", "Canadian Dollars (CAD)"),
    "NZ$ New Zealand Dollar (NZD)": ("NZ$", "New Zealand Dollars (NZD)"),
    "S$ Singapore Dollar (SGD)": ("S$", "Singapore Dollars (SGD)"),
    "HK$ Hong Kong Dollar (HKD)": ("HK$", "Hong Kong Dollars (HKD)"),
    "₩ Korean Won (KRW)": ("₩", "Korean Won (KRW)"),
    "₫ Vietnamese Dong (VND)": ("₫", "Vietnamese Dong (VND)"),
    "₱ Philippine Peso (PHP)": ("₱", "Philippine Pesos (PHP)"),
    "RM Malaysian Ringgit (MYR)": ("RM ", "Malaysian Ringgit (MYR)"),
    "฿ Thai Baht (THB)": ("฿", "Thai Baht (THB)"),
    "Rp Indonesian Rupiah (IDR)": ("Rp ", "Indonesian Rupiah (IDR)"),
    "Rs Pakistani Rupee (PKR)": ("Rs ", "Pakistani Rupees (PKR)"),
    "৳ Bangladeshi Taka (BDT)": ("৳", "Bangladeshi Taka (BDT)"),
    "Rs Sri Lankan Rupee (LKR)": ("Rs ", "Sri Lankan Rupees (LKR)"),
    "Rs Nepalese Rupee (NPR)": ("Rs ", "Nepalese Rupees (NPR)"),
    "R$ Brazilian Real (BRL)": ("R$", "Brazilian Reais (BRL)"),
    "MX$ Mexican Peso (MXN)": ("MX$", "Mexican Pesos (MXN)"),
    "R South African Rand (ZAR)": ("R ", "South African Rand (ZAR)"),
    "₦ Nigerian Naira (NGN)": ("₦", "Nigerian Naira (NGN)"),
    "KSh Kenyan Shilling (KES)": ("KSh ", "Kenyan Shillings (KES)"),
    "E£ Egyptian Pound (EGP)": ("E£", "Egyptian Pounds (EGP)"),
    "₺ Turkish Lira (TRY)": ("₺", "Turkish Lira (TRY)"),
    "CHF Swiss Franc": ("CHF ", "Swiss Francs (CHF)"),
}

# Menu label -> style key
NUMBER_STYLES = {
    "1,234,567.89 (International)": "intl",
    "12,34,567.89 (Indian lakh/crore)": "indian",
    "1.234.567,89 (European)": "eu",
    "1 234 567,89 (Space)": "space",
}


def symbol_for(currency_label: str) -> str:
    c = CURRENCIES.get(currency_label)
    return c[0] if c else ""


def _group_indian(integer: str) -> str:
    if len(integer) <= 3:
        return integer
    head, tail = integer[:-3], integer[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def fmt_number(value, style: str = "intl", decimals: int = 0) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if value < 0 else ""
    text = f"{abs(value):,.{decimals}f}"            # 1,234,567.89
    integer, _, frac = text.partition(".")
    digits = integer.replace(",", "")
    if style == "indian":
        integer = _group_indian(digits)
        return sign + integer + (f".{frac}" if frac else "")
    if style == "eu":
        return sign + integer.replace(",", ".") + (f",{frac}" if frac else "")
    if style == "space":
        return sign + integer.replace(",", " ") + (f",{frac}" if frac else "")
    return sign + text


def fmt_money(value, symbol: str = "", style: str = "intl", decimals: int = 0) -> str:
    text = fmt_number(value, style, decimals)
    if text.startswith("-"):
        return "-" + symbol + text[1:]
    return symbol + text


def fmt_compact(value, symbol: str = "", style: str = "intl") -> str:
    """Short labels for charts: ₹39.8L / ₹1.2Cr (Indian), $3.9M, €12K."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    sign, v = ("-" if v < 0 else ""), abs(v)
    if style == "indian":
        for size, unit in ((1e7, "Cr"), (1e5, "L"), (1e3, "K")):
            if v >= size:
                return f"{sign}{symbol}{v / size:.1f}{unit}".replace(".0", "")
        return f"{sign}{symbol}{v:.0f}"
    for size, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= size:
            num = f"{v / size:.1f}".replace(".0", "")
            if style in ("eu", "space"):
                num = num.replace(".", ",")
            return f"{sign}{symbol}{num}{unit}"
    return f"{sign}{symbol}{v:.0f}"


def plotly_separators(style: str) -> str:
    """Plotly 'separators' layout value: decimal mark then thousands mark."""
    return {"eu": ",.", "space": ", "}.get(style, ".,")


def fmt_pct(value, decimals: int = 1) -> str:
    try:
        return f"{float(value):+.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"
