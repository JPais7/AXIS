import { test, expect } from '@playwright/test';

const project = '/projects/AXIS-DD-ERAP1-CURATED-001';
for (const width of [1440,1024]) {
  test(`frozen structure identity, mapping and provenance at ${width}px`, async ({page}) => {
    await page.setViewportSize({width,height:1000});
    const errors = [];
    const remote = [];
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{if(!request.url().startsWith('http://127.0.0.1:'))remote.push(request.url());});
    await page.goto(`${project}/protein`);
    await page.getByRole('button',{name:'View 1 imported experimental structure(s) →',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Experimental structures',exact:true})).toBeVisible();
    await page.getByRole('link',{name:/3QNF · Crystal structure/}).click();
    await expect(page.getByRole('heading',{name:'3QNF · Experimental structure',exact:true})).toBeVisible();
    await expect(page.locator('#residue-list button')).toHaveCount(954);
    await page.getByLabel('Canonical residue number',{exact:true}).fill('46');
    await page.getByRole('button',{name:'Inspect residue',exact:true}).click();
    await expect(page.locator('#residue-detail')).toContainText('exact_match');
    await expect(page.locator('#residue-detail')).toContainText('52');
    await page.getByLabel('Chain for residue mapping',{exact:true}).selectOption('1');
    await expect(page.locator('#coverage-summary')).toContainText('802');
    await page.getByLabel('Canonical residue number',{exact:true}).fill('1');
    await page.getByRole('button',{name:'Inspect residue',exact:true}).click();
    await expect(page.locator('#residue-detail')).toContainText('unresolved_coordinate');
    await expect(page.locator('#residue-detail')).toContainText('No coordinates');
    const source = page.getByRole('button',{name:'Source and mapping provenance',exact:true});
    await source.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toContainText('AXIS-computed mapping');
    await page.keyboard.press('Escape');
    await expect(source).toBeFocused();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    expect(remote).toEqual([]);
    await page.getByRole('link',{name:'Return to project disease evidence →',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Evidence',exact:true})).toBeVisible();
  });
}

test('local NGL initialization has a textual fallback and no remote coordinate request',async({page})=>{
  await page.goto(`${project}/protein`);
  await page.getByRole('button',{name:'View 1 imported experimental structure(s) →',exact:true}).click();
  await page.getByRole('link',{name:/3QNF · Crystal structure/}).click();
  await page.getByRole('button',{name:'Load local 3D viewer',exact:true}).click();
  await expect(page.locator('#viewer-status')).toHaveText(/Local experimental structure loaded|3D unavailable:/);
  await expect(page.locator('#residue-list button')).toHaveCount(954);
  // WebGL rendering/picking and gestures require the separate manual acceptance.
});
