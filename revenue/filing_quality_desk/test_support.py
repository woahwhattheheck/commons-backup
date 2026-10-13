import json

def b(x):return json.dumps(x,separators=(',',':'),sort_keys=True).encode()
def src(amb=False,changed=False,cik='0000123456'):
    a=[{'end':'2026-06-30','val':100,'accn':'A1','form':'10-Q','filed':'2026-08-01'}]
    if changed:a.insert(0,{'end':'2026-06-30','val':99,'accn':'A0','form':'10-Q/A','filed':'2026-07-15'})
    if amb:a.append({'end':'2026-06-30','val':101,'accn':'A2','form':'10-Q/A','filed':'2026-08-01'})
    return {'cik':cik,'entityName':'Synthetic & Co <QA>','facts':{'us-gaap':{'Assets':{'units':{'USD':a}},'Liabilities':{'units':{'USD':[{'end':'2026-06-30','val':60,'accn':'L1','form':'10-Q','filed':'2026-08-01'}]}},'StockholdersEquity':{'units':{'USD':[{'end':'2026-06-30','val':40,'accn':'E1','form':'10-Q','filed':'2026-08-01'}]}},'Revenue':{'units':{'USD':[{'start':'2026-01-01','end':'2026-06-30','val':25.50,'accn':'R1','form':'10-Q','filed':'2026-08-01'}]}}}}}
def pol(cut='2026-09-01'):
    return {'cik':'123456','filed_on_or_before':cut,'selectors':[{'id':'assets','taxonomy':'us-gaap','concept':'Assets','unit':'USD','kind':'instant','end':'2026-06-30'},{'id':'liabilities','taxonomy':'us-gaap','concept':'Liabilities','unit':'USD','kind':'instant','end':'2026-06-30'},{'id':'equity','taxonomy':'us-gaap','concept':'StockholdersEquity','unit':'USD','kind':'instant','end':'2026-06-30'},{'id':'revenue','taxonomy':'us-gaap','concept':'Revenue','unit':'USD','kind':'duration','start':'2026-01-01','end':'2026-06-30'}],'checks':[{'id':'balance','kind':'sum_equals','lhs':['liabilities','equity'],'rhs':'assets','tolerance':0}]}
