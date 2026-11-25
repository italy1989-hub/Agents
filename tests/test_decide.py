from cards.decide import decide

CARD = {"company": "Ромашка"}
def D(contacts=(), companies=()):
    return {"contacts": list(contacts), "companies": list(companies)}
DEAL = [{"ID": "9", "TITLE": "x", "ASSIGNED_BY_ID": "3"}]

def test_nothing_found_creates_all():
    p = decide(CARD, D(), [])
    assert (p.action, p.create_company, p.create_contact, p.create_deal) == ("execute", True, True, True)

def test_nothing_found_no_company_name():
    p = decide({"company": ""}, D(), [])
    assert p.create_company is False and p.create_contact and p.create_deal

def test_company_found_contact_missing():
    p = decide(CARD, D(companies=[7]), [])
    assert (p.create_company, p.create_contact, p.create_deal, p.company_id) == (False, True, True, 7)

def test_contact_found_no_deals_creates_only_deal():
    p = decide(CARD, D(contacts=[5]), [])
    assert (p.create_company, p.create_contact, p.create_deal, p.contact_id) == (False, False, True, 5)

def test_contact_found_with_deal_is_report_only():
    p = decide(CARD, D(contacts=[5]), DEAL)
    assert p.action == "report_only" and not p.create_deal and p.existing_deals == DEAL

def test_company_with_deal_new_contact_added_no_new_deal():
    p = decide(CARD, D(companies=[7]), DEAL)
    assert p.action == "execute" and p.create_contact and not p.create_deal

def test_multiple_matches_go_to_manual():
    assert decide(CARD, D(contacts=[1, 2]), []).action == "manual"
    assert decide(CARD, D(companies=[1, 2]), []).action == "manual"
