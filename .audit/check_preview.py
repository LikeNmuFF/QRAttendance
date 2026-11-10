from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://localhost:5000/')
    assert page.locator('.motion-toggle').count()==0
    assert 'Pause animation' not in page.locator('body').inner_text()
    assert page.locator('.scanner-object').evaluate('el => getComputedStyle(el).animationName')=='scanner-float'
    page.locator('.product-scene').hover(position={'x':50,'y':50})
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(resolve))')
    assert page.locator('.product-scene').evaluate("el => el.style.getPropertyValue('--tilt-x')")
    page.emulate_media(reduced_motion='reduce')
    assert page.locator('.scanner-object').evaluate('el => getComputedStyle(el).animationName')=='none'
    assert not errors,errors
    print('PASS: control removed; animation, pointer tilt and reduced-motion support work without script errors')
    browser.close()
