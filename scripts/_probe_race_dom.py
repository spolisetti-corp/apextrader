"""Deep probe: dump raw page source snippet + all anchor hrefs + all visible text lines."""
import sys, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from capture_tradeideas import _get_driver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

driver = _get_driver()
driver.get("https://www.trade-ideas.com/TIPro/stockracecentral/")
WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
time.sleep(5)

# 1) Raw body text (first 3000 chars)
body = driver.execute_script("return document.body.innerText;") or ""
print("=== BODY TEXT (first 3000 chars) ===")
print(body[:3000])

# 2) All hrefs
print("\n=== HREFS (first 40) ===")
hrefs = driver.execute_script(
    "return Array.from(document.querySelectorAll('a')).map(function(a){return a.href;}).filter(function(h){return h;}).slice(0,40);"
)
for h in (hrefs or []):
    print(" ", h)

# 3) SVG text elements (TI heatmaps often use SVG/canvas)
print("\n=== SVG TEXT ELEMENTS (first 40) ===")
svgtxt = driver.execute_script(
    "return Array.from(document.querySelectorAll('text,tspan')).map(function(e){return e.textContent;}).filter(function(t){return t.trim();}).slice(0,40);"
)
for t in (svgtxt or []):
    print(" ", repr(t))

# 4) iframes present?
print("\n=== IFRAMES ===")
iframes = driver.execute_script(
    "return Array.from(document.querySelectorAll('iframe')).map(function(f){return {id:f.id,src:f.src,name:f.name};});"
)
for f in (iframes or []):
    print(" ", f)

# 5) Raw HTML snippet (first 2000 chars)
print("\n=== OUTER HTML SNIPPET (first 2000) ===")
html = driver.execute_script("return document.body.outerHTML.slice(0,2000);") or ""
print(html)
