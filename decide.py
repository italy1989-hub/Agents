from dataclasses import dataclass, field


@dataclass
class Plan:
    action: str                    # "execute" | "report_only" | "manual"
    reason: str
    create_company: bool = False
    create_contact: bool = False
    create_deal: bool = False
    company_id: int | None = None
    contact_id: int | None = None
    existing_deals: list = field(default_factory=list)


def decide(card: dict, dups: dict, deals: list[dict]) -> Plan:
    contacts, companies = dups["contacts"], dups["companies"]

    if len(contacts) > 1 or len(companies) > 1:
        return Plan("manual", f"Несколько совпадений: контакты {contacts}, компании {companies}")

    contact_id = contacts[0] if contacts else None
    company_id = companies[0] if companies else None
    base = dict(contact_id=contact_id, company_id=company_id, existing_deals=deals)

    if deals:
        # сделка уже есть: новую не создаём; если контакта нет, добавим его
        if contact_id is None:
            return Plan("execute", "Есть открытая сделка, добавляем новый контакт",
                        create_contact=True, **base)
        return Plan("report_only", "Есть открытая сделка", **base)

    has_company_name = bool((card.get("company") or "").strip())
    return Plan(
        "execute",
        "Открытых сделок нет",
        create_company=(contact_id is None and company_id is None and has_company_name),
        create_contact=contact_id is None,
        create_deal=True,
        **base,
    )
