"""
Défi — Détection de fraude financière.

Vous devez implémenter la fonction `detect_fraud`.
La fonction `load_transactions` vous est FOURNIE (ne la modifiez pas).
"""

import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import isfinite
from statistics import median


NEAR_COUNTRY_PAIRS = {
    frozenset(pair)
    for pair in (
        ("FR", "BE"),
        ("FR", "DE"),
        ("FR", "ES"),
        ("FR", "IT"),
        ("FR", "CH"),
        ("BE", "NL"),
        ("DE", "NL"),
        ("DE", "CH"),
        ("TG", "BJ"),
        ("TG", "GH"),
        ("TG", "BF"),
    )
}

CRITICAL_FIELDS = (
    "transaction_id",
    "timestamp",
    "user_id",
    "currency",
    "merchant",
    "country",
    "card_present",
)


def load_transactions(path):
    """Lit un fichier CSV de transactions et renvoie une liste de dicts."""
    transactions = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transactions.append(_clean_row(row))
    return transactions


def _clean_row(row):
    def get(key):
        v = row.get(key)
        return v.strip() if isinstance(v, str) and v.strip() != "" else None

    amount_raw = get("amount")
    try:
        amount = float(amount_raw) if amount_raw is not None else None
    except ValueError:
        amount = None

    card_raw = get("card_present")
    if card_raw is None:
        card_present = None
    else:
        card_present = card_raw.lower() in ("true", "1", "yes", "oui")

    return {
        "transaction_id": get("transaction_id"),
        "timestamp": get("timestamp"),
        "user_id": get("user_id"),
        "amount": amount,
        "currency": get("currency"),
        "merchant": get("merchant"),
        "country": get("country"),
        "card_present": card_present,
    }


def detect_fraud(transactions):
    """Analyse une liste de transactions et renvoie un verdict pour chacune.

    Retour : list[dict] avec transaction_id, fraud_score (0-1),
    is_suspicious (bool), reason (str) — un résultat par transaction, même ordre.
    """
    transactions = [
        tx if isinstance(tx, dict) else {}
        for tx in (transactions or [])
    ]

    parsed_dates = [_parse_timestamp(tx.get("timestamp")) for tx in transactions]
    duplicate_ids = _duplicate_transaction_ids(transactions)
    duplicate_fingerprints = _duplicate_transaction_fingerprints(transactions)
    geo_flags = _detect_fast_country_changes(transactions, parsed_dates)
    frequency_flags = _detect_high_frequency(transactions, parsed_dates)
    amount_groups = _group_valid_amounts(transactions)

    results = []
    for index, tx in enumerate(transactions):
        signals = []

        missing_fields = _missing_fields(tx)
        amount = tx.get("amount")

        if tx.get("transaction_id") in duplicate_ids:
            signals.append((0.9, "Identifiant de transaction dupliqué"))

        if _transaction_fingerprint(tx) in duplicate_fingerprints:
            signals.append((0.8, "Transaction répétée à l'identique"))

        if amount is None:
            signals.append((0.9, "Montant manquant"))
        elif not _is_valid_number(amount):
            signals.append((0.9, "Montant invalide"))
        elif amount <= 0:
            signals.append((0.9, "Montant nul ou négatif"))

        if missing_fields:
            signals.append((
                0.85,
                "Champs obligatoires manquants: " + ", ".join(missing_fields),
            ))

        if geo_flags[index]:
            signals.append((0.88, "Deux pays différents en trop peu de temps"))

        if frequency_flags[index]:
            signals.append((0.82, "Nombre inhabituel de transactions rapprochées"))

        amount_signal = _amount_signal(index, tx, amount_groups)
        if amount_signal is not None:
            signals.append(amount_signal)

        if _large_online_payment(tx):
            signals.append((0.35, "Paiement en ligne de montant élevé"))

        if parsed_dates[index] is None and tx.get("timestamp") is not None:
            signals.append((0.45, "Horodatage invalide"))

        fraud_score, reason = _choose_verdict(signals)

        results.append({
            "transaction_id": tx.get("transaction_id"),
            "fraud_score": fraud_score,
            "is_suspicious": fraud_score >= 0.75,
            "reason": reason,
        })

    return results


def _parse_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _duplicate_transaction_ids(transactions):
    ids = [
        tx.get("transaction_id")
        for tx in transactions
        if tx.get("transaction_id") is not None
    ]
    counts = Counter(ids)
    return {transaction_id for transaction_id, count in counts.items() if count > 1}


def _duplicate_transaction_fingerprints(transactions):
    fingerprints = [
        _transaction_fingerprint(tx)
        for tx in transactions
        if _transaction_fingerprint(tx) is not None
    ]
    counts = Counter(fingerprints)
    return {fingerprint for fingerprint, count in counts.items() if count > 1}


def _transaction_fingerprint(tx):
    fields = (
        tx.get("user_id"),
        tx.get("timestamp"),
        tx.get("amount"),
        tx.get("currency"),
        tx.get("merchant"),
        tx.get("country"),
    )
    if any(value is None for value in fields):
        return None
    return fields


