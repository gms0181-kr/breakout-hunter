"""Universe policy: small/microcap operating-company common shares and ADS."""
import re
from .core import known
MAX_CAP=2000000000
PRODUCT=re.compile(r'\b(funds?|ETFs?|ETNs?|exchange.traded|closed.end|open.end|portfolios?|bonds?|debentures?|notes?|preferred|preference|warrants?|rights?|units?|REITs?|real estate investment trust|business development company|acquisition corp(?:oration)?)\b',re.I)
TRUST=re.compile(r'\btrust\b',re.I)
BANK_TRUST=re.compile(r'\b(banks?|bancorp|bancshares|financial|trust corporation)\b',re.I)
def security_reason(stock):
    name=stock.get('name','')
    category=' '.join(str(stock.get(k) or '') for k in ('security_type','industry'))
    if stock.get('etf') is True or stock.get('security_type') in ('ETF','ETN','fund','bond','preferred','warrant','right','unit','REIT','BDC'):return 'excluded_security_type'
    if PRODUCT.search(name) or PRODUCT.search(category):return 'fund_or_non_common_security'
    if TRUST.search(name) and not BANK_TRUST.search(name):return 'investment_or_income_trust'
    return None

def scope_reason(stock,cap=MAX_CAP):
    reason=security_reason(stock)
    if reason:return reason
    value=stock.get('market_cap')
    if not known(value) or value<=0:return 'market_cap_unverified'
    if value>min(cap,MAX_CAP):return 'above_smallcap_limit'
    return None

def in_scope(stock,cap=MAX_CAP):return scope_reason(stock,cap) is None

def filter_report(report):
    cap=report.get('config',{}).get('market_cap_max',MAX_CAP)
    for group in ('top10','last_top10','research_top10','watchlist','verification_candidates'):
        report[group]=[s for s in report.get(group,[]) if in_scope(s,cap)]
    report['candidate_scope']={'market_cap_max':min(cap,MAX_CAP),'security_types':'operating-company common shares / ADS','excluded':'funds, ETF/ETN, income/investment trusts, bonds, preferred, warrants, rights, units, REIT/BDC, SPAC'}
    return report
