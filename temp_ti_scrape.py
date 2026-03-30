from scripts.capture_tradeideas import scrape_tradeideas
r = scrape_tradeideas(update_config=False, headless=True, chrome_profile=None, select_30min=False)
print('stockracecentral:', r.get('stockracecentral'))
print('leaders:', r.get('stockracecentral_leaders'))
print('laggards:', r.get('stockracecentral_laggards'))
