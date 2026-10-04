import { test, expect } from '@playwright/test';

const project='/projects/AXIS-DD-ERAP1-CURATED-001';
for(const width of [1440,1024]) {
  test(`chemical identity, measurements and conservative comparison ${width}`,async({page})=>{
    await page.setViewportSize({width,height:1000});
    const errors=[]; const remote=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:'))remote.push(r.url());});
    const shot=async(name)=>page.screenshot({path:`test-results/pharmacology-${width}-${name}.png`});
    await page.goto(`${project}/chemistry`);
    await expect(page.getByRole('heading',{name:'Chemistry',exact:true})).toBeVisible();
    await expect(page.locator('.chemical-depiction')).toHaveCount(3);
    expect(await page.locator('.chemical-depiction').first().evaluate(i=>i.complete && i.naturalWidth>0)).toBe(true);
    await shot('chemistry');
    const identity=page.getByRole('button',{name:'Inspect identity, forms & provenance'}).nth(1);
    await identity.focus(); await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toContainText('C21H30N4O3');
    await shot('compound');
    await page.getByRole('dialog').getByRole('heading',{name:'Provenance',exact:true}).scrollIntoViewIfNeeded();
    await shot('provenance');
    await page.keyboard.press('Escape'); await expect(identity).toBeFocused();
    await page.goto(`${project}/pharmacology`);
    await expect(page.locator('tbody tr')).toHaveCount(15);
    await shot('measurements');
    await page.locator('tbody button').first().click();
    await expect(page.getByRole('dialog')).toContainText(/original value/i);
    await expect(page.getByRole('dialog')).toContainText(/normalization method/i);
    await shot('measurement-detail'); await page.keyboard.press('Escape');
    await page.goto(`${project}/selectivity?compound=compound%3Amaben-2`);
    await expect(page.getByText('Not directly comparable',{exact:true}).first()).toBeVisible();
    await shot('selectivity');
    await page.getByText(/unknown or different substrate/).first().scrollIntoViewIfNeeded();
    await shot('incompatible');
    await page.goto(`${project}/selectivity?compound=compound%3Amaben-1`);
    await expect(page.getByText('Not assessed in this package',{exact:true}).first()).toBeVisible();
    await shot('not-assessed');
    await page.goto(`${project}/pharmacology?endpoint=unknown`);
    await expect(page.getByText('No matching measurements; not evidence of inactivity.')).toBeVisible();
    await shot('unknown');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(errors).toEqual([]); expect(remote).toEqual([]);
    await page.getByRole('link',{name:'Disease evidence',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Evidence',exact:true})).toBeVisible();
  });
}