def _missing_fields(tx):
    return [field for field in CRITICAL_FIELDS if tx.get(field) is None]


def _detect_fast_country_changes(transactions, parsed_dates):
    flagged = [False] * len(transactions)
    by_user = defaultdict(list)

    for index, tx in enumerate(transactions):
        user_id = tx.get("user_id")
        country = tx.get("country")
        timestamp = parsed_dates[index]
        if user_id is None or country is None or timestamp is None:
            continue
        by_user[user_id].append((timestamp, country, index))

    for items in by_user.values():
        items.sort(key=lambda item: item[0])
        for previous, current in zip(items, items[1:]):
            previous_time, previous_country, previous_index = previous
            current_time, current_country, current_index = current
            hours = (current_time - previous_time).total_seconds() / 3600
            if _impossible_country_change(previous_country, current_country, hours):
                flagged[previous_index] = True
                flagged[current_index] = True

    return flagged


def _impossible_country_change(previous_country, current_country, hours):
    if hours < 0:
        return False

    previous_country = _normalize_country(previous_country)
    current_country = _normalize_country(current_country)
    if previous_country is None or current_country is None:
        return False
    if previous_country == current_country:
        return False

    pair = frozenset((previous_country, current_country))
    if pair in NEAR_COUNTRY_PAIRS:
        return hours <= 1

    return hours <= 6


def _normalize_country(country):
    if not isinstance(country, str) or not country.strip():
        return None
    return country.strip().upper()


def _detect_high_frequency(transactions, parsed_dates):
    flagged = [False] * len(transactions)
    by_user = defaultdict(list)

    for index, tx in enumerate(transactions):
        user_id = tx.get("user_id")
        timestamp = parsed_dates[index]
        if user_id is None or timestamp is None:
            continue
        by_user[user_id].append((timestamp, index))

    for items in by_user.values():
        items.sort(key=lambda item: item[0])
        for start in range(len(items)):
            window = []
            for timestamp, index in items[start:]:
                minutes = (timestamp - items[start][0]).total_seconds() / 60
                if minutes > 10:
                    break
                window.append(index)
            if _is_suspicious_frequency_window(transactions, window):
                for index in window:
                    flagged[index] = True

    return flagged


def _is_suspicious_frequency_window(transactions, indexes):
    if len(indexes) < 3:
        return False

    countries = {
        transactions[index].get("country")
        for index in indexes
        if transactions[index].get("country") is not None
    }
    merchants = {
        transactions[index].get("merchant")
        for index in indexes
        if transactions[index].get("merchant") is not None
    }
    total_amount = sum(
        float(transactions[index].get("amount"))
        for index in indexes
        if _is_valid_number(transactions[index].get("amount"))
        and transactions[index].get("amount") > 0
    )

    return (
        len(indexes) >= 4
        or len(countries) > 1
        or len(merchants) > 1
        or total_amount >= 1000
    )


def _group_valid_amounts(transactions):
    grouped = defaultdict(list)
    for index, tx in enumerate(transactions):
        amount = tx.get("amount")
        if not _is_valid_number(amount) or amount <= 0:
            continue
        user_id = tx.get("user_id")
        currency = tx.get("currency")
        if user_id is None:
            continue
        grouped[(user_id, currency)].append((index, float(amount)))
    return grouped


def _amount_signal(index, tx, amount_groups):
    amount = tx.get("amount")
    if not _is_valid_number(amount) or amount <= 0:
        return None

    amount = float(amount)
    baseline = [
        value
        for other_index, value in amount_groups.get(
            (tx.get("user_id"), tx.get("currency")),
            [],
        )
        if other_index != index
    ]

    if baseline:
        usual = median(baseline)
        if usual > 0:
            ratio = amount / usual
            difference = amount - usual

            if ratio >= 5 and difference >= 500:
                return (0.9, "Montant très supérieur à l'habitude du client")
            if ratio >= 3 and difference >= 250:
                return (0.78, "Montant inhabituel par rapport au profil du client")
            if ratio >= 2 and difference >= 1000:
                return (0.65, "Montant élevé pour ce client")

    if amount >= 10000:
        return (0.82, "Montant exceptionnellement élevé")
    if amount >= 5000:
        return (0.55, "Montant élevé sans historique suffisant")

    return None


def _large_online_payment(tx):
    amount = tx.get("amount")
    return (
        _is_valid_number(amount)
        and amount >= 1000
        and tx.get("card_present") is False
    )


def _is_valid_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(value)
    )


def _choose_verdict(signals):
    if not signals:
        return 0.0, "Transaction conforme au profil du client"

    signals.sort(key=lambda signal: signal[0], reverse=True)
    score, reason = signals[0]

    if len(signals) > 1:
        score = min(1.0, score + 0.05 * (len(signals) - 1))

    return round(score, 2), reason
